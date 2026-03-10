"""
Voice Assistant Service - Complete voice interaction system.

Features:
- Wake word detection ("Hey Aion")
- Speech-to-Text using faster-whisper
- Text-to-Speech using edge-tts (natural Microsoft voices)
- Real-time conversation mode
- Voice activity detection
"""

import asyncio
import io
import logging
import os
import tempfile
import wave
from typing import Optional, AsyncGenerator, Callable, Dict, Any
from dataclasses import dataclass
from enum import Enum
import base64

# TTS
import edge_tts

logger = logging.getLogger(__name__)

# Note: These require additional installation
# pip install faster-whisper openwakeword sounddevice webrtcvad


class VoiceState(str, Enum):
    """Current state of voice assistant."""
    IDLE = "idle"
    LISTENING_WAKE = "listening_wake"
    LISTENING_COMMAND = "listening_command"
    PROCESSING = "processing"
    SPEAKING = "speaking"


@dataclass
class VoiceConfig:
    """Configuration for voice assistant."""
    # Wake word
    wake_word: str = "hey_jarvis"  # OpenWakeWord model name
    wake_sensitivity: float = 0.5
    
    # STT (Speech-to-Text)
    whisper_model: str = "base"  # tiny, base, small, medium, large
    language: str = "en"
    
    # TTS (Text-to-Speech)
    tts_voice: str = "en-US-GuyNeural"  # Natural male voice
    tts_rate: str = "+0%"
    tts_pitch: str = "+0Hz"
    
    # Audio
    sample_rate: int = 16000
    channels: int = 1
    silence_threshold: float = 0.01
    max_recording_seconds: float = 30.0


# Available natural voices for edge-tts
NATURAL_VOICES = {
    # English voices
    "guy": "en-US-GuyNeural",           # Natural male (default)
    "jenny": "en-US-JennyNeural",       # Natural female
    "aria": "en-US-AriaNeural",         # Conversational female
    "davis": "en-US-DavisNeural",       # Calm male
    "tony": "en-US-TonyNeural",         # Friendly male
    "nancy": "en-US-NancyNeural",       # Warm female
    "jason": "en-US-JasonNeural",       # Professional male
    "sara": "en-US-SaraNeural",         # Professional female
    
    # British
    "ryan": "en-GB-RyanNeural",         # British male
    "sonia": "en-GB-SoniaNeural",       # British female
    
    # Australian
    "william": "en-AU-WilliamNeural",   # Australian male
    "natasha": "en-AU-NatashaNeural",   # Australian female
}


