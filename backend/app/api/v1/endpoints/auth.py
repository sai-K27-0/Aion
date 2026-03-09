"""
Authentication API Endpoints - User registration, login, and token management.
"""

from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.auth_service import AuthService
from app.schemas.auth import (
    UserCreate,
    UserLogin,
    UserResponse,
    TokenResponse,
    TokenRefresh,
    PasswordChange,
)
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter()


# ============================================================================
# Authentication Endpoints
# ============================================================================

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user",
)
async def register(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user account.
    
    - **email**: Valid email address (must be unique)
    - **password**: At least 8 characters
    - **username**: Optional username (must be unique if provided)
    - **full_name**: Optional display name
    """
    service = AuthService(db)
    
    try:
        user = await service.create_user(data)
        return UserResponse.model_validate(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login",
)
async def login(
    data: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    """
    Login with email and password.
    
    Returns access and refresh tokens for authentication.
    """
    service = AuthService(db)
    
    tokens = await service.login(
        email=data.email,
        username=data.username,
        password=data.password,
        device_id=data.device_id,
    )
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return tokens


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh tokens",
)
async def refresh_tokens(
    data: TokenRefresh,
    db: AsyncSession = Depends(get_db),
):
    """
    Refresh access token using a valid refresh token.
    
    Returns new access and refresh tokens.
    """
    service = AuthService(db)
    
    tokens = await service.refresh_tokens(data.refresh_token, device_id=data.device_id)
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return tokens


# ============================================================================
# User Profile Endpoints
# ============================================================================

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user",
)
async def get_me(
    current_user: User = Depends(get_current_user),
):
    """
    Get the currently authenticated user's profile.
    """
    return UserResponse.model_validate(current_user)


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change password",
)
async def change_password(
    data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Change the current user's password.
    
    Requires the current password for verification.
    """
    service = AuthService(db)
    
    success = await service.change_password(
        current_user.id,
        data.current_password,
        data.new_password,
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid current password",
        )


# ============================================================================
# Logout
# ============================================================================

@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout",
)
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Logout and blacklist the current token.

    The access token in the Authorization header will be invalidated.
    """
    auth_header = request.headers.get("authorization", "")
    token = auth_header.replace("Bearer ", "")
    auth_service = AuthService(db)
    await auth_service.logout(token)
    return Response(status_code=204)


# ============================================================================
# OAuth Stubs
# ============================================================================

@router.post(
    "/oauth/{provider}",
    summary="Initiate OAuth flow",
)
async def oauth_init(
    provider: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Initiate OAuth flow. Returns redirect URL.

    Currently returns 501 until OAuth providers are configured.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"OAuth with {provider} not yet configured. Set GOOGLE_CLIENT_ID/GITHUB_CLIENT_ID in environment.",
    )


@router.post(
    "/oauth/callback/{provider}",
    summary="Handle OAuth callback",
)
async def oauth_callback(
    provider: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle OAuth callback.

    Currently returns 501 until OAuth providers are configured.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"OAuth with {provider} not yet configured.",
    )
