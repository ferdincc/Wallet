"""
Whale Alert Service - Fetches on-chain whale movements
"""
import httpx
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class WhaleAlertService:
    """Service for fetching whale alert data"""
    
    def __init__(self):
        self.api_key: Optional[str] = None
        self.base_url = "https://api.whale-alert.io/v1"
        self._check_api_key()
    
    def _check_api_key(self):
        """Check if API key is available"""
        import os
        self.api_key = os.getenv("WHALE_ALERT_API_KEY", None)
        if not self.api_key:
            logger.warning("Whale Alert API key not found. Set WHALE_ALERT_API_KEY environment variable.")
    
    async def fetch_recent_transactions(
        self,
        min_value: int = 1000000,  # Minimum $1M
        limit: int = 10,
        currency: str = "btc"
    ) -> List[Dict[str, Any]]:
        """
        Fetch recent whale transactions
        
        Args:
            min_value: Minimum transaction value in USD
            limit: Number of transactions to fetch
            currency: Currency to filter (btc, eth, etc.)
        """
        if not self.api_key:
            return []
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Get transactions from last 24 hours
                start_time = int((datetime.utcnow() - timedelta(hours=24)).timestamp())
                
                url = f"{self.base_url}/transactions"
                params = {
                    "api_key": self.api_key,
                    "min_value": min_value,
                    "start": start_time,
                    "limit": limit,
                    "currency": currency
                }
                
                response = await client.get(url, params=params)
                response.raise_for_status()
                
                data = response.json()
                
                if data.get("result") == "success":
                    transactions = data.get("transactions", [])
                    
                    # Normalize transaction data
                    normalized = []
                    for tx in transactions:
                        normalized.append({
                            "id": tx.get("id"),
                            "timestamp": tx.get("timestamp"),
                            "from": tx.get("from", {}),
                            "to": tx.get("to", {}),
                            "amount": tx.get("amount"),
                            "amount_usd": tx.get("amount_usd"),
                            "currency": tx.get("currency"),
                            "transaction_type": tx.get("transaction_type"),  # transfer, exchange
                            "hash": tx.get("hash"),
                            "blockchain": tx.get("blockchain")
                        })
                    
                    return normalized
                else:
                    logger.warning(f"Whale Alert API error: {data.get('message', 'Unknown error')}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error fetching whale alert data: {e}")
            return []
    
    async def get_exchange_inflows(
        self,
        currency: str = "btc",
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get exchange inflows (whales moving to exchanges - potential sell pressure)
        """
        transactions = await self.fetch_recent_transactions(
            min_value=1000000,
            limit=50,
            currency=currency
        )
        
        exchange_inflows = []
        total_inflow_usd = 0
        
        for tx in transactions:
            # Check if transaction is TO an exchange
            to_address = tx.get("to", {})
            if to_address.get("owner_type") == "exchange":
                exchange_inflows.append(tx)
                total_inflow_usd += tx.get("amount_usd", 0)
        
        return {
            "currency": currency.upper(),
            "hours": hours,
            "total_transactions": len(exchange_inflows),
            "total_inflow_usd": total_inflow_usd,
            "transactions": exchange_inflows[:10]  # Top 10
        }
    
    async def get_exchange_outflows(
        self,
        currency: str = "btc",
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get exchange outflows (whales moving from exchanges - potential accumulation)
        """
        transactions = await self.fetch_recent_transactions(
            min_value=1000000,
            limit=50,
            currency=currency
        )
        
        exchange_outflows = []
        total_outflow_usd = 0
        
        for tx in transactions:
            # Check if transaction is FROM an exchange
            from_address = tx.get("from", {})
            if from_address.get("owner_type") == "exchange":
                exchange_outflows.append(tx)
                total_outflow_usd += tx.get("amount_usd", 0)
        
        return {
            "currency": currency.upper(),
            "hours": hours,
            "total_transactions": len(exchange_outflows),
            "total_outflow_usd": total_outflow_usd,
            "transactions": exchange_outflows[:10]  # Top 10
        }
    
    def is_available(self) -> bool:
        """Check if Whale Alert service is available"""
        return self.api_key is not None


# Global instance
whale_alert_service = WhaleAlertService()












