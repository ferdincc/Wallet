"""
Main FastAPI application
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from app.config import settings
from app.api import markets, chat, simulation, websocket, news, prediction, analyze, whale_alert, voice, alerts, ablation
from app.database import engine, Base
from app.db_migrations import ensure_users_risk_columns, normalize_users_risk_appetite_values

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Console output
    ]
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events for startup and shutdown"""
    # Startup
    logger.info("Starting OKYISS...")
    print("Starting OKYISS...")
    try:
        from app.services.claude_chat_service import get_anthropic_api_key, is_claude_chat_available

        logger.info(
            "Claude chat: %s (ANTHROPIC_API_KEY set: %s)",
            "enabled" if is_claude_chat_available() else "disabled",
            bool(get_anthropic_api_key()),
        )
    except Exception as e:
        logger.warning("Could not read Claude status: %s", e)
    # Create database tables
    try:
        Base.metadata.create_all(bind=engine)
        ensure_users_risk_columns(engine)
        normalize_users_risk_appetite_values(engine)
        logger.info("Database tables created/verified")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}", exc_info=True)
    yield
    # Shutdown
    logger.info("Shutting down OKYISS...")
    print("Shutting down OKYISS...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(markets.router, prefix=f"{settings.API_V1_PREFIX}/markets", tags=["Markets"])
app.include_router(chat.router, prefix=f"{settings.API_V1_PREFIX}/chat", tags=["Chat"])
# İstemciler için kısa yol: POST /api/chat/message  (aynı handler)
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(simulation.router, prefix=f"{settings.API_V1_PREFIX}/simulation", tags=["Simulation"])
app.include_router(websocket.router, prefix=f"{settings.API_V1_PREFIX}/ws", tags=["WebSocket"])
app.include_router(news.router, prefix=f"{settings.API_V1_PREFIX}/news", tags=["News & Sentiment"])
app.include_router(prediction.router, prefix=f"{settings.API_V1_PREFIX}/predict", tags=["Prediction"])
app.include_router(analyze.router, prefix=f"{settings.API_V1_PREFIX}", tags=["Analysis"])
app.include_router(whale_alert.router, prefix=f"{settings.API_V1_PREFIX}", tags=["Whale Alert"])
app.include_router(voice.router, prefix=f"{settings.API_V1_PREFIX}/voice", tags=["Voice"])
app.include_router(alerts.router, prefix=f"{settings.API_V1_PREFIX}/alerts", tags=["Alerts"])
app.include_router(ablation.router, prefix=f"{settings.API_V1_PREFIX}/ablation", tags=["Ablation Study"])


@app.get("/")
async def root():
    """Root endpoint"""
    return JSONResponse({
        "message": "OKYİSS API",
        "version": settings.VERSION,
        "docs": "/docs"
    })


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return JSONResponse({"status": "healthy"})

