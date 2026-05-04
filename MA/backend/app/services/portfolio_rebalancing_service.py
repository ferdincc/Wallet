"""
Portfolio Rebalancing Service - Smart portfolio management
"""
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.models.portfolio import Portfolio, Position
from app.services.exchange_service import exchange_service
import logging

logger = logging.getLogger(__name__)


class PortfolioRebalancingService:
    """Service for smart portfolio rebalancing recommendations"""
    
    @staticmethod
    async def analyze_portfolio(
        db: Session,
        portfolio_id: int
    ) -> Dict[str, Any]:
        """
        Analyze portfolio and provide rebalancing recommendations
        
        Returns:
            {
                "total_value": float,
                "positions": [...],
                "recommendations": [...],
                "risk_score": float,
                "diversification_score": float
            }
        """
        portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
        if not portfolio:
            return {
                "success": False,
                "error": "Portfolio not found"
            }
        
        positions = db.query(Position).filter(Position.portfolio_id == portfolio_id).all()
        
        # Calculate current portfolio value
        total_value = portfolio.current_balance
        position_values = []
        
        for position in positions:
            # Get current price
            try:
                ticker = await exchange_service.fetch_ticker(position.symbol, "binance")
                current_price = ticker.get("price", 0) if ticker else 0
                
                position_value = position.quantity * current_price
                position_values.append({
                    "symbol": position.symbol,
                    "quantity": position.quantity,
                    "current_price": current_price,
                    "value": position_value,
                    "percentage": (position_value / total_value * 100) if total_value > 0 else 0
                })
            except Exception as e:
                logger.error(f"Error fetching price for {position.symbol}: {e}")
        
        # Calculate risk metrics
        risk_score = 0.0
        recommendations = []
        
        # Check for over-concentration (single position > 40% of portfolio)
        for pos in position_values:
            if pos["percentage"] > 40:
                risk_score += 30
                recommendations.append({
                    "type": "over_concentration",
                    "severity": "high",
                    "symbol": pos["symbol"],
                    "message": f"Portföyünüzde {pos['symbol']} oranı çok yüksek (%{pos['percentage']:.1f}). Riskini azaltmak için bir kısmını stablecoin'e (USDT) çevirmenizi öneririm.",
                    "current_percentage": pos["percentage"],
                    "recommended_percentage": 30,
                    "action": "sell",
                    "amount_usdt": pos["value"] * 0.3  # Sell 30% to reduce concentration
                })
            elif pos["percentage"] > 30:
                risk_score += 15
                recommendations.append({
                    "type": "high_concentration",
                    "severity": "medium",
                    "symbol": pos["symbol"],
                    "message": f"{pos['symbol']} portföyünüzün %{pos['percentage']:.1f}'ini oluşturuyor. Daha dengeli bir dağılım için bir kısmını stablecoin'e çevirebilirsiniz.",
                    "current_percentage": pos["percentage"],
                    "recommended_percentage": 25,
                    "action": "sell",
                    "amount_usdt": pos["value"] * 0.2
                })
        
        # Check for low diversification (too few positions)
        if len(position_values) < 3:
            risk_score += 20
            recommendations.append({
                "type": "low_diversification",
                "severity": "medium",
                "message": f"Portföyünüzde sadece {len(position_values)} pozisyon var. Risk dağılımı için en az 3-5 farklı coin'e yatırım yapmanız önerilir.",
                "current_count": len(position_values),
                "recommended_count": 5
            })
        
        # Check for all-in-one position
        if len(position_values) == 1:
            risk_score += 50
            recommendations.append({
                "type": "all_in_one",
                "severity": "critical",
                "message": "Tüm portföyünüz tek bir coin'de! Bu çok riskli. Lütfen portföyünüzü çeşitlendirin.",
                "symbol": position_values[0]["symbol"] if position_values else None
            })
        
        # Check for high volatility exposure
        # (This would require historical volatility data, simplified for now)
        if len(position_values) > 0:
            # If all positions are high-volatility coins (not stablecoins)
            stablecoins = ["USDT", "USDC", "BUSD", "DAI"]
            volatile_count = sum(1 for pos in position_values 
                                if not any(stable in pos["symbol"] for stable in stablecoins))
            
            if volatile_count == len(position_values) and len(position_values) > 0:
                risk_score += 15
                recommendations.append({
                    "type": "high_volatility",
                    "severity": "medium",
                    "message": "Portföyünüzde sadece volatil coin'ler var. Risk yönetimi için bir kısmını stablecoin'e (USDT) çevirmeniz önerilir.",
                    "recommended_stablecoin_percentage": 20
                })
        
        # Calculate diversification score (0-100, higher is better)
        diversification_score = 100.0
        if len(position_values) > 0:
            # Penalize for over-concentration
            max_percentage = max((pos["percentage"] for pos in position_values), default=0)
            if max_percentage > 50:
                diversification_score -= 40
            elif max_percentage > 40:
                diversification_score -= 25
            elif max_percentage > 30:
                diversification_score -= 10
            
            # Penalize for too few positions
            if len(position_values) < 3:
                diversification_score -= 30
            elif len(position_values) < 5:
                diversification_score -= 15
        
        return {
            "success": True,
            "portfolio_id": portfolio_id,
            "total_value": total_value,
            "positions": position_values,
            "recommendations": recommendations,
            "risk_score": min(100, risk_score),
            "diversification_score": max(0, diversification_score),
            "recommendation_count": len(recommendations)
        }
    
    @staticmethod
    async def get_rebalancing_plan(
        db: Session,
        portfolio_id: int,
        target_allocation: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        Generate a rebalancing plan
        
        Args:
            portfolio_id: Portfolio ID
            target_allocation: Target allocation percentages (e.g., {"BTC/USDT": 30, "ETH/USDT": 25, "USDT": 45})
        
        Returns:
            Rebalancing plan with buy/sell recommendations
        """
        analysis = await PortfolioRebalancingService.analyze_portfolio(db, portfolio_id)
        
        if not analysis.get("success"):
            return analysis
        
        if not target_allocation:
            # Default balanced allocation
            target_allocation = {
                "BTC/USDT": 30,
                "ETH/USDT": 25,
                "SOL/USDT": 15,
                "USDT": 30  # Stablecoin reserve
            }
        
        # Calculate target values
        total_value = analysis["total_value"]
        target_values = {
            symbol: (percentage / 100) * total_value
            for symbol, percentage in target_allocation.items()
        }
        
        # Compare current vs target
        current_positions = {pos["symbol"]: pos["value"] for pos in analysis["positions"]}
        
        rebalancing_actions = []
        
        for symbol, target_value in target_values.items():
            current_value = current_positions.get(symbol, 0)
            difference = target_value - current_value
            
            if abs(difference) > total_value * 0.05:  # Only rebalance if difference > 5%
                action = {
                    "symbol": symbol,
                    "current_value": current_value,
                    "target_value": target_value,
                    "difference": difference,
                    "action": "buy" if difference > 0 else "sell",
                    "amount_usdt": abs(difference),
                    "current_percentage": (current_value / total_value * 100) if total_value > 0 else 0,
                    "target_percentage": target_allocation.get(symbol, 0)
                }
                rebalancing_actions.append(action)
        
        return {
            "success": True,
            "portfolio_id": portfolio_id,
            "total_value": total_value,
            "target_allocation": target_allocation,
            "rebalancing_actions": rebalancing_actions,
            "estimated_cost": sum(abs(action["difference"]) for action in rebalancing_actions) * 0.001,  # 0.1% trading fee estimate
            "action_count": len(rebalancing_actions)
        }


# Global instance
portfolio_rebalancing_service = PortfolioRebalancingService()












