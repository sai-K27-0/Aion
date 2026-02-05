"""
Device API Endpoints - Device registration and management.

Provides endpoints for:
- Device registration with token generation
- Token validation and refresh
- Device listing and management
"""

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, Header, Query

from app.services.device_service import get_device_service


router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================

class DeviceRegisterRequest(BaseModel):
    """Request to register a device."""
    device_id: str = Field(..., description="Unique device identifier (UUID recommended)")
    device_name: str = Field(..., description="Human-readable device name")
    device_type: str = Field(..., description="Device type: desktop, tablet, phone")
    platform: str = Field(..., description="Platform: windows, macos, android, ios")


class DeviceRegisterResponse(BaseModel):
    """Response with device token."""
    device_id: str
    device_name: str
    device_type: str
    platform: str
    token: str
    expires_at: str
    message: str


class DeviceInfoResponse(BaseModel):
    """Device information response."""
    device_id: str
    device_name: str
    device_type: str
    platform: str
    registered_at: str
    last_active: Optional[str]
    token_valid: bool


# =============================================================================
# Endpoints
# =============================================================================

@router.post(
    "/register",
    response_model=DeviceRegisterResponse,
    summary="Register Device",
    description="Register a new device and get an authentication token.",
)
async def register_device(request: DeviceRegisterRequest):
    """
    Register a new device for sync operations.
    
    Returns a device token that should be included in sync requests.
    If the device is already registered, a new token is generated.
    """
    service = get_device_service()
    
    device = service.register_device(
        device_id=request.device_id,
        device_name=request.device_name,
        device_type=request.device_type,
        platform=request.platform,
    )
    
    return DeviceRegisterResponse(
        device_id=device.device_id,
        device_name=device.device_name,
        device_type=device.device_type,
        platform=device.platform,
        token=device.token,
        expires_at=device.token_expires_at.isoformat(),
        message="Device registered successfully",
    )


@router.post(
    "/validate",
    summary="Validate Token",
    description="Validate a device token.",
)
async def validate_token(
    authorization: str = Header(..., description="Bearer token"),
):
    """
    Validate a device token and return device information.
    
    Include the token in the Authorization header as: Bearer <token>
    """
    service = get_device_service()
    
    # Extract token from header
    token = authorization.replace("Bearer ", "").strip()
    
    device = service.validate_token(token)
    if not device:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired device token",
        )
    
    return {
        "valid": True,
        "device": device.to_dict(),
    }


@router.post(
    "/refresh",
    summary="Refresh Token",
    description="Refresh a device's authentication token.",
)
async def refresh_token(
    device_id: str = Query(..., description="Device ID"),
    authorization: str = Header(..., description="Current Bearer token"),
):
    """
    Refresh a device's token and return the new token.
    
    The old token will be invalidated.
    """
    service = get_device_service()
    
    # Validate current token
    token = authorization.replace("Bearer ", "").strip()
    device = service.validate_token(token)
    
    if not device or device.device_id != device_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid token or device ID mismatch",
        )
    
    # Generate new token
    new_token = service.refresh_token(device_id)
    if not new_token:
        raise HTTPException(
            status_code=500,
            detail="Failed to refresh token",
        )
    
    return {
        "token": new_token,
        "expires_at": device.token_expires_at.isoformat(),
        "message": "Token refreshed successfully",
    }


@router.delete(
    "/{device_id}",
    summary="Revoke Device",
    description="Revoke a device's access.",
)
async def revoke_device(
    device_id: str,
    authorization: str = Header(..., description="Bearer token"),
):
    """
    Revoke a device's access token and remove it from the system.
    
    Use this when a device is lost or no longer needs access.
    """
    service = get_device_service()
    
    # Validate token (allow self-revocation or admin)
    token = authorization.replace("Bearer ", "").strip()
    device = service.validate_token(token)
    
    if not device:
        raise HTTPException(
            status_code=401,
            detail="Invalid device token",
        )
    
    success = service.revoke_device(device_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Device not found",
        )
    
    return {"message": f"Device {device_id} revoked successfully"}


@router.get(
    "/",
    summary="List Devices",
    description="List all registered devices.",
)
async def list_devices():
    """List all registered devices and their status."""
    service = get_device_service()
    
    devices = service.list_devices()
    
    return {
        "devices": [d.to_dict() for d in devices],
        "count": len(devices),
    }


@router.get(
    "/stats",
    summary="Device Statistics",
    description="Get statistics about registered devices.",
)
async def get_stats():
    """Get statistics about registered devices."""
    service = get_device_service()
    return service.get_device_stats()


@router.get(
    "/{device_id}",
    response_model=DeviceInfoResponse,
    summary="Get Device Info",
    description="Get information about a specific device.",
)
async def get_device(device_id: str):
    """Get information about a specific registered device."""
    service = get_device_service()
    
    device = service.get_device(device_id)
    if not device:
        raise HTTPException(
            status_code=404,
            detail="Device not found",
        )
    
    return DeviceInfoResponse(
        device_id=device.device_id,
        device_name=device.device_name,
        device_type=device.device_type,
        platform=device.platform,
        registered_at=device.registered_at.isoformat(),
        last_active=device.last_active.isoformat() if device.last_active else None,
        token_valid=device.is_token_valid,
    )
