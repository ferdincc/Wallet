"""
Anomaly Detection Service using Isolation Forest
"""
from typing import Dict, Any, List, Optional
import logging
import numpy as np
import pandas as pd
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)

_isolation_forest_available = False


class AnomalyService:
    """Service for detecting anomalies in price and volume data"""
    
    def __init__(self):
        self._check_dependencies()
    
    def _check_dependencies(self):
        """Check if scikit-learn is available"""
        global _isolation_forest_available
        
        try:
            from sklearn.ensemble import IsolationForest
            _isolation_forest_available = True
            logger.info("Isolation Forest is available")
        except ImportError:
            logger.warning("scikit-learn not installed. Install with: pip install scikit-learn")
            _isolation_forest_available = False
    
    async def detect_price_anomalies(
        self,
        ohlcv_data: List[List[float]],
        contamination: float = 0.1
    ) -> Dict[str, Any]:
        """
        Detect price anomalies using Isolation Forest
        
        Args:
            ohlcv_data: OHLCV data
            contamination: Expected proportion of anomalies (0.1 = 10%)
        
        Returns:
            Dictionary with anomaly detection results
        """
        if not _isolation_forest_available:
            return {
                "success": False,
                "error": "Isolation Forest not available",
                "model": "isolation_forest"
            }
        
        try:
            # Convert to DataFrame
            df = pd.DataFrame(ohlcv_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # Run in thread pool
            result = await asyncio.to_thread(
                self._detect_anomalies,
                df,
                contamination,
                "price"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error in price anomaly detection: {e}")
            return {
                "success": False,
                "error": str(e),
                "model": "isolation_forest"
            }
    
    async def detect_volume_anomalies(
        self,
        ohlcv_data: List[List[float]],
        contamination: float = 0.1
    ) -> Dict[str, Any]:
        """Detect volume anomalies"""
        if not _isolation_forest_available:
            return {
                "success": False,
                "error": "Isolation Forest not available"
            }
        
        try:
            df = pd.DataFrame(ohlcv_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            result = await asyncio.to_thread(
                self._detect_anomalies,
                df,
                contamination,
                "volume"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error in volume anomaly detection: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _detect_anomalies(
        self,
        df: pd.DataFrame,
        contamination: float,
        feature_type: str
    ) -> Dict[str, Any]:
        """Detect anomalies (runs in thread pool)"""
        from sklearn.ensemble import IsolationForest
        
        # Prepare features
        if feature_type == "price":
            # Use price features
            features = df[['open', 'high', 'low', 'close']].values
            
            # Add price changes
            df['price_change'] = df['close'].pct_change()
            df['volatility'] = df['price_change'].rolling(window=7).std()
            df = df.dropna()
            
            if len(df) < 10:
                return {
                    "success": False,
                    "error": "Insufficient data"
                }
            
            features = df[['close', 'price_change', 'volatility']].values
            feature_names = ['close', 'price_change', 'volatility']
        else:  # volume
            # Use volume features
            df['volume_change'] = df['volume'].pct_change()
            df['volume_ma'] = df['volume'].rolling(window=7).mean()
            df = df.dropna()
            
            if len(df) < 10:
                return {
                    "success": False,
                    "error": "Insufficient data"
                }
            
            features = df[['volume', 'volume_change', 'volume_ma']].values
            feature_names = ['volume', 'volume_change', 'volume_ma']
        
        # Train Isolation Forest
        model = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_estimators=100
        )
        
        model.fit(features)
        
        # Predict anomalies
        predictions = model.predict(features)
        anomaly_scores = model.score_samples(features)
        
        # Get anomaly indices
        anomaly_indices = np.where(predictions == -1)[0]
        
        # Prepare results
        anomalies = []
        for idx in anomaly_indices:
            row = df.iloc[idx]
            anomalies.append({
                "timestamp": datetime.fromtimestamp(row['timestamp'] / 1000).isoformat(),
                "close": float(row['close']),
                "volume": float(row['volume']),
                "anomaly_score": float(anomaly_scores[idx]),
                "type": feature_type
            })
        
        return {
            "success": True,
            "model": "isolation_forest",
            "feature_type": feature_type,
            "total_samples": len(df),
            "anomalies_detected": len(anomalies),
            "anomaly_rate": len(anomalies) / len(df) * 100,
            "anomalies": anomalies,
            "contamination": contamination
        }
    
    async def detect_portfolio_anomalies(
        self,
        portfolio_values: List[float],
        timestamps: List[datetime],
        contamination: float = 0.1
    ) -> Dict[str, Any]:
        """
        Detect anomalies in portfolio value changes
        
        Args:
            portfolio_values: List of portfolio values over time
            timestamps: Corresponding timestamps
            contamination: Expected proportion of anomalies
        """
        if not _isolation_forest_available:
            return {
                "success": False,
                "error": "Isolation Forest not available"
            }
        
        try:
            # Calculate features
            values = np.array(portfolio_values)
            returns = np.diff(values) / values[:-1]
            volatility = pd.Series(returns).rolling(window=7).std().values
            
            # Prepare feature matrix
            features = np.column_stack([
                values[1:],  # Current value
                returns,     # Returns
                volatility[1:]  # Volatility
            ])
            
            # Remove NaN
            valid_mask = ~np.isnan(features).any(axis=1)
            features = features[valid_mask]
            valid_timestamps = [timestamps[i+1] for i, valid in enumerate(valid_mask) if valid]
            
            if len(features) < 10:
                return {
                    "success": False,
                    "error": "Insufficient data"
                }
            
            # Run in thread pool
            result = await asyncio.to_thread(
                self._detect_portfolio_anomalies,
                features,
                valid_timestamps,
                contamination
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error in portfolio anomaly detection: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _detect_portfolio_anomalies(
        self,
        features: np.ndarray,
        timestamps: List[datetime],
        contamination: float
    ) -> Dict[str, Any]:
        """Detect portfolio anomalies (runs in thread pool)"""
        from sklearn.ensemble import IsolationForest
        
        model = IsolationForest(
            contamination=contamination,
            random_state=42
        )
        
        model.fit(features)
        predictions = model.predict(features)
        scores = model.score_samples(features)
        
        anomaly_indices = np.where(predictions == -1)[0]
        
        anomalies = []
        for idx in anomaly_indices:
            anomalies.append({
                "timestamp": timestamps[idx].isoformat(),
                "portfolio_value": float(features[idx][0]),
                "return": float(features[idx][1]),
                "anomaly_score": float(scores[idx])
            })
        
        return {
            "success": True,
            "model": "isolation_forest",
            "type": "portfolio",
            "total_samples": len(features),
            "anomalies_detected": len(anomalies),
            "anomaly_rate": len(anomalies) / len(features) * 100,
            "anomalies": anomalies
        }
    
    def is_available(self) -> bool:
        """Check if Isolation Forest is available"""
        return _isolation_forest_available


# Global instance
anomaly_service = AnomalyService()


















