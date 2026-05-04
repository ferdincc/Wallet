"""
Risk Agent - Monitors portfolio and generates risk warnings
"""
from typing import Dict, Any, List, Optional
from app.agents.base_agent import BaseAgent
from sqlalchemy.orm import Session
from app.models.portfolio import Portfolio, Position, Transaction
from app.services.exchange_service import exchange_service
from app.services.anomaly_service import anomaly_service
from app.services.whale_alert_service import whale_alert_service
from datetime import datetime, timedelta


class RiskAgent(BaseAgent):
    """Agent responsible for risk monitoring and alerts"""
    
    def __init__(self):
        super().__init__("RiskAgent")
    
    async def execute(
        self,
        portfolio_id: int,
        db: Session,
        max_loss_percent: float = 10.0,
        max_position_size: float = 50.0,  # percentage of portfolio
        **kwargs
    ) -> Dict[str, Any]:
        """Analyze portfolio risk"""
        try:
            portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
            
            if not portfolio:
                return {
                    "success": False,
                    "error": "Portfolio not found",
                    "agent": self.name
                }
            
            positions = db.query(Position).filter(Position.portfolio_id == portfolio_id).all()
            
            warnings = []
            total_value = portfolio.current_balance
            
            # Check each position
            for position in positions:
                # Get current price
                ticker = await exchange_service.fetch_ticker(
                    position.symbol, 
                    position.exchange
                )
                
                if not ticker or not position.avg_buy_price:
                    continue
                
                current_price = ticker.get('price', 0)
                position_value = position.quantity * current_price
                position_pct = (position_value / total_value * 100) if total_value > 0 else 0
                
                # Check position size
                if position_pct > max_position_size:
                    warnings.append({
                        "type": "position_size",
                        "severity": "high",
                        "message": f"Position {position.symbol} is {position_pct:.2f}% of portfolio (max: {max_position_size}%)",
                        "symbol": position.symbol
                    })
                
                # Check unrealized loss
                if position.avg_buy_price > 0:
                    loss_pct = ((current_price - position.avg_buy_price) / position.avg_buy_price) * 100
                    if loss_pct < -max_loss_percent:
                        warnings.append({
                            "type": "unrealized_loss",
                            "severity": "high",
                            "message": f"Position {position.symbol} has {loss_pct:.2f}% unrealized loss (threshold: -{max_loss_percent}%)",
                            "symbol": position.symbol,
                            "loss_percent": loss_pct
                        })
            
            # Check overall portfolio health
            initial_value = portfolio.initial_balance
            portfolio_loss_pct = ((total_value - initial_value) / initial_value) * 100
            
            if portfolio_loss_pct < -max_loss_percent:
                warnings.append({
                    "type": "portfolio_loss",
                    "severity": "critical",
                    "message": f"Portfolio has {portfolio_loss_pct:.2f}% total loss",
                    "loss_percent": portfolio_loss_pct
                })
            
            # Anomaly detection for portfolio
            anomaly_result = None
            if anomaly_service.is_available():
                try:
                    # Get portfolio value history from transactions
                    transactions = db.query(Transaction).filter(
                        Transaction.portfolio_id == portfolio_id
                    ).order_by(Transaction.timestamp.asc()).all()
                    
                    if len(transactions) >= 10:
                        # Calculate portfolio values over time
                        portfolio_values = []
                        timestamps = []
                        running_balance = portfolio.initial_balance
                        
                        for transaction in transactions:
                            if transaction.transaction_type.value == "buy":
                                running_balance -= transaction.total
                            else:  # sell
                                running_balance += transaction.total
                            
                            portfolio_values.append(running_balance)
                            timestamps.append(transaction.timestamp)
                        
                        # Add current value
                        portfolio_values.append(total_value)
                        timestamps.append(datetime.utcnow())
                        
                        # Detect anomalies
                        anomaly_result = await anomaly_service.detect_portfolio_anomalies(
                            portfolio_values,
                            timestamps,
                            contamination=0.1
                        )
                        
                        if anomaly_result.get("success") and anomaly_result.get("anomalies"):
                            for anomaly in anomaly_result["anomalies"][:3]:  # Top 3 anomalies
                                warnings.append({
                                    "type": "anomaly",
                                    "severity": "medium",
                                    "message": f"Anomaly detected in portfolio value: ${anomaly['portfolio_value']:,.2f}",
                                    "anomaly_score": anomaly.get("anomaly_score", 0),
                                    "timestamp": anomaly.get("timestamp")
                                })
                except Exception as e:
                    self.log(f"Error in anomaly detection: {e}", "WARNING")
            
            # Whale Alert integration - Check for large exchange inflows
            whale_warnings = []
            if whale_alert_service.is_available():
                try:
                    # Check BTC and ETH for exchange inflows (potential sell pressure)
                    for currency in ["btc", "eth"]:
                        inflows = await whale_alert_service.get_exchange_inflows(
                            currency=currency,
                            hours=24
                        )
                        
                        if inflows.get("total_inflow_usd", 0) > 50000000:  # $50M threshold
                            whale_warnings.append({
                                "type": "whale_exchange_inflow",
                                "severity": "high",
                                "message": f"Büyük bir balina {currency.upper()} borsaya ${inflows['total_inflow_usd']:,.0f} aktardı. Satış baskısı olabilir!",
                                "currency": currency.upper(),
                                "total_inflow_usd": inflows["total_inflow_usd"],
                                "transaction_count": inflows["total_transactions"]
                            })
                        
                        # Check for large outflows (accumulation - positive signal)
                        outflows = await whale_alert_service.get_exchange_outflows(
                            currency=currency,
                            hours=24
                        )
                        
                        if outflows.get("total_outflow_usd", 0) > 100000000:  # $100M threshold
                            whale_warnings.append({
                                "type": "whale_exchange_outflow",
                                "severity": "info",
                                "message": f"Büyük bir balina {currency.upper()} borsadan ${outflows['total_outflow_usd']:,.0f} çekti. Birikim sinyali olabilir.",
                                "currency": currency.upper(),
                                "total_outflow_usd": outflows["total_outflow_usd"],
                                "transaction_count": outflows["total_transactions"]
                            })
                except Exception as e:
                    self.log(f"Error in whale alert check: {e}", "WARNING")
            
            # Add whale warnings to warnings list
            warnings.extend(whale_warnings)
            
            return {
                "success": True,
                "portfolio_id": portfolio_id,
                "current_balance": total_value,
                "initial_balance": initial_value,
                "portfolio_change_percent": portfolio_loss_pct,
                "warnings": warnings,
                "warning_count": len(warnings),
                "anomaly_detection": anomaly_result,
                "whale_alerts": whale_warnings,
                "agent": self.name
            }
            
        except Exception as e:
            self.log(f"Error in RiskAgent: {str(e)}", "ERROR")
            return {
                "success": False,
                "error": str(e),
                "agent": self.name
            }

