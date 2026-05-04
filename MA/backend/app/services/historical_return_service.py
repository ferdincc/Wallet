"""
Uzun vadeli spot getiri özeti — LLM olmadan günlük OHLCV ile yaklaşık cevap (Binance).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from app.services.exchange_service import exchange_service

logger = logging.getLogger(__name__)


def parse_horizon_years(query: str) -> Optional[float]:
    """Sorgudan yıl sayısı çıkar; yoksa None."""
    ql = query.lower().strip()
    # Türkçe "yılda" (dotless ı = U+0131) ve yazım hatası "yilda"
    yil = r'y(?:\u0131|i)l(?:da)?'
    if re.search(r'\bdecade\b', ql) or re.search(r'on\s+' + yil, ql):
        return 10.0
    if re.search(rf'\b10\s+{yil}\b', ql):
        return 10.0
    m = re.search(rf'(?:son|last)\s*(\d+)\s+{yil}', ql)
    if m:
        y = float(m.group(1))
        return y if 0 < y <= 30 else None
    m = re.search(rf'(\d+)\s+{yil}', ql)
    if m:
        y = float(m.group(1))
        return y if 0 < y <= 30 else None
    if re.search(r'\blast\s+year\b', ql) or re.search(r'(?:geçen|gecen)\s+yıl', ql):
        return 1.0
    return None


def query_prefers_english(query: str) -> bool:
    q = query.lower()
    if re.search(r'[çğıöşüİı]', query):
        return False
    return bool(
        re.search(
            r'\b(how much|last \d+ years?|in the last|over the past|decade|did bitcoin|did btc|rise|gain|return)\b',
            q,
        )
    )


def _symbol_from_text(query: str) -> Optional[str]:
    """Basit sembol çıkarımı (ChatAgent ile uyumlu)."""
    qu = query.upper()
    m = re.search(r'\b([A-Z]{2,10}/[A-Z]{2,10})\b', qu)
    if m:
        return m.group(1)
    m = re.search(r'\b(BTC|ETH|BNB|SOL|XRP|ADA|DOGE|AVAX|DOT|MATIC|LINK)\b', qu)
    if m:
        return f"{m.group(1)}/USDT"
    ql = query.lower()
    if 'bitcoin' in ql or re.search(r'\bbtc\b', ql):
        return 'BTC/USDT'
    if 'ethereum' in ql or re.search(r'\beth\b', ql):
        return 'ETH/USDT'
    if 'solana' in ql or re.search(r'\bsol\b', ql):
        return 'SOL/USDT'
    return None


async def long_horizon_spot_summary(
    query: str,
    symbol: str,
    years: float,
    exchange_name: str = 'binance',
) -> Optional[str]:
    """
    Günlük kapanışlara göre yaklaşık toplam değişim yüzdesi.
    """
    try:
        rows = await exchange_service.fetch_ohlcv_paginated_daily(
            symbol, years, exchange_name=exchange_name
        )
    except Exception as e:
        logger.warning('historical_return fetch failed: %s', e)
        return None

    if not rows or len(rows) < 3:
        return None

    first = rows[0]
    last = rows[-1]
    try:
        first_ts = int(first[0])
        first_close = float(first[4])
        last_ts = int(last[0])
        last_close = float(last[4])
    except (IndexError, TypeError, ValueError):
        return None

    if first_close <= 0:
        return None

    pct = (last_close - first_close) / first_close * 100.0
    d0 = datetime.fromtimestamp(first_ts / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
    d1 = datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
    base = symbol.replace('/USDT', '').replace('/', '')

    en = query_prefers_english(query)
    if en:
        return (
            f"{base}/USDT (Binance spot, daily candles, approximate):\n"
            f"- First daily close in window (~{d0}): ${first_close:,.2f}\n"
            f"- Latest daily close in window (~{d1}): ${last_close:,.2f}\n"
            f"- Approximate total change over ~{years:g} years: {pct:+.2f}%\n\n"
            f"For education only; not investment advice. Past performance does not guarantee future results."
        )

    return (
        f"{base}/USDT (Binance spot, günlük mum — yaklaşık özet):\n"
        f"• Pencere başı (~{d0}) günlük kapanış: ${first_close:,.2f}\n"
        f"• Pencere sonu (~{d1}) günlük kapanış: ${last_close:,.2f}\n"
        f"• Yaklaşık toplam değişim (~{years:g} yıl): %{pct:+.2f}\n\n"
        f"Bilgilendirme amaçlıdır; yatırım tavsiyesi değildir. Geçmiş getiri geleceği göstermez.\n"
        f"(LLM kapalıyken bu özet Binance geçmiş mum verisinden üretilir.)"
    )


async def try_answer_long_horizon_query(query: str) -> Optional[str]:
    """Soru uzun vadeli performans içeriyorsa veri tabanlı metin döndür."""
    years = parse_horizon_years(query)
    if years is None:
        return None
    hint = re.search(
        r'(arttı|artti|artış|artsın|değiş|degis|getiri|performans|performance|'
        r'rise|rose|gain|return|increase|went up|kaç|ne kadar|how much)',
        query.lower(),
    )
    if not hint:
        return None

    symbol = _symbol_from_text(query)
    if not symbol:
        return None

    return await long_horizon_spot_summary(query, symbol, years)
