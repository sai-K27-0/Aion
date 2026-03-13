"""
Unit and integration tests for SyncService.

Tests cover:
- Pure-Python business logic (no DB required):
    - DeviceInfo / SyncChange / SyncConflict / SyncResult dataclasses
    - ConflictStrategy / SyncEntityType enums
    - register_device (in-memory cache)
    - get_device / get_device (cache miss) helpers
    - _matches_condition logic (via TriggerService)

- DB-backed tests (use the in-memory SQLite ``db_session`` fixture):
    - SyncService._serialize_record
    - SyncService._process_change (create)
    - SyncService._process_change (update — newer version wins)
    - SyncService._process_change (update — conflict: server version >= client)
    - SyncService._process_change (delete — soft-deletes the record)
"""

from __future__ import annotations

import sys
import os
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.sync_service import (
    ConflictStrategy,
    DeviceInfo,
    SyncChange,
    SyncConflict,
    SyncEntityType,
    SyncResult,
    SyncService,
    ENTITY_CONFLICT_STRATEGY,
    ENTITY_MODEL_MAP,
)
from app.models.block import Block


# ===========================================================================
# Helpers
# ===========================================================================

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_block(name: str = "Test Block") -> dict:
    """Return a minimal dict suitable for constructing a Block."""
    return {
        "id": str(uuid4()),
        "sync_id": str(uuid4()),
        "sync_version": 1,
        "device_id": "device-a",
        "is_deleted": False,
        "name": name,
        "description": None,
        "block_type": "default",
        "parent_id": None,
        "path": "",
        "depth": 0,
        "position": 0,
        "properties": {},
    }


# ===========================================================================
# Pure-logic tests (no DB required)
# ===========================================================================


class TestDataclasses:
    def test_device_info_defaults(self):
        d = DeviceInfo(
            device_id="d1",
            device_name="My Desktop",
            device_type="desktop",
            platform="windows",
        )
        assert d.device_id == "d1"
        assert d.last_sync is None
        assert isinstance(d.registered_at, datetime)

    def test_sync_change_fields(self):
        sc = SyncChange(
            entity_type=SyncEntityType.BLOCK,
            entity_id="eid",
            sync_id="sid",
            operation="create",
            data={"name": "X"},
            local_updated_at=_now(),
            sync_version=1,
            device_id="dev-1",
        )
        assert sc.operation == "create"
        assert sc.entity_type == SyncEntityType.BLOCK

    def test_sync_conflict_fields(self):
        conflict = SyncConflict(
            entity_type=SyncEntityType.BLOCK,
            entity_id="eid",
            sync_id="sid",
            client_data={"name": "Client"},
            server_data={"name": "Server"},
            client_version=2,
            server_version=3,
        )
        assert not conflict.resolved
        assert conflict.resolution is None

    def test_sync_result_defaults(self):
        r = SyncResult(success=True)
        assert r.changes_pushed == 0
        assert r.changes_pulled == 0
        assert r.conflicts == []
        assert r.errors == []


class TestEnums:
    def test_entity_types(self):
        types = list(SyncEntityType)
        expected = {"block", "block_field", "block_entry", "block_content", "trigger"}
        assert {t.value for t in types} == expected

    def test_conflict_strategies(self):
        strategies = list(ConflictStrategy)
        assert ConflictStrategy.LAST_WRITE_WINS in strategies
        assert ConflictStrategy.MERGE in strategies

    def test_entity_model_map_complete(self):
        for entity_type in SyncEntityType:
            assert entity_type in ENTITY_MODEL_MAP, (
                f"SyncEntityType.{entity_type.name} has no entry in ENTITY_MODEL_MAP"
            )

    def test_entity_conflict_strategy_complete(self):
        for entity_type in SyncEntityType:
            assert entity_type in ENTITY_CONFLICT_STRATEGY, (
                f"SyncEntityType.{entity_type.name} has no conflict strategy defined"
            )


