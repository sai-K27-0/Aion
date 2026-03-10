"""
Memory Service - Conversation history and long-term memory management.

Handles:
- Conversation persistence
- Context window management with summarization
- Fact extraction and retrieval
- Memory-augmented prompts
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import uuid4

from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, ConversationMessage, ExtractedFact
from app.services.ai_service import AIService, get_ai_service
from app.config import settings

logger = logging.getLogger(__name__)


# Token limits for context management
MAX_CONTEXT_TOKENS = 4000  # Leave room for response
SUMMARIZE_THRESHOLD = 3000  # Start summarizing when context exceeds this
MESSAGES_TO_KEEP = 4  # Recent messages to keep verbatim


class MemoryService:
    """Service for managing conversation memory and context."""
    
    def __init__(self, db: AsyncSession, user_id: str):
        self.db = db
        self.user_id = user_id
        self.ai_service = get_ai_service()
    
    # ========================================================================
    # Conversation Management
    # ========================================================================
    
    async def get_or_create_conversation(
        self,
        conversation_id: Optional[str] = None,
    ) -> Conversation:
        """Get existing conversation or create new one."""
        if conversation_id:
            result = await self.db.execute(
                select(Conversation).where(
                    and_(
                        Conversation.id == conversation_id,
                        Conversation.user_id == self.user_id,
                    )
                )
            )
            conversation = result.scalar_one_or_none()
            if conversation:
                return conversation
        
        # Create new conversation
        conversation = Conversation(
            user_id=self.user_id,
            is_active=True,
        )
        self.db.add(conversation)
        await self.db.commit()
        await self.db.refresh(conversation)
        return conversation
    
    async def get_active_conversation(self) -> Optional[Conversation]:
        """Get the most recent active conversation."""
        result = await self.db.execute(
            select(Conversation)
            .where(
                and_(
                    Conversation.user_id == self.user_id,
                    Conversation.is_active == True,
                )
            )
            .order_by(desc(Conversation.updated_at))
            .limit(1)
        )
        return result.scalar_one_or_none()
    
    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        model: Optional[str] = None,
        sources: Optional[List[Dict]] = None,
        confidence: Optional[float] = None,
        reasoning: Optional[str] = None,
    ) -> ConversationMessage:
        """Add a message to a conversation."""
        # Estimate tokens (rough approximation: 4 chars per token)
        tokens = len(content) // 4
        
        message = ConversationMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
            model=model,
            tokens=tokens,
            sources=sources,
            confidence=confidence,
            reasoning=reasoning,
        )
        self.db.add(message)
        
        # Update conversation stats (use FOR UPDATE to prevent race conditions)
        result = await self.db.execute(
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .with_for_update()
        )
        conversation = result.scalar_one()
        conversation.message_count += 1
        conversation.context_tokens += tokens
        
        await self.db.commit()
        await self.db.refresh(message)
        
        # Check if we need to summarize
        if conversation.context_tokens > SUMMARIZE_THRESHOLD:
            await self._summarize_old_messages(conversation)
        
        return message
    
    async def get_conversation_context(
        self,
        conversation_id: str,
        max_tokens: int = MAX_CONTEXT_TOKENS,
    ) -> List[Dict[str, str]]:
        """
        Get conversation context for the AI, managing token limits.
        
        Returns messages formatted for the chat API, with older messages
        summarized if necessary.
        """
        result = await self.db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()
        if not conversation:
            return []
        
        context = []
        
        # Add summary if available
        if conversation.summary:
            context.append({
                "role": "system",
                "content": f"[Previous conversation summary]\n{conversation.summary}",
            })
        
        # Get recent messages
        result = await self.db.execute(
            select(ConversationMessage)
            .where(
                and_(
                    ConversationMessage.conversation_id == conversation_id,
                    ConversationMessage.is_summarized == False,
                )
            )
            .order_by(desc(ConversationMessage.created_at))
            .limit(20)  # Get more than needed, then trim
        )
        messages = list(reversed(result.scalars().all()))
        
        # Add messages within token limit
        current_tokens = len(conversation.summary or "") // 4
        for msg in messages:
            if current_tokens + msg.tokens > max_tokens:
                break
            context.append({
                "role": msg.role,
                "content": msg.content,
            })
            current_tokens += msg.tokens
        
        return context
    
    async def _summarize_old_messages(self, conversation: Conversation):
        """Summarize older messages to free up context space."""
        # Get messages to summarize (all except recent ones)
        result = await self.db.execute(
            select(ConversationMessage)
            .where(
                and_(
                    ConversationMessage.conversation_id == conversation.id,
                    ConversationMessage.is_summarized == False,
                )
            )
            .order_by(ConversationMessage.created_at)
        )
        messages = result.scalars().all()
        
        if len(messages) <= MESSAGES_TO_KEEP:
            return
        
        # Messages to summarize
        to_summarize = messages[:-MESSAGES_TO_KEEP]
        
        # Build summary prompt
        conversation_text = "\n".join([
            f"{m.role}: {m.content}" for m in to_summarize
        ])
        
        summary_prompt = f"""Summarize this conversation concisely, preserving key facts, decisions, and context:

{conversation_text}

