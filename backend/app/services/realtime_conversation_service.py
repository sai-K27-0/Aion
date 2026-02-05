"""
Real-time Voice Conversation Service - Natural, human-like AI conversations.

Features:
- Low-latency streaming responses
- Natural conversation flow with interruption handling
- Emotion and tone awareness
- Context memory across conversation
- Multiple voice personas
- Turn-taking management
"""

import asyncio
import json
import time
from typing import Optional, Dict, Any, List, AsyncGenerator, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

import edge_tts

from app.services.ai_service import get_ai_service
from app.services.smart_model_router import get_smart_router, TaskType
from app.services.user_profile_service import get_profile_service


class ConversationState(str, Enum):
    """Current state of conversation."""
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"


class EmotionalTone(str, Enum):
    """Emotional tone for voice synthesis."""
    NEUTRAL = "neutral"
    FRIENDLY = "friendly"
    EXCITED = "excited"
    CALM = "calm"
    SERIOUS = "serious"
    EMPATHETIC = "empathetic"


@dataclass
class ConversationTurn:
    """A single turn in the conversation."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: float
    emotion: Optional[EmotionalTone] = None
    audio_duration: Optional[float] = None


@dataclass
class VoicePersona:
    """Voice persona configuration."""
    name: str
    voice_id: str  # edge-tts voice ID
    speaking_rate: str = "+0%"
    pitch: str = "+0Hz"
    personality: str = "helpful and friendly"
    
    # Conversation style
    use_filler_words: bool = True  # "um", "well", etc.
    use_acknowledgments: bool = True  # "I see", "Got it", etc.
    max_response_sentences: int = 3  # Keep responses concise
    
    # Emotional expression
    express_enthusiasm: bool = True
    express_empathy: bool = True


# Pre-defined personas for natural conversation
PERSONAS = {
    "aion": VoicePersona(
        name="Aion",
        voice_id="en-US-GuyNeural",
        speaking_rate="+5%",
        pitch="+0Hz",
        personality="a knowledgeable and supportive productivity assistant",
    ),
    "aria": VoicePersona(
        name="Aria",
        voice_id="en-US-AriaNeural",
        speaking_rate="+0%",
        pitch="+2Hz",
        personality="a warm and encouraging study companion",
        express_empathy=True,
    ),
    "alex": VoicePersona(
        name="Alex",
        voice_id="en-GB-RyanNeural",
        speaking_rate="+0%",
        pitch="-2Hz",
        personality="a calm and professional advisor",
        use_filler_words=False,
    ),
}


# Filler words and acknowledgments for natural conversation
FILLER_WORDS = ["Well,", "So,", "You know,", "Actually,", "I think"]
ACKNOWLEDGMENTS = ["I see.", "Got it.", "Okay.", "Right.", "Sure."]
THINKING_PHRASES = ["Let me think...", "Hmm...", "That's interesting...", "Good question..."]
EMPATHY_PHRASES = {
    "frustration": "I understand that can be frustrating.",
    "confusion": "I can see how that might be confusing.",
    "excitement": "That's exciting!",
    "achievement": "Great job!",
}


class RealtimeConversationService:
    """
    Manages real-time voice conversations with natural flow.
    
    Key features for realistic conversation:
    1. Low-latency streaming responses
    2. Natural filler words and acknowledgments
    3. Emotion detection and appropriate responses
    4. Context awareness across turns
    5. Interruption handling
    """
    
    MAX_HISTORY = 20  # Keep last 20 turns for context
    
    def __init__(self, persona_name: str = "aion"):
        self.ai_service = get_ai_service()
        self.smart_router = get_smart_router()
        self.profile_service = get_profile_service()
        
        self.persona = PERSONAS.get(persona_name, PERSONAS["aion"])
        self.state = ConversationState.IDLE
        self.history: List[ConversationTurn] = []
        self.current_emotion: EmotionalTone = EmotionalTone.NEUTRAL
        
        # Conversation metrics
        self.conversation_start: Optional[float] = None
        self.total_user_speaking_time: float = 0
        self.total_assistant_speaking_time: float = 0
    
    def _build_conversation_context(self) -> str:
        """Build context from conversation history."""
        if not self.history:
            return ""
        
        # Get recent turns
        recent = self.history[-10:]  # Last 10 turns
        
        context_parts = ["Previous conversation:"]
        for turn in recent:
            role = "User" if turn.role == "user" else "Assistant"
            context_parts.append(f"{role}: {turn.content}")
        
        return "\n".join(context_parts)
    
    def _build_natural_system_prompt(self, user_id: str) -> str:
        """Build a system prompt for natural conversation."""
        profile_context = self.profile_service.get_context_for_prompt(user_id)
        conversation_context = self._build_conversation_context()
        
        prompt = f"""You are {self.persona.name}, {self.persona.personality}.