class VoiceAssistantService:
    """
    Complete voice assistant with wake word, STT, and TTS.
    
    Usage:
    1. Start listening for wake word
    2. On wake word detected, listen for command
    3. Process command with AI
    4. Speak response
    5. Return to listening for wake word
    """
    
    def __init__(self, config: Optional[VoiceConfig] = None):
        self.config = config or VoiceConfig()
        self.state = VoiceState.IDLE
        self._whisper_model = None
        self._wake_model = None
        self._on_wake_callback: Optional[Callable] = None
        self._on_transcription_callback: Optional[Callable] = None
    
    # ========================================================================
    # Text-to-Speech (edge-tts)
    # ========================================================================
    
    async def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        pitch: Optional[str] = None,
    ) -> bytes:
        """
        Convert text to natural speech audio.
        
        Args:
            text: Text to speak
            voice: Voice name (use NATURAL_VOICES keys or full voice name)
            rate: Speech rate (e.g., "+10%", "-20%")
            pitch: Voice pitch (e.g., "+5Hz", "-10Hz")
            
        Returns:
            MP3 audio bytes
        """
        # Resolve voice name
        voice_name = voice or self.config.tts_voice
        if voice_name in NATURAL_VOICES:
            voice_name = NATURAL_VOICES[voice_name]
        
        rate = rate or self.config.tts_rate
        pitch = pitch or self.config.tts_pitch
        
        # Generate speech
        communicate = edge_tts.Communicate(
            text,
            voice_name,
            rate=rate,
            pitch=pitch,
        )
        
        # Collect audio chunks
        audio_chunks = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])
        
        return b"".join(audio_chunks)
    
    async def text_to_speech_stream(
        self,
        text: str,
        voice: Optional[str] = None,
    ) -> AsyncGenerator[bytes, None]:
        """
        Stream text-to-speech audio chunks for real-time playback.
        
        Yields MP3 audio chunks as they're generated.
        """
        voice_name = voice or self.config.tts_voice
        if voice_name in NATURAL_VOICES:
            voice_name = NATURAL_VOICES[voice_name]
        
        communicate = edge_tts.Communicate(
            text,
            voice_name,
            rate=self.config.tts_rate,
            pitch=self.config.tts_pitch,
        )
        
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]
    
    async def list_voices(self, language: str = "en") -> list[Dict[str, Any]]:
        """List available TTS voices for a language."""
        voices = await edge_tts.list_voices()
        
        filtered = []
        for voice in voices:
            if voice["Locale"].startswith(language):
                filtered.append({
                    "name": voice["ShortName"],
                    "gender": voice["Gender"],
                    "locale": voice["Locale"],
                    "friendly_name": voice["FriendlyName"],
                })
        
        return filtered
    
    # ========================================================================
    # Speech-to-Text (faster-whisper)
    # ========================================================================
    
    def _get_whisper_model(self):
        """Lazy load whisper model."""
        if self._whisper_model is None:
            try:
                from faster_whisper import WhisperModel
                
                # Use CPU by default, can change to "cuda" for GPU
                self._whisper_model = WhisperModel(
                    self.config.whisper_model,
                    device="cpu",
                    compute_type="int8",  # Faster on CPU
                )
            except ImportError:
                raise ImportError(
                    "faster-whisper not installed. Run: pip install faster-whisper"
                )
        
        return self._whisper_model
    
    async def transcribe_audio(
        self,
        audio_data: bytes,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Transcribe audio to text using faster-whisper.
        
        Args:
            audio_data: Audio bytes (WAV or raw PCM)
            language: Language code (e.g., "en", "es")
            
        Returns:
            Dict with text, language, and confidence
        """
        model = self._get_whisper_model()
        language = language or self.config.language
        
        # Save to temp file (whisper needs file path)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name
            f.write(audio_data)
        
        try:
            # Transcribe
            segments, info = model.transcribe(
                temp_path,
                language=language,
                beam_size=5,
                vad_filter=True,  # Filter out silence
            )
            
            # Collect text
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text)
            
            full_text = " ".join(text_parts).strip()
            
            return {
                "text": full_text,
                "language": info.language,
                "language_probability": info.language_probability,
                "duration": info.duration,
            }
        finally:
            # Cleanup
            os.unlink(temp_path)
    
    async def transcribe_audio_stream(
        self,
        audio_stream: AsyncGenerator[bytes, None],
    ) -> AsyncGenerator[str, None]:
        """
        Transcribe streaming audio in real-time.
        
        Yields partial transcriptions as audio comes in.
        """
        model = self._get_whisper_model()
        
        # Buffer audio
        audio_buffer = b""
        chunk_duration = 2.0  # Process every 2 seconds
        bytes_per_chunk = int(self.config.sample_rate * chunk_duration * 2)  # 16-bit
        
        async for chunk in audio_stream:
            audio_buffer += chunk
            
            if len(audio_buffer) >= bytes_per_chunk:
                # Save chunk to temp file
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    temp_path = f.name
                    # Write WAV header + data
                    self._write_wav(f, audio_buffer[:bytes_per_chunk])
                
                try:
                    segments, _ = model.transcribe(
                        temp_path,
                        language=self.config.language,
                        beam_size=1,  # Faster for streaming
                    )
                    
                    for segment in segments:
                        if segment.text.strip():
                            yield segment.text.strip()
                finally:
                    os.unlink(temp_path)
                
                audio_buffer = audio_buffer[bytes_per_chunk:]
    
    def _write_wav(self, file_obj, pcm_data: bytes):
        """Write PCM data as WAV file."""
        with wave.open(file_obj, 'wb') as wav:
            wav.setnchannels(self.config.channels)
            wav.setsampwidth(2)  # 16-bit
            wav.setframerate(self.config.sample_rate)
            wav.writeframes(pcm_data)
    
    # ========================================================================
    # Wake Word Detection (OpenWakeWord)
    # ========================================================================
    
    def _get_wake_model(self):
        """Lazy load wake word model."""
        if self._wake_model is None:
            try:
                import openwakeword
                from openwakeword.model import Model
                
                # Download and load model
                openwakeword.utils.download_models()
                
                self._wake_model = Model(
                    wakeword_models=[self.config.wake_word],
                    inference_framework="onnx",
                )
            except ImportError:
                raise ImportError(
                    "openwakeword not installed. Run: pip install openwakeword"
                )
        
        return self._wake_model
    
    async def detect_wake_word(
        self,
        audio_chunk: bytes,
    ) -> bool:
        """
        Check if audio contains wake word.
        
        Args:
            audio_chunk: Raw PCM audio (16kHz, 16-bit, mono)
            
        Returns:
            True if wake word detected
        """
        try:
            import numpy as np
            
            model = self._get_wake_model()
            
            # Convert bytes to numpy array
            audio_array = np.frombuffer(audio_chunk, dtype=np.int16)
            
            # Run prediction
            prediction = model.predict(audio_array)
            
            # Check if any wake word detected
            for key, score in prediction.items():
                if score > self.config.wake_sensitivity:
                    return True
            
            return False
        except Exception as e:
            logger.error("Wake word detection error: %s", e)
            return False
    
    # ========================================================================
    # Voice Activity Detection
    # ========================================================================
    
    def detect_speech(self, audio_chunk: bytes) -> bool:
        """
        Detect if audio chunk contains speech.
        
        Uses WebRTC VAD for accurate speech detection.
        """
        try:
            import webrtcvad
            
            vad = webrtcvad.Vad(3)  # Aggressiveness 0-3 (3 = most aggressive)
            
            # WebRTC VAD needs specific frame sizes
            frame_duration = 30  # ms
            frame_size = int(self.config.sample_rate * frame_duration / 1000) * 2
            
            # Check frames
            for i in range(0, len(audio_chunk) - frame_size, frame_size):
                frame = audio_chunk[i:i + frame_size]
                if len(frame) == frame_size:
                    if vad.is_speech(frame, self.config.sample_rate):
                        return True
            
            return False
        except Exception:
            # Fallback to simple energy detection
            import numpy as np
            audio = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32)
            energy = np.sqrt(np.mean(audio ** 2)) / 32768
            return energy > self.config.silence_threshold
    
    # ========================================================================
    # Conversation Mode
    # ========================================================================
    
    async def process_voice_command(
        self,
        audio_data: bytes,
        ai_callback: Callable[[str], str],
    ) -> Dict[str, Any]:
        """
        Complete voice command processing pipeline:
        1. Transcribe audio to text
        2. Process with AI
        3. Convert response to speech
        
        Args:
            audio_data: Audio bytes from user
            ai_callback: Async function that takes text and returns AI response
            
        Returns:
            Dict with transcription, response text, and audio
        """
        self.state = VoiceState.PROCESSING
        
        try:
            # 1. Transcribe
            transcription = await self.transcribe_audio(audio_data)
            user_text = transcription["text"]
            
            if not user_text:
                return {
                    "success": False,
                    "error": "Could not understand audio",
                }
            
            # 2. Get AI response
            ai_response = await ai_callback(user_text)
            
            # 3. Convert to speech
            self.state = VoiceState.SPEAKING
            audio_response = await self.text_to_speech(ai_response)
            
            return {
                "success": True,
                "user_text": user_text,
                "ai_response": ai_response,
                "audio_base64": base64.b64encode(audio_response).decode(),
                "transcription_info": transcription,
            }
        finally:
            self.state = VoiceState.IDLE
    
    async def speak_response(
        self,
        text: str,
        voice: Optional[str] = None,
    ) -> bytes:
        """
        Convenience method to speak a text response.
        
        Returns MP3 audio bytes.
        """
        self.state = VoiceState.SPEAKING
        try:
            return await self.text_to_speech(text, voice)
        finally:
            self.state = VoiceState.IDLE
    
    # ========================================================================
    # Configuration
    # ========================================================================
    
    def set_voice(self, voice: str):
        """Change the TTS voice."""
        if voice in NATURAL_VOICES:
            self.config.tts_voice = NATURAL_VOICES[voice]
        else:
            self.config.tts_voice = voice
    
    def set_whisper_model(self, model: str):
        """Change the Whisper model size."""
        self.config.whisper_model = model
        self._whisper_model = None  # Force reload
    
    def get_state(self) -> Dict[str, Any]:
        """Get current voice assistant state."""
        return {
            "state": self.state.value,
            "config": {
                "wake_word": self.config.wake_word,
                "whisper_model": self.config.whisper_model,
                "tts_voice": self.config.tts_voice,
                "language": self.config.language,
            },
            "available_voices": list(NATURAL_VOICES.keys()),
        }


# Singleton
_voice_assistant: Optional[VoiceAssistantService] = None


def get_voice_assistant() -> VoiceAssistantService:
    """Get the voice assistant singleton."""
    global _voice_assistant
    if _voice_assistant is None:
        _voice_assistant = VoiceAssistantService()
    return _voice_assistant
