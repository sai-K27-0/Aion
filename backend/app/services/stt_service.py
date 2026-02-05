import logging
import io
import speech_recognition as sr
from pydub import AudioSegment
from pathlib import Path
from app.config import settings

logger = logging.getLogger(__name__)

class STTService:
    """Service for converting Speech to Text using SpeechRecognition."""
    
    def __init__(self):
        self.recognizer = sr.Recognizer()
        
    async def transcribe(self, audio_bytes: bytes) -> str:
        """
        Transcribe audio bytes to text.
        Assumes input is webm/wav/etc. Converts to WAV for SpeechRecognition.
        """
        try:
            # Load audio using pydub
            audio = AudioSegment.from_file(io.BytesIO(audio_bytes))
            
            # Export to WAV in memory
            wav_io = io.BytesIO()
            audio.export(wav_io, format="wav")
            wav_io.seek(0)
            
            # Use SpeechRecognition
            with sr.AudioFile(wav_io) as source:
                audio_data = self.recognizer.record(source)
                # Use Google Speech Recognition (default key)
                # Note: This has limits, but is free and doesn't require extra setup
                text = self.recognizer.recognize_google(audio_data)
                logger.info(f"Transcribed: '{text}'")
                return text
                
        except sr.UnknownValueError:
            logger.warning("STT: Speech unintelligible")
            return ""
        except sr.RequestError as e:
            logger.error(f"STT: Service error: {e}")
            return ""
        except Exception as e:
            logger.error(f"STT: Conversion error: {e}")
            return ""

# Singleton
_stt_service = None

def get_stt_service() -> STTService:
    global _stt_service
    if _stt_service is None:
        _stt_service = STTService()
    return _stt_service
