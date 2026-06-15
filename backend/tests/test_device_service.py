"""Tests for DeviceService: first-device auto-approval, pending second device, approval flow."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device, ApprovalStatus
from app.models.user import User
from app.services.device_service import DeviceService, _CODE_CHARS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(user_id: str = "user-001") -> User:
    return User(
        id=user_id,
        username=f"u_{user_id}",
        hashed_password="fakehash",
        is_active=True,
    )


class TestFirstDeviceAutoApproved:
    async def test_status_is_approved(self, db_session: AsyncSession):
        db_session.add(_make_user())
        await db_session.commit()

        svc = DeviceService()
        result = await svc.register_device(
            db=db_session,
            device_id="dev-001",
            device_name="Desktop",
            device_type="desktop",
            platform="linux",
            user_id="user-001",
        )

        assert result["approval_status"] == ApprovalStatus.APPROVED

    async def test_no_approval_code_on_first_device(self, db_session: AsyncSession):
        db_session.add(_make_user())
        await db_session.commit()

        svc = DeviceService()
        result = await svc.register_device(
            db=db_session,
            device_id="dev-001",
            device_name="Desktop",
            device_type="desktop",
            platform="macos",
            user_id="user-001",
        )

        assert result.get("approval_code") is None

    async def test_message_indicates_auto_approved(self, db_session: AsyncSession):
        db_session.add(_make_user())
        await db_session.commit()

        svc = DeviceService()
        result = await svc.register_device(
            db=db_session,
            device_id="dev-001",
            device_name="Desktop",
            device_type="desktop",
            platform="windows",
            user_id="user-001",
        )

        assert "auto-approved" in result["message"].lower()


class TestSecondDevicePendingWithCode:
    async def _seed(self, db_session: AsyncSession) -> None:
        """Seed user + already-approved first device."""
        db_session.add(_make_user())
        db_session.add(
            Device(
                id="dev-001",
                device_name="First",
                device_type="desktop",
                platform="linux",
                user_id="user-001",
                approval_status=ApprovalStatus.APPROVED,
                is_active=True,
            )
        )
        await db_session.commit()

    async def test_status_is_pending(self, db_session: AsyncSession):
        await self._seed(db_session)

        svc = DeviceService()
        result = await svc.register_device(
            db=db_session,
            device_id="dev-002",
            device_name="Phone",
            device_type="phone",
            platform="android",
            user_id="user-001",
        )

        assert result["approval_status"] == ApprovalStatus.PENDING

    async def test_approval_code_present(self, db_session: AsyncSession):
        await self._seed(db_session)

        svc = DeviceService()
        result = await svc.register_device(
            db=db_session,
            device_id="dev-002",
            device_name="Phone",
            device_type="phone",
            platform="android",
            user_id="user-001",
        )

        assert result.get("approval_code") is not None

    async def test_approval_code_is_6_chars(self, db_session: AsyncSession):
        await self._seed(db_session)

        svc = DeviceService()
        result = await svc.register_device(
            db=db_session,
            device_id="dev-002",
            device_name="Phone",
            device_type="phone",
            platform="ios",
            user_id="user-001",
        )

        assert len(result["approval_code"]) == 6

    async def test_approval_code_uses_safe_charset(self, db_session: AsyncSession):
        """Code must not contain ambiguous characters (0, O, I, 1, L)."""
        await self._seed(db_session)

        svc = DeviceService()
        result = await svc.register_device(
            db=db_session,
            device_id="dev-002",
            device_name="Phone",
            device_type="phone",
            platform="android",
            user_id="user-001",
        )

        code = result["approval_code"]
        for ch in code:
            assert ch in _CODE_CHARS, f"Ambiguous character {ch!r} found in code {code!r}"


class TestApproveDevice:
    async def _seed_pending(self, db_session: AsyncSession) -> str:
        """Return the approval code of the pending second device."""
        db_session.add(_make_user())
        db_session.add(
            Device(
                id="dev-001",
                device_name="First",
                device_type="desktop",
                platform="linux",
                user_id="user-001",
                approval_status=ApprovalStatus.APPROVED,
                is_active=True,
            )
        )
        await db_session.commit()

        svc = DeviceService()
        result = await svc.register_device(
            db=db_session,
            device_id="dev-002",
            device_name="Phone",
            device_type="phone",
            platform="android",
            user_id="user-001",
        )
        return result["approval_code"]

    async def test_approve_with_valid_code(self, db_session: AsyncSession):
        code = await self._seed_pending(db_session)

        svc = DeviceService()
        result = await svc.approve_device(
            db=db_session,
            device_id="dev-002",
            code=code,
            approver_device_id="dev-001",
        )

        assert result["approval_status"] == ApprovalStatus.APPROVED

    async def test_code_cleared_after_approval(self, db_session: AsyncSession):
        code = await self._seed_pending(db_session)

        svc = DeviceService()
        await svc.approve_device(
            db=db_session,
            device_id="dev-002",
            code=code,
            approver_device_id="dev-001",
        )

        device = await svc.get_device(db_session, "dev-002")
        assert device.approval_code is None

    async def test_invalid_code_raises(self, db_session: AsyncSession):
        await self._seed_pending(db_session)

        svc = DeviceService()
        with pytest.raises(ValueError, match="Invalid approval code"):
            await svc.approve_device(
                db=db_session,
                device_id="dev-002",
                code="XXXXXX",
                approver_device_id="dev-001",
            )

    async def test_reapprove_already_approved_raises(self, db_session: AsyncSession):
        code = await self._seed_pending(db_session)

        svc = DeviceService()
        await svc.approve_device(
            db=db_session,
            device_id="dev-002",
            code=code,
            approver_device_id="dev-001",
        )

        with pytest.raises(ValueError):
            await svc.approve_device(
                db=db_session,
                device_id="dev-002",
                code=code,
                approver_device_id="dev-001",
            )


class TestIdempotentRegistration:
    async def test_same_device_id_returns_existing(self, db_session: AsyncSession):
        db_session.add(_make_user())
        await db_session.commit()

        svc = DeviceService()
        first = await svc.register_device(
            db=db_session,
            device_id="dev-001",
            device_name="Desktop",
            device_type="desktop",
            platform="linux",
            user_id="user-001",
        )
        second = await svc.register_device(
            db=db_session,
            device_id="dev-001",
            device_name="Desktop",
            device_type="desktop",
            platform="linux",
            user_id="user-001",
        )

        assert second["message"] == "Device already registered"
        assert second["approval_status"] == first["approval_status"]
