"""
Comprehensive Analysis API endpoint
Combines all agents for complete analysis
"""
import logging
import traceback
from fastapi import APIRouter, HTTPException, Query, Depends, Body
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel, Field

from app.database import get_db
from app.agents.analysis_agent import AnalysisAgent
from app.agents.sentiment_agent import SentimentAgent
from app.agents.prediction_agent import PredictionAgent
from app.agents.risk_agent import RiskAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

router = APIRouter()

analysis_agent = AnalysisAgent()
sentiment_agent = SentimentAgent()
prediction_agent = PredictionAgent()
risk_agent = RiskAgent()


class AnalysisRequest(BaseModel):
    """Request model for analysis endpoint"""
    symbol: str = Field(..., description="Cryptocurrency symbol (e.g., BTC/USDT)")
    exchange: str = Field("binance", description="Exchange name")
    include_sentiment: bool = Field(True, description="Include sentiment analysis")
    include_prediction: bool = Field(True, description="Include price prediction")
    include_technical: bool = Field(True, description="Include technical analysis")


class ComprehensiveAnalysisResponse(BaseModel):
    success: bool
    symbol: str
    technical_analysis: Optional[dict] = None
    sentiment_analysis: Optional[dict] = None
    prediction: Optional[dict] = None
    sources: list = []
    error: Optional[str] = None


@router.post("/analyze", response_model=ComprehensiveAnalysisResponse)
async def comprehensive_analysis(
    request: Optional[AnalysisRequest] = Body(None),
    symbol: Optional[str] = Query(None, description="Cryptocurrency symbol (e.g., BTC/USDT)"),
    exchange: Optional[str] = Query("binance", description="Exchange name"),
    include_sentiment: Optional[bool] = Query(True, description="Include sentiment analysis"),
    include_prediction: Optional[bool] = Query(True, description="Include price prediction"),
    include_technical: Optional[bool] = Query(True, description="Include technical analysis"),
    db: Session = Depends(get_db)
):
    """
    Comprehensive analysis combining all agents
    
    Returns technical analysis, sentiment analysis, and price predictions
    with source links for news and social media.
    
    Accepts either JSON body or query parameters.
    """
    try:
        # Support both JSON body and query parameters
        if request:
            symbol = request.symbol
            exchange = request.exchange
            include_sentiment = request.include_sentiment
            include_prediction = request.include_prediction
            include_technical = request.include_technical
        
        if not symbol:
            logger.error("Symbol parameter is required")
            raise HTTPException(status_code=400, detail="Symbol parameter is required")
        
        logger.info(f"Starting comprehensive analysis for {symbol} on {exchange}")
        
        result = {
            "success": True,
            "symbol": symbol,
            "technical_analysis": None,
            "sentiment_analysis": None,
            "prediction": None,
            "sources": [],
            "error": None
        }
        
        # Technical Analysis with error handling
        if include_technical:
            try:
                logger.info(f"Executing technical analysis for {symbol}")
                ta_result = await analysis_agent.execute(
                    symbol=symbol,
                    exchange=exchange,
                    include_sentiment=False
                )
                if ta_result and ta_result.get("success"):
                    result["technical_analysis"] = ta_result
                    logger.info(f"Technical analysis completed for {symbol}")
                else:
                    error_msg = ta_result.get("error", "Technical analysis failed") if ta_result else "Technical analysis returned None"
                    logger.warning(f"Technical analysis failed for {symbol}: {error_msg}")
                    result["error"] = f"Teknik analiz başarısız: {error_msg}"
            except Exception as e:
                logger.error(f"Error in technical analysis for {symbol}: {str(e)}", exc_info=True)
                result["error"] = f"Teknik analiz hatası: {str(e)}"
        
        # Sentiment Analysis with error handling
        if include_sentiment:
            try:
                symbol_base = symbol.split("/")[0] if "/" in symbol else symbol
                logger.info(f"Executing sentiment analysis for {symbol_base}")
                sentiment_result = await sentiment_agent.execute(
                    symbol=symbol_base,
                    include_news=True,
                    include_reddit=True,
                    hours=24,
                    db=db
                )
                if sentiment_result and sentiment_result.get("success"):
                    result["sentiment_analysis"] = sentiment_result.get("overall_sentiment")
                    result["sources"].extend(sentiment_result.get("sources", []))
                    logger.info(f"Sentiment analysis completed for {symbol_base}")
                else:
                    error_msg = sentiment_result.get("error", "Sentiment analysis failed") if sentiment_result else "Sentiment analysis returned None"
                    logger.warning(f"Sentiment analysis failed for {symbol_base}: {error_msg}")
                    if not result["error"]:
                        result["error"] = f"Sentiment analizi başarısız: {error_msg}"
            except Exception as e:
                logger.error(f"Error in sentiment analysis for {symbol}: {str(e)}", exc_info=True)
                if not result["error"]:
                    result["error"] = f"Sentiment analizi hatası: {str(e)}"
        
        # Price Prediction with error handling
        if include_prediction:
            try:
                logger.info(f"Executing price prediction for {symbol}")
                prediction_result = await prediction_agent.execute(
                    symbol=symbol,
                    exchange=exchange,
                    periods=7,
                    model="ensemble"
                )
                if prediction_result and prediction_result.get("success"):
                    result["prediction"] = {
                        "model": prediction_result.get("model"),
                        "predictions": prediction_result.get("predictions", [])[:5],  # First 5 days
                        "metrics": prediction_result.get("metrics", {}),
                        "predicted_change": prediction_result.get("predicted_change", {})
                    }
                    logger.info(f"Price prediction completed for {symbol}")
                else:
                    error_msg = prediction_result.get("error", "Prediction failed") if prediction_result else "Prediction returned None"
                    logger.warning(f"Price prediction failed for {symbol}: {error_msg}")
                    if not result["error"]:
                        result["error"] = f"Fiyat tahmini başarısız: {error_msg}"
            except Exception as e:
                logger.error(f"Error in price prediction for {symbol}: {str(e)}", exc_info=True)
                if not result["error"]:
                    result["error"] = f"Fiyat tahmini hatası: {str(e)}"
        
        logger.info(f"Comprehensive analysis completed for {symbol}")
        return ComprehensiveAnalysisResponse(**result)
    
    except HTTPException:
        raise
    except Exception as e:
        error_detail = f"Internal server error: {str(e)}"
        logger.error(f"Error in comprehensive_analysis: {error_detail}", exc_info=True)
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=error_detail)


@router.get("/alerts")
async def get_alerts(
    portfolio_id: int = Query(..., description="Portfolio ID"),
    db: Session = Depends(get_db)
):
    """
    Get risk alerts for a portfolio
    
    Returns risk warnings, anomalies, and recommendations.
    """
    try:
        result = await risk_agent.execute(
            portfolio_id=portfolio_id,
            db=db
        )
        
        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Risk analysis failed")
            )
        
        return {
            "success": True,
            "portfolio_id": portfolio_id,
            "warnings": result.get("warnings", []),
            "warning_count": result.get("warning_count", 0),
            "anomaly_detection": result.get("anomaly_detection"),
            "portfolio_health": {
                "current_balance": result.get("current_balance"),
                "initial_balance": result.get("initial_balance"),
                "change_percent": result.get("portfolio_change_percent")
            }
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))














