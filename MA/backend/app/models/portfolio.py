"""
Portfolio and trading models
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.database import Base


class TransactionType(str, enum.Enum):
    """Transaction type enum"""
    BUY = "buy"
    SELL = "sell"
    LIMIT_BUY = "limit_buy"
    LIMIT_SELL = "limit_sell"


class OrderStatus(str, enum.Enum):
    """Order status enum"""
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    PARTIALLY_FILLED = "partially_filled"


class Portfolio(Base):
    """Portfolio model for simulation"""
    __tablename__ = "portfolios"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False, default="Default Portfolio")
    initial_balance = Column(Float, nullable=False, default=10000.0)
    current_balance = Column(Float, nullable=False, default=10000.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    transactions = relationship("Transaction", back_populates="portfolio")
    positions = relationship("Position", back_populates="portfolio")
    orders = relationship("Order", back_populates="portfolio")
    
    def __repr__(self):
        return f"<Portfolio(name='{self.name}', balance={self.current_balance})>"


class Transaction(Base):
    """Transaction model for paper trading"""
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)
    symbol = Column(String, nullable=False, index=True)  # e.g., "BTC/USDT"
    transaction_type = Column(SQLEnum(TransactionType), nullable=False)
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    total = Column(Float, nullable=False)  # quantity * price
    exchange = Column(String, nullable=False, default="binance")
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    portfolio = relationship("Portfolio", back_populates="transactions")
    
    def __repr__(self):
        return f"<Transaction({self.transaction_type.value} {self.quantity} {self.symbol} @ {self.price})>"


class Position(Base):
    """Current position in a portfolio"""
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)
    symbol = Column(String, nullable=False, index=True)
    quantity = Column(Float, nullable=False, default=0.0)
    avg_buy_price = Column(Float, nullable=True)
    exchange = Column(String, nullable=False, default="binance")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    portfolio = relationship("Portfolio", back_populates="positions")
    
    def __repr__(self):
        return f"<Position(symbol='{self.symbol}', quantity={self.quantity})>"


class Order(Base):
    """Pending limit orders"""
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)
    symbol = Column(String, nullable=False, index=True)
    order_type = Column(SQLEnum(TransactionType), nullable=False)  # LIMIT_BUY or LIMIT_SELL
    quantity = Column(Float, nullable=False)
    limit_price = Column(Float, nullable=False)  # Price at which order should execute
    status = Column(SQLEnum(OrderStatus), nullable=False, default=OrderStatus.PENDING)
    filled_quantity = Column(Float, nullable=False, default=0.0)
    exchange = Column(String, nullable=False, default="binance")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    filled_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    portfolio = relationship("Portfolio", back_populates="orders")
    
    def __repr__(self):
        return f"<Order({self.order_type.value} {self.quantity} {self.symbol} @ {self.limit_price})>"

