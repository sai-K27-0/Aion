"""Tests for hub setup, registration lock, and token blacklist."""
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device, ApprovalStatus
from app.models.system_settings import SystemSettings
from app.models.user import User
from app.schemas.auth import UserCreate


class TestSystemSettings:
    @pytest.mark.asyncio
    async def test_create_default_settings(self, db_session: AsyncSession):
        settings = SystemSettings()
        db_session.add(settings)
        await db_session.commit()
        await db_session.refresh(settings)

        assert settings.id is not None
        assert settings.registration_locked is True
        assert settings.setup_complete is False
        assert settings.tunnel_domain is None
        assert settings.tunnel_type is None

    @pytest.mark.asyncio
    async def test_update_tunnel_config(self, db_session: AsyncSession):
        settings = SystemSettings()
        db_session.add(settings)
        await db_session.commit()

        settings.tunnel_domain = "aion.example.com"
        settings.tunnel_type = "permanent"
        await db_session.commit()
        await db_session.refresh(settings)

        assert settings.tunnel_domain == "aion.example.com"
        assert settings.tunnel_type == "permanent"


class TestTokenBlacklistService:
    @pytest.mark.asyncio
    async def test_blacklist_and_check(self):
        from app.services.token_blacklist_service import TokenBlacklistService

        service = TokenBlacklistService()
        # Falls back to in-memory since Redis isn't running in tests
        await service.blacklist_token("test-jti-123", expires_in=3600)
        assert await service.is_blacklisted("test-jti-123") is True

    @pytest.mark.asyncio
    async def test_not_blacklisted(self):
        from app.services.token_blacklist_service import TokenBlacklistService

        service = TokenBlacklistService()
        assert await service.is_blacklisted("unknown-jti") is False


class TestRegistrationLock:
    @pytest.mark.asyncio
    async def test_first_user_becomes_superuser(self, db_session: AsyncSession):
        from app.services.auth_service import register_user_with_lock

        user = await register_user_with_lock(
            db=db_session,
            data=UserCreate(username="admin", password="securepass123"),
        )
        assert user.is_superuser is True
        assert user.username == "admin"

    @pytest.mark.asyncio
    async def test_auto_creates_settings_after_first_user(self, db_session: AsyncSession):
        from app.services.auth_service import register_user_with_lock

        await register_user_with_lock(
            db=db_session,
            data=UserCreate(username="admin", password="securepass123"),
        )
        result = await db_session.execute(select(SystemSettings).limit(1))
        settings = result.scalar_one_or_none()
        assert settings is not None
        assert settings.registration_locked is True

    @pytest.mark.asyncio
    async def test_registration_locked_after_first_user(self, db_session: AsyncSession):
        from app.services.auth_service import register_user_with_lock

        await register_user_with_lock(
            db=db_session,
            data=UserCreate(username="admin", password="securepass123"),
        )

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await register_user_with_lock(
                db=db_session,
                data=UserCreate(username="user2", password="securepass123"),
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_registration_allowed_when_unlocked(self, db_session: AsyncSession):
        from app.services.auth_service import register_user_with_lock

        await register_user_with_lock(
            db=db_session,
            data=UserCreate(username="admin", password="securepass123"),
        )

        result = await db_session.execute(select(SystemSettings).limit(1))
        settings = result.scalar_one()
        settings.registration_locked = False
        await db_session.commit()

        user2 = await register_user_with_lock(
            db=db_session,
            data=UserCreate(username="user2", password="securepass123"),
        )
        assert user2.is_superuser is False


class TestHubEndpoints:
    @pytest.mark.asyncio
    async def test_hub_status_public_no_setup(self, db_session: AsyncSession):
        """When no SystemSettings exists, setup_complete=False, registration_open=True."""
        from app.api.v1.endpoints.hub import _get_hub_status_public
        result = await _get_hub_status_public(db_session)
        assert result.setup_complete is False
        assert result.registration_open is True

    @pytest.mark.asyncio
    async def test_hub_status_public_after_setup(self, db_session: AsyncSession):
        """After setup, reflects actual state."""
        from app.api.v1.endpoints.hub import _get_hub_status_public
        settings = SystemSettings(setup_complete=True, registration_locked=True)
        db_session.add(settings)
        await db_session.commit()

        result = await _get_hub_status_public(db_session)
        assert result.setup_complete is True
        assert result.registration_open is False

    @pytest.mark.asyncio
    async def test_registration_status(self, db_session: AsyncSession):
        """Registration is open when no users exist."""
        from app.api.v1.endpoints.hub import _get_registration_status
        result = await _get_registration_status(db_session)
        assert result.open is True


class TestDeviceServiceDB:
    @pytest.mark.asyncio
    async def test_register_first_device_auto_approved(self, db_session: AsyncSession):
        """First device for a user should be auto-approved."""
        user = User(
            id="test-user-id",
            username="testuser",
            hashed_password="fakehash",
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()

        from app.services.device_service import get_device_service
        service = get_device_service()
        result = await service.register_device(
            db=db_session,
            device_id="device-001",
            device_name="My PC",
            device_type="desktop",
            platform="windows",
            user_id="test-user-id",
        )
        assert result["approval_status"] == ApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_register_second_device_pending(self, db_session: AsyncSession):
        """Second device should be pending approval."""
        user = User(
            id="test-user-id",
            username="testuser",
            hashed_password="fakehash",
            is_active=True,
        )
        db_session.add(user)
        first_device = Device(
            id="device-001",
            device_name="First PC",
            device_type="desktop",
            platform="windows",
            user_id="test-user-id",
            approval_status=ApprovalStatus.APPROVED,
        )
        db_session.add(first_device)
        await db_session.commit()

        from app.services.device_service import get_device_service
        service = get_device_service()
        result = await service.register_device(
            db=db_session,
            device_id="device-002",
            device_name="Phone",
            device_type="phone",
            platform="android",
            user_id="test-user-id",
        )
        assert result["approval_status"] == ApprovalStatus.PENDING
        assert result.get("approval_code") is not None
        assert len(result["approval_code"]) == 6
