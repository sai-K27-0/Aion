"""Schemas for hub status and configuration endpoints."""
from typing import Optional

from pydantic import BaseModel


class HubStatusPublicResponse(BaseModel):
    """Returned to unauthenticated callers — minimal info only."""
    setup_complete: bool
    registration_open: bool


class HubStatusAdminResponse(HubStatusPublicResponse):
    """Returned to authenticated admin — includes operational details."""
    user_count: int
    tunnel_active: bool
    version: str


class RegistrationStatusResponse(BaseModel):
    open: bool


class RegistrationLockRequest(BaseModel):
    locked: bool


class TunnelConfigRequest(BaseModel):
    domain: str
    tunnel_type: str  # "quick" | "permanent"


class TunnelConfigResponse(BaseModel):
    domain: Optional[str]
    tunnel_type: Optional[str]
    active: bool
