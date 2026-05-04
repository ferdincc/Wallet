"""
Voice Service - Handles speech-to-text and text-to-speech
"""
from typing import Dict, Any, Optional
import logging
import asyncio

logger = logging.getLogger(__name__)


class VoiceService:
    """Service for voice interactions"""
    
    def __init__(self):
        self.stt_available = False
        self.tts_available = False
        self._check_dependencies()
    
    def _check_dependencies(self):
        """Check if voice libraries are available"""
        # Speech-to-Text (STT) - Browser Web Speech API will be used on frontend
        # Text-to-Speech (TTS) - Browser SpeechSynthesis API will be used on frontend
        # Backend doesn't need voice libraries, it just processes text
        self.stt_available = True  # Always available via browser
        self.tts_available = True  # Always available via browser
        logger.info("Voice service initialized (browser-based)")
    
    def is_stt_available(self) -> bool:
        """Check if speech-to-text is available"""
        return self.stt_available
    
    def is_tts_available(self) -> bool:
        """Check if text-to-speech is available"""
        return self.tts_available
    
    async def process_voice_command(self, transcript: str) -> Dict[str, Any]:
        """
        Process voice command transcript
        
        Args:
            transcript: Speech-to-text transcript from frontend
        
        Returns:
            Processed command data
        """
        # Normalize transcript
        transcript = transcript.strip().lower()
        
        # Extract intent from voice command
        intent = {
            "action": "general",
            "symbol": None,
            "query": transcript
        }
        
        # Common voice command patterns
        if any(word in transcript for word in ["fiyat", "price", "ne kadar", "kaç"]):
            intent["action"] = "fetch_price"
            # Try to extract symbol
            for coin in ["bitcoin", "btc", "ethereum", "eth", "solana", "sol"]:
                if coin in transcript:
                    if coin in ["bitcoin", "btc"]:
                        intent["symbol"] = "BTC/USDT"
                    elif coin in ["ethereum", "eth"]:
                        intent["symbol"] = "ETH/USDT"
                    elif coin in ["solana", "sol"]:
                        intent["symbol"] = "SOL/USDT"
                    break
        
        elif any(word in transcript for word in ["analiz", "analysis", "piyasa analizi"]):
            intent["action"] = "comprehensive_analyze"
            # Try to extract symbol
            for coin in ["bitcoin", "btc", "ethereum", "eth", "solana", "sol"]:
                if coin in transcript:
                    if coin in ["bitcoin", "btc"]:
                        intent["symbol"] = "BTC/USDT"
                    elif coin in ["solana", "sol"]:
                        intent["symbol"] = "SOL/USDT"
                    break
        
        elif any(word in transcript for word in ["risk", "risk seviyesi", "risk durumu"]):
            intent["action"] = "portfolio_status"
        
        elif any(word in transcript for word in ["portföy", "portfolio", "pozisyon", "bakiye"]):
            intent["action"] = "portfolio_status"
        
        return {
            "success": True,
            "intent": intent,
            "transcript": transcript,
            "processed": True
        }
    
    def generate_voice_response(self, text: str) -> Dict[str, Any]:
        """
        Generate voice response data (TTS will be done on frontend)
        
        Args:
            text: Text to convert to speech
        
        Returns:
            Response data for frontend TTS
        """
        # Clean text for speech
        # Remove markdown, emojis, etc.
        clean_text = text
        # Remove emojis and special characters that don't read well
        import re
        clean_text = re.sub(r'[^\w\s.,!?;:()\-]', '', clean_text)
        # Remove multiple spaces
        clean_text = re.sub(r'\s+', ' ', clean_text)
        
        return {
            "success": True,
            "text": clean_text,
            "length": len(clean_text),
            "estimated_duration_seconds": len(clean_text) / 10  # Rough estimate: 10 chars per second
        }


# Global instance
voice_service = VoiceService()












