"""
Exchange service for fetching data from multiple cryptocurrency exchanges
"""
import ccxt
import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from contextvars import ContextVar
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import logging

from app.config import settings

logger = logging.getLogger(__name__)


def _ccxt_timeout_ms() -> int:
    return max(1000, int(getattr(settings, "EXCHANGE_CCXT_TIMEOUT_MS", 5000)))


def _ccxt_timeout_sec() -> float:
    return _ccxt_timeout_ms() / 1000.0


def _private_timeout_sec() -> float:
    """İmzalı uçlar (bakiye, emir, pozisyon) için daha uzun süre."""
    return max(
        _ccxt_timeout_sec(),
        int(getattr(settings, "EXCHANGE_PRIVATE_TIMEOUT_MS", 15000)) / 1000.0,
    )


def _binance_recv_window() -> int:
    return max(5000, int(getattr(settings, "BINANCE_RECV_WINDOW_MS", 60000)))


# Spot bakiyede pozisyon olarak göstermeyeceğimiz quote / stabil kodlar
_SPOT_BALANCE_ASSET_SKIP = frozenset({
    "USDT", "USDC", "BUSD", "FDUSD", "TUSD", "USDP", "DAI", "EUR", "TRY", "GBP", "USD", "BRL", "AUD",
})

# Paralel HTTP isteklerinde (balance + orders + positions) karışmaması için istek bağlamı başına hata
_private_ccxt_error: ContextVar[Optional[str]] = ContextVar("_private_ccxt_error", default=None)


def _build_binance_watch_portfolio_sync(api_key: str, api_secret: str) -> Dict[str, Any]:
    """
    Binance spot: bakiye → her coin için USDT çiftinde
    myTrades (son ALIŞ) + ticker (anlık fiyat).
    ccxt: fetch_my_trades ≈ GET /api/v3/myTrades, fetch_ticker ≈ /api/v3/ticker/price.
    """
    ex = ccxt.binance(
        {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "timeout": _ccxt_timeout_ms(),
            "options": {
                "defaultType": "spot",
                "recvWindow": _binance_recv_window(),
                "adjustForTimeDifference": True,
            },
        }
    )
    logger.info("[watch-portfolio] Binance: load_markets + fetch_balance (spot)")
    ex.load_markets()
    bal = ex.fetch_balance()
    totals = bal.get("total") or {}
    free_map = bal.get("free") or {}

    holdings: List[Dict[str, Any]] = []
    total_coins_usd = 0.0
    sum_pnl_usd = 0.0
    sum_cost_usd = 0.0

    for asset, qty_raw in totals.items():
        try:
            qty = float(qty_raw or 0)
        except (TypeError, ValueError):
            qty = 0.0
        if qty <= 0 or asset in _SPOT_BALANCE_ASSET_SKIP:
            continue

        pair = f"{asset}/USDT"
        row: Dict[str, Any] = {
            "asset": asset,
            "symbol_pair": f"{asset}USDT",
            "quantity": qty,
            "buy_price": None,
            "buy_time_iso": None,
            "current_price": None,
            "total_value_usd": None,
            "pnl_usd": None,
            "pnl_percent": None,
            "note": None,
        }

        if pair not in ex.markets:
            row["note"] = "USDT işlem çifti yok"
            holdings.append(row)
            continue

        try:
            trades = ex.fetch_my_trades(pair, limit=500)
            buys = [t for t in (trades or []) if str(t.get("side", "")).lower() == "buy"]
            if buys:
                last_buy = max(buys, key=lambda t: int(t.get("timestamp") or 0))
                bp = float(last_buy.get("price") or 0)
                if bp > 0:
                    row["buy_price"] = bp
                ts = last_buy.get("timestamp")
                if ts:
                    dt = datetime.fromtimestamp(int(ts) / 1000.0, tz=timezone.utc)
                    row["buy_time_iso"] = dt.isoformat()
        except Exception as e:
            row["note"] = (row["note"] or "") + f" myTrades:{e!s}"

        try:
            ticker = ex.fetch_ticker(pair)
            last = ticker.get("last") or ticker.get("close")
            if last is not None:
                row["current_price"] = float(last)
        except Exception as e:
            row["note"] = (row["note"] or "") + f" ticker:{e!s}"

        if row["current_price"] is not None:
            row["total_value_usd"] = round(qty * row["current_price"], 8)
            total_coins_usd += row["total_value_usd"]

        if row["buy_price"] is not None and row["current_price"] is not None and row["total_value_usd"] is not None:
            cost = qty * row["buy_price"]
            row["pnl_usd"] = round(row["total_value_usd"] - cost, 8)
            sum_pnl_usd += row["pnl_usd"]
            sum_cost_usd += cost
            if cost > 0:
                row["pnl_percent"] = round((row["pnl_usd"] / cost) * 100, 4)

        holdings.append(row)

    usdt_free = float(free_map.get("USDT") or 0)
    total_portfolio_usd = total_coins_usd + usdt_free
    total_pnl_pct = (sum_pnl_usd / sum_cost_usd * 100) if sum_cost_usd > 0 else None

    return {
        "holdings": holdings,
        "summary": {
            "total_portfolio_usd": round(total_portfolio_usd, 2),
            "total_coins_value_usd": round(total_coins_usd, 2),
            "usdt_free": round(usdt_free, 2),
            "total_pnl_usd": round(sum_pnl_usd, 2),
            "total_pnl_percent": round(total_pnl_pct, 4) if total_pnl_pct is not None else None,
            "cost_basis_usd": round(sum_cost_usd, 2) if sum_cost_usd else None,
        },
    }


