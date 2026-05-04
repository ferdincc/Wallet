"""
Analysis Agent - Performs technical analysis using LLM and indicators
"""
from typing import Dict, Any, Optional
from app.agents.base_agent import BaseAgent
from app.services.exchange_service import exchange_service
from app.services.technical_analysis import technical_analysis
from app.agents.llm_service import llm_service


class AnalysisAgent(BaseAgent):
    """Agent responsible for technical and sentiment analysis"""
    
    def __init__(self):
        super().__init__("AnalysisAgent")
    
    async def execute(
        self, 
        symbol: str,
        exchange: str = "binance",
        timeframe: str = "1h",
        include_sentiment: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Perform comprehensive analysis"""
        import asyncio
        import traceback
        
        if not symbol:
            self.log("Symbol is required", "ERROR")
            return {
                "success": False,
                "error": "Symbol parametresi gereklidir",
                "agent": self.name
            }
        
        try:
            # Fetch OHLCV data with timeout
            self.log(f"Fetching OHLCV data for {symbol} on {exchange}", "INFO")
            ohlcv = await asyncio.wait_for(
                exchange_service.fetch_ohlcv(symbol, timeframe, limit=100, exchange_name=exchange),
                timeout=15.0
            )
            
            # Validate OHLCV data
            if ohlcv is None:
                self.log(f"OHLCV data is None for {symbol}", "WARNING")
                return {
                    "success": False,
                    "error": "Şu an piyasa verisine ulaşılamıyor. Lütfen daha sonra tekrar deneyin.",
                    "agent": self.name
                }
            
            if not isinstance(ohlcv, list) or len(ohlcv) == 0:
                self.log(f"No OHLCV data for {symbol} (empty list)", "WARNING")
                return {
                    "success": False,
                    "error": "Şu an piyasa verisine ulaşılamıyor. Lütfen daha sonra tekrar deneyin.",
                    "agent": self.name
                }
            
            # Calculate technical indicators
            try:
                self.log(f"Calculating technical indicators for {symbol}", "INFO")
                ta_results = technical_analysis.analyze_ohlcv(ohlcv)
                if not ta_results:
                    self.log(f"Technical analysis returned empty for {symbol}", "WARNING")
                    ta_results = {}
            except Exception as e:
                self.log(f"Error calculating technical indicators: {str(e)}", "ERROR")
                ta_results = {}
            
            # Fetch current ticker with timeout
            self.log(f"Fetching ticker data for {symbol}", "INFO")
            ticker = None
            try:
                ticker = await asyncio.wait_for(
                    exchange_service.fetch_ticker(symbol, exchange),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                self.log(f"Ticker fetch timeout for {symbol}", "WARNING")
            except Exception as e:
                self.log(f"Error fetching ticker: {str(e)}", "WARNING")
            
            # Validate ticker data
            if ticker is None:
                self.log(f"Ticker data is None for {symbol}", "WARNING")
                ticker = {
                    "symbol": symbol,
                    "price": None,
                    "change_24h": None,
                    "volume_24h": None
                }
            
            result = {
                "success": True,
                "symbol": symbol,
                "exchange": exchange,
                "technical_analysis": ta_results,
                "current_data": ticker,
                "agent": self.name
            }
            
            # Add LLM-based analysis if requested (with timeout)
            if include_sentiment and llm_service.is_available():
                try:
                    self.log(f"Requesting LLM analysis for {symbol}", "INFO")
                    llm_analysis = await llm_service.analyze_market(
                        symbol=symbol,
                        technical_data=ta_results,
                        current_price=ticker.get('price') if ticker else None
                    )
                    if llm_analysis:
                        result["llm_analysis"] = llm_analysis
                except asyncio.TimeoutError:
                    self.log("LLM analysis timeout", "WARNING")
                except Exception as e:
                    self.log(f"LLM analysis error: {e}", "WARNING")
            
            self.log(f"Analysis completed successfully for {symbol}", "INFO")
            return result
            
        except asyncio.TimeoutError:
            self.log(f"Timeout in AnalysisAgent for {symbol}", "ERROR")
            return {
                "success": False,
                "error": "Analiz zaman aşımına uğradı. Lütfen tekrar deneyin.",
                "agent": self.name
            }
        except Exception as e:
            error_msg = str(e)
            self.log(f"Error in AnalysisAgent: {error_msg}", "ERROR")
            self.log(f"Traceback: {traceback.format_exc()}", "ERROR")
            return {
                "success": False,
                "error": f"Analiz hatası: {error_msg}",
                "agent": self.name
            }

