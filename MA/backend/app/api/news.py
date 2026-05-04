"""
News and Sentiment API endpoints
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.database import get_db
from app.agents.sentiment_agent import SentimentAgent

router = APIRouter()
sentiment_agent = SentimentAgent()


class SentimentResponse(BaseModel):
    success: bool
    symbol: Optional[str] = None
    overall_sentiment: Optional[dict] = None
    news_sentiment: List[dict] = []
    reddit_sentiment: List[dict] = []
    sources: List[dict] = []
    error: Optional[str] = None
    # New fields for enhanced sentiment analysis
    explanation: Optional[str] = None  # Why this score was given
    gauge_score: Optional[int] = None  # 0-100 score for gauge chart


@router.get("/sentiment", response_model=SentimentResponse)
async def get_sentiment(
    symbol: str = Query(..., description="Cryptocurrency symbol (e.g., BTC, ETH)"),
    include_news: bool = Query(True, description="Include news articles"),
    include_reddit: bool = Query(True, description="Include Reddit posts"),
    hours: int = Query(24, ge=1, le=168, description="Hours back to search"),
    locale: str = Query("en", description="UI language (en)"),
    db: Session = Depends(get_db)
):
    """
    Get sentiment analysis for a cryptocurrency symbol
    
    Analyzes news articles and Reddit posts to determine overall sentiment.
    Returns sentiment scores, source links, and aggregated results.
    """
    try:
        result = await sentiment_agent.execute(
            symbol=symbol,
            include_news=include_news,
            include_reddit=include_reddit,
            hours=hours,
            db=db,
            locale=locale,
        )
        
        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Sentiment analysis failed")
            )
        
        overall_sentiment = result.get("overall_sentiment", {})
        
        return SentimentResponse(
            success=True,
            symbol=result.get("symbol"),
            overall_sentiment=overall_sentiment,
            news_sentiment=result.get("news_sentiment", []),
            reddit_sentiment=result.get("reddit_sentiment", []),
            sources=result.get("sources", []),
            explanation=overall_sentiment.get("explanation") if overall_sentiment else None,
            gauge_score=overall_sentiment.get("gauge_score") if overall_sentiment else None
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sentiment/query")
async def get_sentiment_by_query(
    query: str = Query(..., description="Search query"),
    include_news: bool = Query(True),
    include_reddit: bool = Query(True),
    hours: int = Query(24, ge=1, le=168),
    locale: str = Query("en", description="UI language (en)"),
    db: Session = Depends(get_db)
):
    """
    Get sentiment analysis for a custom query
    
    Useful for searching specific topics or events.
    """
    try:
        result = await sentiment_agent.execute(
            query=query,
            include_news=include_news,
            include_reddit=include_reddit,
            hours=hours,
            db=db,
            locale=locale,
        )
        
        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Sentiment analysis failed")
            )
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def news_health():
    """Check news and sentiment service health"""
    from app.services.news_service import news_service
    from app.services.sentiment_service import sentiment_service
    
    return {
        "status": "healthy",
        "newsapi_available": news_service.is_newsapi_available(),
        "reddit_available": news_service.is_reddit_available(),
        "sentiment_available": sentiment_service.is_available()
    }





