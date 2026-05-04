"""
Client for Node News API (RSS, Reddit, Fear & Greed).
Used by Chat agent to fetch latest news for "son haberler" / "BTC haberleri" queries.
"""
import logging
from typing import Optional, List, Dict, Any

import requests

from app.config import settings

logger = logging.getLogger(__name__)


def fetch_latest_news(coin: Optional[str] = None, limit: int = 5) -> Dict[str, Any]:
    """
    Fetch latest news from Node News API.
    Returns {"success": bool, "items": [...], "error": str?}.
    """
    base = settings.NODE_NEWS_API_URL.rstrip("/")
    url = base
    params = {}
    if coin and coin.upper() in ("BTC", "ETH", "BNB", "SOL", "ADA", "XRP", "DOGE"):
        params["coin"] = coin.upper()
    try:
        r = requests.get(url, params=params if params else None, timeout=12)
        r.raise_for_status()
        data = r.json()
        if not data.get("success") or not isinstance(data.get("items"), list):
            return {"success": False, "items": [], "error": "Invalid response"}
        items = data["items"][:limit]
        return {"success": True, "items": items}
    except requests.RequestException as e:
        logger.warning("Node news API request failed: %s", e)
        return {"success": False, "items": [], "error": str(e)}
    except Exception as e:
        logger.warning("Node news client error: %s", e)
        return {"success": False, "items": [], "error": str(e)}
