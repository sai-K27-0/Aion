"""
Voice API Endpoints - Complete voice interaction system.

Provides:
- Text-to-Speech conversion
- Speech-to-Text transcription
- Voice command processing
- Voice configuration
"""

import base64
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field

from app.services.voice_assistant_service import (
    get_voice_assistant,
    NATURAL_VOICES,
    VoiceConfig,
)
from app.services.ai_service import get_ai_service
from app.services.smart_model_router import get_smart_router
from app.services.action_executor import get_action_executor
from app.services.user_profile_service import get_profile_service
from app.services.realtime_conversation_service import (
    get_conversation,
    end_conversation,
    PERSONAS,
)

router = APIRouter()


# ============================================================================
# Schemas
# ============================================================================

class TTSRequest(BaseModel):
    """Request for text-to-speech."""
    text: str = Field(..., min_length=1, max_length=5000)
    voice: Optional[str] = Field(None, description="Voice name (guy, jenny, aria, etc.)")
    rate: Optional[str] = Field(None, description="Speech rate (+10%, -20%, etc.)")
    pitch: Optional[str] = Field(None, description="Voice pitch (+5Hz, -10Hz, etc.)")


class TTSResponse(BaseModel):
    """Response with audio data."""
    audio_base64: str
    format: str = "mp3"
    voice_used: str


class TranscriptionResponse(BaseModel):
    """Response from transcription."""
    text: str
    language: str
    confidence: float
    duration: float


class VoiceCommandRequest(BaseModel):
    """Request for voice command processing."""
    audio_base64: str = Field(..., description="Base64 encoded audio (WAV)")
    user_id: str = "default"
    execute_actions: bool = True


class VoiceCommandResponse(BaseModel):
    """Response from voice command."""
    success: bool
    user_text: Optional[str] = None
    ai_response: Optional[str] = None
    audio_base64: Optional[str] = None
    actions_executed: int = 0
    error: Optional[str] = None


class VoiceConfigUpdate(BaseModel):
    """Update voice configuration."""
    voice: Optional[str] = None
    whisper_model: Optional[str] = None
    language: Optional[str] = None
    wake_word: Optional[str] = None


# ============================================================================
# Text-to-Speech Endpoints
# ============================================================================

@router.post(
    "/tts",
    response_model=TTSResponse,
    summary="Text to Speech",
    description="Convert text to natural speech audio.",
)
async def text_to_speech(request: TTSRequest):
    """
    Convert text to speech using natural Microsoft voices.
    
    Returns base64 encoded MP3 audio.
    """
    voice_assistant = get_voice_assistant()
    
    try:
        audio_bytes = await voice_assistant.text_to_speech(
            text=request.text,
            voice=request.voice,
            rate=request.rate,
            pitch=request.pitch,
        )
        
        return TTSResponse(
            audio_base64=base64.b64encode(audio_bytes).decode(),
            format="mp3",
            voice_used=request.voice or voice_assistant.config.tts_voice,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS failed: {str(e)}")


@router.post(
    "/tts/stream",
    summary="Stream Text to Speech",
    description="Stream audio chunks for real-time playback.",
)
async def stream_tts(request: TTSRequest):
    """
    Stream TTS audio for real-time playback.
    
    Returns MP3 audio stream.
    """
    voice_assistant = get_voice_assistant()
    
    async def audio_generator():
        async for chunk in voice_assistant.text_to_speech_stream(
            text=request.text,
            voice=request.voice,
        ):
            yield chunk
    
    return StreamingResponse(
        audio_generator(),
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": "inline; filename=speech.mp3",
        },
    )


@router.get(
    "/tts/speak",
    summary="Quick Speak",
    description="Quick endpoint to speak text (returns audio file).",
)
async def quick_speak(
    text: str = Query(..., min_length=1, max_length=1000),
    voice: str = Query("guy", description="Voice to use"),
):
    """
    Quick endpoint to speak text.
    
    Returns MP3 audio directly (playable in browser).
    """
    voice_assistant = get_voice_assistant()
    
    try:
        audio_bytes = await voice_assistant.text_to_speech(text, voice)
        
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": f"inline; filename=speech.mp3",
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/tts/voices",
    summary="List Voices",
    description="Get available TTS voices.",
)
async def list_voices(language: str = Query("en", description="Language code")):
    """List all available TTS voices for a language."""
    voice_assistant = get_voice_assistant()
    
    voices = await voice_assistant.list_voices(language)
    
    return {
        "language": language,
        "voices": voices,
        "recommended": NATURAL_VOICES,
    }


