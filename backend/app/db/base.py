"""
SQLAlchemy Base class and common model mixins.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import DateTime, Integer, Boolean, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    
    # Enable type annotations
    type_annotation_map = {
        datetime: DateTime(timezone=True),
    }


class TimestampMixin:
    """Mixin that adds created_at and updated_at timestamps."""
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDMixin:
    """Mixin that adds a UUID primary key."""
    
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )


class SyncMixin:
    """
    Mixin that adds sync tracking fields for offline-first multi-device sync.
    
    Fields:
    - sync_id: Unique identifier for sync operations (different from id for conflict resolution)
    - sync_version: Incrementing version number for conflict detection
    - local_updated_at: Timestamp from the client device (may differ from updated_at)
    - is_deleted: Soft delete flag for sync (record is hidden but synced to other devices)
    - device_id: ID of the device that last modified this record
    """
    
    sync_id: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        default=lambda: str(uuid4()),
        nullable=False,
        index=True,
    )
    
    sync_version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )
    
    local_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )
    
    device_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
