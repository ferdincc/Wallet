"""
Chat API endpoints for LLM-based chatbot
"""
import logging
import traceback
from fastapi import APIRouter, HTTPException, Body, Depends
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from app.agents.chat_agent import ChatAgent
from app.database import get_db

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter()
chat_agent = ChatAgent()


class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # Mevcut istemciler: query | Yeni: message
    query: Optional[str] = None
    message: Optional[str] = None
    user_id: Optional[int] = None
    context: Optional[List[Dict[str, str]]] = None
    conversation_history: Optional[List[Dict[str, str]]] = Field(
        default=None,
        alias="conversationHistory",
    )
    last_agent_context: Optional[str] = Field(default=None, alias="lastAgentContext")
    wallet_address: Optional[str] = None
    wallet_context: Optional[str] = Field(default=None, alias="walletContext")
    locale: Optional[str] = None  # en | tr — agent-facing copy


class ChatResponse(BaseModel):
    success: bool
    response: str
    intent: Optional[Dict[str, Any]] = None
    agent_data: Optional[Dict[str, Any]] = None
    reasoning_log: Optional[Dict[str, Any]] = None
    agent: Optional[str] = None
    response_mode: Optional[str] = None  # "agent" | "chat"
    mode: Optional[str] = None  # response_mode ile aynı (istemci uyumu)
    language: Optional[str] = None  # tr | en | other | auto


@router.post("/message", response_model=ChatResponse)
async def send_message(request: ChatRequest, db: Session = Depends(get_db)):
    """Send a message to the chat agent"""
    import asyncio
    
    text = (request.message or request.query or "").strip()
    if not text:
        logger.warning("Empty query received")
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty. Please enter a question or command.",
        )

    conv = (
        request.conversation_history
        if request.conversation_history is not None
        else request.context
    )

    logger.info(f"Processing chat query: {text[:100]}...")

    try:
        # Add timeout to prevent hanging
        result = await asyncio.wait_for(
            chat_agent.execute(
                query=text,
                user_id=request.user_id,
                db=db,
                wallet_address=request.wallet_address,
                conversation_history=conv,
                last_agent_context=request.last_agent_context,
                wallet_context=request.wallet_context,
                locale=request.locale,
            ),
            timeout=90.0  # 90 second timeout for comprehensive analysis
        )
        
        response_text = (result.get("response") or "").strip()
        if not result.get("success") and not response_text:
            error_msg = result.get("error", "Bilinmeyen hata")
            logger.error(f"Chat agent returned error: {error_msg}")
            raise HTTPException(
                status_code=500,
                detail=f"An error occurred while processing your request: {error_msg}",
            )

        if not result.get("success") and response_text:
            logger.warning(
                "Chat agent success=False but response present; returning 200 for UX: %s",
                result.get("error", ""),
            )

        logger.info("Chat query processed successfully")
        rm = result.get("response_mode")
        return ChatResponse(
            success=bool(result.get("success", True)),
            response=response_text or result.get("response", ""),
            intent=result.get("intent"),
            agent_data=result.get("agent_data"),
            reasoning_log=result.get("reasoning_log"),
            agent=result.get("agent"),
            response_mode=rm,
            mode=rm,
            language=result.get("language"),
        )
        
    except asyncio.TimeoutError:
        logger.error(f"Chat query timeout after 90 seconds: {text[:100]}")
        raise HTTPException(
            status_code=504,
            detail="Request timed out. The analysis may be taking too long. Please try again later or simplify your message.",
        )
    except HTTPException:
        raise
    except Exception as e:
        error_detail = str(e)
        traceback_str = traceback.format_exc()
        logger.error(f"Chat error: {error_detail}")
        logger.error(f"Traceback: {traceback_str}")
        raise HTTPException(
            status_code=500,
            detail=f"Server error: {error_detail}. Please try again.",
        )


@router.get("/health")
async def chat_health():
    """Check chat service health"""
    from app.agents.llm_service import llm_service
    from app.services.claude_chat_service import get_anthropic_api_key, is_claude_chat_available

    return {
        "status": "healthy",
        "llm_available": llm_service.is_available(),
        "claude_chat_available": is_claude_chat_available(),
        "anthropic_api_key_configured": bool(get_anthropic_api_key()),
    }


@router.get("/test-llm")
async def test_llm():
    """
    Calls Claude with a minimal prompt. Use to verify ANTHROPIC_API_KEY and SDK.
    Chat uses the Python backend — key must be in MA/backend/.env
    """
    from app.services.claude_chat_service import test_claude_minimal_message

    return await test_claude_minimal_message()

