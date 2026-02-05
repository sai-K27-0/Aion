"""
Voice Service - Neural Text-to-Speech using ElevenLabs and Edge TTS.
"""

import os
import logging
import hashlib
import asyncio
from pathlib import Path
from typing import Optional

import httpx
import edge_tts
from app.config import settings

logger = logging.getLogger(__name__)

class VoiceService:
    """Service for generating speech from text using ElevenLabs or Edge TTS."""
    
    def __init__(self):
        self.eleven_key = settings.elevenlabs_api_key
        self.eleven_voice = settings.elevenlabs_voice_id
        self.eleven_model = settings.elevenlabs_model_id
        
        self.edge_voice = settings.edge_tts_voice
        
        self.cache_dir = Path(settings.data_dir) / "voice_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    async def text_to_speech(self, text: str) -> Optional[bytes]:
        """
        Convert text to speech bytes. 
        Tries: 1. Cache, 2. ElevenLabs (if key), 3. Edge TTS (Free)
        """
        if not text:
            return None
            
        # 1. Check Cache (Shared for all backends)
        text_hash = hashlib.md5(text.encode()).hexdigest()
        cache_path = self.cache_dir / f"{text_hash}.mp3"
        
        if cache_path.exists():
            logger.info(f"Voice cache hit for: {text[:30]}...")
            return cache_path.read_bytes()
            
        # 2. Try ElevenLabs
        if self.eleven_key:
            audio = await self._tts_elevenlabs(text)
            if audio:
                cache_path.write_bytes(audio)
                return audio
                
        # 3. Fallback to Edge TTS (Free Neural Voice)
        logger.info(f"Using Edge TTS for: {text[:30]}...")
        audio = await self._tts_edge(text)
        if audio:
            cache_path.write_bytes(audio)
            return audio
            
        return None

    async def _tts_elevenlabs(self, text: str) -> Optional[bytes]:
        """ElevenLabs (Paid Neural) Implementation."""
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.eleven_voice}"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.eleven_key
        }
        data = {
            "text": text,
            "model_id": self.eleven_model,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=data, headers=headers, timeout=30.0)
                if response.status_code == 200:
                    return response.content
                logger.error(f"ElevenLabs error: {response.status_code}")
        except Exception as e:
            logger.error(f"ElevenLabs failed: {e}")
        return None

    async def _tts_edge(self, text: str) -> Optional[bytes]:
        """Edge TTS (Free Neural) Implementation."""
        try:
            communicate = edge_tts.Communicate(text, self.edge_voice)
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            return audio_data
        except Exception as e:
            logger.error(f"Edge TTS failed: {e}")
        return None

# Singleton
_voice_service = None

def get_voice_service() -> VoiceService:
    global _voice_service
    if _voice_service is None:
        _voice_service = VoiceService()
    return _voice_service