class ExchangeService:
    """Service for managing multiple exchange connections"""
    
    def __init__(self):
        self.exchanges: Dict[str, ccxt.Exchange] = {}
        self.authenticated_exchanges: Dict[str, ccxt.Exchange] = {}  # User-specific authenticated exchanges
        self._initialize_exchanges()

    def pop_last_private_error(self) -> Optional[str]:
        """Bu istek bağlamındaki son ccxt özel API hatasını oku ve sıfırla."""
        err = _private_ccxt_error.get()
        _private_ccxt_error.set(None)
        return err

    def _note_private_error(
        self,
        operation: str,
        exc: Exception,
        exchange: Optional[ccxt.Exchange] = None,
    ) -> None:
        parts = [operation, f"{type(exc).__name__}: {exc}"]
        if exchange is not None:
            for attr in ("last_request_url", "last_http_response"):
                val = getattr(exchange, attr, None)
                if val is not None and str(val).strip() != "":
                    parts.append(f"{attr}={str(val)[:2000]}")
            lj = getattr(exchange, "last_json_response", None)
            if lj is not None:
                parts.append(f"last_json_response={str(lj)[:2000]}")
        msg = " | ".join(parts)
        _private_ccxt_error.set(msg[:4000])
        logger.error("[CCXT private] %s", msg, exc_info=True)
    
    def _initialize_exchanges(self):
        """Initialize exchange connections"""
        try:
            tm = _ccxt_timeout_ms()
            # Binance
            self.exchanges['binance'] = ccxt.binance({
                'apiKey': '',  # Optional for public data
                'secret': '',
                'enableRateLimit': True,
                'timeout': tm,
                'options': {
                    'defaultType': 'spot',
                }
            })
            
            # Coinbase Pro (try different names)
            try:
                self.exchanges['coinbasepro'] = ccxt.coinbasepro({
                    'apiKey': '',
                    'secret': '',
                    'password': '',
                    'enableRateLimit': True,
                    'timeout': tm,
                })
            except AttributeError:
                try:
                    self.exchanges['coinbasepro'] = ccxt.coinbase({
                        'apiKey': '',
                        'secret': '',
                        'enableRateLimit': True,
                        'timeout': tm,
                    })
                except:
                    logger.warning("Coinbase Pro not available in ccxt")
            
            # Kraken
            self.exchanges['kraken'] = ccxt.kraken({
                'apiKey': '',
                'secret': '',
                'enableRateLimit': True,
                'timeout': tm,
            })
            
            logger.info(f"Initialized {len(self.exchanges)} exchanges: {list(self.exchanges.keys())}")
        except Exception as e:
            logger.error(f"Error initializing exchanges: {e}")
    
    def get_exchange(self, exchange_name: str) -> Optional[ccxt.Exchange]:
        """Get exchange instance by name"""
        return self.exchanges.get(exchange_name.lower())
    
    async def fetch_ticker(self, symbol: str, exchange_name: str = 'binance') -> Optional[Dict[str, Any]]:
        """Fetch ticker data for a symbol"""
        try:
            if not symbol:
                logger.warning("Symbol is required for fetch_ticker")
                return None
            
            exchange = self.get_exchange(exchange_name)
            if not exchange:
                logger.warning(f"Exchange {exchange_name} not found")
                return None
            
            # Add timeout to prevent hanging
            ticker = await asyncio.wait_for(
                asyncio.to_thread(exchange.fetch_ticker, symbol),
                timeout=_ccxt_timeout_sec(),
            )
            
            # Validate ticker data
            if ticker is None:
                logger.warning(f"Ticker data is None for {symbol} on {exchange_name}")
                return None
            
            if not isinstance(ticker, dict):
                logger.warning(f"Ticker data is not a dict for {symbol} on {exchange_name}")
                return None
            
            # Normalize ticker data
            normalized = {
                'symbol': ticker.get('symbol'),
                'price': ticker.get('last'),
                'high_24h': ticker.get('high'),
                'low_24h': ticker.get('low'),
                'volume_24h': ticker.get('quoteVolume'),
                'change_24h': ticker.get('percentage'),
                'exchange': exchange_name,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Validate critical fields
            if normalized.get('price') is None:
                logger.warning(f"Price is None in ticker data for {symbol} on {exchange_name}")
            
            return normalized
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching ticker for {symbol} on {exchange_name}")
            return None
        except Exception as e:
            logger.error(f"Error fetching ticker for {symbol} on {exchange_name}: {e}", exc_info=True)
            return None
    
    async def fetch_multiple_tickers(
        self, 
        symbols: List[str], 
        exchange_name: str = 'binance'
    ) -> Dict[str, Dict[str, Any]]:
        """Fetch multiple tickers"""
        try:
            exchange = self.get_exchange(exchange_name)
            if not exchange:
                return {}
            
            tickers = await asyncio.wait_for(
                asyncio.to_thread(exchange.fetch_tickers, symbols),
                timeout=_ccxt_timeout_sec(),
            )
            
            # Normalize all tickers
            normalized = {}
            for symbol, ticker in tickers.items():
                normalized[symbol] = {
                    'symbol': ticker.get('symbol'),
                    'price': ticker.get('last'),
                    'high_24h': ticker.get('high'),
                    'low_24h': ticker.get('low'),
                    'volume_24h': ticker.get('quoteVolume'),
                    'change_24h': ticker.get('percentage'),
                    'exchange': exchange_name,
                    'timestamp': datetime.utcnow().isoformat()
                }
            
            return normalized
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching tickers on {exchange_name}")
            return {}
        except Exception as e:
            logger.error(f"Error fetching tickers on {exchange_name}: {e}")
            return {}
    
    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = '1h',
        limit: int = 100,
        exchange_name: str = 'binance',
        since_ms: Optional[int] = None,
    ) -> List[List[float]]:
        """Fetch OHLCV (candlestick) data. ``since_ms`` = UTC epoch ms (ccxt ``since``)."""
        try:
            if not symbol:
                logger.warning("Symbol is required for fetch_ohlcv")
                return []
            
            exchange = self.get_exchange(exchange_name)
            if not exchange:
                logger.warning(f"Exchange {exchange_name} not found")
                return []

            def _do_fetch() -> List[List[float]]:
                if since_ms is not None:
                    return exchange.fetch_ohlcv(symbol, timeframe, since_ms, limit)
                return exchange.fetch_ohlcv(symbol, timeframe, None, limit)

            # Add timeout to prevent hanging
            ohlcv = await asyncio.wait_for(
                asyncio.to_thread(_do_fetch),
                timeout=_ccxt_timeout_sec(),
            )
            
            # Validate OHLCV data
            if ohlcv is None:
                logger.warning(f"OHLCV data is None for {symbol} on {exchange_name}")
                return []
            
            if not isinstance(ohlcv, list):
                logger.warning(f"OHLCV data is not a list for {symbol} on {exchange_name}")
                return []
            
            if len(ohlcv) == 0:
                logger.warning(f"OHLCV data is empty for {symbol} on {exchange_name}")
                return []
            
            return ohlcv
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching OHLCV for {symbol} on {exchange_name}")
            return []
        except Exception as e:
            logger.error(f"Error fetching OHLCV for {symbol} on {exchange_name}: {e}", exc_info=True)
            return []

    async def fetch_ohlcv_paginated_daily(
        self,
        symbol: str,
        years: float,
        exchange_name: str = 'binance',
        max_requests: int = 15,
    ) -> List[List[float]]:
        """
        Günlük mumları `years` yıl geriye kadar toplar (Binance ~1000 mum/istek).
        """
        from datetime import timedelta

        if years <= 0 or years > 30:
            return []
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=int(years * 365.25) + 3)
        since_ms = int(start.timestamp() * 1000)
        all_rows: List[List[float]] = []
        cur_since = since_ms
        for _ in range(max_requests):
            batch = await self.fetch_ohlcv(
                symbol, '1d', limit=1000, exchange_name=exchange_name, since_ms=cur_since
            )
            if not batch:
                break
            if all_rows and batch[0][0] <= all_rows[-1][0]:
                batch = [c for c in batch if c[0] > all_rows[-1][0]]
            if not batch:
                break
            all_rows.extend(batch)
            last_ts = int(all_rows[-1][0])
            cur_since = last_ts + 1
            if len(batch) < 1000:
                break
        return all_rows

    async def fetch_orderbook(
        self, 
        symbol: str, 
        limit: int = 20,
        exchange_name: str = 'binance'
    ) -> Optional[Dict[str, Any]]:
        """Fetch order book data"""
        try:
            exchange = self.get_exchange(exchange_name)
            if not exchange:
                return None
            
            orderbook = await asyncio.wait_for(
                asyncio.to_thread(exchange.fetch_order_book, symbol, limit),
                timeout=_ccxt_timeout_sec(),
            )
            
            return {
                'bids': orderbook.get('bids', []),
                'asks': orderbook.get('asks', []),
                'timestamp': datetime.utcnow().isoformat(),
                'symbol': symbol,
                'exchange': exchange_name
            }
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching orderbook for {symbol} on {exchange_name}")
            return None
        except Exception as e:
            logger.error(f"Error fetching orderbook for {symbol} on {exchange_name}: {e}")
            return None
    
    def get_supported_exchanges(self) -> List[str]:
        """Get list of supported exchanges"""
        return list(self.exchanges.keys())
    
    def get_supported_symbols(self, exchange_name: str = 'binance') -> List[str]:
        """Get list of supported symbols for an exchange"""
        try:
            exchange = self.get_exchange(exchange_name)
            if not exchange:
                return []
            
            with ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(exchange.load_markets)
                try:
                    markets = fut.result(timeout=_ccxt_timeout_sec())
                    return list(markets.keys())
                except FuturesTimeout:
                    logger.error(f"Timeout loading markets for {exchange_name}")
                    return []
        except Exception as e:
            logger.error(f"Error loading markets for {exchange_name}: {e}")
            return []
    
    def get_authenticated_exchange(
        self, 
        exchange_name: str, 
        api_key: str, 
        api_secret: str, 
        passphrase: Optional[str] = None
    ) -> Optional[ccxt.Exchange]:
        """Get authenticated exchange instance with API credentials"""
        try:
            exchange_name_lower = exchange_name.lower()
            cache_key = f"{exchange_name_lower}_{api_key[:8]}"  # Cache key with first 8 chars of API key
            
            # Check cache
            if cache_key in self.authenticated_exchanges:
                return self.authenticated_exchanges[cache_key]
            
            # Create authenticated exchange
            exchange_config = {
                'apiKey': api_key,
                'secret': api_secret,
                'enableRateLimit': True,
                'timeout': _ccxt_timeout_ms(),
            }
            
            if exchange_name_lower == "binance":
                rw = _binance_recv_window()
                exchange_config["options"] = {
                    "defaultType": "spot",
                    "recvWindow": rw,
                    "adjustForTimeDifference": True,
                }
                logger.info(
                    "[Binance spot auth] ccxt.binance recvWindow=%sms adjustForTimeDifference=True",
                    rw,
                )
                exchange = ccxt.binance(exchange_config)
            elif exchange_name_lower in ['coinbasepro', 'coinbase']:
                if passphrase:
                    exchange_config['password'] = passphrase
                try:
                    exchange = ccxt.coinbasepro(exchange_config)
                except AttributeError:
                    exchange = ccxt.coinbase(exchange_config)
            elif exchange_name_lower == 'kraken':
                exchange = ccxt.kraken(exchange_config)
            else:
                logger.error(f"Unsupported exchange for authentication: {exchange_name}")
                return None
            
            # Cache authenticated exchange
            self.authenticated_exchanges[cache_key] = exchange
            return exchange
            
        except Exception as e:
            logger.error(f"Error creating authenticated exchange for {exchange_name}: {e}")
            return None
    
    async def fetch_balance(
        self, 
        exchange_name: str, 
        api_key: str, 
        api_secret: str, 
        passphrase: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Fetch account balance from authenticated exchange (Read-Only) — spot (ccxt → /api/v3/account)."""
        op = f"{exchange_name}.fetch_balance"
        exchange: Optional[ccxt.Exchange] = None
        try:
            exchange = self.get_authenticated_exchange(exchange_name, api_key, api_secret, passphrase)
            if not exchange:
                self._note_private_error(f"{op} (örnek oluşturulamadı)", RuntimeError("get_authenticated_exchange None"), None)
                return None

            logger.info(
                "[CCXT] %s → fetch_balance() timeout=%.1fs (Binance spot account)",
                op,
                _private_timeout_sec(),
            )
            balance = await asyncio.wait_for(
                asyncio.to_thread(exchange.fetch_balance),
                timeout=_private_timeout_sec(),
            )
            # Özet log (tam bakiye dict’i loglamıyoruz)
            totals = balance.get("total") or {}
            nonzero = sum(1 for _k, v in totals.items() if v and float(v) > 0)
            logger.info(
                "[CCXT] %s ← OK; nonzero_total_assets=%s info_keys=%s",
                op,
                nonzero,
                list((balance.get("info") or {}).keys())[:12] if isinstance(balance.get("info"), dict) else "n/a",
            )

            return {
                "total": balance.get("total", {}),
                "free": balance.get("free", {}),
                "used": balance.get("used", {}),
                "info": balance.get("info", {}),
                "timestamp": datetime.utcnow().isoformat(),
            }
        except asyncio.TimeoutError as e:
            self._note_private_error(f"{op} TIMEOUT", e, exchange)
            return None
        except Exception as e:
            self._note_private_error(op, e, exchange)
            return None
    
    async def fetch_positions(
        self, 
        exchange_name: str, 
        api_key: str, 
        api_secret: str, 
        passphrase: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Spot: bakiye > 0 varlıklar (USDT vb. quote hariç).
        Binance USDT-M futures: ccxt fetch_positions (≈ /fapi/v2/positionRisk).
        """
        positions: List[Dict[str, Any]] = []
        el = exchange_name.lower()

        if el == "binance":
            spot_ex: Optional[ccxt.Exchange] = None
            try:
                spot_ex = self.get_authenticated_exchange(exchange_name, api_key, api_secret, passphrase)
                if not spot_ex:
                    self._note_private_error(
                        "binance.fetch_positions(spot balance)",
                        RuntimeError("get_authenticated_exchange None"),
                        None,
                    )
                    return []

                logger.info(
                    "[CCXT] binance.fetch_positions(spot) → fetch_balance() timeout=%.1fs",
                    _private_timeout_sec(),
                )
                balance = await asyncio.wait_for(
                    asyncio.to_thread(spot_ex.fetch_balance),
                    timeout=_private_timeout_sec(),
                )
                for currency, amount in (balance.get("total") or {}).items():
                    try:
                        amt = float(amount or 0)
                    except (TypeError, ValueError):
                        amt = 0.0
                    if amt <= 0 or currency in _SPOT_BALANCE_ASSET_SKIP:
                        continue
                    positions.append({
                        "symbol": currency,
                        "amount": amt,
                        "free": balance.get("free", {}).get(currency, 0),
                        "used": balance.get("used", {}).get(currency, 0),
                        "market": "spot",
                    })
                logger.info(
                    "[CCXT] binance.fetch_positions(spot) ← %s spot asset row(s)",
                    len(positions),
                )
            except asyncio.TimeoutError as e:
                self._note_private_error("binance.fetch_positions(spot) TIMEOUT", e, spot_ex)
                return []
            except Exception as e:
                self._note_private_error("binance.fetch_positions(spot)", e, spot_ex)
                return []

            fut_ex: Optional[ccxt.Exchange] = None
            try:
                rw = _binance_recv_window()
                fut_ex = ccxt.binance({
                    "apiKey": api_key,
                    "secret": api_secret,
                    "enableRateLimit": True,
                    "timeout": _ccxt_timeout_ms(),
                    "options": {
                        "defaultType": "future",
                        "recvWindow": rw,
                        "adjustForTimeDifference": True,
                    },
                })
                logger.info(
                    "[CCXT] binance.fetch_positions(futures) → fetch_positions() recvWindow=%sms timeout=%.1fs",
                    rw,
                    _private_timeout_sec(),
                )
                frows = await asyncio.wait_for(
                    asyncio.to_thread(fut_ex.fetch_positions),
                    timeout=_private_timeout_sec(),
                )
                fut_count = 0
                for p in frows or []:
                    try:
                        c = float(p.get("contracts") or 0)
                    except (TypeError, ValueError):
                        c = 0.0
                    if c == 0:
                        continue
                    fut_count += 1
                    positions.append({
                        "symbol": p.get("symbol"),
                        "amount": abs(c),
                        "side": p.get("side"),
                        "notional": p.get("notional"),
                        "unrealizedPnl": p.get("unrealizedPnl"),
                        "entryPrice": p.get("entryPrice"),
                        "free": None,
                        "used": None,
                        "market": "future",
                    })
                logger.info(
                    "[CCXT] binance.fetch_positions(futures) ← %s açık pozisyon",
                    fut_count,
                )
            except Exception as e:
                logger.warning(
                    "[CCXT] binance.fetch_positions(futures) atlandı (Futures API izni yok / hesap yok): %s",
                    e,
                    exc_info=True,
                )
                if fut_ex is not None:
                    _parts = [f"{type(e).__name__}: {e}"]
                    for attr in ("last_request_url", "last_http_response"):
                        val = getattr(fut_ex, attr, None)
                        if val is not None and str(val).strip():
                            _parts.append(f"{attr}={str(val)[:1500]}")
                    logger.warning("[CCXT futures debug] %s", " | ".join(_parts))

            return positions

        # Diğer borsalar: yalnızca spot bakiye türevi
        exchange: Optional[ccxt.Exchange] = None
        try:
            exchange = self.get_authenticated_exchange(exchange_name, api_key, api_secret, passphrase)
            if not exchange:
                return []

            balance = await asyncio.wait_for(
                asyncio.to_thread(exchange.fetch_balance),
                timeout=_private_timeout_sec(),
            )
            out: List[Dict[str, Any]] = []
            for currency, amount in (balance.get("total") or {}).items():
                try:
                    amt = float(amount or 0)
                except (TypeError, ValueError):
                    amt = 0.0
                if amt <= 0 or currency in _SPOT_BALANCE_ASSET_SKIP:
                    continue
                out.append({
                    "symbol": currency,
                    "amount": amt,
                    "free": balance.get("free", {}).get(currency, 0),
                    "used": balance.get("used", {}).get(currency, 0),
                    "market": "spot",
                })
            return out
        except asyncio.TimeoutError as e:
            self._note_private_error(f"{exchange_name}.fetch_positions TIMEOUT", e, exchange)
            return []
        except Exception as e:
            self._note_private_error(f"{exchange_name}.fetch_positions", e, exchange)
            return []
    
    async def fetch_open_orders(
        self, 
        exchange_name: str, 
        api_key: str, 
        api_secret: str, 
        passphrase: Optional[str] = None,
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch open orders — spot (ccxt → /api/v3/openOrders)."""
        op = f"{exchange_name}.fetch_open_orders"
        exchange: Optional[ccxt.Exchange] = None
        try:
            exchange = self.get_authenticated_exchange(exchange_name, api_key, api_secret, passphrase)
            if not exchange:
                return []

            def _fetch_open():
                if symbol:
                    return exchange.fetch_open_orders(symbol)
                return exchange.fetch_open_orders()

            logger.info(
                "[CCXT] %s → symbol=%r timeout=%.1fs",
                op,
                symbol,
                _private_timeout_sec(),
            )
            orders = await asyncio.wait_for(
                asyncio.to_thread(_fetch_open),
                timeout=_private_timeout_sec(),
            )
            logger.info("[CCXT] %s ← %s emir", op, len(orders or []))

            normalized = []
            for order in orders or []:
                normalized.append({
                    "id": order.get("id"),
                    "symbol": order.get("symbol"),
                    "type": order.get("type"),
                    "side": order.get("side"),
                    "amount": order.get("amount"),
                    "price": order.get("price"),
                    "status": order.get("status"),
                    "timestamp": order.get("timestamp"),
                    "info": order.get("info", {}),
                })

            return normalized
        except asyncio.TimeoutError as e:
            self._note_private_error(f"{op} TIMEOUT", e, exchange)
            return []
        except Exception as e:
            self._note_private_error(op, e, exchange)
            return []

    async def fetch_binance_watch_portfolio(
        self,
        api_key: str,
        api_secret: str,
        passphrase: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Binance spot izleme portföyü (myTrades + ticker); tek asyncio.to_thread ile."""
        _ = passphrase
        tout = float(getattr(settings, "WATCH_PORTFOLIO_TIMEOUT_SEC", 120))
        try:
            logger.info(
                "[watch-portfolio] başlıyor timeout=%.1fs (myTrades+ticker / coin)",
                tout,
            )
            result = await asyncio.wait_for(
                asyncio.to_thread(_build_binance_watch_portfolio_sync, api_key, api_secret),
                timeout=tout,
            )
            logger.info(
                "[watch-portfolio] tamam: %s coin satırı",
                len(result.get("holdings") or []),
            )
            return result
        except asyncio.TimeoutError as e:
            self._note_private_error("binance.watch_portfolio TIMEOUT", e, None)
            return None
        except Exception as e:
            self._note_private_error("binance.watch_portfolio", e, None)
            return None
    
    async def create_market_order(
        self, 
        exchange_name: str, 
        api_key: str, 
        api_secret: str, 
        symbol: str, 
        side: str,  # 'buy' or 'sell'
        amount: float,
        passphrase: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Create a market order on authenticated exchange (Real Trading)"""
        try:
            exchange = self.get_authenticated_exchange(exchange_name, api_key, api_secret, passphrase)
            if not exchange:
                return None
            
            order = await asyncio.wait_for(
                asyncio.to_thread(
                    exchange.create_market_order,
                    symbol,
                    side,
                    amount,
                ),
                timeout=_ccxt_timeout_sec(),
            )
            
            return {
                'id': order.get('id'),
                'symbol': order.get('symbol'),
                'type': order.get('type'),
                'side': order.get('side'),
                'amount': order.get('amount'),
                'price': order.get('price'),
                'status': order.get('status'),
                'timestamp': order.get('timestamp'),
                'info': order.get('info', {})
            }
        except asyncio.TimeoutError:
            logger.error(f"Timeout creating market order on {exchange_name}")
            return None
        except Exception as e:
            logger.error(f"Error creating market order on {exchange_name}: {e}")
            return None
    
    async def create_limit_order(
        self, 
        exchange_name: str, 
        api_key: str, 
        api_secret: str, 
        symbol: str, 
        side: str,  # 'buy' or 'sell'
        amount: float,
        price: float,
        passphrase: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Create a limit order on authenticated exchange (Real Trading)"""
        try:
            exchange = self.get_authenticated_exchange(exchange_name, api_key, api_secret, passphrase)
            if not exchange:
                return None
            
            order = await asyncio.wait_for(
                asyncio.to_thread(
                    exchange.create_limit_order,
                    symbol,
                    side,
                    amount,
                    price,
                ),
                timeout=_ccxt_timeout_sec(),
            )
            
            return {
                'id': order.get('id'),
                'symbol': order.get('symbol'),
                'type': order.get('type'),
                'side': order.get('side'),
                'amount': order.get('amount'),
                'price': order.get('price'),
                'status': order.get('status'),
                'timestamp': order.get('timestamp'),
                'info': order.get('info', {})
            }
        except asyncio.TimeoutError:
            logger.error(f"Timeout creating limit order on {exchange_name}")
            return None
        except Exception as e:
            logger.error(f"Error creating limit order on {exchange_name}: {e}")
            return None


# Global instance
exchange_service = ExchangeService()