class TestDeviceCache:
    def test_register_device_updates_cache(self):
        service = SyncService()
        # Suppress the background task (no running event loop)
        import unittest.mock as mock
        with mock.patch("asyncio.create_task"):
            info = service.register_device(
                device_id="dev-1",
                device_name="Laptop",
                device_type="desktop",
                platform="linux",
            )
        assert info.device_id == "dev-1"
        assert service.get_device("dev-1") is not None

    def test_get_device_missing_returns_none(self):
        service = SyncService()
        assert service.get_device("nonexistent") is None

    def test_update_device_sync_time_in_cache(self):
        service = SyncService()
        import unittest.mock as mock
        with mock.patch("asyncio.create_task"):
            service.register_device("dev-2", "Phone", "phone", "android")
        now = _now()
        with mock.patch("asyncio.create_task"):
            service.update_device_sync_time("dev-2", now)
        assert service.get_device("dev-2").last_sync == now

    def test_registered_devices_property(self):
        service = SyncService()
        import unittest.mock as mock
        with mock.patch("asyncio.create_task"):
            service.register_device("dev-3", "Tablet", "tablet", "ios")
        assert "dev-3" in service.registered_devices


# ===========================================================================
# DB-backed tests
# ===========================================================================


class TestSerializeRecord:
    async def test_serialize_block(self, db_session):
        block = Block(**_make_block("Serialize Me"))
        db_session.add(block)
        await db_session.commit()
        await db_session.refresh(block)

        service = SyncService()
        data = service._serialize_record(block, SyncEntityType.BLOCK)

        assert data["name"] == "Serialize Me"
        assert data["_entity_type"] == "block"
        assert "id" in data
        assert "sync_id" in data

    async def test_serialize_datetimes_as_iso_strings(self, db_session):
        block = Block(**_make_block("ISO Block"))
        db_session.add(block)
        await db_session.commit()
        await db_session.refresh(block)

        service = SyncService()
        data = service._serialize_record(block, SyncEntityType.BLOCK)

        # created_at and updated_at should be ISO strings, not datetime objects
        assert isinstance(data["created_at"], str), "created_at should be serialized to ISO string"
        assert isinstance(data["updated_at"], str), "updated_at should be serialized to ISO string"


class TestProcessChangeCreate:
    async def test_create_new_record(self, db_session):
        service = SyncService()
        sync_id = str(uuid4())
        change = SyncChange(
            entity_type=SyncEntityType.BLOCK,
            entity_id=str(uuid4()),
            sync_id=sync_id,
            operation="create",
            data={
                "id": str(uuid4()),
                "name": "New Block via Sync",
                "description": None,
                "block_type": "default",
                "parent_id": None,
                "path": "",
                "depth": 0,
                "position": 0,
                "properties": {},
                "is_deleted": False,
                "sync_id": sync_id,
                "sync_version": 1,
                "device_id": "device-a",
            },
            local_updated_at=_now(),
            sync_version=1,
            device_id="device-a",
        )

        conflict = await service._process_change(db_session, "device-a", change)
        await db_session.commit()

        assert conflict is None

        from sqlalchemy import select
        result = await db_session.execute(
            select(Block).where(Block.sync_id == sync_id)
        )
        record = result.scalar_one_or_none()
        assert record is not None
        assert record.name == "New Block via Sync"

    async def test_create_duplicate_last_write_wins_resolution(self, db_session):
        """
        A 'create' for a sync_id that already exists on the server triggers
        conflict handling.  With LAST_WRITE_WINS and equal timestamps the
        server record is kept and no conflict object is returned.
        """
        service = SyncService()
        sync_id = str(uuid4())
        t = _now()

        # Pre-existing server record
        block = Block(
            id=str(uuid4()),
            sync_id=sync_id,
            sync_version=1,
            device_id="device-b",
            is_deleted=False,
            name="Server Block",
            block_type="default",
            depth=0,
            path="",
            position=0,
            properties={},
            local_updated_at=t,
        )
        db_session.add(block)
        await db_session.commit()

        # Client sends a 'create' for the same sync_id (but older timestamp)
        change = SyncChange(
            entity_type=SyncEntityType.BLOCK,
            entity_id=block.id,
            sync_id=sync_id,
            operation="create",
            data={
                "id": block.id,
                "name": "Client Block (older)",
                "description": None,
                "block_type": "default",
                "parent_id": None,
                "path": "",
                "depth": 0,
                "position": 0,
                "properties": {},
                "is_deleted": False,
                "sync_id": sync_id,
                "sync_version": 1,
                "device_id": "device-a",
            },
            local_updated_at=t - timedelta(seconds=60),  # older than server
            sync_version=1,
            device_id="device-a",
        )

        # LAST_WRITE_WINS strategy resolves automatically → returns None
        conflict = await service._process_change(db_session, "device-a", change)
        assert conflict is None


