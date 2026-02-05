"""
Device Model - Registered devices for multi-device sync.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Device(Base, TimestampMixin):
    """
    Registered device for synchronization.
    
    Stores information about devices that sync with the server,
    including their last sync time and authentication tokens.
    """
    
    __tablename__ = "devices"
    
    # Primary key - the device's unique identifier
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    
    # Device information
    device_name: Mapped[str] = mapped_column(String(255), nullable=False)
    device_type: Mapped[str] = mapped_column(String(50), nullable=False)  # desktop, tablet, phone
    platform: Mapped[str] = mapped_column(String(50), nullable=False)  # windows, macos, android, ios, linux
    
    # Owner (optional - for multi-user support)
    user_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), 
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    
    # Sync state
    last_sync: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_version: Mapped[int] = mapped_column(default=0, nullable=False)
    
    # Authentication
    device_token: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Status
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    
    # Metadata
    app_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    os_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    push_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # For push notifications
    
    # Relationships
    user = relationship("User", backref="devices", lazy="selectin")
    
    def __repr__(self) -> str:
        return f"<Device {self.device_name} ({self.device_type})>"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "device_id": self.id,
            "device_name": self.device_name,
            "device_type": self.device_type,
            "platform": self.platform,
            "user_id": self.user_id,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "is_active": self.is_active,
            "app_version": self.app_version,
            "registered_at": self.created_at.isoformat() if self.created_at else None,
        }
