"""
Sentiment Agent - Analyzes news and social media sentiment
"""
from typing import Dict, Any, List, Optional
from app.agents.base_agent import BaseAgent
from app.services.news_service import news_service
from app.services.sentiment_service import sentiment_service
from app.agents.llm_service import llm_service
from sqlalchemy.orm import Session
from app.models.news import NewsArticle, RedditPost, SentimentScore
from datetime import datetime, timedelta


class SentimentAgent(BaseAgent):
    """Agent responsible for news and social media sentiment analysis"""
    
    def __init__(self):
        super().__init__("SentimentAgent")
    
    async def execute(
        self,
        symbol: str = None,
        query: str = None,
        include_news: bool = True,
        include_reddit: bool = True,
        hours: int = 24,
        db: Session = None,
        locale: str = "en",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Analyze sentiment for a cryptocurrency symbol
        
        Args:
            symbol: Cryptocurrency symbol (e.g., "BTC", "ETH")
            query: Custom search query
            include_news: Include news articles
            include_reddit: Include Reddit posts
            hours: How many hours back to search
            db: Database session (optional, for saving results)
        """
        import traceback
        import asyncio

        lang = "en"

        try:
            search_term = symbol or query
            if not search_term:
                self.log("Symbol or query is required for sentiment analysis", "ERROR")
                err = (
                    "Symbol or query parameter is required"
                    if lang == "en"
                    else "Symbol veya query parametresi gereklidir"
                )
                return {"success": False, "error": err, "agent": self.name}
            
            self.log(f"Starting sentiment analysis for {search_term}", "INFO")
            results = {
                "success": True,
                "symbol": symbol,
                "query": query or symbol,
                "agent": self.name,
                "news_sentiment": [],
                "reddit_sentiment": [],
                "overall_sentiment": None,
                "sources": []
            }
            
            # Fetch news articles - Get last 10 articles
            news_articles = []
            if include_news:
                try:
                    if news_service.is_newsapi_available():
                        self.log(f"Fetching news articles for {search_term}", "INFO")
                        news_articles = await asyncio.wait_for(
                            news_service.fetch_crypto_news(
                                symbol=symbol,
                                keywords=[query] if query else None,
                                hours=hours
                            ),
                            timeout=15.0
                        )
                        # Validate news articles
                        if news_articles is None:
                            self.log("News articles returned None", "WARNING")
                            news_articles = []
                        elif not isinstance(news_articles, list):
                            self.log("News articles is not a list", "WARNING")
                            news_articles = []
                        # Limit to last 10 articles
                        news_articles = news_articles[:10]
                    else:
                        # Fallback: Use mock news data for testing when NewsAPI is not available
                        self.log("NewsAPI not available, using mock data for demonstration", "WARNING")
                        news_articles = self._get_mock_news_articles(symbol or query or "cryptocurrency")
                except asyncio.TimeoutError:
                    self.log("Timeout fetching news articles", "WARNING")
                    news_articles = []
                except Exception as e:
                    self.log(f"Error fetching news articles: {str(e)}", "WARNING")
                    news_articles = []
                
                # Analyze sentiment for each article using FinBERT
                for article in news_articles:
                    # Combine title and description for sentiment analysis
                    text = f"{article.get('title', '')} {article.get('description', '')}"
                    if not text.strip():
                        continue
                    
                    sentiment_result = await sentiment_service.analyze_sentiment(
                        text,
                        model_type="finbert"
                    )
                    
                    sentiment_result["article"] = {
                        "title": article.get("title"),
                        "url": article.get("url"),
                        "source": article.get("source"),
                        "published_at": article.get("published_at")
                    }
                    
                    results["news_sentiment"].append(sentiment_result)
                    results["sources"].append({
                        "type": "news",
                        "title": article.get("title"),
                        "url": article.get("url"),
                        "source": article.get("source")
                    })
                    
                    # Save to database if session provided
                    if db:
                        await self._save_news_article(db, article, sentiment_result, symbol)
            
            # Fetch Reddit posts
            if include_reddit and news_service.is_reddit_available():
                try:
                    self.log(f"Fetching Reddit posts for {search_term}", "INFO")
                    reddit_posts = await asyncio.wait_for(
                        news_service.fetch_crypto_reddit(
                            symbol=symbol,
                            limit=25
                        ),
                        timeout=15.0
                    )
                    # Validate reddit posts
                    if reddit_posts is None:
                        self.log("Reddit posts returned None", "WARNING")
                        reddit_posts = []
                    elif not isinstance(reddit_posts, list):
                        self.log("Reddit posts is not a list", "WARNING")
                        reddit_posts = []
                except asyncio.TimeoutError:
                    self.log("Timeout fetching Reddit posts", "WARNING")
                    reddit_posts = []
                except Exception as e:
                    self.log(f"Error fetching Reddit posts: {str(e)}", "WARNING")
                    reddit_posts = []
            else:
                reddit_posts = []
                
                # Analyze sentiment for each post
                for post in reddit_posts:
                    text = f"{post.get('title', '')} {post.get('content', '')}"
                    sentiment_result = await sentiment_service.analyze_sentiment(
                        text,
                        model_type="mbert"  # mBERT for multilingual Reddit
                    )
                    
                    sentiment_result["post"] = {
                        "title": post.get("title"),
                        "url": post.get("url"),
                        "subreddit": post.get("subreddit"),
                        "score": post.get("score"),
                        "num_comments": post.get("num_comments")
                    }
                    
                    results["reddit_sentiment"].append(sentiment_result)
                    results["sources"].append({
                        "type": "reddit",
                        "title": post.get("title"),
                        "url": post.get("url"),
                        "subreddit": post.get("subreddit")
                    })
                    
                    # Save to database if session provided
                    if db:
                        await self._save_reddit_post(db, post, sentiment_result, symbol)
            
            # Calculate overall sentiment
            all_scores = []
            all_scores.extend([s["score"] for s in results["news_sentiment"]])
            all_scores.extend([s["score"] for s in results["reddit_sentiment"]])
            
            if all_scores:
                avg_score = sum(all_scores) / len(all_scores)
                
                if avg_score > 0.2:
                    overall = "positive"
                elif avg_score < -0.2:
                    overall = "negative"
                else:
                    overall = "neutral"
                
                # Calculate gauge score (0-100, similar to Fear & Greed Index)
                # -1 to 1 score -> 0 to 100 gauge
                gauge_score = int((avg_score + 1) * 50)  # Convert -1..1 to 0..100
                
                # Generate explanation using News Analyst Agent (LLM)
                explanation = await self._generate_news_analysis(
                    symbol or query,
                    results["news_sentiment"],
                    overall,
                    avg_score,
                    lang,
                )
                
                results["overall_sentiment"] = {
                    "sentiment": overall,
                    "score": round(avg_score, 4),
                    "gauge_score": gauge_score,  # 0-100 for gauge chart
                    "confidence": min(1.0, abs(avg_score) * 2),
                    "sample_size": len(all_scores),
                    "explanation": explanation  # Why this score was given
                }
            else:
                no_data = (
                    "Not enough data. News or social posts are required for sentiment analysis."
                    if lang == "en"
                    else "Yeterli veri bulunamadı. Sentiment analizi için haber veya sosyal medya verisi gerekli."
                )
                results["overall_sentiment"] = {
                    "sentiment": "neutral",
                    "score": 0.0,
                    "gauge_score": 50,  # Neutral = 50
                    "confidence": 0.0,
                    "sample_size": 0,
                    "explanation": no_data,
                }
            
            self.log(f"Sentiment analysis completed for {search_term}", "INFO")
            return results
            
        except Exception as e:
            error_msg = str(e)
            self.log(f"Error in SentimentAgent: {error_msg}", "ERROR")
            self.log(f"Traceback: {traceback.format_exc()}", "ERROR")
            err_prefix = "Sentiment analysis error" if lang == "en" else "Sentiment analizi hatası"
            return {
                "success": False,
                "error": f"{err_prefix}: {error_msg}",
                "agent": self.name
            }
    
    async def _save_news_article(
        self,
        db: Session,
        article: Dict[str, Any],
        sentiment: Dict[str, Any],
        symbol: Optional[str]
    ):
        """Save news article and sentiment to database"""
        try:
            # Check if article already exists
            existing = db.query(NewsArticle).filter(
                NewsArticle.url == article.get("url")
            ).first()
            
            if existing:
                news_article = existing
            else:
                # Create new article
                published_at = None
                if article.get("published_at"):
                    try:
                        published_at = datetime.fromisoformat(
                            article["published_at"].replace("Z", "+00:00")
                        )
                    except:
                        pass
                
                news_article = NewsArticle(
                    title=article.get("title", ""),
                    description=article.get("description"),
                    content=article.get("content"),
                    url=article.get("url", ""),
                    source=article.get("source"),
                    author=article.get("author"),
                    published_at=published_at,
                    url_to_image=article.get("url_to_image"),
                    query=article.get("query"),
                    symbol=symbol
                )
                db.add(news_article)
                db.flush()
            
            # Create sentiment score
            sentiment_score = SentimentScore(
                article_id=news_article.id,
                text=f"{article.get('title', '')} {article.get('description', '')}",
                sentiment=sentiment.get("sentiment"),
                score=sentiment.get("score"),
                confidence=sentiment.get("confidence"),
                model=sentiment.get("model"),
                scores=sentiment.get("scores"),
                language="en"
            )
            db.add(sentiment_score)
            db.commit()
        
        except Exception as e:
            self.log(f"Error saving news article: {e}", "ERROR")
            db.rollback()
    
    async def _save_reddit_post(
        self,
        db: Session,
        post: Dict[str, Any],
        sentiment: Dict[str, Any],
        symbol: Optional[str]
    ):
        """Save Reddit post and sentiment to database"""
        try:
            # Check if post already exists
            existing = db.query(RedditPost).filter(
                RedditPost.url == post.get("url")
            ).first()
            
            if existing:
                reddit_post = existing
            else:
                # Create new post
                created_utc = None
                if post.get("created_utc"):
                    try:
                        created_utc = datetime.fromisoformat(post["created_utc"])
                    except:
                        pass
                
                reddit_post = RedditPost(
                    title=post.get("title", ""),
                    content=post.get("content"),
                    url=post.get("url", ""),
                    author=post.get("author"),
                    score=post.get("score", 0),
                    num_comments=post.get("num_comments", 0),
                    subreddit=post.get("subreddit"),
                    created_utc=created_utc,
                    symbol=symbol
                )
                db.add(reddit_post)
                db.flush()
            
            # Create sentiment score
            sentiment_score = SentimentScore(
                reddit_post_id=reddit_post.id,
                text=f"{post.get('title', '')} {post.get('content', '')}",
                sentiment=sentiment.get("sentiment"),
                score=sentiment.get("score"),
                confidence=sentiment.get("confidence"),
                model=sentiment.get("model"),
                scores=sentiment.get("scores"),
                language="en"
            )
            db.add(sentiment_score)
            db.commit()
        
        except Exception as e:
            self.log(f"Error saving Reddit post: {e}", "ERROR")
            db.rollback()
    
    async def _generate_news_analysis(
        self,
        symbol: str,
        news_sentiment: List[Dict[str, Any]],
        overall_sentiment: str,
        avg_score: float,
        lang: str = "en",
    ) -> str:
        """
        Generate news analysis summary using LLM (News Analyst Agent)
        Explains WHY the sentiment score was given
        """
        if not llm_service.is_available() or not news_sentiment:
            positive_count = sum(1 for s in news_sentiment if s.get("sentiment") == "positive")
            negative_count = sum(1 for s in news_sentiment if s.get("sentiment") == "negative")
            neutral_count = sum(1 for s in news_sentiment if s.get("sentiment") == "neutral")

            pos_pct = int(positive_count / len(news_sentiment) * 100) if news_sentiment else 0
            neg_pct = int(negative_count / len(news_sentiment) * 100) if news_sentiment else 0
            neu_pct = int(neutral_count / len(news_sentiment) * 100) if news_sentiment else 0

            if lang == "en":
                return (
                    f"Analysis of the last {len(news_sentiment)} headlines:\n"
                    f"- Positive: {positive_count} ({pos_pct}%)\n"
                    f"- Negative: {negative_count} ({neg_pct}%)\n"
                    f"- Neutral: {neutral_count} ({neu_pct}%)\n\n"
                    f"Overall sentiment: {overall_sentiment.upper()} (score: {avg_score:.3f})"
                )
            return f"""Son {len(news_sentiment)} haberin analizi:
- Pozitif: {positive_count} haber (%{pos_pct})
- Negatif: {negative_count} haber (%{neg_pct})
- Notr: {neutral_count} haber (%{neu_pct})

Genel sentiment: {overall_sentiment.upper()} (Skor: {avg_score:.3f})"""

        try:
            untitled = "Untitled" if lang == "en" else "Başlıksız"
            score_lbl = "Score" if lang == "en" else "Skor"
            news_summary = []
            for idx, item in enumerate(news_sentiment[:10], 1):
                article = item.get("article", {})
                sentiment = item.get("sentiment", "neutral")
                score = item.get("score", 0.0)
                news_summary.append(
                    f"{idx}. [{sentiment.upper()}] {article.get('title', untitled)} "
                    f"({score_lbl}: {score:.3f})"
                )

            positive_count = sum(1 for s in news_sentiment if s.get("sentiment") == "positive")
            negative_count = sum(1 for s in news_sentiment if s.get("sentiment") == "negative")
            neutral_count = sum(1 for s in news_sentiment if s.get("sentiment") == "neutral")

            if lang == "en":
                analysis_prompt = f"""You are a crypto news analyst. Explain why this sentiment score was assigned.

Asset: {symbol}
Overall sentiment: {overall_sentiment.upper()}
Average score: {avg_score:.3f} (-1 very negative, 0 neutral, +1 very positive)

Headline mix:
- Positive: {positive_count} ({int(positive_count / len(news_sentiment) * 100) if news_sentiment else 0}%)
- Negative: {negative_count} ({int(negative_count / len(news_sentiment) * 100) if news_sentiment else 0}%)
- Neutral: {neutral_count} ({int(neutral_count / len(news_sentiment) * 100) if news_sentiment else 0}%)

Recent headlines:
{chr(10).join(news_summary)}

Answer in English in 3–4 short sentences:
1) Why this score?
2) Which themes or headlines drove it?
3) Possible price impact?