CRITICAL VOICE CONVERSATION RULES:
1. This is a VOICE conversation - keep responses SHORT (1-3 sentences max)
2. Sound NATURAL and conversational, like talking to a friend
3. Use contractions (I'm, you're, don't, can't)
4. Avoid lists, bullet points, or formatted text
5. Don't say "as an AI" or "I don't have feelings"
6. React naturally to what the user says

{f"User profile: {profile_context}" if profile_context else ""}

{f"Recent conversation:{chr(10)}{conversation_context}" if conversation_context else ""}

PERSONALITY TRAITS:
- Be {self.persona.personality}
- {"Use occasional filler words like 'well', 'so', 'you know'" if self.persona.use_filler_words else "Be direct and concise"}
- {"Acknowledge what the user says before responding" if self.persona.use_acknowledgments else ""}
- {"Show enthusiasm when appropriate" if self.persona.express_enthusiasm else ""}
- {"Express empathy when the user seems frustrated or confused" if self.persona.express_empathy else ""}

Current emotional context: {self.current_emotion.value}

Remember: You're having a natural voice conversation. Keep it brief, warm, and human-like."""

        return prompt
    
    def _detect_emotion(self, text: str) -> EmotionalTone:
        """Detect emotional context from user's message."""
        text_lower = text.lower()
        
        # Frustration indicators
        frustration_words = ["frustrated", "annoying", "hate", "ugh", "can't", "won't work", "stupid"]
        if any(word in text_lower for word in frustration_words):
            return EmotionalTone.EMPATHETIC
        
        # Excitement indicators
        excitement_words = ["awesome", "amazing", "great", "love", "excited", "yes!", "finally"]
        if any(word in text_lower for word in excitement_words):
            return EmotionalTone.EXCITED
        
        # Question/confusion
        if "?" in text or any(w in text_lower for w in ["confused", "don't understand", "what do you mean"]):
            return EmotionalTone.CALM
        
        # Serious topic
        serious_words = ["important", "urgent", "deadline", "exam", "test", "interview"]
        if any(word in text_lower for word in serious_words):
            return EmotionalTone.SERIOUS
        
        return EmotionalTone.FRIENDLY
    
    async def generate_response(
        self,
        user_message: str,
        user_id: str = "default",
    ) -> Dict[str, Any]:
        """
        Generate a natural conversational response.
        
        Returns text response and metadata.
        """
        self.state = ConversationState.THINKING
        
        # Start conversation timer if needed
        if self.conversation_start is None:
            self.conversation_start = time.time()
        
        # Add user message to history
        self.history.append(ConversationTurn(
            role="user",
            content=user_message,
            timestamp=time.time(),
        ))
        
        # Detect emotion
        self.current_emotion = self._detect_emotion(user_message)
        
        # Extract facts from message
        await self.profile_service.extract_facts(user_id, user_message)
        
        # Route to optimal model
        routing = await self.smart_router.route(user_message)
        model = routing["model"]
        
        # Build natural prompt
        system_prompt = self._build_natural_system_prompt(user_id)
        
        # Generate response
        response = await self.ai_service.chat(
            message=user_message,
            system_prompt=system_prompt,
            temperature=0.8,  # Slightly higher for more natural variation
            model=model,
        )
        
        # Clean up response for voice
        response = self._clean_for_voice(response)
        
        # Add assistant response to history
        self.history.append(ConversationTurn(
            role="assistant",
            content=response,
            timestamp=time.time(),
            emotion=self.current_emotion,
        ))
        
        # Trim history if too long
        if len(self.history) > self.MAX_HISTORY:
            self.history = self.history[-self.MAX_HISTORY:]
        
        self.state = ConversationState.IDLE
        
        return {
            "response": response,
            "emotion": self.current_emotion.value,
            "model": model,
            "turn_count": len(self.history),
        }
    
    def _clean_for_voice(self, text: str) -> str:
        """Clean text for natural voice output."""
        # Remove markdown
        import re
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # Bold
        text = re.sub(r'\*([^*]+)\*', r'\1', text)  # Italic
        text = re.sub(r'`([^`]+)`', r'\1', text)  # Code
        text = re.sub(r'^[-*]\s+', '', text, flags=re.MULTILINE)  # List items
        text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)  # Numbered lists
        
        # Remove extra whitespace
        text = re.sub(r'\n+', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        
        # Limit length for voice
        sentences = text.split('. ')
        if len(sentences) > self.persona.max_response_sentences:
            text = '. '.join(sentences[:self.persona.max_response_sentences]) + '.'
        
        return text.strip()
    
    async def generate_voice_response(
        self,
        user_message: str,
        user_id: str = "default",
    ) -> Dict[str, Any]:
        """
        Generate response with voice audio.
        
        Returns text, audio bytes, and metadata.
        """
        # Get text response
        result = await self.generate_response(user_message, user_id)
        text = result["response"]
        
        # Generate speech with emotion-appropriate settings
        self.state = ConversationState.SPEAKING
        
        # Adjust voice settings based on emotion
        rate = self.persona.speaking_rate
        pitch = self.persona.pitch
        
        if self.current_emotion == EmotionalTone.EXCITED:
            rate = "+10%"
            pitch = "+5Hz"
        elif self.current_emotion == EmotionalTone.CALM:
            rate = "-5%"
        elif self.current_emotion == EmotionalTone.EMPATHETIC:
            rate = "-3%"
            pitch = "-2Hz"
        
        # Generate audio
        communicate = edge_tts.Communicate(
            text,
            self.persona.voice_id,
            rate=rate,
            pitch=pitch,
        )
        
        audio_chunks = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])
        
        audio_bytes = b"".join(audio_chunks)
        
        self.state = ConversationState.IDLE
        
        return {
            "response": text,
            "audio": audio_bytes,
            "emotion": self.current_emotion.value,
            "model": result["model"],
            "turn_count": result["turn_count"],
            "voice_settings": {
                "voice": self.persona.voice_id,
                "rate": rate,
                "pitch": pitch,
            },
        }
    
    async def stream_response(
        self,
        user_message: str,
        user_id: str = "default",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream response for real-time conversation.
        
        Yields partial responses as they're generated.
        """
        self.state = ConversationState.THINKING
        
        # Quick acknowledgment
        if self.persona.use_acknowledgments:
            import random
            ack = random.choice(ACKNOWLEDGMENTS)
            yield {"type": "acknowledgment", "text": ack}
        
        # Generate and stream response
        result = await self.generate_response(user_message, user_id)
        
        # Stream text in chunks
        text = result["response"]
        words = text.split()
        
        chunk_size = 5  # Words per chunk
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i + chunk_size])
            yield {"type": "text_chunk", "text": chunk}
            await asyncio.sleep(0.05)  # Small delay for streaming effect
        
        yield {
            "type": "complete",
            "response": text,
            "emotion": result["emotion"],
            "model": result["model"],
        }
        
        self.state = ConversationState.IDLE
    
    def set_persona(self, persona_name: str):
        """Change the conversation persona."""
        if persona_name in PERSONAS:
            self.persona = PERSONAS[persona_name]
    
    def reset_conversation(self):
        """Reset conversation history."""
        self.history = []
        self.conversation_start = None
        self.current_emotion = EmotionalTone.NEUTRAL
    
    def get_conversation_summary(self) -> Dict[str, Any]:
        """Get summary of current conversation."""
        return {
            "turn_count": len(self.history),
            "duration_seconds": time.time() - self.conversation_start if self.conversation_start else 0,
            "current_emotion": self.current_emotion.value,
            "persona": self.persona.name,
            "state": self.state.value,
        }


# Store active conversations
_active_conversations: Dict[str, RealtimeConversationService] = {}


def get_conversation(user_id: str = "default", persona: str = "aion") -> RealtimeConversationService:
    """Get or create a conversation for a user."""
    if user_id not in _active_conversations:
        _active_conversations[user_id] = RealtimeConversationService(persona)
    return _active_conversations[user_id]


def end_conversation(user_id: str):
    """End and cleanup a conversation."""
    if user_id in _active_conversations:
        del _active_conversations[user_id]
