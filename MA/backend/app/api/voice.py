"""
Voice API endpoints for speech-to-text and text-to-speech
"""
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from typing import Optional

from app.services.voice_service import voice_service
from app.agents.chat_agent import ChatAgent
from app.database import get_db
from sqlalchemy.orm import Session
from fastapi import Depends

router = APIRouter()
chat_agent = ChatAgent()


class VoiceCommandRequest(BaseModel):
    transcript: str
    user_id: Optional[int] = None


class VoiceResponseRequest(BaseModel):
    text: str


@router.post("/command")
async def process_voice_command(
    request: VoiceCommandRequest,
    db: Session = Depends(get_db)
):
    """
    Process voice command transcript
    
    Frontend sends speech-to-text transcript, backend processes it
    and returns response that can be converted to speech.
    """
    try:
        # Process voice command
        voice_result = await voice_service.process_voice_command(request.transcript)
        
        if not voice_result.get("success"):
            raise HTTPException(
                status_code=400,
                detail="Voice command processing failed"
            )
        
        # Get intent
        intent = voice_result.get("intent", {})
        
        # Execute command via ChatAgent
        result = await chat_agent.execute(
            query=intent.get("query", request.transcript),
            user_id=request.user_id,
            db=db
        )
        
        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Command execution failed")
            )
        
        # Generate voice response
        response_text = result.get("response", "")
        voice_response = voice_service.generate_voice_response(response_text)
        
        return {
            "success": True,
            "transcript": request.transcript,
            "intent": intent,
            "response": response_text,
            "voice_response": voice_response,
            "agent_data": result.get("agent_data")
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/response")
async def generate_voice_response(request: VoiceResponseRequest):
    """
    Generate voice response data from text
    
    Returns cleaned text ready for browser TTS.
    """
    try:
        voice_response = voice_service.generate_voice_response(request.text)
        return voice_response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def voice_health():
    """Check voice service health"""
    return {
        "status": "healthy",
        "stt_available": voice_service.is_stt_available(),
        "tts_available": voice_service.is_tts_available()
    }












