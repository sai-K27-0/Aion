"""
Block Model - The fundamental organizational unit of Aion.

This module implements a hierarchical Block system using a hybrid approach:
- Adjacency List: Simple parent_id relationship for immediate parent
- Materialized Path (ltree): PostgreSQL ltree extension for efficient tree queries

The ltree extension enables O(1) ancestor/descendant queries, which is critical
for displaying block hierarchies and performing bulk operations.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin, SyncMixin

if TYPE_CHECKING:
    from typing import List


class Block(Base, UUIDMixin, TimestampMixin, SyncMixin):
    """
    The fundamental organizational unit in Aion.
    
    Blocks form a tree structure where each block can contain:
    - Sub-blocks (nested hierarchy)
    - Custom database fields (Notion-like)
    - Database entries (rows)
    - Rich text content
    
    The hierarchy is managed using both:
    - parent_id: Direct parent reference (adjacency list)
    - path: Materialized path using PostgreSQL ltree for efficient queries
    
    Examples of blocks:
    - "Work" -> "Project Phoenix" -> "Research Phase"
    - "Personal" -> "Health" -> "Exercise Log"
    - "Studies" -> "Computer Science" -> "Machine Learning"
    """
    
    __tablename__ = "blocks"
    
    # Basic metadata
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Emoji or icon key
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)  # Hex color
    
    # Hierarchy - Adjacency List
    parent_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("blocks.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    
    # Hierarchy - Materialized Path (stored as text, ltree operations in queries)
    # Format: "root_id.parent_id.current_id" using safe IDs
    # Note: Actual ltree type requires PostgreSQL extension; we use text + custom queries
    path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Ordering within parent
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Extensible properties (custom metadata)
    properties: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    
    # Block type for different behaviors
    block_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="default",
    )  # default, database, document, folder, etc.
    
    # Relationships
    parent: Mapped[Optional["Block"]] = relationship(
        "Block",
        remote_side="Block.id",
        back_populates="children",
    )
    children: Mapped[list["Block"]] = relationship(
        "Block",
        back_populates="parent",
        cascade="all, delete-orphan",
        order_by="Block.position",
    )
    fields: Mapped[list["BlockField"]] = relationship(
        "BlockField",
        back_populates="block",
        cascade="all, delete-orphan",
        order_by="BlockField.position",
    )
    entries: Mapped[list["BlockEntry"]] = relationship(
        "BlockEntry",
        back_populates="block",
        cascade="all, delete-orphan",
    )
    contents: Mapped[list["BlockContent"]] = relationship(
        "BlockContent",
        back_populates="block",
        cascade="all, delete-orphan",
    )
    
    # Indexes for efficient querying
    __table_args__ = (
        Index("ix_blocks_path", "path"),
        Index("ix_blocks_parent_position", "parent_id", "position"),
        Index("ix_blocks_type", "block_type"),
        UniqueConstraint("parent_id", "name", name="uq_block_parent_name"),
    )
    
    def __repr__(self) -> str:
        return f"<Block(id={self.id}, name='{self.name}', depth={self.depth})>"
    
    @property
    def is_root(self) -> bool:
        """Check if this block is a root-level block."""
        return self.parent_id is None
    
    def get_path_ids(self) -> list[str]:
        """Get list of block IDs from root to this block."""
        if not self.path:
            return [self.id]
        return self.path.split(".") + [self.id]


class BlockField(Base, UUIDMixin, TimestampMixin, SyncMixin):
    """
    Custom field definition for a Block's database.
    
    Similar to Notion's database properties, each field defines
    a column in the block's data table.
    
    Supported field types:
    - text: Plain or rich text
    - number: Integer or decimal
    - date: Date or datetime
    - select: Single selection from options
    - multi_select: Multiple selections
    - checkbox: Boolean
    - url: URL with optional preview
    - email: Email address
    - phone: Phone number
    - relation: Link to entries in another block
    - rollup: Computed from related entries
    - formula: Calculated from other fields
    - file: File attachment reference
    """
    
    __tablename__ = "block_fields"
    
    block_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("blocks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    field_type: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Field configuration (options for select, format for date, etc.)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    
    # Display order
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Field options
    is_required: Mapped[bool] = mapped_column(default=False)
    is_hidden: Mapped[bool] = mapped_column(default=False)
    default_value: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Relationships
    block: Mapped["Block"] = relationship("Block", back_populates="fields")
    
    __table_args__ = (
        UniqueConstraint("block_id", "name", name="uq_field_block_name"),
        Index("ix_block_fields_block_position", "block_id", "position"),
    )
    
    def __repr__(self) -> str:
        return f"<BlockField(name='{self.name}', type='{self.field_type}')>"


class BlockEntry(Base, UUIDMixin, TimestampMixin, SyncMixin):
    """
    A single entry (row) in a Block's database.
    
    The data is stored as JSONB with field IDs as keys,
    allowing flexible schema and efficient querying.
    """
    
    __tablename__ = "block_entries"
    
    block_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("blocks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Field values (keys are field IDs, values are the data)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    
    # Entry metadata
    is_archived: Mapped[bool] = mapped_column(default=False)
    archived_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    
    # Relationships
    block: Mapped["Block"] = relationship("Block", back_populates="entries")
    
    __table_args__ = (
        Index("ix_block_entries_block_archived", "block_id", "is_archived"),
        Index("ix_block_entries_data", "data", postgresql_using="gin"),
    )
    
    def __repr__(self) -> str:
        return f"<BlockEntry(id={self.id}, block_id={self.block_id})>"


class BlockContent(Base, UUIDMixin, TimestampMixin, SyncMixin):
    """
    Rich text content associated with a Block.
    
    Stores unstructured content like notes, documents,
    and any free-form text. Supports full-text search
    via PostgreSQL tsvector.
    """
    
    __tablename__ = "block_contents"
    
    block_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("blocks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Content storage
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="markdown",
    )  # markdown, html, plain
    
    # Ordering within block
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Full-text search vector (populated by trigger)
    # search_vector: Mapped[str] = mapped_column(TSVECTOR, nullable=True)
    
    # Relationships
    block: Mapped["Block"] = relationship("Block", back_populates="contents")
    
    __table_args__ = (
        Index("ix_block_contents_block_position", "block_id", "position"),
    )
    
    def __repr__(self) -> str:
        title_preview = self.title[:30] if self.title else "Untitled"
        return f"<BlockContent(title='{title_preview}...')>"


# Event listeners for automatic path management
@event.listens_for(Block, "before_insert")
def set_block_path(mapper, connection, target: Block):
    """Automatically set the materialized path before insertion."""
    if target.parent_id:
        # Path will be set by the service layer after parent is fetched
        pass
    else:
        # Root block
        target.path = ""
        target.depth = 0


@event.listens_for(Block, "before_update")
def update_block_path(mapper, connection, target: Block):
    """Update path when parent changes."""
    # Path updates should be handled by the service layer
    # to properly update all descendant paths
    pass
