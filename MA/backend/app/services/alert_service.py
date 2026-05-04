"""
Alert Service - Handles flash alerts and push notifications
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging
from app.services.anomaly_service import anomaly_service
from app.services.exchange_service import exchange_service
from app.services.news_service import news_service
import asyncio

logger = logging.getLogger(__name__)


class AlertService:
    """Service for managing alerts and notifications"""
    
    def __init__(self):
        self.active_alerts: List[Dict[str, Any]] = []
        self.alert_history: List[Dict[str, Any]] = []
    
    async def check_anomaly_alerts(
        self,
        symbol: str,
        exchange: str = "binance"
    ) -> List[Dict[str, Any]]:
        """
        Check for anomaly-based alerts
        
        Returns list of alerts if anomalies detected
        """
        alerts = []
        
        if not anomaly_service.is_available():
            return alerts
        
        try:
            # Fetch OHLCV data
            ohlcv = await exchange_service.fetch_ohlcv(symbol, "1h", limit=100, exchange_name=exchange)
            
            if not ohlcv or len(ohlcv) < 10:
                return alerts
            
            # Check volume anomalies
            volume_result = await anomaly_service.detect_volume_anomalies(ohlcv, contamination=0.1)
            
            if volume_result.get("success") and volume_result.get("anomalies"):
                anomalies = volume_result.get("anomalies", [])
                
                for anomaly in anomalies[:3]:  # Top 3 anomalies
                    volume = anomaly.get("volume", 0)
                    # Calculate volume multiplier
                    avg_volume = sum(candle[5] for candle in ohlcv[-24:]) / 24 if len(ohlcv) >= 24 else 0
                    
                    if avg_volume > 0:
                        multiplier = volume / avg_volume
                        
                        if multiplier > 3:  # 300% increase
                            alerts.append({
                                "type": "volume_anomaly",
                                "severity": "high",
                                "symbol": symbol,
                                "message": f"{symbol} için olağandışı hacim artışı saptandı! Hacim son 1 saatte normalin {multiplier:.1f}x katına çıktı. Bir balina hareketi olabilir!",
                                "multiplier": multiplier,
                                "timestamp": datetime.utcnow().isoformat(),
                                "exchange": exchange
                            })
            
            # Check price anomalies
            price_result = await anomaly_service.detect_price_anomalies(ohlcv, contamination=0.1)
            
            if price_result.get("success") and price_result.get("anomalies"):
                anomalies = price_result.get("anomalies", [])
                
                for anomaly in anomalies[:2]:  # Top 2 price anomalies
                    price = anomaly.get("price", 0)
                    current_price = ohlcv[-1][4] if ohlcv else 0
                    
                    if current_price > 0:
                        change_pct = abs((price - current_price) / current_price * 100)
                        
                        if change_pct > 10:  # 10% price swing
                            alerts.append({
                                "type": "price_anomaly",
                                "severity": "high",
                                "symbol": symbol,
                                "message": f"{symbol} için olağandışı fiyat hareketi! Fiyat %{change_pct:.1f} değişti.",
                                "price_change": change_pct,
                                "timestamp": datetime.utcnow().isoformat(),
                                "exchange": exchange
                            })
        
        except Exception as e:
            logger.error(f"Error checking anomaly alerts: {e}")
        
        return alerts
    
    async def check_news_shock_alerts(
        self,
        symbol: str,
        hours: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Check for critical news that might cause market shock
        
        Returns list of alerts for critical news
        """
        alerts = []
        
        try:
            # Fetch recent news
            news_articles = await news_service.fetch_news(
                query=symbol.split("/")[0] if "/" in symbol else symbol,
                page_size=10,
                hours=hours,
            )
            
            if not news_articles:
                return alerts
            
            # Keywords that indicate critical news
            critical_keywords = [
                "SEC", "regulation", "ban", "yasa", "yasak",
                "hack", "hack", "exploit", "sızıntı",
                "lawsuit", "dava", "mahkeme",
                "bankruptcy", "iflas",
                "partnership", "ortaklık", "anlaşma",
                "halving", "yarılanma"
            ]
            
            for article in news_articles:
                title = article.get("title", "").lower()
                description = article.get("description", "").lower()
                content = f"{title} {description}"
                
                # Check for critical keywords
                for keyword in critical_keywords:
                    if keyword.lower() in content:
                        alerts.append({
                            "type": "news_shock",
                            "severity": "critical",
                            "symbol": symbol,
                            "message": f"KRİTİK HABER: {article.get('title', 'Haber başlığı yok')} - Bu haber piyasayı etkileyebilir!",
                            "article_title": article.get("title"),
                            "article_url": article.get("url"),
                            "keyword": keyword,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        break  # Only one alert per article
        
        except Exception as e:
            logger.error(f"Error checking news shock alerts: {e}")
        
        return alerts
    
    async def get_all_alerts(
        self,
        symbols: List[str],
        exchange: str = "binance"
    ) -> List[Dict[str, Any]]:
        """
        Get all alerts for given symbols
        
        Combines anomaly and news alerts
        """
        all_alerts = []
        
        for symbol in symbols:
            # Check anomalies
            anomaly_alerts = await self.check_anomaly_alerts(symbol, exchange)
            all_alerts.extend(anomaly_alerts)
            
            # Check news shocks
            news_alerts = await self.check_news_shock_alerts(symbol, hours=1)
            all_alerts.extend(news_alerts)
        
        # Sort by severity and timestamp
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        all_alerts.sort(key=lambda x: (
            severity_order.get(x.get("severity", "low"), 3),
            -datetime.fromisoformat(x.get("timestamp", datetime.utcnow().isoformat())).timestamp()
        ))
        
        # Store in history
        self.alert_history.extend(all_alerts)
        # Keep only last 100 alerts
        if len(self.alert_history) > 100:
            self.alert_history = self.alert_history[-100:]
        
        return all_alerts
    
    def get_recent_alerts(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent alerts from history"""
        return self.alert_history[-limit:]


# Global instance
alert_service = AlertService()












