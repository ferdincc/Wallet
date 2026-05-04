"""
Prediction API endpoints
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from pydantic import BaseModel

from app.agents.prediction_agent import PredictionAgent
from app.services.backtest_service import backtest_service
from app.database import get_db
from sqlalchemy.orm import Session
from fastapi import Depends

router = APIRouter()
prediction_agent = PredictionAgent()


def _prediction_http_exception(result: dict) -> HTTPException:
    """Borsa zaman aşımı / boş veri için 500 yerine anlamlı HTTP kodları."""
    code = result.get("failure_code") or "UNKNOWN"
    detail = result.get("error", "Prediction failed")
    status_map = {
        "SYMBOL_REQUIRED": 400,
        "FETCH_TIMEOUT": 504,
        "NO_MARKET_DATA": 404,
        "EXCHANGE_EMPTY": 503,
        "INSUFFICIENT_HISTORY": 422,
        "PREDICTION_FAILED": 500,
        "UNKNOWN": 500,
    }
    return HTTPException(status_code=status_map.get(code, 500), detail=detail)


class PredictionResponse(BaseModel):
    success: bool
    symbol: str
    model: str
    predictions: list
    metrics: dict
    current_price: float
    predicted_change: Optional[dict] = None
    confidence_score: Optional[float] = None  # 0-100 confidence score
    confidence_message: Optional[str] = None  # "Modelimiz %65 güven oranıyla yükseliş bekliyor"
    direction: Optional[str] = None  # "yükseliş" or "düşüş"
    explanation: Optional[str] = None  # XAI explanation
    feature_importance: Optional[dict] = None  # Feature importance for XAI
    error: Optional[str] = None


@router.get("", response_model=PredictionResponse)
async def get_prediction(
    symbol: str = Query(..., description="Cryptocurrency symbol (e.g., BTC/USDT)"),
    exchange: str = Query("binance", description="Exchange name"),
    timeframe: str = Query("1h", description="Timeframe (1h, 4h, 1d)"),
    periods: int = Query(7, ge=1, le=30, description="Number of periods to forecast"),
    model: str = Query("ensemble", description="Model: prophet, lightgbm, or ensemble"),
    lang: str = Query("en", description="Response language (en)"),
):
    """
    Get price prediction for a cryptocurrency
    
    Uses Prophet (baseline) and/or LightGBM models to predict future prices.
    Returns predictions, metrics (MAE, MAPE, Directional Accuracy), and price change estimates.
    """
    try:
        result = await prediction_agent.execute(
            symbol=symbol,
            exchange=exchange,
            timeframe=timeframe,
            periods=periods,
            model=model,
            lang=lang,
        )
        
        if not result.get("success"):
            raise _prediction_http_exception(result)
        
        # Record prediction for backtesting (async, don't wait)
        # Note: We'll record it when actual price is known, not here
        # This is just for the response
        
        return PredictionResponse(
            success=True,
            symbol=result.get("symbol"),
            model=result.get("model"),
            predictions=result.get("predictions", []),
            metrics=result.get("metrics", {}),
            current_price=result.get("current_price", 0),
            predicted_change=result.get("predicted_change"),
            confidence_score=result.get("confidence_score"),
            confidence_message=result.get("confidence_message"),
            direction=result.get("direction"),
            explanation=result.get("explanation"),
            feature_importance=result.get("feature_importance")
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/short")
async def get_short_term_prediction(
    symbol: str = Query(..., description="Cryptocurrency symbol"),
    exchange: str = Query("binance", description="Exchange name"),
    lang: str = Query("en", description="Response language (en)"),
):
    """
    Get short-term prediction (24 hours)
    
    Optimized for 24-hour forecasting with confidence intervals.
    Uses Prophet baseline with confidence bands.
    """
    result = await prediction_agent.execute(
        symbol=symbol,
        exchange=exchange,
        timeframe="1h",
        periods=24,  # 24 hours
        model="prophet",  # Prophet for confidence intervals
        lang=lang,
    )
    
    if not result.get("success"):
        raise _prediction_http_exception(result)

    return PredictionResponse(
        success=True,
        symbol=result.get("symbol"),
        model=result.get("model"),
        predictions=result.get("predictions", []),
        metrics=result.get("metrics", {}),
        current_price=result.get("current_price", 0),
        predicted_change=result.get("predicted_change"),
        confidence_score=result.get("confidence_score"),
        confidence_message=result.get("confidence_message"),
        direction=result.get("direction"),
        explanation=result.get("explanation")
    )


@router.get("/medium")
async def get_medium_term_prediction(
    symbol: str = Query(..., description="Cryptocurrency symbol"),
    exchange: str = Query("binance", description="Exchange name"),
    lang: str = Query("en", description="Response language (en)"),
):
    """
    Get medium-term prediction (7-30 days)
    
    Uses ensemble model for better accuracy.
    """
    result = await prediction_agent.execute(
        symbol=symbol,
        exchange=exchange,
        timeframe="4h",
        periods=42,  # 42 * 4h = 7 days
        model="ensemble",
        lang=lang,
    )
    
    if not result.get("success"):
        raise _prediction_http_exception(result)

    return result


@router.get("/health")
async def prediction_health():
    """Check prediction service health"""
    from app.services.prediction_service import prediction_service
    
    # Force re-check dependencies
    prediction_service._check_dependencies()
    
    # Also check directly by importing
    try:
        from prophet import Prophet
        prophet_direct = True
    except:
        prophet_direct = False
    
    try:
        import lightgbm
        lightgbm_direct = True
    except:
        lightgbm_direct = False
    
    return {
        "status": "healthy",
        "prophet_available": prediction_service.is_prophet_available() or prophet_direct,
        "lightgbm_available": prediction_service.is_lightgbm_available() or lightgbm_direct,
        "prophet_direct_check": prophet_direct,
        "lightgbm_direct_check": lightgbm_direct
    }


@router.get("/backtest/stats")
async def get_backtest_stats(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    model_type: Optional[str] = Query(None, description="Filter by model type"),
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    db: Session = Depends(get_db)
):
    """Get backtest statistics"""
    stats = await backtest_service.calculate_backtest_stats(
        db=db,
        symbol=symbol,
        model_type=model_type,
        days=days
    )
    return stats


@router.get("/backtest/recent")
async def get_recent_predictions(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    limit: int = Query(10, ge=1, le=100, description="Number of recent predictions"),
    db: Session = Depends(get_db)
):
    """Get recent predictions with results"""
    predictions = await backtest_service.get_recent_predictions(
        db=db,
        symbol=symbol,
        limit=limit
    )
    return {"predictions": predictions}

