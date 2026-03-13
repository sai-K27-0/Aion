"""
Sync Service - Multi-device offline-first synchronization.

This service handles:
- Delta sync (only send changed records)
- Conflict resolution (last-write-wins with merge capability)
- Batch operations for efficiency
- Device tracking
- Sync state management
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple, Type
from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4

logger = logging.getLogger(__name__)

from sqlalchemy import select, update, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import async_session_maker
from app.models.block import Block, BlockField, BlockEntry, BlockContent
from app.models.trigger import Trigger
from app.services.field_encryption import (
    decrypt_sensitive_fields,
    encrypt_sensitive_fields,
)


class ConflictStrategy(str, Enum):
    """Strategy for resolving sync conflicts."""
    LAST_WRITE_WINS = "last_write_wins"
    CLIENT_WINS = "client_wins"
    SERVER_WINS = "server_wins"
    MERGE = "merge"


class SyncEntityType(str, Enum):
    """Types of entities that can be synced."""
    BLOCK = "block"
    BLOCK_FIELD = "block_field"
    BLOCK_ENTRY = "block_entry"
    BLOCK_CONTENT = "block_content"
    TRIGGER = "trigger"


@dataclass
class SyncChange:
    """Represents a single change to be synced."""
    entity_type: SyncEntityType
    entity_id: str
    sync_id: str
    operation: str  # "create", "update", "delete"
    data: Dict[str, Any]
    local_updated_at: datetime
    sync_version: int
    device_id: str


@dataclass
class SyncConflict:
    """Represents a sync conflict between client and server."""
    entity_type: SyncEntityType
    entity_id: str
    sync_id: str
    client_data: Dict[str, Any]
    server_data: Dict[str, Any]
    client_version: int
    server_version: int
    resolved: bool = False
    resolution: Optional[Dict[str, Any]] = None


@dataclass
class SyncResult:
    """Result of a sync operation."""
    success: bool
    changes_pushed: int = 0
    changes_pulled: int = 0
    conflicts: List[SyncConflict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    last_sync_time: Optional[datetime] = None


@dataclass
class DeviceInfo:
    """Information about a registered device."""
    device_id: str
    device_name: str
    device_type: str  # "desktop", "tablet", "phone"
    platform: str  # "windows", "macos", "android", "ios"
    last_sync: Optional[datetime] = None
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: Optional[str] = None


# Entity type to model class mapping
ENTITY_MODEL_MAP: Dict[SyncEntityType, Type] = {
    SyncEntityType.BLOCK: Block,
    SyncEntityType.BLOCK_FIELD: BlockField,
    SyncEntityType.BLOCK_ENTRY: BlockEntry,
    SyncEntityType.BLOCK_CONTENT: BlockContent,
    SyncEntityType.TRIGGER: Trigger,
}

# Conflict resolution strategy per entity type
ENTITY_CONFLICT_STRATEGY: Dict[SyncEntityType, ConflictStrategy] = {
    SyncEntityType.BLOCK: ConflictStrategy.LAST_WRITE_WINS,
    SyncEntityType.BLOCK_FIELD: ConflictStrategy.LAST_WRITE_WINS,
    SyncEntityType.BLOCK_ENTRY: ConflictStrategy.MERGE,
    SyncEntityType.BLOCK_CONTENT: ConflictStrategy.LAST_WRITE_WINS,
    SyncEntityType.TRIGGER: ConflictStrategy.LAST_WRITE_WINS,
}


class SyncService:
    """
    Manages synchronization between devices.
    
    Key concepts:
    - Each record has a sync_id (stable across devices) and sync_version (increments on change)
    - Changes are tracked by comparing sync_version and local_updated_at
    - Conflicts occur when both client and server have different versions of the same record
    """
    
    def __init__(self):
        # In-memory cache for fast lookups (populated from DB)
        self._device_cache: Dict[str, DeviceInfo] = {}
        self._cache_initialized = False
    
    @property
    def registered_devices(self) -> Dict[str, DeviceInfo]:
        """Get registered devices (from cache)."""
        return self._device_cache
    
    # =========================================================================
    # Device Management (Database-Backed)
    # =========================================================================
    
    async def _ensure_cache_initialized(self):
        """Load devices from database into cache if not already done."""
        if self._cache_initialized:
            return
        
        from app.models.device import Device
        
        async with async_session_maker() as session:
            result = await session.execute(select(Device).where(Device.is_active == True))
            devices = result.scalars().all()
            
            for device in devices:
                self._device_cache[device.id] = DeviceInfo(
                    device_id=device.id,
                    device_name=device.device_name,
                    device_type=device.device_type,
                    platform=device.platform,
                    last_sync=device.last_sync,
                    registered_at=device.created_at,
                )
        
        self._cache_initialized = True
    
    def register_device(
        self,
        device_id: str,
        device_name: str,
        device_type: str,
        platform: str,
        user_id: Optional[str] = None,
    ) -> DeviceInfo:
        """
        Register a new device for syncing (sync version - updates cache).
        Use register_device_async for database persistence.
        """
        device = DeviceInfo(
            device_id=device_id,
            device_name=device_name,
            device_type=device_type,
            platform=platform,
        )
        self._device_cache[device_id] = device
        
        # Schedule async database write (fire and forget)
        asyncio.create_task(self._persist_device(device, user_id))
        
        return device
    
    async def _persist_device(self, device_info: DeviceInfo, user_id: Optional[str] = None):
        """Persist device to database."""
        from app.models.device import Device
        
        try:
            async with async_session_maker() as session:
                # Check if device exists
                result = await session.execute(
                    select(Device).where(Device.id == device_info.device_id)
                )
                existing = result.scalar_one_or_none()
                
                if existing:
                    # Update existing device
                    existing.device_name = device_info.device_name
                    existing.device_type = device_info.device_type
                    existing.platform = device_info.platform
                    existing.is_active = True
                    if user_id:
                        existing.user_id = user_id
                else:
                    # Create new device
                    device = Device(
                        id=device_info.device_id,
                        device_name=device_info.device_name,
                        device_type=device_info.device_type,
                        platform=device_info.platform,
                        user_id=user_id,
                    )
                    session.add(device)
                
                await session.commit()
        except Exception as e:
            logger.error("Failed to persist device: %s", e)
    
    async def register_device_async(
        self,
        device_id: str,
        device_name: str,
        device_type: str,
        platform: str,
        user_id: Optional[str] = None,
        app_version: Optional[str] = None,
    ) -> DeviceInfo:
        """Register a new device with database persistence."""
        from app.models.device import Device
        
        async with async_session_maker() as session:
            # Check if device exists
            result = await session.execute(
                select(Device).where(Device.id == device_id)
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                # Update existing device
                existing.device_name = device_name
                existing.device_type = device_type
                existing.platform = platform
                existing.is_active = True
                if user_id:
                    existing.user_id = user_id
                if app_version:
                    existing.app_version = app_version
                await session.commit()
                
                device_info = DeviceInfo(
                    device_id=existing.id,
                    device_name=existing.device_name,
                    device_type=existing.device_type,
                    platform=existing.platform,
                    last_sync=existing.last_sync,
                    registered_at=existing.created_at,
                )
            else:
                # Create new device
                device = Device(
                    id=device_id,
                    device_name=device_name,
                    device_type=device_type,
                    platform=platform,
                    user_id=user_id,
                    app_version=app_version,
                )
                session.add(device)
                await session.commit()
                
                device_info = DeviceInfo(
                    device_id=device.id,
                    device_name=device.device_name,
                    device_type=device.device_type,
                    platform=device.platform,
                    registered_at=device.created_at,
                )
            
            # Update cache
            self._device_cache[device_id] = device_info
            
            return device_info
    
    def get_device(self, device_id: str) -> Optional[DeviceInfo]:
        """Get device info by ID from cache."""
        return self._device_cache.get(device_id)
    
    async def get_device_async(self, device_id: str) -> Optional[DeviceInfo]:
        """Get device info by ID from database."""
        from app.models.device import Device
        
        # Check cache first
        if device_id in self._device_cache:
            return self._device_cache[device_id]
        
        # Query database
        async with async_session_maker() as session:
            result = await session.execute(
                select(Device).where(Device.id == device_id)
            )
            device = result.scalar_one_or_none()
            
            if device:
                device_info = DeviceInfo(
                    device_id=device.id,
                    device_name=device.device_name,
                    device_type=device.device_type,
                    platform=device.platform,
                    last_sync=device.last_sync,
                    registered_at=device.created_at,
                    user_id=device.user_id,
                )
                self._device_cache[device_id] = device_info
                return device_info

            return None
    
    def update_device_sync_time(self, device_id: str, sync_time: datetime):
        """Update the last sync time for a device (updates cache and schedules DB write)."""
        if device_id in self._device_cache:
            self._device_cache[device_id].last_sync = sync_time
        
        # Schedule async database write
        asyncio.create_task(self._update_device_sync_time_db(device_id, sync_time))
    
    async def _update_device_sync_time_db(self, device_id: str, sync_time: datetime):
        """Update device sync time in database."""
        from app.models.device import Device
        
        try:
            async with async_session_maker() as session:
                await session.execute(
                    update(Device)
                    .where(Device.id == device_id)
                    .values(last_sync=sync_time)
                )
                await session.commit()
        except Exception as e:
            logger.error("Failed to update device sync time: %s", e)
    
    async def get_all_devices(self, user_id: Optional[str] = None) -> List[DeviceInfo]:
        """Get all registered devices from database."""
        from app.models.device import Device
        
        async with async_session_maker() as session:
            query = select(Device).where(Device.is_active == True)
            if user_id:
                query = query.where(Device.user_id == user_id)
            
            result = await session.execute(query)
            devices = result.scalars().all()
            
            return [
                DeviceInfo(
                    device_id=d.id,
                    device_name=d.device_name,
                    device_type=d.device_type,
                    platform=d.platform,
                    last_sync=d.last_sync,
                    registered_at=d.created_at,
                )
                for d in devices
            ]
    
    async def deactivate_device(self, device_id: str) -> bool:
        """Deactivate a device (soft delete)."""
        from app.models.device import Device
        
        try:
            async with async_session_maker() as session:
                await session.execute(
                    update(Device)
                    .where(Device.id == device_id)
                    .values(is_active=False)
                )
                await session.commit()
            
            # Remove from cache
            if device_id in self._device_cache:
                del self._device_cache[device_id]
            
            return True
        except Exception as e:
            logger.error("Failed to deactivate device: %s", e)
            return False
    
    # =========================================================================
    # Pull Changes (Server -> Client)
    # =========================================================================
    
    async def get_changes_since(
        self,
        device_id: str,
        since: Optional[datetime] = None,
        entity_types: Optional[List[SyncEntityType]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all changes since a given timestamp.
        
        Returns a dictionary with entity types as keys and lists of changed records.
        """
        if entity_types is None:
            entity_types = list(SyncEntityType)
        
        changes: Dict[str, List[Dict[str, Any]]] = {}
        
        async with async_session_maker() as session:
            for entity_type in entity_types:
                model_class = ENTITY_MODEL_MAP[entity_type]
                
                # Build query for changed records
                query = select(model_class)
                
                if since:
                    # Get records updated after the given time
                    # Also include records that were synced by other devices
                    if hasattr(model_class, 'device_id') and hasattr(model_class, 'local_updated_at'):
                        # Model has sync fields - include records from other devices
                        query = query.where(
                            or_(
                                model_class.updated_at > since,
                                and_(
                                    model_class.device_id != device_id,
                                    model_class.local_updated_at > since,
                                ),
                            )
                        )
                    else:
                        # Model doesn't have sync fields - just use updated_at
                        query = query.where(model_class.updated_at > since)
                
                result = await session.execute(query)
                records = result.scalars().all()
                
                changes[entity_type.value] = [
                    self._serialize_record(record, entity_type)
                    for record in records
                ]
        
        return changes
    
    def _serialize_record(self, record: Any, entity_type: SyncEntityType) -> Dict[str, Any]:
        """Serialize a database record for sync (decrypting sensitive fields when encryption is enabled)."""
        # Get all columns
        data = {}
        for column in record.__table__.columns:
            value = getattr(record, column.name)
            # Handle datetime serialization
            if isinstance(value, datetime):
                value = value.isoformat()
            data[column.name] = value

        data = decrypt_sensitive_fields(entity_type.value, data)
        data["_entity_type"] = entity_type.value
        return data
    
    # =========================================================================
    # Push Changes (Client -> Server)
    # =========================================================================
    
    async def apply_changes(
        self,
        device_id: str,
        changes: List[SyncChange],
    ) -> SyncResult:
        """
        Apply changes from a client device to the server.
        
        Handles conflict detection and resolution.
        """
        result = SyncResult(success=True)
        conflicts: List[SyncConflict] = []
        
        async with async_session_maker() as session:
            for change in changes:
                try:
                    conflict = await self._process_change(session, device_id, change)
                    if conflict:
                        conflicts.append(conflict)
                    else:
                        result.changes_pushed += 1
                except Exception as e:
                    result.errors.append(f"Error processing {change.entity_type}: {str(e)}")
            
            # Commit all non-conflicting changes
            if result.changes_pushed > 0:
                await session.commit()
        
        result.conflicts = conflicts
        result.last_sync_time = datetime.now(timezone.utc)
        
        # Update device sync time
        self.update_device_sync_time(device_id, result.last_sync_time)
        
        return result
    
    async def _process_change(
        self,
        session: AsyncSession,
        device_id: str,
        change: SyncChange,
    ) -> Optional[SyncConflict]:
        """Process a single change, returning a conflict if detected."""
        model_class = ENTITY_MODEL_MAP[change.entity_type]
        
        # Verify the model has sync fields (SyncMixin)
        if not hasattr(model_class, 'sync_id'):
            raise ValueError(f"Model {model_class.__name__} does not have SyncMixin applied")
        
        # Find existing record by sync_id
        query = select(model_class).where(model_class.sync_id == change.sync_id)
        result = await session.execute(query)
        existing = result.scalar_one_or_none()
        
        if change.operation == "create":
            if existing:
                # Record already exists - this is an update from another device
                return await self._handle_conflict(
                    session, device_id, change, existing
                )
            else:
                # Create new record
                await self._create_record(session, device_id, change)
                return None
        
        elif change.operation == "update":
            if not existing:
                # Record doesn't exist - create it
                await self._create_record(session, device_id, change)
                return None
            
            # Check for conflict
            if existing.sync_version >= change.sync_version:
                # Server has same or newer version
                if existing.device_id != device_id:
                    # Different device - potential conflict
                    return await self._handle_conflict(
                        session, device_id, change, existing
                    )
                else:
                    # Same device sent a stale/duplicate version — server already
                    # has the same or a newer version, so skip the update.
                    return None
            
            # Apply update (client has a newer version)
            await self._update_record(session, device_id, change, existing)
            return None
        
        elif change.operation == "delete":
            if existing:
                # Soft delete - verify sync fields exist before setting
                if hasattr(existing, 'is_deleted'):
                    existing.is_deleted = True
                if hasattr(existing, 'sync_version'):
                    existing.sync_version += 1
                if hasattr(existing, 'device_id'):
                    existing.device_id = device_id
                if hasattr(existing, 'local_updated_at'):
                    existing.local_updated_at = change.local_updated_at
            return None
        
        return None
    
    async def _create_record(
        self,
        session: AsyncSession,
        device_id: str,
        change: SyncChange,
    ):
        """Create a new record from sync change."""
        model_class = ENTITY_MODEL_MAP[change.entity_type]
        
        # Filter out internal fields
        data = {k: v for k, v in change.data.items() if not k.startswith("_")}
        
        # Ensure sync fields are set
        data["sync_id"] = change.sync_id
        data["sync_version"] = change.sync_version
        data["device_id"] = device_id
        data["local_updated_at"] = change.local_updated_at
        data["is_deleted"] = False
        
        # Parse datetime fields
        for key, value in data.items():
            if isinstance(value, str) and "T" in value and ":" in value:
                try:
                    data[key] = datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    pass

        # Encrypt sensitive fields at rest when DATA_ENCRYPTION_KEY is set
        data = encrypt_sensitive_fields(change.entity_type.value, data)

        record = model_class(**data)
        session.add(record)
    
    async def _update_record(
        self,
        session: AsyncSession,
        device_id: str,
        change: SyncChange,
        existing: Any,
    ):
        """Update an existing record from sync change."""
        # Filter out internal fields and primary key
        data = {
            k: v for k, v in change.data.items()
            if not k.startswith("_") and k != "id"
        }
        
        # Update sync fields
        data["sync_version"] = change.sync_version + 1
        data["device_id"] = device_id
        data["local_updated_at"] = change.local_updated_at
        
        # Parse datetime fields
        for key, value in data.items():
            if isinstance(value, str) and "T" in value and ":" in value:
                try:
                    data[key] = datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    pass

        # Encrypt sensitive fields at rest when DATA_ENCRYPTION_KEY is set
        data = encrypt_sensitive_fields(change.entity_type.value, data)

        # Apply updates
        for key, value in data.items():
            if hasattr(existing, key):
                setattr(existing, key, value)
    
    async def _handle_conflict(
        self,
        session: AsyncSession,
        device_id: str,
        change: SyncChange,
        existing: Any,
    ) -> Optional[SyncConflict]:
        """Handle a sync conflict based on configured strategy."""
        strategy = ENTITY_CONFLICT_STRATEGY.get(
            change.entity_type,
            ConflictStrategy.LAST_WRITE_WINS,
        )
        
        server_data = self._serialize_record(existing, change.entity_type)
        
        conflict = SyncConflict(
            entity_type=change.entity_type,
            entity_id=change.entity_id,
            sync_id=change.sync_id,
            client_data=change.data,
            server_data=server_data,
            client_version=change.sync_version,
            server_version=existing.sync_version,
        )
        
        if strategy == ConflictStrategy.LAST_WRITE_WINS:
            # Compare timestamps
            client_time = change.local_updated_at
            # Use 'is not None' instead of 'or' to handle falsy datetime values correctly
            server_time = existing.local_updated_at if existing.local_updated_at is not None else existing.updated_at
            
            if client_time > server_time:
                # Client wins
                await self._update_record(session, device_id, change, existing)
                conflict.resolved = True
                conflict.resolution = change.data
            else:
                # Server wins - no change needed
                conflict.resolved = True
                conflict.resolution = server_data
            
            return None  # Resolved, no need to return conflict
        
        elif strategy == ConflictStrategy.CLIENT_WINS:
            await self._update_record(session, device_id, change, existing)
            return None
        
        elif strategy == ConflictStrategy.SERVER_WINS:
            return None  # Keep server version
        
        elif strategy == ConflictStrategy.MERGE:
            # Return conflict for manual resolution
            return conflict
        
        return conflict
    
    # =========================================================================
    # Conflict Resolution
    # =========================================================================
    
    async def resolve_conflict(
        self,
        device_id: str,
        conflict: SyncConflict,
        resolution: Dict[str, Any],
    ) -> bool:
        """Manually resolve a sync conflict."""
        model_class = ENTITY_MODEL_MAP[conflict.entity_type]
        
        async with async_session_maker() as session:
            query = select(model_class).where(model_class.sync_id == conflict.sync_id)
            result = await session.execute(query)
            existing = result.scalar_one_or_none()
            
            if not existing:
                return False
            
            # Apply resolution
            for key, value in resolution.items():
                if not key.startswith("_") and key != "id" and hasattr(existing, key):
                    setattr(existing, key, value)
            
            existing.sync_version = max(conflict.client_version, conflict.server_version) + 1
            existing.device_id = device_id
            existing.local_updated_at = datetime.now(timezone.utc)
            
            await session.commit()
        
        return True
    
    # =========================================================================
    # Sync Status
    # =========================================================================
    
    async def get_sync_status(self, device_id: str) -> Dict[str, Any]:
        """Get the current sync status for a device."""
        # Ensure cache is initialized
        await self._ensure_cache_initialized()
        
        # Get device from cache (or from DB if not in cache)
        device = self._device_cache.get(device_id)
        if not device:
            device = await self.get_device_async(device_id)
        
        # Extract last_sync from device
        last_sync = device.last_sync if device else None
        
        # Count pending changes
        pending_counts: Dict[str, int] = {}
        
        async with async_session_maker() as session:
            for entity_type in SyncEntityType:
                model_class = ENTITY_MODEL_MAP[entity_type]
                
                query = select(model_class)
                if last_sync:
                    query = query.where(model_class.updated_at > last_sync)
                
                result = await session.execute(query)
                pending_counts[entity_type.value] = len(result.scalars().all())
        
        return {
            "device_id": device_id,
            "device_info": {
                "name": device.device_name if device else None,
                "type": device.device_type if device else None,
                "platform": device.platform if device else None,
            } if device else None,
            "last_sync": last_sync.isoformat() if last_sync else None,
            "pending_changes": pending_counts,
            "total_pending": sum(pending_counts.values()),
            "is_registered": device is not None,
        }
    
    # =========================================================================
    # Batch Operations
    # =========================================================================
    
    async def full_sync(
        self,
        device_id: str,
        client_changes: List[SyncChange],
        last_sync: Optional[datetime] = None,
    ) -> Tuple[SyncResult, Dict[str, List[Dict[str, Any]]]]:
        """
        Perform a full sync operation.
        
        1. Push client changes to server
        2. Pull server changes since last sync
        
        Returns both the push result and the pulled changes.
        """
        # Push changes
        push_result = await self.apply_changes(device_id, client_changes)
        
        # Pull changes (use the new sync time to avoid re-syncing what was just pushed)
        # But use the old time to get changes from other devices
        pull_changes = await self.get_changes_since(
            device_id,
            since=last_sync,
            entity_types=None,
        )
        
        push_result.changes_pulled = sum(len(c) for c in pull_changes.values())
        
        return push_result, pull_changes


# Singleton instance
_sync_service: Optional[SyncService] = None


def get_sync_service() -> SyncService:
    """Get the sync service singleton."""
    global _sync_service
    if _sync_service is None:
        _sync_service = SyncService()
    return _sync_service
