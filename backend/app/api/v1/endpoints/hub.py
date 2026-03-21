"""Hub status and configuration endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.api.deps import get_current_user
from app.models.system_settings import SystemSettings
from app.models.user import User
from app.schemas.hub import (
    HubStatusPublicResponse,
    HubStatusAdminResponse,
    RegistrationStatusResponse,
    TunnelConfigRequest,
    TunnelConfigResponse,
)

router = APIRouter()

VERSION = "0.5.0"


async def _get_or_create_settings(db: AsyncSession) -> SystemSettings:
    """Get the singleton SystemSettings row, creating it if absent."""
    result = await db.execute(select(SystemSettings).limit(1))
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = SystemSettings()
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings


async def _require_admin(
    user: User = Depends(get_current_user),
) -> User:
    """Dependency that requires an authenticated admin user."""
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def _get_hub_status_public(db: AsyncSession) -> HubStatusPublicResponse:
    """Build public hub status (no sensitive info)."""
    settings_result = await db.execute(select(SystemSettings).limit(1))
    settings = settings_result.scalar_one_or_none()

    if settings is None:
        return HubStatusPublicResponse(setup_complete=False, registration_open=True)

    return HubStatusPublicResponse(
        setup_complete=settings.setup_complete,
        registration_open=not settings.registration_locked,
    )


async def _get_registration_status(db: AsyncSession) -> RegistrationStatusResponse:
    """Check if registration is open."""
    user_count = await db.scalar(select(func.count(User.id)))
    if user_count == 0:
        return RegistrationStatusResponse(open=True)

    settings_result = await db.execute(select(SystemSettings).limit(1))
    settings = settings_result.scalar_one_or_none()
    if settings is None:
        return RegistrationStatusResponse(open=False)

    return RegistrationStatusResponse(open=not settings.registration_locked)


@router.get("/status")
async def hub_status(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_require_admin),
):
    """Hub status — full info for authenticated admins only.
    Unauthenticated callers get public response via /status/public."""
    settings = await _get_or_create_settings(db)
    user_count = await db.scalar(select(func.count(User.id)))
    return HubStatusAdminResponse(
        setup_complete=settings.setup_complete,
        registration_open=not settings.registration_locked,
        user_count=user_count,
        tunnel_active=settings.tunnel_domain is not None,
        version=VERSION,
    )


@router.get("/status/public", response_model=HubStatusPublicResponse)
async def hub_status_public(db: AsyncSession = Depends(get_db)):
    """Public hub status — minimal info, no auth required."""
    return await _get_hub_status_public(db)


@router.get("/registration-status", response_model=RegistrationStatusResponse)
async def registration_status(db: AsyncSession = Depends(get_db)):
    """Check if registration is currently open."""
    return await _get_registration_status(db)


@router.post("/setup-complete")
async def mark_setup_complete(
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Mark hub setup as complete. Requires admin auth."""
    settings = await _get_or_create_settings(db)
    settings.setup_complete = True
    await db.commit()
    return {"ok": True}


@router.post("/registration-lock")
async def lock_registration(
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Lock registration. Requires admin auth."""
    settings = await _get_or_create_settings(db)
    settings.registration_locked = True
    await db.commit()
    return {"locked": True}


@router.post("/registration-unlock")
async def unlock_registration(
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Unlock registration. Requires admin auth."""
    settings = await _get_or_create_settings(db)
    settings.registration_locked = False
    await db.commit()
    return {"locked": False}


@router.post("/tunnel-config", response_model=TunnelConfigResponse)
async def update_tunnel_config(
    config: TunnelConfigRequest,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update tunnel configuration. Requires admin auth."""
    settings = await _get_or_create_settings(db)
    settings.tunnel_domain = config.domain
    settings.tunnel_type = config.tunnel_type
    await db.commit()
    return TunnelConfigResponse(
        domain=settings.tunnel_domain,
        tunnel_type=settings.tunnel_type,
        active=settings.tunnel_domain is not None,
    )
