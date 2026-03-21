"""System-wide settings for the Aion hub (singleton row pattern)."""
from typing import Optional

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin, TimestampMixin


class SystemSettings(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "system_settings"

    registration_locked: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    setup_complete: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    tunnel_domain: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, default=None
    )
    tunnel_type: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, default=None
    )  # "quick" | "permanent" | None
