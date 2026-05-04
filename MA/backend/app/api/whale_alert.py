"""
Whale Alert API endpoints for on-chain data
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.services.whale_alert_service import whale_alert_service

router = APIRouter()


@router.get("/whale-alert/transactions")
async def get_whale_transactions(
    currency: str = Query("btc", description="Currency (btc, eth, etc.)"),
    min_value: int = Query(1000000, description="Minimum transaction value in USD"),
    limit: int = Query(10, ge=1, le=50, description="Number of transactions")
):
    """Get recent whale transactions"""
    try:
        transactions = await whale_alert_service.fetch_recent_transactions(
            min_value=min_value,
            limit=limit,
            currency=currency.lower()
        )
        
        return {
            "success": True,
            "currency": currency.upper(),
            "count": len(transactions),
            "transactions": transactions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/whale-alert/exchange-inflows")
async def get_exchange_inflows(
    currency: str = Query("btc", description="Currency (btc, eth, etc.)"),
    hours: int = Query(24, ge=1, le=168, description="Hours back to search")
):
    """Get exchange inflows (potential sell pressure)"""
    try:
        result = await whale_alert_service.get_exchange_inflows(
            currency=currency.lower(),
            hours=hours
        )
        
        return {
            "success": True,
            **result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/whale-alert/exchange-outflows")
async def get_exchange_outflows(
    currency: str = Query("btc", description="Currency (btc, eth, etc.)"),
    hours: int = Query(24, ge=1, le=168, description="Hours back to search")
):
    """Get exchange outflows (potential accumulation)"""
    try:
        result = await whale_alert_service.get_exchange_outflows(
            currency=currency.lower(),
            hours=hours
        )
        
        return {
            "success": True,
            **result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/whale-alert/health")
async def whale_alert_health():
    """Check Whale Alert service health"""
    return {
        "status": "healthy" if whale_alert_service.is_available() else "unavailable",
        "api_key_configured": whale_alert_service.is_available()
    }












