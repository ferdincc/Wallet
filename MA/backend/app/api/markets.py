"""
Markets API endpoints
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel

from app.services.exchange_service import exchange_service
from app.services.anomaly_service import anomaly_service
from app.services.technical_analysis import technical_analysis
from app.symbol_query import expand_symbol_list

router = APIRouter()


class TickerResponse(BaseModel):
    symbol: str
    price: float
    high_24h: Optional[float] = None
    low_24h: Optional[float] = None
    volume_24h: Optional[float] = None
    change_24h: Optional[float] = None
    exchange: str
    timestamp: str


@router.get("/ticker/{symbol:path}")
async def get_ticker(
    symbol: str,
    exchange: str = Query("binance", description="Exchange name (binance, coinbasepro, kraken)")
):
    """Get ticker data for a symbol"""
    ticker = await exchange_service.fetch_ticker(symbol, exchange)
    
    if not ticker:
        raise HTTPException(status_code=404, detail=f"Ticker not found for {symbol} on {exchange}")
    
    return ticker


@router.get("/tickers")
async def get_tickers(
    symbols: List[str] = Query(..., description="List of symbols"),
    exchange: str = Query("binance", description="Exchange name")
):
    """Get multiple tickers"""
    symbols = expand_symbol_list(symbols)
    tickers = await exchange_service.fetch_multiple_tickers(symbols, exchange)
    
    if not tickers:
        raise HTTPException(status_code=404, detail="No tickers found")
    
    return {"tickers": tickers}


@router.get("/ohlcv/{symbol:path}")
async def get_ohlcv(
    symbol: str,
    timeframe: str = Query("1h", description="Timeframe (1m, 5m, 1h, 1d, etc.)"),
    limit: int = Query(100, ge=1, le=1000, description="Number of candles"),
    exchange: str = Query("binance", description="Exchange name")
):
    """Get OHLCV (candlestick) data"""
    ohlcv = await exchange_service.fetch_ohlcv(symbol, timeframe, limit, exchange)
    
    if not ohlcv:
        raise HTTPException(status_code=404, detail=f"OHLCV data not found for {symbol}")
    
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "exchange": exchange,
        "data": ohlcv
    }


@router.get("/orderbook/{symbol:path}")
async def get_orderbook(
    symbol: str,
    limit: int = Query(20, ge=1, le=100, description="Number of bids/asks"),
    exchange: str = Query("binance", description="Exchange name")
):
    """Get order book data"""
    orderbook = await exchange_service.fetch_orderbook(symbol, limit, exchange)
    
    if not orderbook:
        raise HTTPException(status_code=404, detail=f"Orderbook not found for {symbol}")
    
    return orderbook


@router.get("/analysis/{symbol:path}")
async def get_analysis(
    symbol: str,
    timeframe: str = Query("1h", description="Timeframe for analysis"),
    exchange: str = Query("binance", description="Exchange name")
):
    """Get technical analysis for a symbol"""
    ohlcv = await exchange_service.fetch_ohlcv(symbol, timeframe, limit=100, exchange_name=exchange)
    
    if not ohlcv:
        raise HTTPException(status_code=404, detail=f"Data not found for {symbol}")
    
    analysis = technical_analysis.analyze_ohlcv(ohlcv)
    
    return {
        "symbol": symbol,
        "exchange": exchange,
        "timeframe": timeframe,
        "analysis": analysis
    }


@router.get("/exchanges")
async def get_exchanges():
    """Get list of supported exchanges"""
    return {"exchanges": exchange_service.get_supported_exchanges()}


@router.get("/symbols/{exchange}")
async def get_symbols(exchange: str):
    """Get supported symbols for an exchange"""
    symbols = exchange_service.get_supported_symbols(exchange)
    
    if not symbols:
        raise HTTPException(status_code=404, detail=f"Exchange {exchange} not found or no symbols available")
    
    return {
        "exchange": exchange,
        "symbols": symbols[:100],  # Limit to first 100
        "total": len(symbols)
    }


@router.get("/anomalies/{symbol:path}")
async def get_anomalies(
    symbol: str,
    timeframe: str = Query("1h", description="Timeframe for anomaly detection"),
    exchange: str = Query("binance", description="Exchange name"),
    anomaly_type: str = Query("volume", description="Type: 'price' or 'volume'")
):
    """Detect anomalies in price or volume data"""
    if not anomaly_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Anomaly detection service not available. Install scikit-learn: pip install scikit-learn"
        )
    
    # Fetch OHLCV data
    ohlcv = await exchange_service.fetch_ohlcv(symbol, timeframe, limit=100, exchange_name=exchange)
    
    if not ohlcv or len(ohlcv) < 10:
        raise HTTPException(
            status_code=400,
            detail="Insufficient data for anomaly detection. Need at least 10 data points."
        )
    
    # Detect anomalies
    if anomaly_type == "price":
        result = await anomaly_service.detect_price_anomalies(ohlcv, contamination=0.1)
    else:  # volume
        result = await anomaly_service.detect_volume_anomalies(ohlcv, contamination=0.1)
    
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Anomaly detection failed"))
    
    return {
        "symbol": symbol,
        "exchange": exchange,
        "timeframe": timeframe,
        "anomaly_type": anomaly_type,
        **result
    }

