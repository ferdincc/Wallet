"""
Backtesting Service - Evaluates prediction accuracy over time
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.prediction_history import PredictionHistory, BacktestResult
from app.agents.llm_service import llm_service
import logging

logger = logging.getLogger(__name__)


class BacktestService:
    """Service for backtesting predictions"""
    
    @staticmethod
    async def record_prediction(
        db: Session,
        symbol: str,
        model_type: str,
        predicted_price: float,
        predicted_change: float,
        confidence_score: float,
        periods: int = 7,
        features_used: Optional[Dict[str, float]] = None
    ) -> PredictionHistory:
        """Record a new prediction"""
        prediction = PredictionHistory(
            symbol=symbol,
            model_type=model_type,
            predicted_price=predicted_price,
            predicted_change=predicted_change,
            confidence_score=confidence_score,
            periods=periods,
            features_used=str(features_used) if features_used else None
        )
        
        db.add(prediction)
        db.commit()
        db.refresh(prediction)
        
        return prediction
    
    @staticmethod
    async def update_prediction_with_actual(
        db: Session,
        prediction_id: int,
        actual_price: float
    ) -> PredictionHistory:
        """Update prediction with actual price"""
        prediction = db.query(PredictionHistory).filter(
            PredictionHistory.id == prediction_id
        ).first()
        
        if not prediction:
            raise ValueError("Prediction not found")
        
        # Calculate actual change
        base_price = prediction.predicted_price / (1 + prediction.predicted_change / 100)
        actual_change = ((actual_price - base_price) / base_price) * 100
        
        prediction.actual_price = actual_price
        prediction.actual_change = actual_change
        prediction.actual_date = datetime.utcnow()
        
        # Check if direction was correct
        if prediction.predicted_change > 0 and actual_change > 0:
            prediction.was_correct = True
        elif prediction.predicted_change < 0 and actual_change < 0:
            prediction.was_correct = True
        elif prediction.predicted_change == 0 and abs(actual_change) < 1:
            prediction.was_correct = True
        else:
            prediction.was_correct = False
        
        db.commit()
        db.refresh(prediction)
        
        # Generate error analysis if prediction was wrong
        if not prediction.was_correct and llm_service.is_available():
            try:
                error_analysis = await BacktestService._analyze_prediction_error(
                    prediction
                )
                prediction.error_analysis = error_analysis
                db.commit()
            except Exception as e:
                logger.error(f"Error generating error analysis: {e}")
        
        return prediction
    
    @staticmethod
    async def _analyze_prediction_error(prediction: PredictionHistory) -> str:
        """Use LLM to analyze why prediction was wrong"""
        prompt = f"""Bir kripto para fiyat tahmini yanlış çıktı. Nedenini analiz et:

Sembol: {prediction.symbol}
Model: {prediction.model_type}
Tahmin Edilen Değişim: {prediction.predicted_change:+.2f}%
Gerçek Değişim: {prediction.actual_change:+.2f}%
Tahmin Tarihi: {prediction.prediction_date}
Gerçek Tarih: {prediction.actual_date}

Bu hatanın olası nedenleri:
1. Beklenmedik bir haber mi oldu?
2. Teknik bir kırılım mı yaşandı?
3. Modelin eksik olduğu bir faktör mü var?

Kısa ve öz bir analiz yap (2-3 cümle). Türkçe yanıt ver."""
        
        try:
            response = await llm_service.chat(prompt, [])
            return response.get("response", "Analiz yapılamadı")
        except Exception as e:
            logger.error(f"Error in LLM error analysis: {e}")
            return "Analiz yapılamadı"
    
    @staticmethod
    async def calculate_backtest_stats(
        db: Session,
        symbol: Optional[str] = None,
        model_type: Optional[str] = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """Calculate backtest statistics"""
        query = db.query(PredictionHistory).filter(
            PredictionHistory.actual_price.isnot(None),
            PredictionHistory.prediction_date >= datetime.utcnow() - timedelta(days=days)
        )
        
        if symbol:
            query = query.filter(PredictionHistory.symbol == symbol)
        if model_type:
            query = query.filter(PredictionHistory.model_type == model_type)
        
        predictions = query.all()
        
        if not predictions:
            return {
                "total_predictions": 0,
                "accuracy": 0.0,
                "mae": 0.0,
                "mape": 0.0
            }
        
        correct = sum(1 for p in predictions if p.was_correct)
        total = len(predictions)
        
        # Calculate MAE and MAPE
        errors = []
        percentage_errors = []
        
        for pred in predictions:
            if pred.actual_price and pred.predicted_price:
                error = abs(pred.actual_price - pred.predicted_price)
                errors.append(error)
                
                base_price = pred.predicted_price / (1 + pred.predicted_change / 100)
                if base_price > 0:
                    pct_error = abs((pred.actual_price - base_price) / base_price) * 100
                    percentage_errors.append(pct_error)
        
        mae = sum(errors) / len(errors) if errors else 0.0
        mape = sum(percentage_errors) / len(percentage_errors) if percentage_errors else 0.0
        
        return {
            "total_predictions": total,
            "correct_predictions": correct,
            "accuracy": correct / total if total > 0 else 0.0,
            "mae": mae,
            "mape": mape,
            "model_type": model_type or "all",
            "symbol": symbol or "all",
            "period": f"last_{days}_days"
        }
    
    @staticmethod
    async def get_recent_predictions(
        db: Session,
        symbol: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get recent predictions with results"""
        query = db.query(PredictionHistory).order_by(
            PredictionHistory.prediction_date.desc()
        )
        
        if symbol:
            query = query.filter(PredictionHistory.symbol == symbol)
        
        predictions = query.limit(limit).all()
        
        return [
            {
                "id": p.id,
                "symbol": p.symbol,
                "model_type": p.model_type,
                "predicted_change": p.predicted_change,
                "actual_change": p.actual_change,
                "was_correct": p.was_correct,
                "confidence_score": p.confidence_score,
                "prediction_date": p.prediction_date.isoformat() if p.prediction_date else None,
                "actual_date": p.actual_date.isoformat() if p.actual_date else None,
                "error_analysis": p.error_analysis
            }
            for p in predictions
        ]


# Global instance
backtest_service = BacktestService()












