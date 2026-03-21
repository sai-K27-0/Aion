"""Tests for hub setup, registration lock, and token blacklist."""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_settings import SystemSettings


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
