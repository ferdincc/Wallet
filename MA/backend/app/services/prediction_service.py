"""
Prediction Service using Prophet and LightGBM
"""
from typing import Dict, Any, List, Optional, Tuple
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import asyncio

from app.i18n.prediction_strings import (
    normalize_lang,
    confidence_message,
    direction_label,
    fallback_warning,
    feature_importance_labels,
)

logger = logging.getLogger(__name__)

# Lazy loading for models
_prophet_available = False
_lightgbm_available = False


class PredictionService:
    """Service for cryptocurrency price prediction"""
    
    def __init__(self):
        self._check_dependencies()
    
    def _check_dependencies(self):
        """Check if prediction libraries are available"""
        global _prophet_available, _lightgbm_available
        
        try:
            from prophet import Prophet
            _prophet_available = True
            logger.info("Prophet is available")
        except ImportError as e:
            logger.warning(f"Prophet not installed. Install with: pip install prophet. Error: {e}")
            _prophet_available = False
        except Exception as e:
            logger.warning(f"Prophet import error: {e}")
            _prophet_available = False
        
        try:
            import lightgbm as lgb
            _lightgbm_available = True
            logger.info("LightGBM is available")
        except ImportError as e:
            logger.warning(f"LightGBM not installed. Install with: pip install lightgbm. Error: {e}")
            _lightgbm_available = False
        except Exception as e:
            logger.warning(f"LightGBM import error: {e}")
            _lightgbm_available = False
        
        # Log final status
        logger.info(f"Prediction models status - Prophet: {_prophet_available}, LightGBM: {_lightgbm_available}")
    
    async def predict_prophet(
        self,
        ohlcv_data: List[List[float]],
        periods: int = 7,
        confidence_interval: float = 0.95,
        lang: str = "en",
    ) -> Dict[str, Any]:
        """
        Predict future prices using Prophet
        
        Args:
            ohlcv_data: OHLCV data [[timestamp, open, high, low, close, volume], ...]
            periods: Number of periods to forecast
            confidence_interval: Confidence interval (0.95 = 95%)
        
        Returns:
            Dictionary with predictions and metrics
        """
        lang = normalize_lang(lang)

        if not _prophet_available:
            return {
                "success": False,
                "error": "Prophet not available",
                "model": "prophet"
            }
        
        try:
            # Convert to DataFrame
            df = pd.DataFrame(ohlcv_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # Prophet requires 'ds' (datestamp) and 'y' (value) columns
            df_prophet = pd.DataFrame({
                'ds': pd.to_datetime(df['timestamp'], unit='ms'),
                'y': df['close']
            })
            
            # Run in thread pool (Prophet is CPU intensive)
            result = await asyncio.to_thread(
                self._prophet_predict,
                df_prophet,
                periods,
                confidence_interval,
                lang,
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error in Prophet prediction: {e}")
            return {
                "success": False,
                "error": str(e),
                "model": "prophet"
            }
    
    def _prophet_predict(
        self,
        df: pd.DataFrame,
        periods: int,
        confidence_interval: float,
        lang: str = "en",
    ) -> Dict[str, Any]:
        """Prophet prediction (runs in thread pool)"""
        from prophet import Prophet
        
        # Get current price for bounds
        current_price = df['y'].iloc[-1]
        
        # Initialize and fit model with conservative settings
        model = Prophet(
            interval_width=confidence_interval,
            daily_seasonality=True,
            weekly_seasonality=True,
            yearly_seasonality=False,  # Disable for crypto (less relevant)
            changepoint_prior_scale=0.05,  # More conservative (default 0.05, lower = smoother)
            seasonality_prior_scale=10.0,  # Allow more seasonality
            holidays_prior_scale=10.0,
            mcmc_samples=0,  # Disable MCMC for speed
            uncertainty_samples=1000  # More samples for better intervals
        )
        
        # Add cap and floor to prevent extreme predictions
        # Cap at 2x current price, floor at 0.5x
        df['cap'] = current_price * 2.0
        df['floor'] = current_price * 0.5
        
        model.fit(df)
        
        # Make future dataframe
        future = model.make_future_dataframe(periods=periods)
        
        # Add cap and floor to future dataframe
        future['cap'] = current_price * 2.0
        future['floor'] = current_price * 0.5
        
        # Predict
        forecast = model.predict(future)
        
        # Clip predictions to reasonable bounds (prevent extreme values)
        forecast['yhat'] = forecast['yhat'].clip(lower=current_price * 0.5, upper=current_price * 2.0)
        forecast['yhat_lower'] = forecast['yhat_lower'].clip(lower=current_price * 0.3, upper=current_price * 2.5)
        forecast['yhat_upper'] = forecast['yhat_upper'].clip(lower=current_price * 0.3, upper=current_price * 2.5)
        
        # Get predictions (last 'periods' rows)
        predictions = forecast.tail(periods)
        
        # Calculate metrics on training data
        actual = df['y'].values
        predicted_train = forecast.head(len(df))['yhat'].values
        
        mae = np.mean(np.abs(actual - predicted_train))
        mape = np.mean(np.abs((actual - predicted_train) / actual)) * 100
        
        # Directional accuracy (up/down prediction)
        actual_direction = np.diff(actual) > 0
        predicted_direction = np.diff(predicted_train) > 0
        directional_accuracy = np.mean(actual_direction == predicted_direction) * 100
        
        # Calculate confidence score for Prophet
        # Prophet has confidence intervals, use them for confidence calculation
        avg_confidence_width = np.mean(predictions['yhat_upper'] - predictions['yhat_lower'])
        price_range = df['y'].max() - df['y'].min()
        relative_uncertainty = (avg_confidence_width / price_range) if price_range > 0 else 1.0
        
        # Lower uncertainty = higher confidence
        confidence_score = min(100, max(0, 
            (directional_accuracy * 0.6) +  # 60% weight on direction
            (max(0, 100 - (relative_uncertainty * 100)) * 0.4)  # 40% weight on uncertainty
        ))
        
        # Determine direction
        price_change = (predictions['yhat'].iloc[-1] - df['y'].iloc[-1]) / df['y'].iloc[-1] * 100
        up = price_change > 0
        direction = direction_label(lang, up)
        
        return {
            "success": True,
            "model": "prophet",
            "predictions": [
                {
                    "date": row['ds'].isoformat(),
                    "price": float(row['yhat']),
                    "lower": float(row['yhat_lower']),
                    "upper": float(row['yhat_upper'])
                }
                for _, row in predictions.iterrows()
            ],
            "metrics": {
                "mae": float(mae),
                "mape": float(mape),
                "directional_accuracy": float(directional_accuracy)
            },
            "confidence_score": float(confidence_score),
            "confidence_message": confidence_message(lang, confidence_score, up),
            "direction": direction,
            "last_price": float(df['y'].iloc[-1]),
            "forecast_periods": periods
        }
    
    async def predict_lightgbm(
        self,
        ohlcv_data: List[List[float]],
        periods: int = 7,
        lookback: int = 30,
        lang: str = "en",
    ) -> Dict[str, Any]:
        """
        Predict future prices using LightGBM
        
        Args:
            ohlcv_data: OHLCV data
            periods: Number of periods to forecast
            lookback: Number of historical periods to use as features
        
        Returns:
            Dictionary with predictions and metrics
        """
        lang = normalize_lang(lang)

        if not _lightgbm_available:
            return {
                "success": False,
                "error": "LightGBM not available",
                "model": "lightgbm"
            }
        
        try:
            # Convert to DataFrame
            df = pd.DataFrame(ohlcv_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # Run in thread pool
            result = await asyncio.to_thread(
                self._lightgbm_predict,
                df,
                periods,
                lookback,
                lang,
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error in LightGBM prediction: {e}")
            return {
                "success": False,
                "error": str(e),
                "model": "lightgbm"
            }
    
    def _lightgbm_predict(
        self,
        df: pd.DataFrame,
        periods: int,
        lookback: int,
        lang: str = "en",
    ) -> Dict[str, Any]:
        """LightGBM prediction (runs in thread pool)"""
        import lightgbm as lgb
        from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error
        
        # Prepare features
        df = df.copy()
        df['returns'] = df['close'].pct_change()
        df['volatility'] = df['returns'].rolling(window=7).std()
        
        # Create lag features
        for lag in range(1, min(lookback, len(df))):
            df[f'close_lag_{lag}'] = df['close'].shift(lag)
            df[f'volume_lag_{lag}'] = df['volume'].shift(lag)
        
        # Technical indicators
        df['sma_7'] = df['close'].rolling(window=7).mean()
        df['sma_14'] = df['close'].rolling(window=14).mean()
        df['rsi'] = self._calculate_rsi_simple(df['close'], 14)
        
        # MACD indicator
        macd_data = self._calculate_macd(df['close'])
        df['macd'] = macd_data['macd']
        df['macd_signal'] = macd_data['signal']
        df['macd_histogram'] = macd_data['histogram']
        
        # Drop NaN rows
        df = df.dropna()
        
        if len(df) < 20:
            return {
                "success": False,
                "error": "Insufficient data for LightGBM",
                "model": "lightgbm"
            }
        
        # Prepare training data
        feature_cols = [col for col in df.columns if col not in ['timestamp', 'close', 'returns']]
        X = df[feature_cols].values
        y = df['close'].values
        
        # Split train/test (80/20)
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]
        
        # Get current price for bounds
        current_price = df['close'].iloc[-1]
        
        # Train model with more conservative settings
        model = lgb.LGBMRegressor(
            n_estimators=100,
            learning_rate=0.03,  # Lower learning rate for more conservative predictions
            max_depth=4,  # Shallower trees for less overfitting
            random_state=42,
            verbose=-1,
            reg_alpha=0.1,  # L1 regularization
            reg_lambda=0.1  # L2 regularization
        )
        
        model.fit(X_train, y_train)
        
        # Evaluate on test set
        y_pred_test = model.predict(X_test)
        
        # Clip test predictions to reasonable bounds
        y_pred_test = np.clip(y_pred_test, current_price * 0.5, current_price * 2.0)
        
        mae = mean_absolute_error(y_test, y_pred_test)
        mape = mean_absolute_percentage_error(y_test, y_pred_test) * 100
        
        # Directional accuracy
        actual_direction = np.diff(y_test) > 0
        predicted_direction = np.diff(y_pred_test) > 0
        directional_accuracy = np.mean(actual_direction == predicted_direction) * 100
        
        # Calculate confidence score based on model performance
        # Higher directional accuracy and lower MAPE = higher confidence
        confidence_score = min(100, max(0, 
            (directional_accuracy * 0.7) +  # 70% weight on direction
            (max(0, 100 - mape) * 0.3)  # 30% weight on accuracy (lower MAPE = better)
        ))
        
        # Determine direction (up/down) for confidence message
        # Use last actual price vs first prediction
        if len(y_test) > 0 and len(y_pred_test) > 0:
            price_change = (y_pred_test[-1] - y_test[-1]) / y_test[-1] * 100
        else:
            price_change = 0
        up = price_change > 0
        direction = direction_label(lang, up)
        
        # Make future predictions (iterative)
        predictions = []
        last_features = df[feature_cols].iloc[-1:].values
        
        for i in range(periods):
            # Predict next value
            next_price = model.predict(last_features)[0]
            
            # Clip to reasonable bounds (max 2x, min 0.5x current price)
            next_price = np.clip(next_price, current_price * 0.5, current_price * 2.0)
            
            # Apply gradual mean reversion (pull towards current price over time)
            mean_reversion_factor = 0.05 * (i / periods)  # 5% pull per period
            next_price = next_price * (1 - mean_reversion_factor) + current_price * mean_reversion_factor
            
            # Create timestamp (assuming hourly data)
            next_timestamp = df['timestamp'].iloc[-1] + (i + 1) * 3600000  # 1 hour in ms
            
            predictions.append({
                "date": datetime.fromtimestamp(next_timestamp / 1000).isoformat(),
                "price": float(next_price)
            })
            
            # Update features for next prediction (simplified)
            # In production, you'd update all lag features properly
            last_features[0][0] = next_price  # Update first close_lag feature
        
        # Get feature importance for XAI
        feature_importance = {}
        try:
            importance_scores = model.feature_importances_
            # Normalize to percentages
            total_importance = sum(importance_scores)
            if total_importance > 0:
                for idx, feature_name in enumerate(feature_cols):
                    feature_importance[feature_name] = float((importance_scores[idx] / total_importance) * 100)
            
            # Group similar features for better visualization
            fl = feature_importance_labels(lang)
            grouped_importance = {
                fl["rsi"]: feature_importance.get("rsi", 0),
                fl["macd"]: (feature_importance.get("macd", 0) +
                        feature_importance.get("macd_signal", 0) +
                        feature_importance.get("macd_histogram", 0)),
                fl["sma"]: (feature_importance.get("sma_7", 0) +
                       feature_importance.get("sma_14", 0)),
                fl["past"]: sum(v for k, v in feature_importance.items() if "close_lag" in k),
                fl["vol"]: sum(v for k, v in feature_importance.items() if "volume" in k or k == "volatility"),
                fl["other"]: sum(v for k, v in feature_importance.items()
                            if k not in ["rsi", "macd", "macd_signal", "macd_histogram",
                                        "sma_7", "sma_14", "volatility"] and
                            "close_lag" not in k and "volume" not in k)
            }
            # Remove zero values
            grouped_importance = {k: v for k, v in grouped_importance.items() if v > 0}
        except Exception as e:
            logger.warning(f"Could not calculate feature importance: {e}")
            grouped_importance = {}
        
        return {
            "success": True,
            "model": "lightgbm",
            "predictions": predictions,
            "metrics": {
                "mae": float(mae),
                "mape": float(mape),
                "directional_accuracy": float(directional_accuracy)
            },
            "confidence_score": float(confidence_score),
            "confidence_message": confidence_message(lang, confidence_score, up),
            "direction": direction,
            "last_price": float(df['close'].iloc[-1]),
            "forecast_periods": periods,
            "feature_importance": grouped_importance
        }
    
    def _calculate_rsi_simple(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _calculate_macd(self, prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, pd.Series]:
        """Calculate MACD indicator"""
        ema_fast = prices.ewm(span=fast, adjust=False).mean()
        ema_slow = prices.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }
    
    async def predict_ensemble(
        self,
        ohlcv_data: List[List[float]],
        periods: int = 7,
        use_prophet: bool = True,
        use_lightgbm: bool = True,
        lang: str = "en",
    ) -> Dict[str, Any]:
        """
        Ensemble prediction using both models
        
        Args:
            ohlcv_data: OHLCV data
            periods: Number of periods to forecast
            use_prophet: Use Prophet model
            use_lightgbm: Use LightGBM model
            lang: Response language (tr or en)
        
        Returns:
            Combined predictions
        """
        lang = normalize_lang(lang)
        results = []
        
        if use_prophet and _prophet_available:
            prophet_result = await self.predict_prophet(ohlcv_data, periods, lang=lang)
            if prophet_result.get("success"):
                results.append(prophet_result)
        
        if use_lightgbm and _lightgbm_available:
            lightgbm_result = await self.predict_lightgbm(ohlcv_data, periods, lang=lang)
            if lightgbm_result.get("success"):
                results.append(lightgbm_result)
        
        # Fallback to simple prediction if no models available
        if not results:
            logger.warning("No ML models available, using fallback prediction")
            return await self.predict_fallback(ohlcv_data, periods, lang=lang)
        
        # Combine predictions (average)
        if len(results) == 1:
            return results[0]
        
        # Average predictions from both models
        prophet_preds = results[0].get("predictions", [])
        lightgbm_preds = results[1].get("predictions", [])
        
        combined_predictions = []
        for i in range(min(len(prophet_preds), len(lightgbm_preds))):
            p_price = prophet_preds[i].get("price", 0)
            l_price = lightgbm_preds[i].get("price", 0)
            avg_price = (p_price + l_price) / 2
            
            combined_predictions.append({
                "date": prophet_preds[i].get("date", lightgbm_preds[i].get("date")),
                "price": float(avg_price),
                "prophet_price": float(p_price),
                "lightgbm_price": float(l_price)
            })
        
        # Average metrics
        avg_mae = np.mean([r.get("metrics", {}).get("mae", 0) for r in results])
        avg_mape = np.mean([r.get("metrics", {}).get("mape", 0) for r in results])
        avg_directional = np.mean([r.get("metrics", {}).get("directional_accuracy", 0) for r in results])
        
        # Average confidence scores
        confidence_scores = [r.get("confidence_score", 0) for r in results if r.get("confidence_score")]
        avg_confidence = np.mean(confidence_scores) if confidence_scores else 0
        
        # Combine feature importance (if available from LightGBM)
        combined_feature_importance = {}
        for r in results:
            if r.get("feature_importance"):
                for feature, importance in r.get("feature_importance", {}).items():
                    if feature in combined_feature_importance:
                        combined_feature_importance[feature] = (
                            combined_feature_importance[feature] + importance
                        ) / 2
                    else:
                        combined_feature_importance[feature] = importance
        
        # Determine direction from combined predictions
        if combined_predictions:
            first_price = combined_predictions[0].get("price", 0)
            last_price = combined_predictions[-1].get("price", 0)
            price_change = (last_price - first_price) / first_price * 100 if first_price > 0 else 0
            up = price_change > 0
            direction = direction_label(lang, up)
            conf_msg = confidence_message(lang, avg_confidence, up)
        else:
            direction = direction_label(lang, True, neutral=True)
            conf_msg = confidence_message(lang, avg_confidence, False, neutral=True)
        
        return {
            "success": True,
            "model": "ensemble",
            "predictions": combined_predictions,
            "metrics": {
                "mae": float(avg_mae),
                "mape": float(avg_mape),
                "directional_accuracy": float(avg_directional)
            },
            "confidence_score": float(avg_confidence),
            "confidence_message": conf_msg,
            "direction": direction,
            "last_price": results[0].get("last_price", 0),
            "forecast_periods": periods,
            "models_used": [r.get("model") for r in results],
            "feature_importance": combined_feature_importance if combined_feature_importance else None
        }
    
    async def predict_fallback(
        self,
        ohlcv_data: List[List[float]],
        periods: int = 7,
        lang: str = "en",
    ) -> Dict[str, Any]:
        """
        Fallback prediction using simple moving average and trend
        Used when Prophet/LightGBM are not available
        """
        lang = normalize_lang(lang)
        try:
            df = pd.DataFrame(ohlcv_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # Calculate simple moving averages
            sma_7 = df['close'].rolling(window=7).mean().iloc[-1]
            sma_14 = df['close'].rolling(window=14).mean().iloc[-1]
            current_price = df['close'].iloc[-1]
            
            # Calculate trend (simple linear regression on last 20 points)
            recent_prices = df['close'].tail(20).values
            x = np.arange(len(recent_prices))
            slope = np.polyfit(x, recent_prices, 1)[0]
            
            # Calculate volatility and mean reversion
            price_std = df['close'].tail(20).std()
            price_mean = df['close'].tail(20).mean()
            recent_volatility = df['close'].tail(20).pct_change().std()
            
            # Limit trend to be more conservative (max 5% change per period)
            max_daily_change = current_price * 0.05  # Max 5% change
            slope = np.clip(slope, -max_daily_change, max_daily_change)
            
            # Apply mean reversion - if price is far from mean, pull it back
            mean_reversion_factor = 0.1  # 10% pull towards mean
            mean_reversion_force = (price_mean - current_price) * mean_reversion_factor
            
            # Generate predictions
            predictions = []
            last_timestamp = df['timestamp'].iloc[-1]
            
            # Assume hourly data (3600000 ms)
            timeframe_ms = 3600000
            
            for i in range(1, periods + 1):
                # Conservative trend-based prediction with mean reversion
                trend_component = slope * i
                mean_reversion_component = mean_reversion_force * (i / periods)  # Gradually apply
                
                # Combine trend and mean reversion
                predicted_price = current_price + trend_component + mean_reversion_component
                
                # Ensure price doesn't go negative
                predicted_price = max(predicted_price, current_price * 0.5)  # At least 50% of current
                
                # Add uncertainty based on historical volatility (more realistic)
                volatility_multiplier = 1.0 + (recent_volatility * i * 0.5)  # Increase uncertainty over time
                lower = predicted_price - (price_std * 0.8 * volatility_multiplier)
                upper = predicted_price + (price_std * 0.8 * volatility_multiplier)
                
                next_timestamp = last_timestamp + (i * timeframe_ms)
                predictions.append({
                    "date": datetime.fromtimestamp(next_timestamp / 1000).isoformat(),
                    "price": float(predicted_price),
                    "lower": float(lower),
                    "upper": float(upper)
                })
            
            # Calculate simple metrics
            # Use recent volatility as error estimate
            recent_returns = df['close'].tail(20).pct_change().dropna()
            mae = float(recent_returns.abs().mean() * current_price)
            mape = float(recent_returns.abs().mean() * 100)
            
            # Directional accuracy (simplified)
            up_days = (recent_returns > 0).sum()
            directional_accuracy = (up_days / len(recent_returns)) * 100 if len(recent_returns) > 0 else 50
            
            # Confidence score (lower for fallback)
            confidence_score = min(60, max(30, directional_accuracy))
            up = slope > 0
            direction = direction_label(lang, up)
            
            return {
                "success": True,
                "model": "fallback",
                "predictions": predictions,
                "metrics": {
                    "mae": float(mae),
                    "mape": float(mape),
                    "directional_accuracy": float(directional_accuracy)
                },
                "confidence_score": float(confidence_score),
                "confidence_message": confidence_message(
                    lang, confidence_score, up, simple_fallback=True
                ),
                "direction": direction,
                "last_price": float(current_price),
                "forecast_periods": periods,
                "warning": fallback_warning(lang),
            }
            
        except Exception as e:
            logger.error(f"Error in fallback prediction: {e}")
            return {
                "success": False,
                "error": f"Fallback prediction failed: {str(e)}",
                "model": "fallback"
            }
    
    def is_prophet_available(self) -> bool:
        """Check if Prophet is available"""
        return _prophet_available
    
    def is_lightgbm_available(self) -> bool:
        """Check if LightGBM is available"""
        return _lightgbm_available


# Global instance
prediction_service = PredictionService()





