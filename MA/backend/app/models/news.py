"""
News and Sentiment Data Models
"""
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class NewsArticle(Base):
    """News article model"""
    __tablename__ = "news_articles"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    content = Column(Text)
    url = Column(String(1000), unique=True, nullable=False)
    source = Column(String(200))
    author = Column(String(200))
    published_at = Column(DateTime(timezone=True))
    url_to_image = Column(String(1000))
    query = Column(String(200))  # Search query used
    symbol = Column(String(50))  # Related cryptocurrency symbol
    collected_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    sentiment_scores = relationship("SentimentScore", back_populates="article", cascade="all, delete-orphan")


class SentimentScore(Base):
    """Sentiment analysis score for news articles or social media posts"""
    __tablename__ = "sentiment_scores"
    
    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey("news_articles.id"), nullable=True)
    reddit_post_id = Column(Integer, ForeignKey("reddit_posts.id"), nullable=True)
    
    text = Column(Text, nullable=False)
    sentiment = Column(String(20))  # positive, negative, neutral
    score = Column(Float)  # -1 to 1
    confidence = Column(Float)  # 0 to 1
    model = Column(String(50))  # finbert, mbert, fallback
    scores = Column(JSON)  # Detailed scores from model
    language = Column(String(10), default="en")
    analyzed_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    article = relationship("NewsArticle", back_populates="sentiment_scores")
    reddit_post = relationship("RedditPost", back_populates="sentiment_scores")


class RedditPost(Base):
    """Reddit post model"""
    __tablename__ = "reddit_posts"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    content = Column(Text)
    url = Column(String(1000), unique=True, nullable=False)
    author = Column(String(200))
    score = Column(Integer, default=0)
    num_comments = Column(Integer, default=0)
    subreddit = Column(String(200))
    created_utc = Column(DateTime(timezone=True))
    symbol = Column(String(50))  # Related cryptocurrency symbol
    collected_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    sentiment_scores = relationship("SentimentScore", back_populates="reddit_post", cascade="all, delete-orphan")


















