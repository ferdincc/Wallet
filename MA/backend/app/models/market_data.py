"""
Market data models
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Index
from sqlalchemy.sql import func
from app.database import Base


class MarketData(Base):
    """Real-time market data snapshot"""
    __tablename__ = "market_data"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)  # e.g., "BTC/USDT"
    exchange = Column(String, nullable=False, index=True)  # e.g., "binance"
    price = Column(Float, nullable=False)
    volume_24h = Column(Float, nullable=True)
    change_24h = Column(Float, nullable=True)  # percentage change
    high_24h = Column(Float, nullable=True)
    low_24h = Column(Float, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Index for efficient queries
    __table_args__ = (
        Index('idx_symbol_exchange_timestamp', 'symbol', 'exchange', 'timestamp'),
    )
    
    def __repr__(self):
        return f"<MarketData(symbol='{self.symbol}', price={self.price})>"


class PriceHistory(Base):
    __tablename__ = "price_history"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    exchange = Column(String, nullable=False, index=True)
    timeframe = Column(String, nullable=False, default="1h") 
    open_price = Column(Float, nullable=False)
    high_price = Column(Float, nullable=False)
    low_price = Column(Float, nullable=False)
    close_price = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    
   
    __table_args__ = (
        Index('idx_symbol_exchange_timeframe_timestamp', 'symbol', 'exchange', 'timeframe', 'timestamp'),
    )
    
    def __repr__(self):
        return f"<PriceHistory(symbol='{self.symbol}', close={self.close_price}, timestamp={self.timestamp})>"

