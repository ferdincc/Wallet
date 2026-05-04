"""
Technical analysis service for calculating indicators
"""
import pandas as pd
from typing import List, Dict, Any, Optional


class TechnicalAnalysis:
    """Technical analysis calculations"""
    
    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
        """Calculate Relative Strength Index (RSI)"""
        if len(prices) < period + 1:
            return None
        
        df = pd.Series(prices)
        delta = df.diff()
        
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return float(rsi.iloc[-1]) if not rsi.empty else None
    
    @staticmethod
    def calculate_macd(
        prices: List[float], 
        fast: int = 12, 
        slow: int = 26, 
        signal: int = 9
    ) -> Dict[str, Optional[float]]:
        """Calculate MACD (Moving Average Convergence Divergence)"""
        if len(prices) < slow:
            return {'macd': None, 'signal': None, 'histogram': None}
        
        df = pd.Series(prices)
        
        ema_fast = df.ewm(span=fast, adjust=False).mean()
        ema_slow = df.ewm(span=slow, adjust=False).mean()
        
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return {
            'macd': float(macd_line.iloc[-1]) if not macd_line.empty else None,
            'signal': float(signal_line.iloc[-1]) if not signal_line.empty else None,
            'histogram': float(histogram.iloc[-1]) if not histogram.empty else None
        }
    
    @staticmethod
    def calculate_bollinger_bands(
        prices: List[float], 
        period: int = 20, 
        std_dev: int = 2
    ) -> Dict[str, Optional[float]]:
        """Calculate Bollinger Bands"""
        if len(prices) < period:
            return {'upper': None, 'middle': None, 'lower': None}
        
        df = pd.Series(prices)
        middle_band = df.rolling(window=period).mean()
        std = df.rolling(window=period).std()
        
        upper_band = middle_band + (std * std_dev)
        lower_band = middle_band - (std * std_dev)
        
        return {
            'upper': float(upper_band.iloc[-1]) if not upper_band.empty else None,
            'middle': float(middle_band.iloc[-1]) if not middle_band.empty else None,
            'lower': float(lower_band.iloc[-1]) if not lower_band.empty else None
        }
    
    @staticmethod
    def calculate_sma(prices: List[float], period: int) -> Optional[float]:
        """Calculate Simple Moving Average"""
        if len(prices) < period:
            return None
        
        df = pd.Series(prices)
        sma = df.rolling(window=period).mean()
        return float(sma.iloc[-1]) if not sma.empty else None
    
    @staticmethod
    def calculate_ema(prices: List[float], period: int) -> Optional[float]:
        """Calculate Exponential Moving Average"""
        if len(prices) < period:
            return None
        
        df = pd.Series(prices)
        ema = df.ewm(span=period, adjust=False).mean()
        return float(ema.iloc[-1]) if not ema.empty else None
    
    @staticmethod
    def analyze_ohlcv(ohlcv_data: List[List[float]]) -> Dict[str, Any]:
        """Analyze OHLCV data and return technical indicators"""
        if not ohlcv_data or len(ohlcv_data) < 26:
            return {}
        
        # Extract close prices (index 4)
        close_prices = [candle[4] for candle in ohlcv_data]
        
        # Calculate indicators
        rsi = TechnicalAnalysis.calculate_rsi(close_prices)
        macd = TechnicalAnalysis.calculate_macd(close_prices)
        bollinger = TechnicalAnalysis.calculate_bollinger_bands(close_prices)
        sma_20 = TechnicalAnalysis.calculate_sma(close_prices, 20)
        sma_50 = TechnicalAnalysis.calculate_sma(close_prices, 50)
        ema_12 = TechnicalAnalysis.calculate_ema(close_prices, 12)
        
        current_price = close_prices[-1]
        
        # Generate signals
        signals = []
        if rsi:
            if rsi > 70:
                signals.append("RSI Overbought")
            elif rsi < 30:
                signals.append("RSI Oversold")
        
        if macd['macd'] and macd['signal']:
            if macd['macd'] > macd['signal']:
                signals.append("MACD Bullish")
            else:
                signals.append("MACD Bearish")
        
        if bollinger['upper'] and bollinger['lower']:
            if current_price > bollinger['upper']:
                signals.append("Price Above Upper Bollinger Band")
            elif current_price < bollinger['lower']:
                signals.append("Price Below Lower Bollinger Band")
        
        return {
            'current_price': current_price,
            'rsi': rsi,
            'macd': macd,
            'bollinger_bands': bollinger,
            'sma_20': sma_20,
            'sma_50': sma_50,
            'ema_12': ema_12,
            'signals': signals,
            'price_change_24h': (
                ((close_prices[-1] - close_prices[0]) / close_prices[0] * 100)
                if len(close_prices) >= 24 else None
            )
        }


technical_analysis = TechnicalAnalysis()

