"""
Authentication Service - JWT token management and user authentication.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.schemas.auth import UserCreate, TokenResponse, TokenPayload


# JWT Configuration
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7


class AuthService:
    """Service for authentication operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # ========================================================================
    # Password Management
    # ========================================================================
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt."""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode(), salt).decode()
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
    
    # ========================================================================
    # Token Management
    # ========================================================================
    
    @staticmethod
    def create_access_token(user_id: str, device_id: Optional[str] = None) -> tuple[str, datetime]:
        """Create a JWT access token."""
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        payload = {
            "sub": user_id,
            "exp": expires_at,
            "type": "access",
            "jti": str(uuid4()),  # unique token ID
        }
        if device_id:
            payload["device_id"] = device_id
        token = jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)
        return token, expires_at
    
    @staticmethod
    def create_refresh_token(user_id: str, device_id: Optional[str] = None) -> tuple[str, datetime]:
        """Create a JWT refresh token."""
        expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        payload = {
            "sub": user_id,
            "exp": expires_at,
            "type": "refresh",
            "jti": str(uuid4()),
        }
        if device_id:
            payload["device_id"] = device_id
        token = jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)
        return token, expires_at
    
    @staticmethod
    def decode_token(token: str) -> Optional[TokenPayload]:
        """Decode and validate a JWT token."""
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
            return TokenPayload(
                sub=payload["sub"],
                exp=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
                type=payload.get("type", "access"),
                device_id=payload.get("device_id"),
            )
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
    
    # ========================================================================
    # User Operations
    # ========================================================================
    
    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email address."""
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Get a user by username."""
        result = await self.db.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()
    
    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get a user by ID."""
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def create_user(self, data: UserCreate) -> User:
        """Create a new user account."""
        # Check if username already exists
        existing_username = await self.get_user_by_username(data.username)
        if existing_username:
            raise ValueError("Username already taken")

        # Email is optional; if provided, enforce uniqueness
        if data.email:
            existing_email = await self.get_user_by_email(data.email)
            if existing_email:
                raise ValueError("Email already registered")
        
        # Create user
        user = User(
            email=data.email,
            hashed_password=self.hash_password(data.password),
            username=data.username,
            full_name=data.full_name,
        )
        
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        
        return user
    
    async def authenticate(self, *, email: Optional[str], username: Optional[str], password: str) -> Optional[User]:
        """Authenticate a user by email or username and password."""
        user: Optional[User] = None
        if email:
            user = await self.get_user_by_email(email)
        elif username:
            user = await self.get_user_by_username(username)
        if not user:
            return None
        if not self.verify_password(password, user.hashed_password):
            return None
        if not user.is_active:
            return None
        
        # Update last login
        user.last_login = datetime.now(timezone.utc)
        await self.db.commit()
        
        return user
    
    async def login(
        self,
        *,
        email: Optional[str],
        username: Optional[str],
        password: str,
        device_id: Optional[str] = None,
    ) -> Optional[TokenResponse]:
        """Authenticate and return tokens."""
        user = await self.authenticate(email=email, username=username, password=password)
        if not user:
            return None
        
        access_token, access_exp = self.create_access_token(user.id, device_id=device_id)
        refresh_token, _ = self.create_refresh_token(user.id, device_id=device_id)
        
        expires_in = int((access_exp - datetime.now(timezone.utc)).total_seconds())
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=expires_in,
            user_id=user.id,
        )

    async def refresh_tokens(self, refresh_token: str, device_id: Optional[str] = None) -> Optional[TokenResponse]:
        """Refresh access token using refresh token."""
        payload = self.decode_token(refresh_token)
        if not payload or payload.type != "refresh":
            return None

        user = await self.get_user_by_id(payload.sub)
        if not user or not user.is_active:
            return None

        effective_device_id = device_id or payload.device_id
        access_token, access_exp = self.create_access_token(user.id, device_id=effective_device_id)
        new_refresh_token, _ = self.create_refresh_token(user.id, device_id=effective_device_id)

        expires_in = int((access_exp - datetime.now(timezone.utc)).total_seconds())

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=expires_in,
            user_id=user.id,
        )
    
    async def change_password(self, user_id: str, current_password: str, new_password: str) -> bool:
        """Change a user's password."""
        user = await self.get_user_by_id(user_id)
        if not user:
            return False
        
        if not self.verify_password(current_password, user.hashed_password):
            return False
        
        user.hashed_password = self.hash_password(new_password)
        await self.db.commit()
        
        return True


# Dependency provider
async def get_auth_service(db: AsyncSession) -> AuthService:
    """Get an AuthService instance."""
    return AuthService(db)
