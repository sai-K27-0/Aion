"""
Trigger Model - Automated actions based on system events.
"""

from typing import Optional
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin, SyncMixin

class Trigger(Base, UUIDMixin, TimestampMixin, SyncMixin):
    """
    Defines an automated rule in Aion.
    
    Trigger Types:
    - block_created: Fires when a new block is added.
    - block_updated: Fires when block name/description changes.
    - field_updated: Fires when a specific field in a database block changes.
    - time_reached: Scheduled automation.
    - neural_match: Fires when a new memory is semantically similar to a watchword.
    
    Actions:
    - action_type matches ActionService dispatch keys (e.g., 'open_url', 'browser_task').
    """
    
    __tablename__ = "triggers"
    
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # event_type: block_created, block_updated, field_updated, etc.
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    # condition: JSON logic or search criteria (e.g., {"block_name": "Urgent"})
    condition: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    
    # Action to execute
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    action_params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    
    # Optional association with a block
    block_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("blocks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    
    # Relationship
    block: Mapped[Optional["Block"]] = relationship("Block")

    def __repr__(self) -> str:
        return f"<Trigger(name='{self.name}', event='{self.event_type}', active={self.is_active})>"