Be professional and concise."""
            else:
                analysis_prompt = f"""Sen bir Kripto Para Haber Analisti'sin. Son haberleri analiz edip kullanıcıya neden bu sentiment skorunun verildiğini açıkla.

Kripto Para: {symbol}
Genel Sentiment: {overall_sentiment.upper()}
Ortalama Skor: {avg_score:.3f} (-1: çok negatif, 0: nötr, +1: çok pozitif)

Haber Dağılımı:
- Pozitif: {positive_count} haber (%{int(positive_count / len(news_sentiment) * 100) if news_sentiment else 0})
- Negatif: {negative_count} haber (%{int(negative_count / len(news_sentiment) * 100) if news_sentiment else 0})
- Nötr: {neutral_count} haber (%{int(neutral_count / len(news_sentiment) * 100) if news_sentiment else 0})

Son Haberler:
{chr(10).join(news_summary)}

Görevin: Kullanıcıya şunu açıkla:
1. Neden bu sentiment skoru verildi?
2. Hangi haberler/temalar bu skora etki etti?
3. Bu sentiment'in fiyat üzerindeki olası etkisi nedir?

Kısa ve öz bir analiz yap (3-4 cümle). Türkçe yanıt ver. Profesyonel ama anlaşılır dil kullan.
Örnek format: "Son 3 saatteki haberlerin %70'i regülasyonlarla ilgili ve negatif, bu durum fiyata baskı yapabilir" gibi."""

            llm_response = await llm_service.chat(analysis_prompt)
            explanation = llm_response.get("response", "")

            if not explanation or len(explanation.strip()) < 20:
                return self._generate_fallback_explanation(
                    news_sentiment, overall_sentiment, avg_score, lang
                )

            return explanation

        except Exception as e:
            self.log(f"Error generating news analysis: {e}", "ERROR")
            return self._generate_fallback_explanation(
                news_sentiment, overall_sentiment, avg_score, lang
            )

    def _generate_fallback_explanation(
        self,
        news_sentiment: List[Dict[str, Any]],
        overall_sentiment: str,
        avg_score: float,
        lang: str = "en",
    ) -> str:
        """Fallback explanation without LLM"""
        if not news_sentiment:
            return (
                "Not enough headline data."
                if lang == "en"
                else "Yeterli haber verisi bulunamadı."
            )

        positive_count = sum(1 for s in news_sentiment if s.get("sentiment") == "positive")
        negative_count = sum(1 for s in news_sentiment if s.get("sentiment") == "negative")
        total = len(news_sentiment)
        pos_pct = int(positive_count / total * 100) if total > 0 else 0
        neg_pct = int(negative_count / total * 100) if total > 0 else 0

        if lang == "en":
            if overall_sentiment == "positive":
                return (
                    f"About {pos_pct}% of the last {total} headlines skew positive, "
                    "which points to a constructive tone and may support upward pressure on price."
                )
            if overall_sentiment == "negative":
                return (
                    f"About {neg_pct}% of the last {total} headlines skew negative, "
                    "which points to a cautious tone and may weigh on price."
                )
            return (
                f"The last {total} headlines are mixed; positive and negative stories largely offset, "
                "suggesting a neutral market read."
            )

        if overall_sentiment == "positive":
            return f"Son {total} haberin %{pos_pct}'i pozitif sentiment gösteriyor. Bu durum genel olarak olumlu bir piyasa görünümüne işaret ediyor ve fiyat üzerinde yukarı yönlü bir baskı oluşturabilir."
        if overall_sentiment == "negative":
            return f"Son {total} haberin %{neg_pct}'i negatif sentiment gösteriyor. Bu durum genel olarak olumsuz bir piyasa görünümüne işaret ediyor ve fiyat üzerinde aşağı yönlü bir baskı oluşturabilir."
        return f"Son {total} haberin sentiment dağılımı dengeli görünüyor. Pozitif ve negatif haberler birbirini dengeleyerek nötr bir piyasa görünümü oluşturuyor."
    
    def _get_mock_news_articles(self, symbol: str) -> List[Dict[str, Any]]:
        """Generate mock news articles for testing when NewsAPI is not available"""
        from datetime import datetime, timedelta
        
        # Mock news articles with varying sentiment
        mock_articles = [
            {
                "title": f"{symbol} Price Surges After Major Institutional Adoption",
                "description": f"Major financial institutions announce {symbol} adoption, driving positive market sentiment.",
                "url": "https://example.com/news1",
                "source": "CryptoNews",
                "published_at": (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z",
                "author": "Crypto Analyst",
                "query": symbol
            },
            {
                "title": f"{symbol} Faces Regulatory Scrutiny in Key Markets",
                "description": f"Regulatory concerns emerge regarding {symbol} trading in several jurisdictions.",
                "url": "https://example.com/news2",
                "source": "FinanceDaily",
                "published_at": (datetime.utcnow() - timedelta(hours=2)).isoformat() + "Z",
                "author": "Market Reporter",
                "query": symbol
            },
            {
                "title": f"{symbol} Technical Analysis Shows Bullish Pattern",
                "description": f"Technical indicators suggest potential upward movement for {symbol} in coming days.",
                "url": "https://example.com/news3",
                "source": "TradingView",
                "published_at": (datetime.utcnow() - timedelta(hours=3)).isoformat() + "Z",
                "author": "Technical Analyst",
                "query": symbol
            },
            {
                "title": f"{symbol} Network Upgrade Successfully Completed",
                "description": f"Major network upgrade for {symbol} completed successfully, improving transaction speed.",
                "url": "https://example.com/news4",
                "source": "BlockchainNews",
                "published_at": (datetime.utcnow() - timedelta(hours=4)).isoformat() + "Z",
                "author": "Blockchain Expert",
                "query": symbol
            },
            {
                "title": f"{symbol} Trading Volume Hits Record High",
                "description": f"Trading volume for {symbol} reaches all-time high, indicating strong market interest.",
                "url": "https://example.com/news5",
                "source": "MarketWatch",
                "published_at": (datetime.utcnow() - timedelta(hours=5)).isoformat() + "Z",
                "author": "Market Analyst",
                "query": symbol
            },
            {
                "title": f"{symbol} Security Concerns Raised by Experts",
                "description": f"Security researchers identify potential vulnerabilities in {symbol} ecosystem.",
                "url": "https://example.com/news6",
                "source": "SecurityNews",
                "published_at": (datetime.utcnow() - timedelta(hours=6)).isoformat() + "Z",
                "author": "Security Expert",
                "query": symbol
            },
            {
                "title": f"{symbol} Partnership with Major Tech Company Announced",
                "description": f"Strategic partnership announced between {symbol} and leading technology firm.",
                "url": "https://example.com/news7",
                "source": "TechCrunch",
                "published_at": (datetime.utcnow() - timedelta(hours=7)).isoformat() + "Z",
                "author": "Tech Reporter",
                "query": symbol
            },
            {
                "title": f"{symbol} Market Cap Declines Amidst Market Correction",
                "description": f"Market capitalization for {symbol} decreases as broader crypto market corrects.",
                "url": "https://example.com/news8",
                "source": "CryptoMarket",
                "published_at": (datetime.utcnow() - timedelta(hours=8)).isoformat() + "Z",
                "author": "Market Analyst",
                "query": symbol
            },
            {
                "title": f"{symbol} Developer Activity Reaches New Heights",
                "description": f"GitHub activity for {symbol} shows increased developer engagement and project growth.",
                "url": "https://example.com/news9",
                "source": "DevNews",
                "published_at": (datetime.utcnow() - timedelta(hours=9)).isoformat() + "Z",
                "author": "Developer Reporter",
                "query": symbol
            },
            {
                "title": f"{symbol} Exchange Listing on Major Platform",
                "description": f"Major cryptocurrency exchange announces listing of {symbol}, increasing accessibility.",
                "url": "https://example.com/news10",
                "source": "ExchangeNews",
                "published_at": (datetime.utcnow() - timedelta(hours=10)).isoformat() + "Z",
                "author": "Exchange Reporter",
                "query": symbol
            }
        ]
        
        return mock_articles[:10]





