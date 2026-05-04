"""
Application configuration settings
"""
import os
from pathlib import Path
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

# backend/.env (Chat / Claude) — önce kök .env, sonra backend/.env ile override (anahtar burada olmalı)
BACKEND_ROOT = Path(__file__).resolve().parent.parent


def reload_dotenv_files() -> None:
    """İşlem içi yeniden yükleme (test ve Claude çağrısı öncesi). Kök sonra backend kazanır."""
    try:
        from dotenv import load_dotenv

        load_dotenv(BACKEND_ROOT.parent / ".env", override=False)
        load_dotenv(BACKEND_ROOT / ".env", override=True)
    except ImportError:
        pass


try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_ROOT.parent / ".env", override=False)
    load_dotenv(BACKEND_ROOT / ".env", override=True)
except ImportError:
    pass


class Settings(BaseSettings):
    """Application settings"""

    model_config = SettingsConfigDict(
        env_file=(
            str(BACKEND_ROOT.parent / ".env"),
            str(BACKEND_ROOT / ".env"),
        ),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # API Settings
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "OKYİSS - Otonom Kripto Yatırım İstihbarat ve Simülasyon Sistemi"
    VERSION: str = "1.0.0"
    
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "sqlite:///./okyiss.db"  # SQLite for easy testing without PostgreSQL
    )
    
    # Redis (for caching and WebSocket)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Exchange API Keys (optional for public data; simülasyon kullanıcı anahtarları DB'de)
    BINANCE_API_KEY: Optional[str] = os.getenv("BINANCE_API_KEY", None)
    BINANCE_API_SECRET: Optional[str] = os.getenv("BINANCE_API_SECRET", None)
    # ccxt HTTP zaman aşımı (ms); Binance vb. çağrılar bu sürede kesilir
    EXCHANGE_CCXT_TIMEOUT_MS: int = int(os.getenv("EXCHANGE_CCXT_TIMEOUT_MS", "15000"))
    # Özel (imzalı) uçlar: bakiye / emir / pozisyon — daha uzun süre
    EXCHANGE_PRIVATE_TIMEOUT_MS: int = int(os.getenv("EXCHANGE_PRIVATE_TIMEOUT_MS", "15000"))
    # Binance recvWindow (ms); "Timestamp outside recvWindow" için artırılabilir
    BINANCE_RECV_WINDOW_MS: int = int(os.getenv("BINANCE_RECV_WINDOW_MS", "60000"))
    # Binance izleme portföyü (myTrades + ticker, çoklu coin) toplam asyncio timeout (sn)
    WATCH_PORTFOLIO_TIMEOUT_SEC: float = float(os.getenv("WATCH_PORTFOLIO_TIMEOUT_SEC", "120"))
    COINBASE_API_KEY: Optional[str] = os.getenv("COINBASE_API_KEY", None)
    COINBASE_API_SECRET: Optional[str] = os.getenv("COINBASE_API_SECRET", None)
    KRAKEN_API_KEY: Optional[str] = os.getenv("KRAKEN_API_KEY", None)
    KRAKEN_API_SECRET: Optional[str] = os.getenv("KRAKEN_API_SECRET", None)
    
    # News and Social Media API Keys
    NEWSAPI_KEY: Optional[str] = os.getenv("NEWSAPI_KEY", None)
    REDDIT_CLIENT_ID: Optional[str] = os.getenv("REDDIT_CLIENT_ID", None)
    REDDIT_CLIENT_SECRET: Optional[str] = os.getenv("REDDIT_CLIENT_SECRET", None)
    REDDIT_USER_AGENT: Optional[str] = os.getenv("REDDIT_USER_AGENT", "OKYISS/1.0")
    
    # LLM Settings
    LLM_MODEL_NAME: str = os.getenv("LLM_MODEL_NAME", "llama3")
    LLM_API_BASE: Optional[str] = os.getenv("LLM_API_BASE", None)  # Ollama or other API
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    LANGCHAIN_TRACING_V2: bool = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    LANGCHAIN_API_KEY: Optional[str] = os.getenv("LANGCHAIN_API_KEY", None)

    # Anthropic Claude — env + .env dosyaları (model_config); load_dotenv ile de yüklendi
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None)
    CLAUDE_CHAT_MODEL: str = Field(default="claude-sonnet-4-20250514")
    
    # Whale Alert API
    WHALE_ALERT_API_KEY: Optional[str] = os.getenv("WHALE_ALERT_API_KEY", None)
    
    # Node News API (RSS + Reddit + Fear & Greed)
    NODE_NEWS_API_URL: str = os.getenv("NODE_NEWS_API_URL", "http://127.0.0.1:3001/api/news")
    # Node backend base (kampanya, cüzdan, backtest; path /api/... ile eklenir)
    NODE_BACKEND_BASE_URL: str = os.getenv("NODE_BACKEND_BASE_URL", "http://127.0.0.1:3010")
    
    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = 30  # seconds
    
    # CORS 
    CORS_ORIGINS: list = ["*"]  # Allow all origins for testing

    @model_validator(mode="after")
    def binance_secret_env_alias(self):
        """BINANCE_SECRET_KEY, BINANCE_API_SECRET boşsa kullanılır."""
        cur = self.BINANCE_API_SECRET
        if cur is None or (isinstance(cur, str) and not cur.strip()):
            alt = os.getenv("BINANCE_SECRET_KEY")
            if alt and alt.strip():
                object.__setattr__(self, "BINANCE_API_SECRET", alt.strip())
        # Ek güvence: ANTHROPIC sadece os.environ'da kaldıysa
        ak = self.ANTHROPIC_API_KEY
        if ak is None or (isinstance(ak, str) and not ak.strip()):
            alt_a = os.getenv("ANTHROPIC_API_KEY")
            if alt_a and alt_a.strip():
                object.__setattr__(self, "ANTHROPIC_API_KEY", alt_a.strip())
        return self


settings = Settings()
