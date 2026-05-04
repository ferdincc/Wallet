"""
Performance Metrics Service
Calculates Sharpe Ratio, Max Drawdown, Win Rate, etc.
"""
from typing import Dict, Any, List, Optional
import logging
import numpy as np
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)


class PerformanceService:
    """Service for calculating financial performance metrics"""
    
    def calculate_sharpe_ratio(
        self,
        returns: List[float],
        risk_free_rate: float = 0.02  # 2% annual risk-free rate
    ) -> float:
        """
        Calculate Sharpe Ratio
        
        Args:
            returns: List of returns (percentage changes)
            risk_free_rate: Annual risk-free rate (default 2%)
        
        Returns:
            Sharpe ratio
        """
        if not returns or len(returns) < 2:
            return 0.0
        
        returns_array = np.array(returns)
        
        # Annualize if needed (assuming daily returns)
        # For hourly data, adjust accordingly
        annualized_return = np.mean(returns_array) * 365  # Daily to annual
        annualized_std = np.std(returns_array) * np.sqrt(365)  # Daily to annual
        
        if annualized_std == 0:
            return 0.0
        
        sharpe = (annualized_return - risk_free_rate) / annualized_std
        return float(sharpe)
    
    def calculate_max_drawdown(
        self,
        values: List[float]
    ) -> Dict[str, float]:
        """
        Calculate Maximum Drawdown
        
        Args:
            values: List of portfolio/asset values over time
        
        Returns:
            Dictionary with max drawdown, peak, and trough
        """
        if not values or len(values) < 2:
            return {
                "max_drawdown": 0.0,
                "max_drawdown_percent": 0.0,
                "peak": values[0] if values else 0.0,
                "trough": values[0] if values else 0.0
            }
        
        values_array = np.array(values)
        peak = np.maximum.accumulate(values_array)
        drawdown = (values_array - peak) / peak
        max_drawdown = np.min(drawdown)
        max_drawdown_idx = np.argmin(drawdown)
        
        return {
            "max_drawdown": float(max_drawdown),
            "max_drawdown_percent": float(max_drawdown * 100),
            "peak": float(peak[max_drawdown_idx]),
            "trough": float(values_array[max_drawdown_idx]),
            "peak_index": int(np.argmax(peak[:max_drawdown_idx + 1])),
            "trough_index": int(max_drawdown_idx)
        }
    
    def calculate_win_rate(
        self,
        returns: List[float]
    ) -> Dict[str, float]:
        """
        Calculate Win Rate
        
        Args:
            returns: List of returns
        
        Returns:
            Dictionary with win rate and statistics
        """
        if not returns:
            return {
                "win_rate": 0.0,
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0
            }
        
        returns_array = np.array(returns)
        winning_trades = np.sum(returns_array > 0)
        losing_trades = np.sum(returns_array < 0)
        total_trades = len(returns_array)
        
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        return {
            "win_rate": float(win_rate),
            "total_trades": int(total_trades),
            "winning_trades": int(winning_trades),
            "losing_trades": int(losing_trades),
            "average_win": float(np.mean(returns_array[returns_array > 0])) if winning_trades > 0 else 0.0,
            "average_loss": float(np.mean(returns_array[returns_array < 0])) if losing_trades > 0 else 0.0
        }
    
    def calculate_directional_accuracy(
        self,
        actual: List[float],
        predicted: List[float]
    ) -> Dict[str, float]:
        """
        Calculate Directional Accuracy
        
        Args:
            actual: Actual price changes
            predicted: Predicted price changes
        
        Returns:
            Dictionary with directional accuracy metrics
        """
        if len(actual) != len(predicted) or len(actual) < 2:
            return {
                "directional_accuracy": 0.0,
                "total_predictions": 0,
                "correct_predictions": 0
            }
        
        actual_direction = np.diff(actual) > 0  # True if up, False if down
        predicted_direction = np.diff(predicted) > 0
        
        correct = np.sum(actual_direction == predicted_direction)
        total = len(actual_direction)
        
        accuracy = (correct / total * 100) if total > 0 else 0.0
        
        return {
            "directional_accuracy": float(accuracy),
            "total_predictions": int(total),
            "correct_predictions": int(correct),
            "up_predictions_correct": int(np.sum((actual_direction == predicted_direction) & actual_direction)),
            "down_predictions_correct": int(np.sum((actual_direction == predicted_direction) & ~actual_direction))
        }
    
    def calculate_mae_mape(
        self,
        actual: List[float],
        predicted: List[float]
    ) -> Dict[str, float]:
        """
        Calculate MAE and MAPE
        
        Args:
            actual: Actual values
            predicted: Predicted values
        
        Returns:
            Dictionary with MAE and MAPE
        """
        if len(actual) != len(predicted) or len(actual) == 0:
            return {
                "mae": 0.0,
                "mape": 0.0
            }
        
        actual_array = np.array(actual)
        predicted_array = np.array(predicted)
        
        mae = np.mean(np.abs(actual_array - predicted_array))
        
        # MAPE (avoid division by zero)
        mask = actual_array != 0
        if np.sum(mask) > 0:
            mape = np.mean(np.abs((actual_array[mask] - predicted_array[mask]) / actual_array[mask])) * 100
        else:
            mape = 0.0
        
        return {
            "mae": float(mae),
            "mape": float(mape)
        }
    
    def calculate_portfolio_metrics(
        self,
        portfolio_values: List[float],
        transactions: List[Dict[str, Any]],
        initial_balance: float
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive portfolio performance metrics
        
        Args:
            portfolio_values: Portfolio values over time
            transactions: List of transactions
            initial_balance: Initial portfolio balance
        
        Returns:
            Dictionary with all performance metrics
        """
        if not portfolio_values:
            return {
                "success": False,
                "error": "No portfolio data"
            }
        
        # Calculate returns
        returns = []
        for i in range(1, len(portfolio_values)):
            if portfolio_values[i-1] > 0:
                ret = (portfolio_values[i] - portfolio_values[i-1]) / portfolio_values[i-1]
                returns.append(ret)
        
        # Calculate transaction returns
        transaction_returns = []
        for transaction in transactions:
            if transaction.get("transaction_type") == "sell":
                # Calculate return for this transaction
                buy_price = transaction.get("avg_buy_price", 0)
                sell_price = transaction.get("price", 0)
                if buy_price > 0:
                    ret = (sell_price - buy_price) / buy_price
                    transaction_returns.append(ret)
        
        # Calculate all metrics
        sharpe = self.calculate_sharpe_ratio(returns) if returns else 0.0
        max_dd = self.calculate_max_drawdown(portfolio_values)
        win_rate = self.calculate_win_rate(transaction_returns) if transaction_returns else {"win_rate": 0.0, "total_trades": 0}
        
        # Total return
        total_return = (portfolio_values[-1] - initial_balance) / initial_balance * 100 if initial_balance > 0 else 0.0
        
        return {
            "success": True,
            "total_return": float(total_return),
            "sharpe_ratio": sharpe,
            "max_drawdown": max_dd,
            "win_rate": win_rate,
            "current_value": float(portfolio_values[-1]),
            "initial_value": float(initial_balance),
            "total_trades": win_rate.get("total_trades", 0)
        }


# Global instance
performance_service = PerformanceService()

