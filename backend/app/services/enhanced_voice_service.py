"""
Enhanced Voice Service - Advanced voice interaction features.

Features:
- Wake word detection ("Hey Aion")
- Interrupt handling (stop speaking when user talks)
- Voice activity detection
- Streaming transcription
"""

import asyncio
import logging
import wave
import io
from typing import Optional, Callable, Awaitable, List
from dataclasses import dataclass
from enum import Enum

from app.services.voice_service import VoiceService, get_voice_service
from app.services.stt_service import STTService, get_stt_service

logger = logging.getLogger(__name__)


class VoiceState(str, Enum):
    """Current state of voice interaction."""
    IDLE = "idle"
    LISTENING_WAKE_WORD = "listening_wake_word"
    LISTENING_COMMAND = "listening_command"
    PROCESSING = "processing"
    SPEAKING = "speaking"


@dataclass
class WakeWordConfig:
    """Configuration for wake word detection."""
    phrases: List[str]
    threshold: float = 0.7
    timeout_seconds: float = 5.0


@dataclass
class VoiceConfig:
    """Configuration for voice interaction."""
    wake_word: WakeWordConfig
    interrupt_enabled: bool = True
    auto_stop_silence_ms: int = 1500
    max_listen_seconds: float = 30.0


class EnhancedVoiceService:
    """
    Enhanced voice service with wake word and interrupt handling.
    """
    
    DEFAULT_WAKE_WORDS = [
        "hey aion",
        "hi aion",
        "okay aion",
        "aion",
    ]
    
    def __init__(self):
        self.voice_service = get_voice_service()
        self.stt_service = get_stt_service()
        self.state = VoiceState.IDLE
        self.config = VoiceConfig(
            wake_word=WakeWordConfig(phrases=self.DEFAULT_WAKE_WORDS),
        )
        
        # Callbacks
        self.on_wake_word: Optional[Callable[[], Awaitable[None]]] = None
        self.on_command: Optional[Callable[[str], Awaitable[None]]] = None
        self.on_state_change: Optional[Callable[[VoiceState], Awaitable[None]]] = None
        
        # State
        self._speaking = False
        self._interrupted = False
        self._current_audio_task: Optional[asyncio.Task] = None
    
    async def _set_state(self, new_state: VoiceState):
        """Update state and notify listeners."""
        if self.state != new_state:
            self.state = new_state
            if self.on_state_change:
                await self.on_state_change(new_state)
    
    # ========================================================================
    # Wake Word Detection
    # ========================================================================
    
    async def start_wake_word_listening(self):
        """
        Start listening for wake word.
        
        When detected, transitions to command listening mode.
        """
        await self._set_state(VoiceState.LISTENING_WAKE_WORD)
        
        # In a real implementation, this would use a dedicated wake word
        # detection model (like Porcupine, Snowboy, or a custom model).
        # For now, we use STT and check for wake phrases.
        
    async def check_for_wake_word(self, transcript: str) -> bool:
        """Check if transcript contains a wake word."""
        transcript_lower = transcript.lower().strip()
        
        for phrase in self.config.wake_word.phrases:
            if phrase in transcript_lower:
                return True
        
        return False
    
    async def process_audio_for_wake_word(self, audio_data: bytes) -> bool:
        """
        Process audio chunk and check for wake word.
        
        Returns True if wake word detected.
        """
        if self.state != VoiceState.LISTENING_WAKE_WORD:
            return False
        
        try:
            # Transcribe audio
            transcript = await self.stt_service.transcribe(audio_data)
            
            if await self.check_for_wake_word(transcript):
                if self.on_wake_word:
                    await self.on_wake_word()
                await self._set_state(VoiceState.LISTENING_COMMAND)
                return True
                
        except Exception as e:
            logger.error("Wake word detection error: %s", e)
        
        return False
    
    # ========================================================================
    # Command Listening
    # ========================================================================
    
    async def start_command_listening(
        self,
        timeout_seconds: Optional[float] = None,
    ):
        """
        Start listening for a voice command.
        
        Automatically stops after silence or timeout.
        """
        await self._set_state(VoiceState.LISTENING_COMMAND)
        
        timeout = timeout_seconds or self.config.max_listen_seconds
        
        # In real implementation, this would:
        # 1. Start audio capture
        # 2. Use VAD to detect speech
        # 3. Transcribe incrementally
        # 4. Stop on silence or timeout
    
    async def process_command_audio(self, audio_data: bytes) -> Optional[str]:
        """
        Process audio for command and return transcript when complete.
        """
        if self.state != VoiceState.LISTENING_COMMAND:
            return None
        
        try:
            transcript = await self.stt_service.transcribe(audio_data)
            
            if transcript and len(transcript.strip()) > 0:
                await self._set_state(VoiceState.PROCESSING)
                
                if self.on_command:
                    await self.on_command(transcript)
                
                return transcript
                
        except Exception as e:
            logger.error("Command processing error: %s", e)
        
        return None
    
    # ========================================================================
    # Speaking with Interrupt Support
    # ========================================================================
    
    async def speak(
        self,
        text: str,
        interruptible: bool = True,
    ) -> bool:
        """
        Speak text with optional interrupt support.
        
        Returns True if completed, False if interrupted.
        """
        self._speaking = True
        self._interrupted = False
        await self._set_state(VoiceState.SPEAKING)
        
        try:
            # Generate audio
            audio_data = await self.voice_service.text_to_speech(text)
            
            if not audio_data:
                return False
            
            # In real implementation, this would:
            # 1. Stream audio in chunks
            # 2. Check for interrupts between chunks
            # 3. Stop if interrupted
            
            if self._interrupted:
                return False
            
            # Simulate playback (in real impl, would play audio)
            # For now, just mark as complete
            return True
            
        finally:
            self._speaking = False
            await self._set_state(VoiceState.IDLE)
    
    async def speak_streaming(
        self,
        text_generator,
        interruptible: bool = True,
    ):
        """
        Speak text from a streaming generator.
        
        Useful for speaking AI responses as they're generated.
        """
        self._speaking = True
        self._interrupted = False
        await self._set_state(VoiceState.SPEAKING)
        
        try:
            buffer = ""
            sentence_endings = ".!?;"
            
            async for chunk in text_generator:
                if self._interrupted:
                    break
                
                buffer += chunk
                
                # Check for complete sentences
                for ending in sentence_endings:
                    if ending in buffer:
                        parts = buffer.split(ending, 1)
                        sentence = parts[0] + ending
                        buffer = parts[1] if len(parts) > 1 else ""
                        
                        # Speak sentence
                        await self.speak(sentence.strip(), interruptible=False)
                        
                        if self._interrupted:
                            break
            
            # Speak remaining buffer
            if buffer.strip() and not self._interrupted:
                await self.speak(buffer.strip(), interruptible=False)
                
        finally:
            self._speaking = False
            await self._set_state(VoiceState.IDLE)
    
    def interrupt(self):
        """Interrupt current speech."""
        if self._speaking and self.config.interrupt_enabled:
            self._interrupted = True
            if self._current_audio_task:
                self._current_audio_task.cancel()
    
    # ========================================================================
    # Voice Activity Detection
    # ========================================================================
    
    def detect_voice_activity(self, audio_chunk: bytes) -> bool:
        """
        Simple voice activity detection.
        
        Returns True if voice activity detected in the audio chunk.
        """
        # Simple energy-based VAD
        # In production, would use WebRTC VAD or similar
        
        if len(audio_chunk) < 2:
            return False
        
        # Calculate RMS energy
        samples = [
            int.from_bytes(audio_chunk[i:i+2], 'little', signed=True)
            for i in range(0, len(audio_chunk) - 1, 2)
        ]
        
        if not samples:
            return False
        
        rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
        
        # Threshold (adjustable)
        return rms > 500
    
    async def wait_for_speech_end(
        self,
        silence_threshold_ms: int = 1500,
        max_wait_ms: int = 30000,
    ) -> bool:
        """
        Wait for speech to end (silence detected).
        
        Returns True if silence detected, False if timeout.
        """
        # In real implementation, this would monitor audio stream
        # and return when silence is detected
        await asyncio.sleep(silence_threshold_ms / 1000)
        return True
    
    # ========================================================================
    # Configuration
    # ========================================================================
    
    def set_wake_words(self, phrases: List[str]):
        """Set custom wake word phrases."""
        self.config.wake_word.phrases = [p.lower() for p in phrases]
    
    def enable_interrupt(self, enabled: bool = True):
        """Enable or disable interrupt handling."""
        self.config.interrupt_enabled = enabled
    
    def set_silence_timeout(self, ms: int):
        """Set silence timeout for auto-stop."""
        self.config.auto_stop_silence_ms = ms


# Singleton
_enhanced_voice_service: Optional[EnhancedVoiceService] = None


def get_enhanced_voice_service() -> EnhancedVoiceService:
    """Get the enhanced voice service singleton."""
    global _enhanced_voice_service
    if _enhanced_voice_service is None:
        _enhanced_voice_service = EnhancedVoiceService()
    return _enhanced_voice_service
