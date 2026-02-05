"""
Conversation Model - Persistent conversation history and memory.
"""

from datetime import datetime
from typing import Optional, List
from uuid import uuid4

from sqlalchemy import String, Text, Integer, Boolean, DateTime, ForeignKey, JSON, func, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class Conversation(Base, UUIDMixin, TimestampMixin):
    """
    A conversation session with the AI.
    
    Groups related messages together for context management.
    """
    
    __tablename__ = "conversations"
    
    # Owner
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Metadata
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # State
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Context management
    last_summary_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    context_tokens: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    messages: Mapped[List["ConversationMessage"]] = relationship(
        "ConversationMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.created_at",
    )
    
    def __repr__(self) -> str:
        return f"<Conversation {self.id[:8]}... ({self.message_count} messages)>"


class ConversationMessage(Base, UUIDMixin, TimestampMixin):
    """
    A single message in a conversation.
    """
    
    __tablename__ = "conversation_messages"
    
    # Parent conversation
    conversation_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Message content
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant, system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Metadata
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    
    # For assistant messages
    sources: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # RAG sources used
    confidence: Mapped[Optional[float]] = mapped_column(nullable=True)
    reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # For summarization
    is_summarized: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Relationships
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
    
    __table_args__ = (
        Index("ix_conversation_messages_conv_created", "conversation_id", "created_at"),
    )
    
    def __repr__(self) -> str:
        return f"<Message {self.role}: {self.content[:50]}...>"


class ExtractedFact(Base, UUIDMixin, TimestampMixin):
    """
    Facts and preferences extracted from conversations.
    
    Long-term memory that persists across conversations.
    """
    
    __tablename__ = "extracted_facts"
    
    # Owner
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Source
    conversation_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    message_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("conversation_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Fact content
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Categories: preference, fact, relationship, schedule, goal, habit
    
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(default=1.0)
    
    # State
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_referenced: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reference_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # For vector search
    embedding_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    def __repr__(self) -> str:
        return f"<Fact [{self.category}]: {self.content[:50]}...>"
