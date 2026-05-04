"""
Alerts API endpoints for flash alerts and notifications
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel

from app.services.alert_service import alert_service
from app.symbol_query import expand_symbol_list

router = APIRouter()


class AlertResponse(BaseModel):
    alerts: List[dict]
    count: int


@router.get("/check")
async def check_alerts(
    symbols: List[str] = Query(..., description="List of symbols to check"),
    exchange: str = Query("binance", description="Exchange name")
):
    """
    Check for alerts (anomalies, news shocks) for given symbols
    
    Returns list of alerts sorted by severity
    """
    try:
        symbols = expand_symbol_list(symbols)
        alerts = await alert_service.get_all_alerts(symbols, exchange)
        
        return AlertResponse(
            alerts=alerts,
            count=len(alerts)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recent")
async def get_recent_alerts(
    limit: int = Query(10, ge=1, le=50, description="Number of recent alerts")
):
    """Get recent alerts from history"""
    alerts = alert_service.get_recent_alerts(limit)
    return AlertResponse(
        alerts=alerts,
        count=len(alerts)
    )


@router.get("/health")
async def alerts_health():
    """Check alerts service health"""
    return {
        "status": "healthy",
        "active_alerts": len(alert_service.active_alerts),
        "alert_history_count": len(alert_service.alert_history)
    }












