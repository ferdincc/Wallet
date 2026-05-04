"""
News and Social Media Data Collection Service
"""
from typing import Dict, Any, List, Optional
import logging
import asyncio
from datetime import datetime, timedelta
import aiohttp

logger = logging.getLogger(__name__)


class NewsService:
    """Service for collecting news and social media data"""
    
    def __init__(self):
        self.newsapi_key = None
        self.reddit_client = None
        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialize API clients"""
        try:
            # NewsAPI
            import os
            self.newsapi_key = os.getenv("NEWSAPI_KEY")
            if self.newsapi_key:
                logger.info("NewsAPI key found")
            else:
                logger.warning("NewsAPI key not found. News collection will be limited.")
            
            # Reddit (PRAW)
            try:
                import praw
                reddit_client_id = os.getenv("REDDIT_CLIENT_ID")
                reddit_client_secret = os.getenv("REDDIT_CLIENT_SECRET")
                reddit_user_agent = os.getenv("REDDIT_USER_AGENT", "OKYISS/1.0")
                
                if reddit_client_id and reddit_client_secret:
                    self.reddit_client = praw.Reddit(
                        client_id=reddit_client_id,
                        client_secret=reddit_client_secret,
                        user_agent=reddit_user_agent
                    )
                    logger.info("Reddit client initialized")
                else:
                    logger.warning("Reddit credentials not found")
            except ImportError:
                logger.warning("PRAW not installed. Install with: pip install praw")
            except Exception as e:
                logger.error(f"Error initializing Reddit: {e}")
        
        except Exception as e:
            logger.error(f"Error initializing news service: {e}")
    
    async def fetch_news(
        self,
        query: str,
        language: str = "en",
        sort_by: str = "relevancy",
        page_size: int = 20,
        hours: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch news articles from NewsAPI
        
        Args:
            query: Search query (e.g., "bitcoin", "cryptocurrency")
            language: Language code (en, tr, etc.)
            sort_by: Sort order (relevancy, popularity, publishedAt)
            page_size: Number of articles to fetch
        
        Returns:
            List of news articles
        """
        if not self.newsapi_key:
            logger.warning("NewsAPI key not available")
            return []
        
        try:
            url = "https://newsapi.org/v2/everything"
            params = {
                "q": query,
                "language": language,
                "sortBy": sort_by,
                "pageSize": page_size,
                "apiKey": self.newsapi_key
            }
            if hours is not None and hours > 0:
                from_dt = datetime.utcnow() - timedelta(hours=hours)
                params["from"] = from_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        articles = data.get("articles", [])
                        
                        normalized_articles = []
                        for article in articles:
                            normalized_articles.append({
                                "title": article.get("title", ""),
                                "description": article.get("description", ""),
                                "content": article.get("content", ""),
                                "url": article.get("url", ""),
                                "source": article.get("source", {}).get("name", "Unknown"),
                                "published_at": article.get("publishedAt", ""),
                                "author": article.get("author", ""),
                                "url_to_image": article.get("urlToImage", ""),
                                "query": query,
                                "collected_at": datetime.utcnow().isoformat()
                            })
                        
                        logger.info(f"Fetched {len(normalized_articles)} news articles for query: {query}")
                        return normalized_articles
                    else:
                        error_text = await response.text()
                        logger.error(f"NewsAPI error: {response.status} - {error_text}")
                        return []
        
        except Exception as e:
            logger.error(f"Error fetching news: {e}")
            return []
    
    async def fetch_crypto_news(
        self,
        symbol: str = None,
        keywords: List[str] = None,
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """
        Fetch cryptocurrency-related news
        
        Args:
            symbol: Cryptocurrency symbol (e.g., "BTC", "bitcoin")
            keywords: Additional keywords
            hours: How many hours back to search
        """
        # Build query
        query_parts = []
        if symbol:
            # Map common symbols to search terms
            symbol_map = {
                "BTC": "bitcoin",
                "ETH": "ethereum",
                "BNB": "binance coin",
                "SOL": "solana",
                "ADA": "cardano",
                "XRP": "ripple"
            }
            query_parts.append(symbol_map.get(symbol.upper(), symbol.lower()))
        
        if keywords:
            query_parts.extend(keywords)
        
        if not query_parts:
            query_parts = ["cryptocurrency", "crypto"]
        
        query = " OR ".join(query_parts)
        
        # Fetch news
        articles = await self.fetch_news(query, page_size=50)
        
        # Filter by time if needed
        if hours < 24:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            filtered_articles = []
            for article in articles:
                try:
                    pub_time = datetime.fromisoformat(article["published_at"].replace("Z", "+00:00"))
                    if pub_time >= cutoff_time:
                        filtered_articles.append(article)
                except:
                    # If parsing fails, include the article
                    filtered_articles.append(article)
            return filtered_articles
        
        return articles
    
    async def fetch_reddit_posts(
        self,
        subreddit: str = "cryptocurrency",
        limit: int = 25,
        time_filter: str = "day"
    ) -> List[Dict[str, Any]]:
        """
        Fetch Reddit posts from a subreddit
        
        Args:
            subreddit: Subreddit name
            limit: Number of posts to fetch
            time_filter: Time filter (hour, day, week, month, year, all)
        """
        if not self.reddit_client:
            logger.warning("Reddit client not available")
            return []
        
        try:
            subreddit_obj = self.reddit_client.subreddit(subreddit)
            posts = []
            
            # Fetch hot posts
            for post in subreddit_obj.hot(limit=limit):
                posts.append({
                    "title": post.title,
                    "content": post.selftext,
                    "url": f"https://reddit.com{post.permalink}",
                    "author": str(post.author) if post.author else "Unknown",
                    "score": post.score,
                    "num_comments": post.num_comments,
                    "created_utc": datetime.fromtimestamp(post.created_utc).isoformat(),
                    "subreddit": subreddit,
                    "source": "reddit",
                    "collected_at": datetime.utcnow().isoformat()
                })
            
            logger.info(f"Fetched {len(posts)} Reddit posts from r/{subreddit}")
            return posts
        
        except Exception as e:
            logger.error(f"Error fetching Reddit posts: {e}")
            return []
    
    async def fetch_crypto_reddit(
        self,
        symbol: str = None,
        subreddits: List[str] = None,
        limit: int = 25
    ) -> List[Dict[str, Any]]:
        """
        Fetch cryptocurrency-related Reddit posts
        
        Args:
            symbol: Cryptocurrency symbol
            subreddits: List of subreddits to search
            limit: Posts per subreddit
        """
        if not subreddits:
            subreddits = ["cryptocurrency", "Bitcoin", "ethereum", "CryptoCurrency"]
        
        if symbol:
            # Add symbol-specific subreddits
            symbol_lower = symbol.lower()
            if symbol_lower == "btc" or "bitcoin" in symbol_lower:
                subreddits.append("Bitcoin")
            elif symbol_lower == "eth" or "ethereum" in symbol_lower:
                subreddits.append("ethereum")
        
        all_posts = []
        for subreddit in subreddits:
            try:
                posts = await asyncio.to_thread(
                    self._fetch_reddit_sync,
                    subreddit,
                    limit
                )
                all_posts.extend(posts)
            except Exception as e:
                logger.error(f"Error fetching from r/{subreddit}: {e}")
        
        return all_posts
    
    def _fetch_reddit_sync(self, subreddit: str, limit: int) -> List[Dict[str, Any]]:
        """Synchronous Reddit fetching (runs in thread pool)"""
        if not self.reddit_client:
            return []
        
        subreddit_obj = self.reddit_client.subreddit(subreddit)
        posts = []
        
        for post in subreddit_obj.hot(limit=limit):
            posts.append({
                "title": post.title,
                "content": post.selftext,
                "url": f"https://reddit.com{post.permalink}",
                "author": str(post.author) if post.author else "Unknown",
                "score": post.score,
                "num_comments": post.num_comments,
                "created_utc": datetime.fromtimestamp(post.created_utc).isoformat(),
                "subreddit": subreddit,
                "source": "reddit",
                "collected_at": datetime.utcnow().isoformat()
            })
        
        return posts
    
    def is_newsapi_available(self) -> bool:
        """Check if NewsAPI is available"""
        return self.newsapi_key is not None
    
    def is_reddit_available(self) -> bool:
        """Check if Reddit API is available"""
        return self.reddit_client is not None


# Global instance
news_service = NewsService()


















