"""
Device Service - Device registration and token management for multi-device sync.

This service manages device authentication and authorization for the sync system.
Each device gets its own access token for sync operations.
"""

import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from uuid import uuid4


# Token configuration
DEVICE_TOKEN_EXPIRE_DAYS = 30
DEVICE_TOKEN_PREFIX = "aion_dev_"


@dataclass
class RegisteredDevice:
    """A registered device with its authentication token."""
    device_id: str
    device_name: str
    device_type: str  # "desktop", "tablet", "phone"
    platform: str  # "windows", "macos", "android", "ios"
    token: str
    token_expires_at: datetime
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_active: Optional[datetime] = None
    user_id: Optional[str] = None  # Optional user association
    
    @property
    def is_token_valid(self) -> bool:
        """Check if the device token is still valid."""
        return datetime.now(timezone.utc) < self.token_expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "device_id": self.device_id,
            "device_name": self.device_name,
            "device_type": self.device_type,
            "platform": self.platform,
            "registered_at": self.registered_at.isoformat(),
            "last_active": self.last_active.isoformat() if self.last_active else None,
            "token_valid": self.is_token_valid,
        }


class DeviceService:
    """
    Manages device registration and authentication.
    
    Features:
    - Device registration with unique tokens
    - Token validation and refresh
    - Device activity tracking
    - Multi-user support (optional)
    """
    
    def __init__(self):
        # In-memory storage (replace with database in production)
        self._devices: Dict[str, RegisteredDevice] = {}
        self._tokens: Dict[str, str] = {}  # token -> device_id
    
    def _generate_token(self) -> str:
        """Generate a secure device token."""
        return f"{DEVICE_TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
    
    def register_device(
        self,
        device_id: str,
        device_name: str,
        device_type: str,
        platform: str,
        user_id: Optional[str] = None,
    ) -> RegisteredDevice:
        """
        Register a new device or refresh existing device token.
        
        Returns the registered device with its authentication token.
        """
        # Check if device already exists
        if device_id in self._devices:
            # Refresh token for existing device
            device = self._devices[device_id]
            old_token = device.token
            
            # Generate new token
            new_token = self._generate_token()
            device.token = new_token
            device.token_expires_at = datetime.now(timezone.utc) + timedelta(days=DEVICE_TOKEN_EXPIRE_DAYS)
            device.last_active = datetime.now(timezone.utc)
            device.device_name = device_name  # Allow name update
            
            # Update token mapping
            if old_token in self._tokens:
                del self._tokens[old_token]
            self._tokens[new_token] = device_id
            
            return device
        
        # Create new device
        token = self._generate_token()
        device = RegisteredDevice(
            device_id=device_id,
            device_name=device_name,
            device_type=device_type,
            platform=platform,
            token=token,
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=DEVICE_TOKEN_EXPIRE_DAYS),
            user_id=user_id,
        )
        
        self._devices[device_id] = device
        self._tokens[token] = device_id
        
        return device
    
    def validate_token(self, token: str) -> Optional[RegisteredDevice]:
        """
        Validate a device token and return the device if valid.
        
        Also updates the device's last_active timestamp.
        """
        if not token or not token.startswith(DEVICE_TOKEN_PREFIX):
            return None
        
        device_id = self._tokens.get(token)
        if not device_id:
            return None
        
        device = self._devices.get(device_id)
        if not device or not device.is_token_valid:
            return None
        
        # Update last active
        device.last_active = datetime.now(timezone.utc)
        
        return device
    
    def get_device(self, device_id: str) -> Optional[RegisteredDevice]:
        """Get a device by ID."""
        return self._devices.get(device_id)
    
    def get_device_by_token(self, token: str) -> Optional[RegisteredDevice]:
        """Get a device by its token."""
        return self.validate_token(token)
    
    def revoke_device(self, device_id: str) -> bool:
        """Revoke a device's access token."""
        device = self._devices.get(device_id)
        if not device:
            return False
        
        # Remove token mapping
        if device.token in self._tokens:
            del self._tokens[device.token]
        
        # Remove device
        del self._devices[device_id]
        
        return True
    
    def list_devices(self, user_id: Optional[str] = None) -> List[RegisteredDevice]:
        """List all registered devices, optionally filtered by user."""
        if user_id:
            return [d for d in self._devices.values() if d.user_id == user_id]
        return list(self._devices.values())
    
    def refresh_token(self, device_id: str) -> Optional[str]:
        """Refresh a device's token and return the new token."""
        device = self._devices.get(device_id)
        if not device:
            return None
        
        old_token = device.token
        new_token = self._generate_token()
        
        device.token = new_token
        device.token_expires_at = datetime.now(timezone.utc) + timedelta(days=DEVICE_TOKEN_EXPIRE_DAYS)
        device.last_active = datetime.now(timezone.utc)
        
        # Update token mapping
        if old_token in self._tokens:
            del self._tokens[old_token]
        self._tokens[new_token] = device_id
        
        return new_token
    
    def get_device_stats(self) -> Dict[str, Any]:
        """Get statistics about registered devices."""
        now = datetime.now(timezone.utc)
        active_24h = sum(
            1 for d in self._devices.values()
            if d.last_active and (now - d.last_active) < timedelta(hours=24)
        )
        
        by_type = {}
        by_platform = {}
        for device in self._devices.values():
            by_type[device.device_type] = by_type.get(device.device_type, 0) + 1
            by_platform[device.platform] = by_platform.get(device.platform, 0) + 1
        
        return {
            "total_devices": len(self._devices),
            "active_24h": active_24h,
            "by_type": by_type,
            "by_platform": by_platform,
        }


# Singleton instance
_device_service: Optional[DeviceService] = None


def get_device_service() -> DeviceService:
    """Get the device service singleton."""
    global _device_service
    if _device_service is None:
        _device_service = DeviceService()
    return _device_service
