"""
Prediction Agent - Performs price predictions using Prophet and LightGBM
"""
from typing import Dict, Any, Optional
from app.agents.base_agent import BaseAgent
from app.services.exchange_service import exchange_service
from app.services.prediction_service import prediction_service
from app.i18n.prediction_strings import (
    normalize_lang,
    xai_explanation,
    xai_explanation_failed,
    err_symbol_required,
    err_fetch_timeout,
    err_no_market_data,
    err_insufficient_history,
    err_prediction_failed,
)


class PredictionAgent(BaseAgent):
    """Agent responsible for price prediction"""
    
    def __init__(self):
        super().__init__("PredictionAgent")
    
    async def execute(
        self,
        symbol: str,
        exchange: str = "binance",
        timeframe: str = "1h",
        periods: int = 7,
        model: str = "ensemble",  # "prophet", "lightgbm", or "ensemble"
        lang: str = "en",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Predict future prices for a symbol
        
        Args:
            symbol: Cryptocurrency symbol
            exchange: Exchange name
            timeframe: Timeframe for data (1h, 4h, 1d)
            periods: Number of periods to forecast
            model: Model to use ("prophet", "lightgbm", "ensemble")
        """
        import traceback
        import asyncio

        lang = normalize_lang(kwargs.get("locale") or lang)
        
        if not symbol:
            self.log("Symbol is required for prediction", "ERROR")
            return {
                "success": False,
                "failure_code": "SYMBOL_REQUIRED",
                "error": err_symbol_required(lang),
                "agent": self.name
            }
        
        try:
            # Fetch historical OHLCV data
            # Get more data for better predictions
            limit = max(100, periods * 10)
            self.log(f"Fetching OHLCV data for {symbol} (limit: {limit})", "INFO")
            
            try:
                ohlcv = await asyncio.wait_for(
                    exchange_service.fetch_ohlcv(
                        symbol,
                        timeframe,
                        limit=limit,
                        exchange_name=exchange
                    ),
                    timeout=45.0,
                )
            except asyncio.TimeoutError:
                self.log(f"Timeout fetching OHLCV for {symbol}", "ERROR")
                return {
                    "success": False,
                    "failure_code": "FETCH_TIMEOUT",
                    "error": err_fetch_timeout(lang),
                    "agent": self.name
                }
            
            # Validate OHLCV data
            if ohlcv is None:
                self.log(f"OHLCV data is None for {symbol}", "WARNING")
                return {
                    "success": False,
                    "failure_code": "NO_MARKET_DATA",
                    "error": err_no_market_data(lang),
                    "agent": self.name
                }

            if not isinstance(ohlcv, list):
                self.log(f"OHLCV data is not a list for {symbol}", "WARNING")
                return {
                    "success": False,
                    "failure_code": "NO_MARKET_DATA",
                    "error": err_no_market_data(lang),
                    "agent": self.name
                }

            if len(ohlcv) == 0:
                self.log(f"Empty OHLCV for {symbol} (exchange timeout or no candles)", "WARNING")
                return {
                    "success": False,
                    "failure_code": "EXCHANGE_EMPTY",
                    "error": err_no_market_data(lang),
                    "agent": self.name
                }

            if len(ohlcv) < 30:
                self.log(
                    f"Insufficient OHLCV data for {symbol} (got {len(ohlcv)} items)",
                    "WARNING",
                )
                return {
                    "success": False,
                    "failure_code": "INSUFFICIENT_HISTORY",
                    "error": err_insufficient_history(lang),
                    "agent": self.name
                }
            
            # Get current price
            current_price = 0
            try:
                self.log(f"Fetching current price for {symbol}", "INFO")
                ticker = await asyncio.wait_for(
                    exchange_service.fetch_ticker(symbol, exchange),
                    timeout=10.0
                )
                if ticker and isinstance(ticker, dict):
                    current_price = ticker.get("price", 0) or 0
            except asyncio.TimeoutError:
                self.log(f"Timeout fetching ticker for {symbol}", "WARNING")
            except Exception as e:
                self.log(f"Error fetching ticker: {str(e)}", "WARNING")
            
            # Make predictions based on model choice
            if model == "prophet":
                if prediction_service.is_prophet_available():
                    result = await prediction_service.predict_prophet(ohlcv, periods, lang=lang)
                else:
                    # Fallback if Prophet not available
                    result = await prediction_service.predict_fallback(ohlcv, periods, lang=lang)
            elif model == "lightgbm":
                if prediction_service.is_lightgbm_available():
                    result = await prediction_service.predict_lightgbm(ohlcv, periods, lang=lang)
                else:
                    # Fallback if LightGBM not available
                    result = await prediction_service.predict_fallback(ohlcv, periods, lang=lang)
            else:  # ensemble
                result = await prediction_service.predict_ensemble(ohlcv, periods, lang=lang)
            
            if not result.get("success"):
                return {
                    "success": False,
                    "failure_code": "PREDICTION_FAILED",
                    "error": result.get("error", "Prediction failed"),
                    "agent": self.name
                }
            
            # Add symbol and exchange info
            result["symbol"] = symbol
            result["exchange"] = exchange
            result["timeframe"] = timeframe
            result["current_price"] = current_price
            result["agent"] = self.name
            
            # Calculate price change predictions
            if result.get("predictions"):
                first_pred = result["predictions"][0].get("price", current_price)
                last_pred = result["predictions"][-1].get("price", current_price)
                
                result["predicted_change"] = {
                    "absolute": float(last_pred - current_price),
                    "percentage": float((last_pred - current_price) / current_price * 100) if current_price > 0 else 0,
                    "first_period_price": float(first_pred),
                    "last_period_price": float(last_pred)
                }
            
            # Generate XAI explanation
            result["explanation"] = self._generate_explanation(
                result,
                current_price,
                model,
                periods,
                timeframe,
                lang,
            )
            
            self.log(f"Prediction completed for {symbol}", "INFO")
            return result
            
        except Exception as e:
            error_msg = str(e)
            self.log(f"Error in PredictionAgent: {error_msg}", "ERROR")
            self.log(f"Traceback: {traceback.format_exc()}", "ERROR")
            return {
                "success": False,
                "failure_code": "PREDICTION_FAILED",
                "error": err_prediction_failed(lang, error_msg),
                "agent": self.name
            }
    
    def _generate_explanation(
        self,
        result: Dict[str, Any],
        current_price: float,
        model: str,
        periods: int,
        timeframe: str,
        lang: str = "en",
    ) -> str:
        """
        Generate explainable AI (XAI) explanation for the prediction
        """
        try:
            metrics = result.get("metrics", {})
            confidence_score = float(result.get("confidence_score", 0))
            mape = float(metrics.get("mape", 0))
            directional_accuracy = float(metrics.get("directional_accuracy", 0))
            effective_model = str(result.get("model") or model)
            if effective_model not in ("prophet", "lightgbm", "ensemble", "fallback"):
                effective_model = "ensemble"

            change_pct = 0.0
            direction_up = True
            if result.get("predicted_change"):
                change_pct = float(result["predicted_change"].get("percentage", 0))
                direction_up = change_pct >= 0

            return xai_explanation(
                lang,
                model=effective_model,
                periods=periods,
                timeframe=timeframe,
                confidence_score=confidence_score,
                directional_accuracy=directional_accuracy,
                mape=mape,
                current_price=float(current_price),
                change_pct=change_pct,
                direction_up=direction_up,
            )
            
        except Exception as e:
            self.log(f"Error generating explanation: {e}", "WARNING")
            return xai_explanation_failed(lang)





