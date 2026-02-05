import logging
import re
import asyncio
from typing import AsyncGenerator, Optional
from app.services.voice_service import VoiceService

logger = logging.getLogger(__name__)

class RealtimeVoiceService:
    """
    Handles streaming text-to-speech by buffering tokens into sentences.
    This reduces latency by speaking the first sentence while the rest are still generating.
    """
    
    def __init__(self, voice_service: VoiceService):
        self.voice = voice_service
        # Regex for sentence splitting (English)
        # Matches periods, exclamation marks, question marks followed by space or end of string
        self.sentence_end_pattern = re.compile(r'(?<=[.!?])\s+')
        
    async def process_token_stream(self, token_stream: AsyncGenerator[str, None]) -> AsyncGenerator[bytes, None]:
        """
        Consumes a stream of text tokens, buffers them into sentences, 
        and yields audio chunks for each sentence.
        """
        buffer = ""
        
        async for token in token_stream:
            buffer += token
            
            # Check for sentence boundary
            # We look for a split that gives us at least one complete sentence part
            parts = self.sentence_end_pattern.split(buffer)
            
            if len(parts) > 1:
                # We have at least one complete sentence
                # The last part is the incomplete buffer for the next sentence
                complete_sentences = parts[:-1]
                buffer = parts[-1]
                
                for sentence in complete_sentences:
                    sentence = sentence.strip()
                    if sentence:
                        logger.info(f"Streaming sentence: {sentence}")
                        try:
                            # VoiceService returns bytes directly
                            audio_bytes = await self.voice.text_to_speech(sentence)
                            if audio_bytes:
                                yield audio_bytes
                        except Exception as e:
                            logger.error(f"TTS Error on stream: {e}")

        # Process remaining buffer
        if buffer.strip():
            logger.info(f"Streaming final fragment: {buffer}")
            try:
                audio_bytes = await self.voice.text_to_speech(buffer.strip())
                if audio_bytes:
                    yield audio_bytes
            except Exception as e:
                logger.error(f"TTS Error on final chunk: {e}")

# Singleton
_realtime_voice_service: Optional[RealtimeVoiceService] = None

def get_realtime_voice_service(voice_service: VoiceService) -> RealtimeVoiceService:
    global _realtime_voice_service
    if _realtime_voice_service is None:
        _realtime_voice_service = RealtimeVoiceService(voice_service)
    return _realtime_voice_service
