"""
Data Agent - Fetches real-time market data
"""
from typing import Dict, Any, List
from app.agents.base_agent import BaseAgent
from app.services.exchange_service import exchange_service


class DataAgent(BaseAgent):
    """Agent responsible for fetching and normalizing market data"""
    
    def __init__(self):
        super().__init__("DataAgent")
    
    async def execute(
        self, 
        symbol: str = None,
        symbols: List[str] = None,
        exchange: str = "binance",
        **kwargs
    ) -> Dict[str, Any]:
        """Fetch market data"""
        import traceback
        import asyncio
        
        try:
            if symbol:
                self.log(f"Fetching ticker for {symbol} on {exchange}", "INFO")
                try:
                    ticker = await asyncio.wait_for(
                        exchange_service.fetch_ticker(symbol, exchange),
                        timeout=10.0
                    )
                    
                    # Validate ticker data
                    if ticker is None:
                        self.log(f"Ticker data is None for {symbol}", "WARNING")
                        return {
                            "success": False,
                            "error": "Şu an piyasa verisine ulaşılamıyor. Lütfen daha sonra tekrar deneyin.",
                            "agent": self.name
                        }
                    
                    if not isinstance(ticker, dict):
                        self.log(f"Invalid ticker data type for {symbol}", "WARNING")
                        return {
                            "success": False,
                            "error": "Şu an piyasa verisine ulaşılamıyor. Lütfen daha sonra tekrar deneyin.",
                            "agent": self.name
                        }
                    
                    self.log(f"Ticker data fetched successfully for {symbol}", "INFO")
                    return {
                        "success": True,
                        "data": ticker,
                        "agent": self.name
                    }
                except asyncio.TimeoutError:
                    self.log(f"Timeout fetching ticker for {symbol}", "ERROR")
                    return {
                        "success": False,
                        "error": "Veri çekme zaman aşımına uğradı. Lütfen tekrar deneyin.",
                        "agent": self.name
                    }
            elif symbols:
                self.log(f"Fetching multiple tickers for {len(symbols)} symbols", "INFO")
                try:
                    tickers = await asyncio.wait_for(
                        exchange_service.fetch_multiple_tickers(symbols, exchange),
                        timeout=15.0
                    )
                    
                    # Validate tickers data
                    if tickers is None:
                        self.log("Tickers data is None", "WARNING")
                        return {
                            "success": False,
                            "error": "Şu an piyasa verisine ulaşılamıyor. Lütfen daha sonra tekrar deneyin.",
                            "agent": self.name
                        }
                    
                    return {
                        "success": True,
                        "data": tickers,
                        "agent": self.name
                    }
                except asyncio.TimeoutError:
                    self.log("Timeout fetching multiple tickers", "ERROR")
                    return {
                        "success": False,
                        "error": "Veri çekme zaman aşımına uğradı. Lütfen tekrar deneyin.",
                        "agent": self.name
                    }
            
            self.log("No symbol or symbols provided", "ERROR")
            return {
                "success": False,
                "error": "Symbol veya symbols parametresi gereklidir",
                "agent": self.name
            }
        except Exception as e:
            error_msg = str(e)
            self.log(f"Error in DataAgent: {error_msg}", "ERROR")
            self.log(f"Traceback: {traceback.format_exc()}", "ERROR")
            return {
                "success": False,
                "error": f"Veri çekme hatası: {error_msg}",
                "agent": self.name
            }

