"""
Device Approval Service - One-time device verification for secure multi-device sync.

Security model:
- First device registered by a user is automatically approved (bootstrap).
- Every subsequent device starts in "pending" status with a 6-character approval code.
- An already-approved device must submit the approval code to approve the new device.
- Pending devices cannot perform any sync operations until approved.
- Rejected devices are deactivated and cannot re-register without admin action.

This ensures that even if credentials are compromised, an attacker cannot sync
data without physical access to an already-trusted device.
"""

import secrets
import string
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_maker
from app.models.device import Device, ApprovalStatus


def _generate_approval_code() -> str:
    """Generate a 6-character alphanumeric approval code (uppercase for readability)."""
    alphabet = string.ascii_uppercase + string.digits
    # Exclude ambiguous characters (0/O, 1/I/L)
    safe_alphabet = alphabet.replace("0", "").replace("O", "").replace("1", "").replace("I", "").replace("L", "")
    return "".join(secrets.choice(safe_alphabet) for _ in range(6))


class DeviceApprovalService:
    """
    Manages the one-time device approval workflow.

    Usage flow:
    1. User logs in on a new device → register_device_with_approval() is called
    2. If first device for user → auto-approved, returns approval_status="approved"
    3. If not first device → returns approval_status="pending" + approval_code
    4. User reads the code on the new device's screen
    5. On an approved device, user enters the code → approve_device() is called
    6. New device is now approved and can sync
    """

    async def is_first_device_for_user(self, user_id: str) -> bool:
        """Check if this is the first device being registered for a user."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(func.count(Device.id)).where(
                    Device.user_id == user_id,
                    Device.is_active == True,
                    Device.approval_status == ApprovalStatus.APPROVED,
                )
            )
            count = result.scalar()
            return count == 0

    async def register_device_with_approval(
        self,
        device_id: str,
        device_name: str,
        device_type: str,
        platform: str,
        user_id: str,
        app_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Register a device with the approval system.

        Returns dict with:
        - device: device info
        - approval_status: "approved" or "pending"
        - approval_code: 6-char code (only if pending)
        - message: human-readable status message
        """
        first_device = await self.is_first_device_for_user(user_id)

        async with async_session_maker() as session:
            # Check if device already exists
            result = await session.execute(
                select(Device).where(Device.id == device_id)
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Device exists - check its current status
                if existing.approval_status == ApprovalStatus.APPROVED:
                    # Already approved, update info and return
                    existing.device_name = device_name
                    existing.device_type = device_type
                    existing.platform = platform
                    existing.is_active = True
                    if user_id:
                        existing.user_id = user_id
                    if app_version:
                        existing.app_version = app_version
                    await session.commit()

                    return {
                        "device": existing.to_dict(),
                        "approval_status": ApprovalStatus.APPROVED,
                        "approval_code": None,
                        "message": "Device already approved",
                    }

                elif existing.approval_status == ApprovalStatus.REJECTED:
                    # Rejected device trying to re-register
                    return {
                        "device": existing.to_dict(),
                        "approval_status": ApprovalStatus.REJECTED,
                        "approval_code": None,
                        "message": "Device has been rejected. Contact the account owner to re-enable.",
                    }

                elif existing.approval_status == ApprovalStatus.PENDING:
                    # Already pending - refresh the code and return it
                    new_code = _generate_approval_code()
                    existing.approval_code = new_code
                    existing.device_name = device_name
                    if app_version:
                        existing.app_version = app_version
                    await session.commit()

                    return {
                        "device": existing.to_dict(),
                        "approval_status": ApprovalStatus.PENDING,
                        "approval_code": new_code,
                        "message": "Device is pending approval. Enter the code on an approved device.",
                    }

            # New device registration
            if first_device:
                # Auto-approve first device (bootstrap)
                device = Device(
                    id=device_id,
                    device_name=device_name,
                    device_type=device_type,
                    platform=platform,
                    user_id=user_id,
                    app_version=app_version,
                    approval_status=ApprovalStatus.APPROVED,
                    approval_code=None,
                    approved_at=datetime.now(timezone.utc),
                )
                session.add(device)
                await session.commit()

                return {
                    "device": device.to_dict(),
                    "approval_status": ApprovalStatus.APPROVED,
                    "approval_code": None,
                    "message": "First device registered and auto-approved.",
                }
            else:
                # Generate approval code for subsequent devices
                approval_code = _generate_approval_code()
                device = Device(
                    id=device_id,
                    device_name=device_name,
                    device_type=device_type,
                    platform=platform,
                    user_id=user_id,
                    app_version=app_version,
                    approval_status=ApprovalStatus.PENDING,
                    approval_code=approval_code,
                )
                session.add(device)
                await session.commit()

                return {
                    "device": device.to_dict(),
                    "approval_status": ApprovalStatus.PENDING,
                    "approval_code": approval_code,
                    "message": "Device registered. Enter the approval code on an already-approved device to activate sync.",
                }

    async def approve_device(
        self,
        target_device_id: str,
        approval_code: str,
        approver_device_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """
        Approve a pending device using its approval code.

        The approver must be an already-approved device owned by the same user.

        Returns dict with status and message.
        """
        async with async_session_maker() as session:
            # Verify the approver device is approved and belongs to the user
            approver_result = await session.execute(
                select(Device).where(
                    Device.id == approver_device_id,
                    Device.user_id == user_id,
                    Device.is_active == True,
                )
            )
            approver = approver_result.scalar_one_or_none()

            if not approver:
                return {
                    "success": False,
                    "message": "Approver device not found or not owned by this user.",
                }

            if approver.approval_status != ApprovalStatus.APPROVED:
                return {
                    "success": False,
                    "message": "Approver device is not yet approved. Only approved devices can approve new ones.",
                }

            # Find the target device
            target_result = await session.execute(
                select(Device).where(
                    Device.id == target_device_id,
                    Device.user_id == user_id,
                    Device.is_active == True,
                )
            )
            target = target_result.scalar_one_or_none()

            if not target:
                return {
                    "success": False,
                    "message": "Target device not found or not owned by this user.",
                }

            if target.approval_status == ApprovalStatus.APPROVED:
                return {
                    "success": True,
                    "message": "Device is already approved.",
                }

            if target.approval_status == ApprovalStatus.REJECTED:
                return {
                    "success": False,
                    "message": "Device has been rejected and cannot be approved. Re-register the device first.",
                }

            # Verify the approval code
            if not target.approval_code or target.approval_code != approval_code.upper().strip():
                return {
                    "success": False,
                    "message": "Invalid approval code.",
                }

            # Approve the device
            target.approval_status = ApprovalStatus.APPROVED
            target.approval_code = None  # Clear the code after use
            target.approved_by_device_id = approver_device_id
            target.approved_at = datetime.now(timezone.utc)
            await session.commit()

            return {
                "success": True,
                "message": f"Device '{target.device_name}' has been approved.",
                "device": target.to_dict(),
            }

    async def reject_device(
        self,
        target_device_id: str,
        rejector_device_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """
        Reject a pending device. It will be deactivated.

        Only an approved device owned by the same user can reject.
        """
        async with async_session_maker() as session:
            # Verify the rejector device
            rejector_result = await session.execute(
                select(Device).where(
                    Device.id == rejector_device_id,
                    Device.user_id == user_id,
                    Device.is_active == True,
                    Device.approval_status == ApprovalStatus.APPROVED,
                )
            )
            rejector = rejector_result.scalar_one_or_none()

            if not rejector:
                return {
                    "success": False,
                    "message": "Rejector device not found or not authorized.",
                }

            # Find and reject the target device
            target_result = await session.execute(
                select(Device).where(
                    Device.id == target_device_id,
                    Device.user_id == user_id,
                )
            )
            target = target_result.scalar_one_or_none()

            if not target:
                return {
                    "success": False,
                    "message": "Target device not found.",
                }

            target.approval_status = ApprovalStatus.REJECTED
            target.approval_code = None
            target.is_active = False
            await session.commit()

            return {
                "success": True,
                "message": f"Device '{target.device_name}' has been rejected and deactivated.",
            }

    async def get_pending_devices(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all pending devices for a user (to show on approved devices)."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(Device).where(
                    Device.user_id == user_id,
                    Device.is_active == True,
                    Device.approval_status == ApprovalStatus.PENDING,
                )
            )
            devices = result.scalars().all()

            return [
                {
                    "device_id": d.id,
                    "device_name": d.device_name,
                    "device_type": d.device_type,
                    "platform": d.platform,
                    "registered_at": d.created_at.isoformat() if d.created_at else None,
                }
                for d in devices
            ]

    async def get_device_approval_status(
        self, device_id: str, user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get the approval status of a specific device."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(Device).where(
                    Device.id == device_id,
                    Device.user_id == user_id,
                )
            )
            device = result.scalar_one_or_none()

            if not device:
                return None

            return {
                "device_id": device.id,
                "device_name": device.device_name,
                "approval_status": device.approval_status,
                "approved_at": device.approved_at.isoformat() if device.approved_at else None,
                "approved_by_device_id": device.approved_by_device_id,
            }

    async def is_device_approved(self, device_id: str) -> bool:
        """Check if a device is approved for sync operations."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(Device.approval_status).where(
                    Device.id == device_id,
                    Device.is_active == True,
                )
            )
            status = result.scalar_one_or_none()
            return status == ApprovalStatus.APPROVED


# Singleton
_device_approval_service: Optional[DeviceApprovalService] = None


def get_device_approval_service() -> DeviceApprovalService:
    """Get the device approval service singleton."""
    global _device_approval_service
    if _device_approval_service is None:
        _device_approval_service = DeviceApprovalService()
    return _device_approval_service
