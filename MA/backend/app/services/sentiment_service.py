"""
Sentiment Analysis Service using FinBERT and mBERT
"""
from typing import Dict, Any, List, Optional
import logging
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

# Lazy loading for transformers (heavy models)
_sentiment_models = {}
_tokenizers = {}


class SentimentService:
    """Service for sentiment analysis of financial news and social media"""
    
    def __init__(self):
        self.finbert_loaded = False
        self.mbert_loaded = False
        self._initialize_models()
    
    def _initialize_models(self):
        """Initialize sentiment models (lazy loading)"""
        try:
            # Models will be loaded on first use
            logger.info("Sentiment models will be loaded on first use")
        except Exception as e:
            logger.warning(f"Could not initialize sentiment models: {e}")
    
    def _load_finbert(self):
        """Load FinBERT model"""
        if self.finbert_loaded:
            return
        
        try:
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            
            model_name = "ProsusAI/finbert"
            logger.info(f"Loading FinBERT model: {model_name}")
            
            _tokenizers['finbert'] = AutoTokenizer.from_pretrained(model_name)
            _sentiment_models['finbert'] = AutoModelForSequenceClassification.from_pretrained(model_name)
            
            self.finbert_loaded = True
            logger.info("FinBERT model loaded successfully")
        except ImportError:
            logger.warning("Transformers library not installed. Install with: pip install transformers torch")
        except Exception as e:
            logger.error(f"Error loading FinBERT: {e}")
    
    def _load_mbert(self):
        """Load mBERT model for multilingual support"""
        if self.mbert_loaded:
            return
        
        try:
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            
            model_name = "nlptown/bert-base-multilingual-uncased-sentiment"
            logger.info(f"Loading mBERT model: {model_name}")
            
            _tokenizers['mbert'] = AutoTokenizer.from_pretrained(model_name)
            _sentiment_models['mbert'] = AutoModelForSequenceClassification.from_pretrained(model_name)
            
            self.mbert_loaded = True
            logger.info("mBERT model loaded successfully")
        except ImportError:
            logger.warning("Transformers library not installed")
        except Exception as e:
            logger.error(f"Error loading mBERT: {e}")
    
    async def analyze_sentiment(
        self,
        text: str,
        model_type: str = "finbert",
        language: str = "en"
    ) -> Dict[str, Any]:
        """
        Analyze sentiment of a text
        
        Args:
            text: Text to analyze
            model_type: "finbert" or "mbert"
            language: Language code (en, tr, etc.)
        
        Returns:
            Dictionary with sentiment scores and label
        """
        if not text or len(text.strip()) == 0:
            return {
                "sentiment": "neutral",
                "score": 0.0,
                "confidence": 0.0,
                "model": None
            }
        
        try:
            # Load model if needed
            if model_type == "finbert":
                self._load_finbert()
                if not self.finbert_loaded:
                    return self._fallback_sentiment(text)
                
                tokenizer = _tokenizers.get('finbert')
                model = _sentiment_models.get('finbert')
            else:  # mbert
                self._load_mbert()
                if not self.mbert_loaded:
                    return self._fallback_sentiment(text)
                
                tokenizer = _tokenizers.get('mbert')
                model = _sentiment_models.get('mbert')
            
            if not tokenizer or not model:
                return self._fallback_sentiment(text)
            
            # Run inference in thread pool to avoid blocking
            result = await asyncio.to_thread(
                self._predict_sentiment,
                text,
                tokenizer,
                model,
                model_type
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error in sentiment analysis: {e}")
            return self._fallback_sentiment(text)
    
    def _predict_sentiment(
        self,
        text: str,
        tokenizer,
        model,
        model_type: str
    ) -> Dict[str, Any]:
        """Predict sentiment (runs in thread pool)"""
        import torch
        
        # Tokenize
        inputs = tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=512,
            padding=True
        )
        
        # Predict
        with torch.no_grad():
            outputs = model(**inputs)
            predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
        
        # Get scores
        scores = predictions[0].tolist()
        
        if model_type == "finbert":
            # FinBERT: positive, negative, neutral
            labels = ["positive", "negative", "neutral"]
            max_idx = scores.index(max(scores))
            sentiment = labels[max_idx]
            confidence = scores[max_idx]
            
            # Calculate overall score (-1 to 1)
            score = scores[0] - scores[1]  # positive - negative
        else:
            # mBERT: 1-5 star rating
            max_idx = scores.index(max(scores))
            confidence = scores[max_idx]
            
            # Convert to sentiment
            if max_idx >= 3:
                sentiment = "positive"
            elif max_idx <= 1:
                sentiment = "negative"
            else:
                sentiment = "neutral"
            
            # Calculate score (-1 to 1)
            score = (max_idx - 2) / 2.0
        
        return {
            "sentiment": sentiment,
            "score": round(score, 4),
            "confidence": round(confidence, 4),
            "scores": {label: round(score, 4) for label, score in zip(labels if model_type == "finbert" else ["1", "2", "3", "4", "5"], scores)},
            "model": model_type,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def _fallback_sentiment(self, text: str) -> Dict[str, Any]:
        """Fallback sentiment analysis using simple keyword matching"""
        text_lower = text.lower()
        
        positive_words = ["bullish", "rise", "gain", "up", "positive", "good", "strong", "buy", "yükseliş", "artış", "iyi", "güçlü"]
        negative_words = ["bearish", "fall", "drop", "down", "negative", "bad", "weak", "sell", "düşüş", "azalış", "kötü", "zayıf"]
        
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        
        if positive_count > negative_count:
            sentiment = "positive"
            score = min(0.5, positive_count * 0.1)
        elif negative_count > positive_count:
            sentiment = "negative"
            score = max(-0.5, -negative_count * 0.1)
        else:
            sentiment = "neutral"
            score = 0.0
        
        return {
            "sentiment": sentiment,
            "score": round(score, 4),
            "confidence": 0.5,
            "model": "fallback",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def analyze_batch(
        self,
        texts: List[str],
        model_type: str = "finbert"
    ) -> List[Dict[str, Any]]:
        """Analyze sentiment for multiple texts"""
        results = []
        for text in texts:
            result = await self.analyze_sentiment(text, model_type)
            results.append(result)
        return results
    
    def is_available(self) -> bool:
        """Check if sentiment models are available"""
        return self.finbert_loaded or self.mbert_loaded


# Global instance
sentiment_service = SentimentService()


















