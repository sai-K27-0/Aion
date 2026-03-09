"""
User Model - Authentication and user management.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, Boolean, DateTime, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class User(Base, UUIDMixin, TimestampMixin):
    """
    User account for authentication.
    
    Stores user credentials and profile information.
    Passwords are hashed using bcrypt.
    """
    
    __tablename__ = "users"
    
    # Authentication
    # Email is optional (plan: username/password accounts).
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Profile
    username: Mapped[Optional[str]] = mapped_column(String(100), unique=True, nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Auth provider: "local", "google", "github"
    auth_provider: Mapped[str] = mapped_column(
        String(20), default="local", server_default="local"
    )
    # Email verification
    email_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    # OAuth provider user ID (for Google/GitHub)
    oauth_provider_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )

    # Token management
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    def __repr__(self) -> str:
        return f"<User {self.email}>"
