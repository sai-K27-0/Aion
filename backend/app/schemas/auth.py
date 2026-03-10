"""
Authentication Schemas - Request/response models for auth endpoints.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, model_validator


# ============================================================================
# Request Schemas
# ============================================================================

class UserCreate(BaseModel):
    """Schema for user registration."""
    # Plan: username/password accounts; email optional.
    username: str = Field(..., min_length=3, max_length=100)
    email: Optional[EmailStr] = None
    password: str = Field(..., min_length=8, max_length=100)
    full_name: Optional[str] = Field(None, max_length=255)


class UserLogin(BaseModel):
    """Schema for user login."""
    # Backwards compatible: allow email or username; require one.
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    password: str
    device_id: Optional[str] = Field(
        None,
        description="Optional physical device id to embed in JWT claims",
    )

    @model_validator(mode="after")
    def _require_identifier(self):
        if not self.email and not self.username:
            raise ValueError("Either 'email' or 'username' is required")
        return self


class TokenRefresh(BaseModel):
    """Schema for token refresh."""
    refresh_token: str
    device_id: Optional[str] = Field(
        None,
        description="Optional device id to embed in rotated tokens",
    )


class PasswordChange(BaseModel):
    """Schema for password change."""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)


# ============================================================================
# Response Schemas
# ============================================================================

class UserResponse(BaseModel):
    """Schema for user data in responses."""
    id: str
    email: str
    username: Optional[str] = None
    full_name: Optional[str] = None
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None
    
    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """Schema for authentication token response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires
    user_id: Optional[str] = None  # included so clients can persist identity


class TokenPayload(BaseModel):
    """Schema for JWT token payload."""
    sub: str  # user ID
    exp: datetime
    type: str = "access"  # access or refresh
    device_id: Optional[str] = None
