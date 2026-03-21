"""Device registration and management service (DB-backed)."""
import secrets
import string
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device, ApprovalStatus

logger = logging.getLogger(__name__)

# Characters for approval code (no ambiguous chars)
_CODE_CHARS = "".join(
    c for c in string.ascii_uppercase + string.digits
    if c not in "0OI1L"
)


def _generate_approval_code() -> str:
    return "".join(secrets.choice(_CODE_CHARS) for _ in range(6))


class DeviceService:
    async def register_device(
        self,
        db: AsyncSession,
        device_id: str,
        device_name: str,
        device_type: str,
        platform: str,
        user_id: str,
        app_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register a device. First device auto-approved; subsequent need approval."""
        # Check if device already exists
        existing = await db.get(Device, device_id)
        if existing:
            return {
                "device": existing,
                "approval_status": existing.approval_status,
                "message": "Device already registered",
            }

        # Check if this is the first device for the user
        count = await db.scalar(
            select(func.count(Device.id)).where(
                Device.user_id == user_id,
                Device.is_active == True,
                Device.approval_status == ApprovalStatus.APPROVED,
            )
        )
        is_first = count == 0

        device = Device(
            id=device_id,
            device_name=device_name,
            device_type=device_type,
            platform=platform,
            user_id=user_id,
            app_version=app_version,
            approval_status=ApprovalStatus.APPROVED if is_first else ApprovalStatus.PENDING,
            approval_code=None if is_first else _generate_approval_code(),
            approved_at=datetime.now(timezone.utc) if is_first else None,
        )
        db.add(device)
        await db.commit()

        result: Dict[str, Any] = {
            "device": device,
            "approval_status": device.approval_status,
        }
        if device.approval_code:
            result["approval_code"] = device.approval_code
        if is_first:
            result["message"] = "First device — auto-approved"
        else:
            result["message"] = "Pending approval. Share the code with an approved device."

        return result

    async def approve_device(
        self, db: AsyncSession, device_id: str, code: str, approver_device_id: str
    ) -> Dict[str, Any]:
        """Approve a pending device using its 6-digit code."""
        device = await db.get(Device, device_id)
        if not device:
            raise ValueError("Device not found")
        if device.approval_status != ApprovalStatus.PENDING:
            raise ValueError(f"Device is already {device.approval_status}")
        if device.approval_code != code.upper():
            raise ValueError("Invalid approval code")

        device.approval_status = ApprovalStatus.APPROVED
        device.approved_at = datetime.now(timezone.utc)
        device.approved_by_device_id = approver_device_id
        device.approval_code = None
        await db.commit()

        return {"device": device, "approval_status": ApprovalStatus.APPROVED}

    async def get_device(self, db: AsyncSession, device_id: str) -> Optional[Device]:
        return await db.get(Device, device_id)

    async def list_devices(self, db: AsyncSession, user_id: str) -> List[Device]:
        result = await db.execute(
            select(Device).where(Device.user_id == user_id, Device.is_active == True)
        )
        return list(result.scalars().all())


_service: Optional[DeviceService] = None


def get_device_service() -> DeviceService:
    global _service
    if _service is None:
        _service = DeviceService()
    return _service