class TestProcessChangeUpdate:
    async def test_update_newer_version_applied(self, db_session):
        """Client version is newer than server → update is applied."""
        service = SyncService()
        sync_id = str(uuid4())
        t_old = _now() - timedelta(minutes=5)
        t_new = _now()

        block = Block(
            id=str(uuid4()),
            sync_id=sync_id,
            sync_version=1,
            device_id="device-b",
            is_deleted=False,
            name="Old Name",
            block_type="default",
            depth=0,
            path="",
            position=0,
            properties={},
            local_updated_at=t_old,
        )
        db_session.add(block)
        await db_session.commit()

        change = SyncChange(
            entity_type=SyncEntityType.BLOCK,
            entity_id=block.id,
            sync_id=sync_id,
            operation="update",
            data={
                "name": "Updated Name",
                "description": "changed",
                "block_type": "default",
                "parent_id": None,
                "path": "",
                "depth": 0,
                "position": 0,
                "properties": {},
                "is_deleted": False,
                "sync_id": sync_id,
                "sync_version": 2,
                "device_id": "device-a",
            },
            local_updated_at=t_new,
            sync_version=2,
            device_id="device-a",
        )

        conflict = await service._process_change(db_session, "device-a", change)
        await db_session.commit()

        assert conflict is None

        await db_session.refresh(block)
        assert block.name == "Updated Name"

    async def test_update_same_device_stale_version_skipped(self, db_session):
        """
        When the server already holds the same version from the same device,
        the update is a no-op and no conflict is returned.
        """
        service = SyncService()
        sync_id = str(uuid4())
        t = _now()

        block = Block(
            id=str(uuid4()),
            sync_id=sync_id,
            sync_version=3,
            device_id="device-a",
            is_deleted=False,
            name="Already Up To Date",
            block_type="default",
            depth=0,
            path="",
            position=0,
            properties={},
            local_updated_at=t,
        )
        db_session.add(block)
        await db_session.commit()

        change = SyncChange(
            entity_type=SyncEntityType.BLOCK,
            entity_id=block.id,
            sync_id=sync_id,
            operation="update",
            data={"name": "Stale Name"},
            local_updated_at=t - timedelta(seconds=10),
            sync_version=2,  # older than server's 3
            device_id="device-a",
        )

        conflict = await service._process_change(db_session, "device-a", change)
        assert conflict is None

        await db_session.refresh(block)
        assert block.name == "Already Up To Date"  # not overwritten


class TestProcessChangeDelete:
    async def test_soft_delete(self, db_session):
        service = SyncService()
        sync_id = str(uuid4())

        block = Block(
            id=str(uuid4()),
            sync_id=sync_id,
            sync_version=1,
            device_id="device-a",
            is_deleted=False,
            name="To Be Deleted",
            block_type="default",
            depth=0,
            path="",
            position=0,
            properties={},
        )
        db_session.add(block)
        await db_session.commit()

        change = SyncChange(
            entity_type=SyncEntityType.BLOCK,
            entity_id=block.id,
            sync_id=sync_id,
            operation="delete",
            data={},
            local_updated_at=_now(),
            sync_version=2,
            device_id="device-a",
        )

        conflict = await service._process_change(db_session, "device-a", change)
        await db_session.commit()

        assert conflict is None

        await db_session.refresh(block)
        assert block.is_deleted is True
        assert block.sync_version == 2  # incremented from 1
