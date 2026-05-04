"""
Exchange API credentials model for real trading
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.database import Base


class TradingMode(str, enum.Enum):
    """Trading mode enum"""
    PAPER_TRADING = "paper_trading"  # Simülasyon (varsayılan)
    REAL_TRADING = "real_trading"  # Gerçek işlem (API key ile)
    READ_ONLY = "read_only"  # Sadece okuma (API key ile, işlem yapmaz)


class ExchangeCredentials(Base):
    """Exchange API credentials for authenticated access"""
    __tablename__ = "exchange_credentials"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    exchange = Column(String, nullable=False, index=True)  # binance, coinbasepro, kraken
    api_key = Column(String, nullable=False)  # Encrypted in production
    api_secret = Column(String, nullable=False)  # Encrypted in production
    passphrase = Column(String, nullable=True)  # For Coinbase Pro
    trading_mode = Column(SQLEnum(TradingMode), nullable=False, default=TradingMode.READ_ONLY)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", backref="exchange_credentials")
    
    def __repr__(self):
        return f"<ExchangeCredentials(exchange='{self.exchange}', mode='{self.trading_mode.value}')>"












