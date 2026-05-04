"""
Ablation Study Service - For thesis comparison of different model configurations
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.prediction_history import PredictionHistory
import logging

logger = logging.getLogger(__name__)


class AblationStudyService:
    """Service for ablation study comparisons"""
    
    @staticmethod
    async def compare_models(
        db: Session,
        symbol: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Compare different model configurations for ablation study
        
        Returns:
            {
                "technical_only": {...},
                "technical_sentiment": {...},
                "multi_agent": {...},
                "comparison": {...}
            }
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Get predictions for each model type
        technical_only = db.query(PredictionHistory).filter(
            PredictionHistory.symbol == symbol,
            PredictionHistory.model_type == "prophet",  # Technical only
            PredictionHistory.prediction_date >= cutoff_date,
            PredictionHistory.actual_price.isnot(None)
        ).all()
        
        technical_sentiment = db.query(PredictionHistory).filter(
            PredictionHistory.symbol == symbol,
            PredictionHistory.model_type == "lightgbm",  # Technical + features
            PredictionHistory.prediction_date >= cutoff_date,
            PredictionHistory.actual_price.isnot(None)
        ).all()
        
        multi_agent = db.query(PredictionHistory).filter(
            PredictionHistory.symbol == symbol,
            PredictionHistory.model_type == "ensemble",  # Multi-agent
            PredictionHistory.prediction_date >= cutoff_date,
            PredictionHistory.actual_price.isnot(None)
        ).all()
        
        # Calculate metrics for each
        def calculate_metrics(predictions: List[PredictionHistory]) -> Dict[str, Any]:
            if not predictions:
                return {
                    "count": 0,
                    "accuracy": 0.0,
                    "mae": 0.0,
                    "mape": 0.0
                }
            
            correct = sum(1 for p in predictions if p.was_correct)
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
                "count": len(predictions),
                "accuracy": correct / len(predictions) if predictions else 0.0,
                "mae": mae,
                "mape": mape
            }
        
        tech_metrics = calculate_metrics(technical_only)
        tech_sent_metrics = calculate_metrics(technical_sentiment)
        multi_metrics = calculate_metrics(multi_agent)
        
        # Comparison
        comparison = {
            "best_accuracy": max(
                ("technical_only", tech_metrics["accuracy"]),
                ("technical_sentiment", tech_sent_metrics["accuracy"]),
                ("multi_agent", multi_metrics["accuracy"]),
                key=lambda x: x[1]
            )[0],
            "best_mape": min(
                ("technical_only", tech_metrics["mape"]),
                ("technical_sentiment", tech_sent_metrics["mape"]),
                ("multi_agent", multi_metrics["mape"]),
                key=lambda x: x[1] if x[1] > 0 else float('inf')
            )[0],
            "improvement_technical_to_sentiment": (
                (tech_sent_metrics["accuracy"] - tech_metrics["accuracy"]) / tech_metrics["accuracy"] * 100
                if tech_metrics["accuracy"] > 0 else 0
            ),
            "improvement_sentiment_to_multi": (
                (multi_metrics["accuracy"] - tech_sent_metrics["accuracy"]) / tech_sent_metrics["accuracy"] * 100
                if tech_sent_metrics["accuracy"] > 0 else 0
            )
        }
        
        return {
            "symbol": symbol,
            "period_days": days,
            "technical_only": {
                **tech_metrics,
                "description": "Sadece Teknik Analiz (Prophet - Zaman Serisi)"
            },
            "technical_sentiment": {
                **tech_sent_metrics,
                "description": "Teknik Analiz + Sentiment (LightGBM - Özellik Mühendisliği)"
            },
            "multi_agent": {
                **multi_metrics,
                "description": "Multi-Agent Sistem (Ensemble - Tüm Ajanlar)"
            },
            "comparison": comparison,
            "conclusion": _generate_conclusion(comparison, tech_metrics, tech_sent_metrics, multi_metrics)
        }
    
    @staticmethod
    async def get_study_summary(
        db: Session,
        symbols: List[str],
        days: int = 30
    ) -> Dict[str, Any]:
        """Get ablation study summary for multiple symbols"""
        results = []
        
        for symbol in symbols:
            try:
                result = await AblationStudyService.compare_models(db, symbol, days)
                results.append(result)
            except Exception as e:
                logger.error(f"Error comparing models for {symbol}: {e}")
        
        # Aggregate results
        if not results:
            return {
                "success": False,
                "error": "No data available for comparison"
            }
        
        avg_tech_acc = sum(r["technical_only"]["accuracy"] for r in results) / len(results)
        avg_tech_sent_acc = sum(r["technical_sentiment"]["accuracy"] for r in results) / len(results)
        avg_multi_acc = sum(r["multi_agent"]["accuracy"] for r in results) / len(results)
        
        return {
            "success": True,
            "symbols_analyzed": len(results),
            "period_days": days,
            "average_accuracy": {
                "technical_only": avg_tech_acc,
                "technical_sentiment": avg_tech_sent_acc,
                "multi_agent": avg_multi_acc
            },
            "improvement": {
                "sentiment_adds": (avg_tech_sent_acc - avg_tech_acc) * 100,
                "multi_agent_adds": (avg_multi_acc - avg_tech_sent_acc) * 100,
                "total_improvement": (avg_multi_acc - avg_tech_acc) * 100
            },
            "detailed_results": results
        }


def _generate_conclusion(
    comparison: Dict[str, Any],
    tech_metrics: Dict[str, Any],
    tech_sent_metrics: Dict[str, Any],
    multi_metrics: Dict[str, Any]
) -> str:
    """Generate conclusion text for ablation study"""
    best = comparison["best_accuracy"]
    
    if best == "multi_agent":
        improvement = comparison["improvement_sentiment_to_multi"]
        return (
            f"Multi-Agent sistem en yüksek başarı oranını gösterdi (%{multi_metrics['accuracy']*100:.1f}). "
            f"Teknik+Sentiment yaklaşımına göre %{improvement:.1f} iyileşme sağladı. "
            f"Bu, ajanlar arası koordinasyonun ve konsensüs mekanizmasının değerini kanıtlamaktadır."
        )
    elif best == "technical_sentiment":
        improvement = comparison["improvement_technical_to_sentiment"]
        return (
            f"Teknik+Sentiment yaklaşımı en yüksek başarı oranını gösterdi (%{tech_sent_metrics['accuracy']*100:.1f}). "
            f"Sadece teknik analize göre %{improvement:.1f} iyileşme sağladı. "
            f"Sentiment verilerinin eklenmesi model performansını artırmıştır."
        )
    else:
        return (
            f"Teknik analiz yaklaşımı %{tech_metrics['accuracy']*100:.1f} başarı oranı gösterdi. "
            f"Sentiment ve multi-agent yaklaşımları daha fazla veri gerektirebilir."
        )


# Global instance
ablation_study_service = AblationStudyService()