# ============================================================================
# Speech-to-Text Endpoints
# ============================================================================

@router.post(
    "/stt",
    response_model=TranscriptionResponse,
    summary="Speech to Text",
    description="Transcribe audio to text using Whisper.",
)
async def speech_to_text(
    audio: UploadFile = File(..., description="Audio file (WAV, MP3, etc.)"),
    language: Optional[str] = Query(None, description="Language code"),
):
    """
    Transcribe audio file to text.
    
    Supports WAV, MP3, and other common formats.
    """
    voice_assistant = get_voice_assistant()
    
    try:
        audio_bytes = await audio.read()
        
        result = await voice_assistant.transcribe_audio(audio_bytes, language)
        
        return TranscriptionResponse(
            text=result["text"],
            language=result["language"],
            confidence=result["language_probability"],
            duration=result["duration"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


@router.post(
    "/stt/base64",
    response_model=TranscriptionResponse,
    summary="Transcribe Base64 Audio",
    description="Transcribe base64 encoded audio.",
)
async def transcribe_base64(
    audio_base64: str = Query(..., description="Base64 encoded audio"),
    language: Optional[str] = Query(None, description="Language code"),
):
    """Transcribe base64 encoded audio."""
    voice_assistant = get_voice_assistant()
    
    try:
        audio_bytes = base64.b64decode(audio_base64)
        result = await voice_assistant.transcribe_audio(audio_bytes, language)
        
        return TranscriptionResponse(
            text=result["text"],
            language=result["language"],
            confidence=result["language_probability"],
            duration=result["duration"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Voice Command (Full Pipeline)
# ============================================================================

@router.post(
    "/command",
    response_model=VoiceCommandResponse,
    summary="Process Voice Command",
    description="Full voice command pipeline: STT -> AI -> TTS",
)
async def process_voice_command(request: VoiceCommandRequest):
    """
    Process a voice command through the full pipeline:
    1. Transcribe audio to text
    2. Process with AI (with action execution)
    3. Convert response to speech
    
    Returns both text and audio response.
    """
    voice_assistant = get_voice_assistant()
    ai_service = get_ai_service()
    smart_router = get_smart_router()
    action_executor = get_action_executor()
    profile_service = get_profile_service()
    
    try:
        # Decode audio
        audio_bytes = base64.b64decode(request.audio_base64)
        
        # 1. Transcribe
        transcription = await voice_assistant.transcribe_audio(audio_bytes)
        user_text = transcription["text"]
        
        if not user_text:
            return VoiceCommandResponse(
                success=False,
                error="Could not understand audio",
            )
        
        # Extract facts from speech
        await profile_service.extract_facts(request.user_id, user_text)
        
        # 2. Route to optimal model
        routing = await smart_router.route(user_text)
        model = routing["model"]
        
        # Get profile context
        profile_context = profile_service.get_context_for_prompt(request.user_id)
        
        # Build voice-optimized system prompt
        tools_desc = action_executor.get_tools_description()
        
        system_prompt = f"""You are Aion, a helpful voice assistant. You are speaking to the user.

{profile_context}

IMPORTANT VOICE GUIDELINES:
- Be CONCISE. This is voice, not text. Keep responses under 2-3 sentences.
- Sound natural and conversational.
- Don't use markdown, lists, or formatting.
- Speak times naturally: "six forty PM" not "18:40:00".
- Don't read out long lists unless asked.

You can perform actions:
{tools_desc}

Include actions as: [ACTION: action_name | param=value]
"""
        
        # Get AI response
        ai_response = await ai_service.chat(
            message=user_text,
            system_prompt=system_prompt,
            temperature=0.7,
            model=model,
        )
        
        # Parse and execute actions
        import re
        actions_executed = 0
        clean_response = ai_response
        
        if request.execute_actions:
            action_pattern = r'\[ACTION:\s*(\w+)\s*(?:\|([^\]]+))?\]'
            matches = re.findall(action_pattern, ai_response)
            
            for match in matches:
                action_type = match[0]
                params_str = match[1] if match[1] else ""
                
                params = {}
                if params_str:
                    for param in params_str.split("|"):
                        if "=" in param:
                            key, value = param.split("=", 1)
                            params[key.strip()] = value.strip()
                
                result = await action_executor.execute(action_type, params)
                if result.success:
                    actions_executed += 1
            
            clean_response = re.sub(action_pattern, '', ai_response).strip()
        
        # 3. Convert to speech
        audio_response = await voice_assistant.text_to_speech(clean_response)
        
        return VoiceCommandResponse(
            success=True,
            user_text=user_text,
            ai_response=clean_response,
            audio_base64=base64.b64encode(audio_response).decode(),
            actions_executed=actions_executed,
        )
        
    except Exception as e:
        return VoiceCommandResponse(
            success=False,
            error=str(e),
        )


# ============================================================================
# Configuration
# ============================================================================

@router.get(
    "/config",
    summary="Get Voice Configuration",
    description="Get current voice assistant settings.",
)
async def get_voice_config():
    """Get current voice configuration."""
    voice_assistant = get_voice_assistant()
    return voice_assistant.get_state()


@router.post(
    "/config",
    summary="Update Voice Configuration",
    description="Update voice assistant settings.",
)
async def update_voice_config(config: VoiceConfigUpdate):
    """Update voice configuration."""
    voice_assistant = get_voice_assistant()
    
    if config.voice:
        voice_assistant.set_voice(config.voice)
    
    if config.whisper_model:
        voice_assistant.set_whisper_model(config.whisper_model)
    
    if config.language:
        voice_assistant.config.language = config.language
    
    return voice_assistant.get_state()


# ============================================================================
# WebSocket for Real-time Voice
# ============================================================================

@router.websocket("/ws")
async def voice_websocket(websocket: WebSocket):
    """
    Real-time voice WebSocket.
    
    Protocol:
    1. Client sends audio chunks (binary)
    2. Server detects wake word
    3. On wake word, server starts recording
    4. When speech ends, server processes and responds
    5. Server sends audio response (binary)
    
    Text messages for control:
    - {"type": "config", "voice": "guy"}
    - {"type": "speak", "text": "Hello"}
    """
    await websocket.accept()
    
    voice_assistant = get_voice_assistant()
    ai_service = get_ai_service()
    action_executor = get_action_executor()
    
    is_recording = False
    audio_buffer = b""
    
    try:
        while True:
            message = await websocket.receive()
            
            if "bytes" in message:
                # Audio data
                audio_chunk = message["bytes"]
                
                if not is_recording:
                    # Check for wake word
                    try:
                        if await voice_assistant.detect_wake_word(audio_chunk):
                            is_recording = True
                            audio_buffer = b""
                            await websocket.send_json({
                                "type": "wake_detected",
                                "message": "Listening...",
                            })
                    except Exception:
                        # Wake word detection not available
                        pass
                else:
                    # Recording command
                    audio_buffer += audio_chunk
                    
                    # Check for end of speech
                    if not voice_assistant.detect_speech(audio_chunk):
                        # End of speech - process command
                        if len(audio_buffer) > 0:
                            await websocket.send_json({
                                "type": "processing",
                                "message": "Processing...",
                            })
                            
                            # Process the voice command
                            try:
                                result = await voice_assistant.transcribe_audio(audio_buffer)
                                user_text = result["text"]
                                
                                if user_text:
                                    await websocket.send_json({
                                        "type": "transcription",
                                        "text": user_text,
                                    })
                                    
                                    # Get AI response
                                    response = await ai_service.chat(
                                        message=user_text,
                                        system_prompt="You are Aion. Be concise, this is voice conversation.",
                                    )
                                    
                                    await websocket.send_json({
                                        "type": "response",
                                        "text": response,
                                    })
                                    
                                    # Send audio response
                                    audio_response = await voice_assistant.text_to_speech(response)
                                    await websocket.send_bytes(audio_response)
                            except Exception as e:
                                await websocket.send_json({
                                    "type": "error",
                                    "message": str(e),
                                })
                        
                        is_recording = False
                        audio_buffer = b""
            
            elif "text" in message:
                # Text command
                import json
                data = json.loads(message["text"])
                
                if data.get("type") == "speak":
                    # Speak text
                    text = data.get("text", "")
                    audio = await voice_assistant.text_to_speech(text)
                    await websocket.send_bytes(audio)
                
                elif data.get("type") == "config":
                    # Update config
                    if "voice" in data:
                        voice_assistant.set_voice(data["voice"])
                    await websocket.send_json({
                        "type": "config_updated",
                        "config": voice_assistant.get_state(),
                    })
                
                elif data.get("type") == "start_listening":
                    # Manual start
                    is_recording = True
                    audio_buffer = b""
                    await websocket.send_json({
                        "type": "listening",
                        "message": "Speak now...",
                    })
    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
            })
        except:
            pass


# ============================================================================
# Real-time Natural Conversation
# ============================================================================

class ConversationRequest(BaseModel):
    """Request for natural conversation."""
    message: str
    user_id: str = "default"
    persona: str = "aion"
    include_audio: bool = True


class ConversationResponse(BaseModel):
    """Response from natural conversation."""
    response: str
    emotion: str
    audio_base64: Optional[str] = None
    model: str
    turn_count: int
    persona: str


@router.post(
    "/conversation",
    response_model=ConversationResponse,
    summary="Natural Conversation",
    description="Have a natural voice conversation with context memory.",
)
async def natural_conversation(request: ConversationRequest):
    """
    Natural conversation endpoint with:
    - Context memory across turns
    - Emotion-aware responses
    - Multiple personas
    - Natural, concise responses
    """
    conversation = get_conversation(request.user_id, request.persona)
    
    try:
        if request.include_audio:
            result = await conversation.generate_voice_response(
                request.message,
                request.user_id,
            )
            
            import base64
            return ConversationResponse(
                response=result["response"],
                emotion=result["emotion"],
                audio_base64=base64.b64encode(result["audio"]).decode(),
                model=result["model"],
                turn_count=result["turn_count"],
                persona=conversation.persona.name,
            )
        else:
            result = await conversation.generate_response(
                request.message,
                request.user_id,
            )
            
            return ConversationResponse(
                response=result["response"],
                emotion=result["emotion"],
                model=result["model"],
                turn_count=result["turn_count"],
                persona=conversation.persona.name,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/conversation/personas",
    summary="List Personas",
    description="Get available conversation personas.",
)
async def list_personas():
    """List all available conversation personas."""
    return {
        "personas": {
            name: {
                "name": persona.name,
                "voice": persona.voice_id,
                "personality": persona.personality,
            }
            for name, persona in PERSONAS.items()
        }
    }


@router.post(
    "/conversation/reset",
    summary="Reset Conversation",
    description="Reset conversation history for a user.",
)
async def reset_conversation(user_id: str = Query("default")):
    """Reset conversation history."""
    end_conversation(user_id)
    return {"success": True, "message": "Conversation reset"}


@router.get(
    "/conversation/status",
    summary="Conversation Status",
    description="Get status of current conversation.",
)
async def conversation_status(user_id: str = Query("default")):
    """Get current conversation status."""
    conversation = get_conversation(user_id)
    return conversation.get_conversation_summary()


@router.websocket("/conversation/ws")
async def conversation_websocket(websocket: WebSocket):
    """
    Real-time conversation WebSocket with natural flow.
    
    Protocol:
    - Send: {"type": "message", "text": "...", "user_id": "..."}
    - Receive: {"type": "thinking"} -> {"type": "response", "text": "...", "audio": base64}
    
    Features:
    - Context memory
    - Emotion-aware responses
    - Streaming text chunks
    - Audio responses
    """
    await websocket.accept()
    
    user_id = "default"
    persona = "aion"
    conversation = None
    
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "message")
            
            if msg_type == "init":
                # Initialize conversation
                user_id = data.get("user_id", "default")
                persona = data.get("persona", "aion")
                conversation = get_conversation(user_id, persona)
                
                await websocket.send_json({
                    "type": "initialized",
                    "persona": conversation.persona.name,
                    "personality": conversation.persona.personality,
                })
            
            elif msg_type == "message":
                if conversation is None:
                    conversation = get_conversation(user_id, persona)
                
                message = data.get("text", "")
                if not message:
                    continue
                
                # Send thinking indicator
                await websocket.send_json({"type": "thinking"})
                
                # Generate response with audio
                try:
                    result = await conversation.generate_voice_response(message, user_id)
                    
                    # Send text response
                    await websocket.send_json({
                        "type": "response",
                        "text": result["response"],
                        "emotion": result["emotion"],
                        "model": result["model"],
                        "turn_count": result["turn_count"],
                    })
                    
                    # Send audio
                    import base64
                    await websocket.send_json({
                        "type": "audio",
                        "data": base64.b64encode(result["audio"]).decode(),
                        "format": "mp3",
                    })
                    
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "message": str(e),
                    })
            
            elif msg_type == "set_persona":
                persona_name = data.get("persona", "aion")
                if conversation:
                    conversation.set_persona(persona_name)
                    await websocket.send_json({
                        "type": "persona_changed",
                        "persona": conversation.persona.name,
                    })
            
            elif msg_type == "reset":
                if conversation:
                    conversation.reset_conversation()
                    await websocket.send_json({
                        "type": "conversation_reset",
                    })
            
            elif msg_type == "status":
                if conversation:
                    await websocket.send_json({
                        "type": "status",
                        **conversation.get_conversation_summary(),
                    })
    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
            })
        except:
            pass
