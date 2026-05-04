"""
Ablation Study API endpoints
"""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import List, Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
from fastapi import Depends

from app.services.ablation_study_service import ablation_study_service
from app.database import get_db

router = APIRouter()


@router.get("/compare")
async def compare_models(
    symbol: str = Query(..., description="Symbol to compare"),
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    db: Session = Depends(get_db)
):
    """
    Compare different model configurations for ablation study
    
    Compares:
    - Technical Only (Prophet)
    - Technical + Sentiment (LightGBM)
    - Multi-Agent (Ensemble)
    """
    try:
        result = await ablation_study_service.compare_models(db, symbol, days)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/summary")
async def get_study_summary(
    symbols: List[str] = Body(..., description="List of symbols to analyze"),
    days: int = Body(30, description="Number of days to analyze"),
    db: Session = Depends(get_db)
):
    """
    Get ablation study summary for multiple symbols
    
    Returns aggregated results showing which approach performs best
    """
    try:
        result = await ablation_study_service.get_study_summary(db, symbols, days)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("error"))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))