Summary (be concise but preserve important details):"""
        
        try:
            # Generate summary
            summary = await self.ai_service.chat(
                message=summary_prompt,
                system_prompt="You are a conversation summarizer. Extract key points concisely.",
                temperature=0.3,
            )
            
            # Update conversation summary
            if conversation.summary:
                conversation.summary = f"{conversation.summary}\n\n{summary}"
            else:
                conversation.summary = summary
            
            # Mark messages as summarized
            tokens_freed = 0
            for msg in to_summarize:
                msg.is_summarized = True
                tokens_freed += msg.tokens
            
            conversation.context_tokens -= tokens_freed
            conversation.last_summary_at = datetime.now(timezone.utc)
            
            await self.db.commit()
            
        except Exception as e:
            logger.error("Summarization failed: %s", e)
    
    # ========================================================================
    # Fact Extraction and Memory
    # ========================================================================
    
    async def extract_facts_from_message(
        self,
        message: ConversationMessage,
    ) -> List[ExtractedFact]:
        """Extract memorable facts from a user message."""
        if message.role != "user":
            return []
        
        extraction_prompt = f"""Analyze this user message and extract any facts worth remembering long-term.

Message: "{message.content}"

Extract facts in these categories:
- preference: User likes/dislikes, preferred ways of doing things
- fact: Personal facts (name, job, location, etc.)
- relationship: People mentioned and their relation to user
- schedule: Regular schedules, routines, recurring events
- goal: Goals, aspirations, things they want to achieve
- habit: Habits, regular behaviors

Return JSON array of facts, or empty array if nothing to extract:
[{{"category": "...", "content": "...", "confidence": 0.0-1.0}}]

Only extract clear, explicit facts. Don't infer or assume.
Return ONLY the JSON array, no other text."""
        
        try:
            response = await self.ai_service.chat(
                message=extraction_prompt,
                system_prompt="You extract facts from messages. Return only valid JSON.",
                temperature=0.1,
            )
            
            # Parse JSON
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            
            facts_data = json.loads(response)
            
            # Create fact records
            facts = []
            for fact_data in facts_data:
                if fact_data.get("content"):
                    fact = ExtractedFact(
                        user_id=self.user_id,
                        conversation_id=message.conversation_id,
                        message_id=message.id,
                        category=fact_data.get("category", "fact"),
                        content=fact_data["content"],
                        confidence=fact_data.get("confidence", 0.8),
                    )
                    self.db.add(fact)
                    facts.append(fact)
            
            if facts:
                await self.db.commit()
            
            return facts
            
        except Exception as e:
            logger.error("Fact extraction failed: %s", e)
            return []
    
    async def get_relevant_facts(
        self,
        query: str,
        limit: int = 5,
    ) -> List[ExtractedFact]:
        """Get facts relevant to a query."""
        # For now, use keyword matching
        # TODO: Use vector similarity when embeddings are added
        
        result = await self.db.execute(
            select(ExtractedFact)
            .where(
                and_(
                    ExtractedFact.user_id == self.user_id,
                    ExtractedFact.is_active == True,
                )
            )
            .order_by(desc(ExtractedFact.reference_count))
            .limit(limit * 2)  # Get more, then filter
        )
        facts = result.scalars().all()
        
        # Simple relevance scoring based on word overlap
        query_words = set(query.lower().split())
        scored_facts = []
        for fact in facts:
            fact_words = set(fact.content.lower().split())
            overlap = len(query_words & fact_words)
            if overlap > 0:
                scored_facts.append((fact, overlap))
        
        # Sort by relevance and return top results
        scored_facts.sort(key=lambda x: x[1], reverse=True)
        return [f[0] for f in scored_facts[:limit]]
    
    async def get_user_facts(
        self,
        category: Optional[str] = None,
        limit: int = 20,
    ) -> List[ExtractedFact]:
        """Get all facts for a user, optionally filtered by category."""
        query = select(ExtractedFact).where(
            and_(
                ExtractedFact.user_id == self.user_id,
                ExtractedFact.is_active == True,
            )
        )
        
        if category:
            query = query.where(ExtractedFact.category == category)
        
        query = query.order_by(desc(ExtractedFact.updated_at)).limit(limit)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    # ========================================================================
    # Memory-Augmented Prompts
    # ========================================================================
    
    async def build_memory_context(self, query: str) -> str:
        """Build a memory context string to include in prompts."""
        facts = await self.get_relevant_facts(query, limit=5)
        
        if not facts:
            return ""
        
        context_parts = ["[User Memory]"]
        for fact in facts:
            context_parts.append(f"- [{fact.category}] {fact.content}")
            
            # Update reference count
            fact.reference_count += 1
            fact.last_referenced = datetime.now(timezone.utc)
        
        await self.db.commit()
        
        return "\n".join(context_parts)
    
    async def generate_conversation_title(
        self,
        conversation_id: str,
    ) -> str:
        """Generate a title for a conversation based on its content."""
        result = await self.db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.created_at)
            .limit(3)
        )
        messages = result.scalars().all()
        
        if not messages:
            return "New Conversation"
        
        content = "\n".join([f"{m.role}: {m.content[:100]}" for m in messages])
        
        try:
            title = await self.ai_service.chat(
                message=f"Generate a short title (3-6 words) for this conversation:\n\n{content}",
                system_prompt="Generate only the title, nothing else.",
                temperature=0.5,
            )
            title = title.strip().strip('"').strip("'")
            
            # Update conversation
            result = await self.db.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conversation = result.scalar_one()
            conversation.title = title[:255]
            await self.db.commit()
            
            return title
            
        except Exception:
            return "Untitled Conversation"


# Factory function
async def get_memory_service(db: AsyncSession, user_id: str) -> MemoryService:
    return MemoryService(db, user_id)
