"""
Prediction History Model - For backtesting and learning
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class PredictionHistory(Base):
    """Store prediction history for backtesting"""
    __tablename__ = "prediction_history"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    model_type = Column(String, nullable=False)  # prophet, lightgbm, ensemble, fallback
    predicted_price = Column(Float, nullable=False)
    predicted_change = Column(Float, nullable=False)  # percentage
    actual_price = Column(Float, nullable=True)  # Filled after prediction period
    actual_change = Column(Float, nullable=True)  # Filled after prediction period
    confidence_score = Column(Float, nullable=False)
    prediction_date = Column(DateTime(timezone=True), server_default=func.now())
    actual_date = Column(DateTime(timezone=True), nullable=True)  # When actual price was recorded
    periods = Column(Integer, nullable=False, default=7)  # Days ahead predicted
    was_correct = Column(Boolean, nullable=True)  # True if direction was correct
    error_analysis = Column(Text, nullable=True)  # LLM-generated error analysis
    features_used = Column(Text, nullable=True)  # JSON string of features and importance
    
    def __repr__(self):
        return f"<PredictionHistory(symbol='{self.symbol}', predicted={self.predicted_change:+.2f}%, actual={self.actual_change or 'N/A'})>"


class BacktestResult(Base):
    """Store backtest results"""
    __tablename__ = "backtest_results"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    model_type = Column(String, nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    total_predictions = Column(Integer, nullable=False)
    correct_predictions = Column(Integer, nullable=False)
    accuracy = Column(Float, nullable=False)  # correct_predictions / total_predictions
    mae = Column(Float, nullable=True)  # Mean Absolute Error
    mape = Column(Float, nullable=True)  # Mean Absolute Percentage Error
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<BacktestResult(symbol='{self.symbol}', accuracy={self.accuracy*100:.1f}%)>"












