"""
Consensus Agent - Coordinates multi-agent consensus and voting
"""
from typing import Dict, Any, List, Optional
from app.agents.base_agent import BaseAgent
from app.agents.analysis_agent import AnalysisAgent
from app.agents.sentiment_agent import SentimentAgent
from app.agents.prediction_agent import PredictionAgent
from app.agents.risk_agent import RiskAgent
from app.agents.reasoning_log import ReasoningLog, ReasoningStepType


class ConsensusAgent(BaseAgent):
    """Agent responsible for coordinating consensus among other agents"""
    
    def __init__(self):
        super().__init__("ConsensusAgent")
        self.analysis_agent = AnalysisAgent()
        self.sentiment_agent = SentimentAgent()
        self.prediction_agent = PredictionAgent()
        self.risk_agent = RiskAgent()
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute consensus voting (required by BaseAgent)"""
        symbol = kwargs.get("symbol", "BTC/USDT")
        reasoning_log = kwargs.get("reasoning_log")
        return await self.get_agent_votes(symbol, reasoning_log)
    
    async def get_agent_votes(
        self,
        symbol: str,
        reasoning_log: Optional[ReasoningLog] = None
    ) -> Dict[str, Any]:
        """
        Get votes from all agents for a trading decision
        
        Returns:
            {
                "votes": {
                    "AnalysisAgent": {"vote": "BUY/SELL/HOLD", "confidence": 0.8, "reasoning": "..."},
                    "SentimentAgent": {...},
                    "PredictionAgent": {...},
                    "RiskAgent": {...}
                },
                "consensus": "BUY/SELL/HOLD",
                "consensus_confidence": 0.75,
                "disagreement": False,
                "disagreement_reasons": []
            }
        """
        votes = {}
        
        # 1. Analysis Agent Vote (Technical Analysis)
        try:
            ta_result = await self.analysis_agent.execute(symbol=symbol, include_sentiment=False)
            if ta_result.get("success"):
                ta = ta_result.get("technical_analysis", {})
                signals = ta.get("signals", [])
                
                # Determine vote from signals
                buy_signals = sum(1 for s in signals if "AL" in s.upper() or "BUY" in s.upper())
                sell_signals = sum(1 for s in signals if "SAT" in s.upper() or "SELL" in s.upper())
                
                if buy_signals > sell_signals:
                    vote = "BUY"
                    confidence = min(0.9, 0.5 + (buy_signals * 0.1))
                elif sell_signals > buy_signals:
                    vote = "SELL"
                    confidence = min(0.9, 0.5 + (sell_signals * 0.1))
                else:
                    vote = "HOLD"
                    confidence = 0.5
                
                votes["AnalysisAgent"] = {
                    "vote": vote,
                    "confidence": confidence,
                    "reasoning": f"Teknik göstergeler: {', '.join(signals[:3]) if signals else 'Nötr'}",
                    "rsi": ta.get("rsi"),
                    "macd": ta.get("macd", {}).get("macd")
                }
                
                if reasoning_log:
                    reasoning_log.add_decision(
                        agent_name="AnalysisAgent",
                        decision=f"Oylama: {vote}",
                        reasoning=f"Teknik analiz {vote} sinyali veriyor",
                        confidence=confidence
                    )
        except Exception as e:
            self.log(f"Error getting AnalysisAgent vote: {e}", "ERROR")
        
        # 2. Sentiment Agent Vote
        try:
            sentiment_result = await self.sentiment_agent.execute(
                symbol=symbol.split("/")[0] if "/" in symbol else symbol,
                include_news=True,
                include_reddit=True,
                hours=24
            )
            if sentiment_result.get("success"):
                overall = sentiment_result.get("overall_sentiment", {})
                sentiment_score = overall.get("score", 0)
                sentiment_type = overall.get("sentiment", "neutral")
                
                if sentiment_score > 0.2:
                    vote = "BUY"
                    confidence = min(0.9, 0.5 + abs(sentiment_score))
                elif sentiment_score < -0.2:
                    vote = "SELL"
                    confidence = min(0.9, 0.5 + abs(sentiment_score))
                else:
                    vote = "HOLD"
                    confidence = 0.5
                
                votes["SentimentAgent"] = {
                    "vote": vote,
                    "confidence": confidence,
                    "reasoning": f"Sentiment: {sentiment_type} (skor: {sentiment_score:.3f})",
                    "sentiment_score": sentiment_score
                }
                
                if reasoning_log:
                    reasoning_log.add_decision(
                        agent_name="SentimentAgent",
                        decision=f"Oylama: {vote}",
                        reasoning=f"Sentiment analizi {sentiment_type} gösteriyor",
                        confidence=confidence
                    )
        except Exception as e:
            self.log(f"Error getting SentimentAgent vote: {e}", "ERROR")
        
        # 3. Prediction Agent Vote
        try:
            prediction_result = await self.prediction_agent.execute(
                symbol=symbol,
                periods=7,
                model="ensemble"
            )
            if prediction_result.get("success"):
                pred_change = prediction_result.get("predicted_change", {}).get("percentage", 0)
                metrics = prediction_result.get("metrics", {})
                directional_acc = metrics.get("directional_accuracy", 0) / 100.0
                
                if pred_change > 3:
                    vote = "BUY"
                    confidence = min(0.9, 0.5 + (pred_change / 20) * directional_acc)
                elif pred_change < -3:
                    vote = "SELL"
                    confidence = min(0.9, 0.5 + (abs(pred_change) / 20) * directional_acc)
                else:
                    vote = "HOLD"
                    confidence = 0.5
                
                votes["PredictionAgent"] = {
                    "vote": vote,
                    "confidence": confidence,
                    "reasoning": f"7 günlük tahmin: {pred_change:+.2f}% değişim bekleniyor (Doğruluk: {directional_acc*100:.1f}%)",
                    "predicted_change": pred_change
                }
                
                if reasoning_log:
                    reasoning_log.add_decision(
                        agent_name="PredictionAgent",
                        decision=f"Oylama: {vote}",
                        reasoning=f"Tahmin {pred_change:+.2f}% değişim öngörüyor",
                        confidence=confidence
                    )
        except Exception as e:
            self.log(f"Error getting PredictionAgent vote: {e}", "ERROR")
        
        # 4. Risk Agent Vote (Negative Confirmation)
        try:
            # Risk agent provides negative confirmation
            # Ask: "What are the biggest obstacles to this prediction?"
            risk_warnings = []
            risk_vote = "HOLD"
            risk_confidence = 0.5
            
            # Check if prediction is too optimistic/pessimistic
            if "PredictionAgent" in votes:
                pred_vote = votes["PredictionAgent"]["vote"]
                pred_change = votes["PredictionAgent"].get("predicted_change", 0)
                
                # Risk agent asks critical questions
                if pred_vote == "BUY" and pred_change > 5:
                    risk_warnings.append(f"Tahmin çok iyimser (+{pred_change:.1f}%). Düzeltme riski yüksek olabilir.")
                    risk_vote = "HOLD"
                    risk_confidence = 0.6
                elif pred_vote == "SELL" and pred_change < -5:
                    risk_warnings.append(f"Tahmin çok kötümser ({pred_change:.1f}%). Toparlanma potansiyeli olabilir.")
                    risk_vote = "HOLD"
                    risk_confidence = 0.6
                else:
                    risk_vote = pred_vote  # Risk agent agrees
                    risk_confidence = 0.7
            
            votes["RiskAgent"] = {
                "vote": risk_vote,
                "confidence": risk_confidence,
                "reasoning": "Risk değerlendirmesi: " + ("; ".join(risk_warnings) if risk_warnings else "Önemli bir risk tespit edilmedi"),
                "warnings": risk_warnings
            }
            
            if reasoning_log:
                reasoning_log.add_coordination(
                    from_agent="RiskAgent",
                    to_agent="PredictionAgent",
                    message="Risk kontrolü: Tahminin önündeki engeller değerlendiriliyor",
                    data={"warnings": risk_warnings}
                )
        except Exception as e:
            self.log(f"Error getting RiskAgent vote: {e}", "ERROR")
        
        # Calculate Consensus
        if not votes:
            return {
                "votes": {},
                "consensus": "HOLD",
                "consensus_confidence": 0.0,
                "disagreement": True,
                "disagreement_reasons": ["Hiçbir ajan oy veremedi"]
            }
        
        # Count votes
        vote_counts = {"BUY": 0, "SELL": 0, "HOLD": 0}
        total_confidence = 0.0
        
        for agent_name, vote_data in votes.items():
            vote = vote_data["vote"]
            vote_counts[vote] += 1
            total_confidence += vote_data["confidence"]
        
        # Determine consensus
        max_votes = max(vote_counts.values())
        consensus_vote = [v for v, count in vote_counts.items() if count == max_votes][0]
        consensus_confidence = total_confidence / len(votes) if votes else 0.0
        
        # Check for disagreement (if votes are split)
        unique_votes = set(v["vote"] for v in votes.values())
        disagreement = len(unique_votes) > 1 and max_votes < len(votes)
        
        disagreement_reasons = []
        if disagreement:
            for agent_name, vote_data in votes.items():
                if vote_data["vote"] != consensus_vote:
                    disagreement_reasons.append(
                        f"{agent_name}: {vote_data['vote']} ({vote_data['reasoning']})"
                    )
        
        if reasoning_log:
            reasoning_log.add_decision(
                agent_name=self.name,
                decision=f"Konsensüs: {consensus_vote}",
                reasoning=f"{max_votes}/{len(votes)} ajan {consensus_vote} oyu verdi" + 
                         (". Fikir ayrılığı var." if disagreement else ". Çoğunluk sağlandı."),
                confidence=consensus_confidence
            )
        
        return {
            "votes": votes,
            "consensus": consensus_vote,
            "consensus_confidence": consensus_confidence,
            "disagreement": disagreement,
            "disagreement_reasons": disagreement_reasons,
            "vote_distribution": vote_counts
        }
    
    async def negative_confirmation(
        self,
        agent_name: str,
        decision: str,
        reasoning: str,
        target_agent: str = "RiskAgent"
    ) -> Dict[str, Any]:
        """
        Get negative confirmation from another agent
        
        Example: "PredictionAgent says BUY, but what does RiskAgent think?"
        """
        if target_agent == "RiskAgent":
            # Risk agent provides critical analysis
            warnings = []
            
            if decision == "BUY":
                warnings.append("Yükselişin önündeki potansiyel engeller: Aşırı alım bölgesi, negatif haber riski, teknik direnç noktaları")
            elif decision == "SELL":
                warnings.append("Düşüşün önündeki potansiyel engeller: Aşırı satım bölgesi, pozitif haber potansiyeli, teknik destek seviyeleri")
            
            return {
                "confirmed": True,
                "warnings": warnings,
                "agent": target_agent,
                "message": f"{target_agent} tarafından onaylandı, ancak dikkat edilmesi gereken noktalar var."
            }
        
        return {
            "confirmed": True,
            "warnings": [],
            "agent": target_agent
        }

