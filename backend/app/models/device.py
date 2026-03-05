"""
Device Model - Registered devices for multi-device sync.

Includes one-time device approval system:
- First device for a user is auto-approved (bootstrap)
- Subsequent devices require approval from an already-approved device
- Approval uses a 6-character code for verification
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, DateTime, ForeignKey, Text, Index, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class ApprovalStatus:
    """Device approval status constants."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Device(Base, TimestampMixin):
    """
    Registered device for synchronization.

    Stores information about devices that sync with the server,
    including their last sync time, authentication tokens, and
    approval status for the one-time device verification system.
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

    # Device Approval (one-time verification)
    approval_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ApprovalStatus.PENDING,
        server_default=ApprovalStatus.APPROVED,  # Existing devices grandfathered
    )
    approval_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    approved_by_device_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Metadata
    app_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    os_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    push_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # For push notifications

    # Relationships
    user = relationship("User", backref="devices", lazy="selectin")

    # Indexes
    __table_args__ = (
        Index("ix_devices_approval_status", "approval_status"),
    )

    @property
    def is_approved(self) -> bool:
        """Check if this device has been approved for sync."""
        return self.approval_status == ApprovalStatus.APPROVED

    def __repr__(self) -> str:
        return f"<Device {self.device_name} ({self.device_type}) [{self.approval_status}]>"

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
            "approval_status": self.approval_status,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "app_version": self.app_version,
            "registered_at": self.created_at.isoformat() if self.created_at else None,
        }
