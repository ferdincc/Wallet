"""
User Profile Service - Handles personalized recommendations based on risk appetite
"""
from typing import Dict, Any, Optional
from app.models.user import User, RiskAppetite
from sqlalchemy.orm import Session


def _ui_lang(lang: Optional[str]) -> str:
    return "en"


class UserProfileService:
    """Service for user profile-based recommendations"""
    
    @staticmethod
    def get_confidence_threshold(user: User) -> float:
        """Get minimum confidence threshold based on risk appetite"""
        if user.risk_appetite == RiskAppetite.CONSERVATIVE:
            return 0.80  # 80% confidence required
        elif user.risk_appetite == RiskAppetite.MODERATE:
            return 0.65  # 65% confidence required
        else:  # AGGRESSIVE
            return 0.60  # 60% confidence sufficient
    
    @staticmethod
    def should_recommend_trade(
        user: User,
        confidence_score: float,
        prediction_change: float,
        sentiment_score: float,
        lang: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Determine if a trade should be recommended based on user profile
        
        Returns:
            {
                "recommend": bool,
                "action": "AL" | "SAT" | "NÖTR",
                "reasoning": str,
                "confidence_met": bool
            }
        """
        L = _ui_lang(lang)
        threshold = UserProfileService.get_confidence_threshold(user)
        confidence_met = confidence_score >= threshold
        
        # Conservative profile: Very strict
        if user.risk_appetite == RiskAppetite.CONSERVATIVE:
            if not confidence_met:
                return {
                    "recommend": False,
                    "action": "NÖTR",
                    "reasoning": (
                        f"For a conservative profile, confidence is too low ({confidence_score*100:.1f}% < {threshold*100:.0f}%). No trade suggested."
                        if L == "en"
                        else f"Muhafazakar profiliniz için güven skoru yetersiz (%{confidence_score*100:.1f} < %{threshold*100:.0f}). İşlem önerilmiyor."
                    ),
                    "confidence_met": False,
                    "user_profile": "conservative"
                }
            
            # Conservative: Only recommend if strong positive signals
            if prediction_change > 5 and sentiment_score > 0.3:
                return {
                    "recommend": True,
                    "action": "AL",
                    "reasoning": (
                        f"For a conservative profile, confidence is sufficient ({confidence_score*100:.1f}%) with strong positive signals."
                        if L == "en"
                        else f"Muhafazakar profiliniz için güven skoru yeterli (%{confidence_score*100:.1f}%) ve güçlü pozitif sinyaller var."
                    ),
                    "confidence_met": True,
                    "user_profile": "conservative"
                }
            elif prediction_change < -5 and sentiment_score < -0.3:
                return {
                    "recommend": True,
                    "action": "SAT",
                    "reasoning": (
                        f"For a conservative profile, confidence is sufficient ({confidence_score*100:.1f}%) but strong negative signals are present."
                        if L == "en"
                        else f"Muhafazakar profiliniz için güven skoru yeterli (%{confidence_score*100:.1f}%) ancak güçlü negatif sinyaller var."
                    ),
                    "confidence_met": True,
                    "user_profile": "conservative"
                }
            else:
                return {
                    "recommend": False,
                    "action": "NÖTR",
                    "reasoning": (
                        "For a conservative profile, signals are not strong enough; waiting is preferable."
                        if L == "en"
                        else f"Muhafazakar profiliniz için sinyaller yeterince güçlü değil. Beklemeniz önerilir."
                    ),
                    "confidence_met": True,
                    "user_profile": "conservative"
                }
        
        # Moderate profile: Balanced
        elif user.risk_appetite == RiskAppetite.MODERATE:
            if not confidence_met:
                return {
                    "recommend": False,
                    "action": "NÖTR",
                    "reasoning": (
                        f"For a moderate-risk profile, confidence is too low ({confidence_score*100:.1f}% < {threshold*100:.0f}%)."
                        if L == "en"
                        else f"Orta risk profiliniz için güven skoru yetersiz (%{confidence_score*100:.1f} < %{threshold*100:.0f})."
                    ),
                    "confidence_met": False,
                    "user_profile": "moderate"
                }
            
            if prediction_change > 3 and sentiment_score > 0.2:
                return {
                    "recommend": True,
                    "action": "AL",
                    "reasoning": (
                        f"For a moderate-risk profile, confidence is sufficient ({confidence_score*100:.1f}%) with positive signals."
                        if L == "en"
                        else f"Orta risk profiliniz için güven skoru yeterli (%{confidence_score*100:.1f}%) ve pozitif sinyaller mevcut."
                    ),
                    "confidence_met": True,
                    "user_profile": "moderate"
                }
            elif prediction_change < -3 and sentiment_score < -0.2:
                return {
                    "recommend": True,
                    "action": "SAT",
                    "reasoning": (
                        f"For a moderate-risk profile, confidence is sufficient ({confidence_score*100:.1f}%) but negative signals are present."
                        if L == "en"
                        else f"Orta risk profiliniz için güven skoru yeterli (%{confidence_score*100:.1f}%) ancak negatif sinyaller var."
                    ),
                    "confidence_met": True,
                    "user_profile": "moderate"
                }
            else:
                return {
                    "recommend": False,
                    "action": "NÖTR",
                    "confidence_met": True,
                    "reasoning": (
                        "Signals are mixed; waiting is preferable."
                        if L == "en"
                        else "Sinyaller belirsiz, beklemeniz önerilir."
                    ),
                    "user_profile": "moderate"
                }
        
        # Aggressive profile: More lenient
        else:  # AGGRESSIVE
            if not confidence_met:
                return {
                    "recommend": False,
                    "action": "NÖTR",
                    "reasoning": (
                        f"Even for an aggressive profile, confidence is too low ({confidence_score*100:.1f}% < {threshold*100:.0f}%)."
                        if L == "en"
                        else f"Agresif profiliniz için bile güven skoru çok düşük (%{confidence_score*100:.1f} < %{threshold*100:.0f})."
                    ),
                    "confidence_met": False,
                    "user_profile": "aggressive"
                }
            
            if prediction_change > 2 or sentiment_score > 0.1:
                return {
                    "recommend": True,
                    "action": "AL",
                    "reasoning": (
                        f"For an aggressive profile, confidence is sufficient ({confidence_score*100:.1f}%). A buy opportunity appears likely."
                        if L == "en"
                        else f"Agresif profiliniz için güven skoru yeterli (%{confidence_score*100:.1f}%). Alım fırsatı görünüyor."
                    ),
                    "confidence_met": True,
                    "user_profile": "aggressive"
                }
            elif prediction_change < -2 or sentiment_score < -0.1:
                return {
                    "recommend": True,
                    "action": "SAT",
                    "reasoning": (
                        f"For an aggressive profile, confidence is sufficient ({confidence_score*100:.1f}%) but downside signals are present."
                        if L == "en"
                        else f"Agresif profiliniz için güven skoru yeterli (%{confidence_score*100:.1f}%) ancak düşüş sinyalleri var."
                    ),
                    "confidence_met": True,
                    "user_profile": "aggressive"
                }
            else:
                return {
                    "recommend": True,
                    "action": "NÖTR",
                    "reasoning": (
                        "Signals are mixed; waiting is still suggested for an aggressive profile."
                        if L == "en"
                        else "Sinyaller belirsiz, agresif profiliniz için beklemeniz önerilir."
                    ),
                    "confidence_met": True,
                    "user_profile": "aggressive"
                }
    
    @staticmethod
    def get_profile_description(risk_appetite: RiskAppetite, lang: Optional[str] = None) -> str:
        """Get human-readable profile description"""
        L = _ui_lang(lang)
        if L == "en":
            descriptions = {
                RiskAppetite.CONSERVATIVE: "Conservative: requires high confidence scores (80%+). Lower risk, lower return.",
                RiskAppetite.MODERATE: "Moderate: balanced approach. 65%+ confidence is enough. Medium risk and return.",
                RiskAppetite.AGGRESSIVE: "Aggressive: 60%+ confidence is enough. Higher risk, higher return potential."
            }
            return descriptions.get(risk_appetite, "Unknown profile")
        descriptions = {
            RiskAppetite.CONSERVATIVE: "Muhafazakar: Yüksek güven skorları (%80+) gerektirir. Düşük risk, düşük getiri.",
            RiskAppetite.MODERATE: "Orta: Dengeli yaklaşım. %65+ güven skoru yeterli. Orta risk, orta getiri.",
            RiskAppetite.AGGRESSIVE: "Agresif: %60+ güven skoru yeterli. Yüksek risk, yüksek getiri potansiyeli."
        }
        return descriptions.get(risk_appetite, "Bilinmeyen profil")


# Global instance
user_profile_service = UserProfileService()












