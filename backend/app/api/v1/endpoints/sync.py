"""
Sync API Endpoints - Multi-device synchronization.

Endpoints:
- POST /sync/push - Client pushes local changes to server
- POST /sync/pull - Client pulls server changes since last sync
- GET /sync/status - Get sync status for a device
- POST /sync/resolve - Resolve sync conflicts manually
- POST /sync/register - Register a new device
- POST /sync/full - Full bidirectional sync
- WS /sync/ws/{device_id} - Real-time WebSocket sync
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Set
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, Depends
from fastapi.websockets import WebSocketState

from app.services.sync_service import (
    get_sync_service,
    SyncChange,
    SyncConflict,
    SyncEntityType,
    ConflictStrategy,
)
from app.services.auth_service import AuthService
from app.api.deps import CurrentUser


# =============================================================================
# WebSocket Connection Manager
# =============================================================================

class SyncConnectionManager:
    """Manage WebSocket connections for real-time sync."""
    
    def __init__(self):
        # device_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}
        # device_id -> user_id (for authentication)
        self.device_users: Dict[str, str] = {}
        self._lock = asyncio.Lock()
    
    async def connect(self, device_id: str, websocket: WebSocket, user_id: Optional[str] = None):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            # Close existing connection for this device if any
            if device_id in self.active_connections:
                old_ws = self.active_connections[device_id]
                try:
                    await old_ws.close(code=4000, reason="New connection from same device")
                except Exception:
                    pass
            
            self.active_connections[device_id] = websocket
            if user_id:
                self.device_users[device_id] = user_id
        
        # Notify device connected
        await self.broadcast_device_event("device_connected", device_id)
    
    async def disconnect(self, device_id: str):
        """Remove a WebSocket connection."""
        async with self._lock:
            if device_id in self.active_connections:
                del self.active_connections[device_id]
            if device_id in self.device_users:
                del self.device_users[device_id]
        
        # Notify device disconnected
        await self.broadcast_device_event("device_disconnected", device_id)
    
    async def send_to_device(self, device_id: str, message: Dict[str, Any]):
        """Send a message to a specific device."""
        if device_id in self.active_connections:
            websocket = self.active_connections[device_id]
            try:
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json(message)
            except Exception:
                await self.disconnect(device_id)
    
    async def broadcast_to_user(self, user_id: str, message: Dict[str, Any], exclude_device: Optional[str] = None):
        """Broadcast a message to all devices of a user."""
        async with self._lock:
            target_devices = [
                device_id for device_id, uid in self.device_users.items()
                if uid == user_id and device_id != exclude_device
            ]
        
        for device_id in target_devices:
            await self.send_to_device(device_id, message)
    
    async def broadcast_sync_change(self, change: Dict[str, Any], source_device_id: str, user_id: str):
        """Broadcast a sync change to all other devices of the user."""
        message = {
            "type": "sync_change",
            "source_device": source_device_id,
            "change": change,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self.broadcast_to_user(user_id, message, exclude_device=source_device_id)
    
    async def broadcast_device_event(self, event_type: str, device_id: str):
        """Broadcast a device event to all connected devices."""
        message = {
            "type": event_type,
            "device_id": device_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        # Send to all connections except the device itself
        async with self._lock:
            for did, ws in list(self.active_connections.items()):
                if did != device_id:
                    try:
                        if ws.client_state == WebSocketState.CONNECTED:
                            await ws.send_json(message)
                    except Exception:
                        pass
    
    def get_connected_devices(self) -> List[str]:
        """Get list of connected device IDs."""
        return list(self.active_connections.keys())


# Global connection manager
sync_manager = SyncConnectionManager()


router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================

class DeviceRegistration(BaseModel):
    """Request to register a new device."""
    device_id: str = Field(..., description="Unique device identifier")
    device_name: str = Field(..., description="Human-readable device name")
    device_type: str = Field(..., description="Device type: desktop, tablet, phone")
    platform: str = Field(..., description="Platform: windows, macos, android, ios")


class SyncChangeRequest(BaseModel):
    """A single change from the client."""
    entity_type: str = Field(..., description="Type of entity: block, block_field, etc.")
    entity_id: str = Field(..., description="Entity primary key ID")
    sync_id: str = Field(..., description="Sync identifier")
    operation: str = Field(..., description="Operation: create, update, delete")
    data: Dict[str, Any] = Field(..., description="Entity data")
    local_updated_at: str = Field(..., description="ISO timestamp of local update")
    sync_version: int = Field(..., description="Current sync version")


class PushRequest(BaseModel):
    """Request to push changes to server."""
    device_id: str = Field(..., description="Device ID")
    changes: List[SyncChangeRequest] = Field(..., description="List of changes")


class PullRequest(BaseModel):
    """Request to pull changes from server."""
    device_id: str = Field(..., description="Device ID")
    since: Optional[str] = Field(None, description="ISO timestamp of last sync")
    entity_types: Optional[List[str]] = Field(None, description="Filter by entity types")


class FullSyncRequest(BaseModel):
    """Request for full bidirectional sync."""
    device_id: str
    changes: List[SyncChangeRequest] = Field(default_factory=list)
    last_sync: Optional[str] = None


class ConflictResolution(BaseModel):
    """Request to resolve a conflict."""
    device_id: str
    sync_id: str
    entity_type: str
    resolution: Dict[str, Any]


class SyncConflictResponse(BaseModel):
    """Response containing conflict details."""
    entity_type: str
    entity_id: str
    sync_id: str
    client_data: Dict[str, Any]
    server_data: Dict[str, Any]
    client_version: int
    server_version: int


class PushResponse(BaseModel):
    """Response from push operation."""
    success: bool
    changes_pushed: int
    conflicts: List[SyncConflictResponse] = []
    errors: List[str] = []
    last_sync_time: str


class PullResponse(BaseModel):
    """Response from pull operation."""
    success: bool
    changes: Dict[str, List[Dict[str, Any]]]
    total_changes: int
    last_sync_time: str


class FullSyncResponse(BaseModel):
    """Response from full sync operation."""
    success: bool
    changes_pushed: int
    changes_pulled: int
    conflicts: List[SyncConflictResponse] = []
    errors: List[str] = []
    server_changes: Dict[str, List[Dict[str, Any]]]
    last_sync_time: str


# =============================================================================
# Endpoints
# =============================================================================

@router.post(
    "/register",
    summary="Register Device",
    description="Register a new device for syncing. Requires authentication.",
)
async def register_device(request: DeviceRegistration, current_user: CurrentUser):
    """
    Register a new device for synchronization.
    
    Each device needs a unique device_id (UUID recommended).
    Device is associated with the authenticated user.
    """
    sync_service = get_sync_service()
    
    device = sync_service.register_device(
        device_id=request.device_id,
        device_name=request.device_name,
        device_type=request.device_type,
        platform=request.platform,
        user_id=str(current_user.id),
    )
    
    return {
        "success": True,
        "device": {
            "device_id": device.device_id,
            "device_name": device.device_name,
            "device_type": device.device_type,
            "platform": device.platform,
            "registered_at": device.registered_at.isoformat(),
        },
    }


@router.post(
    "/push",
    response_model=PushResponse,
    summary="Push Changes",
    description="Push local changes from client to server. Requires authentication.",
)
async def push_changes(request: PushRequest, current_user: CurrentUser):
    """
    Push local changes to the server.
    
    Handles conflict detection and resolution based on entity type strategy.
    """
    sync_service = get_sync_service()
    
    # Convert request changes to SyncChange objects
    changes = []
    for change_req in request.changes:
        try:
            entity_type = SyncEntityType(change_req.entity_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid entity_type: {change_req.entity_type}",
            )
        
        # Parse timestamp
        try:
            local_updated_at = datetime.fromisoformat(
                change_req.local_updated_at.replace("Z", "+00:00")
            )
        except ValueError:
            local_updated_at = datetime.now(timezone.utc)
        
        changes.append(SyncChange(
            entity_type=entity_type,
            entity_id=change_req.entity_id,
            sync_id=change_req.sync_id,
            operation=change_req.operation,
            data=change_req.data,
            local_updated_at=local_updated_at,
            sync_version=change_req.sync_version,
            device_id=request.device_id,
        ))
    
    # Apply changes
    result = await sync_service.apply_changes(request.device_id, changes)
    
    # Convert conflicts to response format
    conflicts = [
        SyncConflictResponse(
            entity_type=c.entity_type.value,
            entity_id=c.entity_id,
            sync_id=c.sync_id,
            client_data=c.client_data,
            server_data=c.server_data,
            client_version=c.client_version,
            server_version=c.server_version,
        )
        for c in result.conflicts
    ]
    
    return PushResponse(
        success=result.success,
        changes_pushed=result.changes_pushed,
        conflicts=conflicts,
        errors=result.errors,
        last_sync_time=result.last_sync_time.isoformat() if result.last_sync_time else "",
    )


@router.post(
    "/pull",
    response_model=PullResponse,
    summary="Pull Changes",
    description="Pull server changes since last sync. Requires authentication.",
)
async def pull_changes(request: PullRequest, current_user: CurrentUser):
    """
    Pull changes from the server since the last sync.
    
    Returns all changed records for the specified entity types.
    """
    sync_service = get_sync_service()
    
    # Parse since timestamp
    since = None
    if request.since:
        try:
            since = datetime.fromisoformat(request.since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid 'since' timestamp format",
            )
    
    # Parse entity types
    entity_types = None
    if request.entity_types:
        try:
            entity_types = [SyncEntityType(t) for t in request.entity_types]
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid entity_type: {str(e)}",
            )
    
    # Get changes
    changes = await sync_service.get_changes_since(
        device_id=request.device_id,
        since=since,
        entity_types=entity_types,
    )
    
    total_changes = sum(len(c) for c in changes.values())
    last_sync_time = datetime.now(timezone.utc)
    
    # Update device sync time
    sync_service.update_device_sync_time(request.device_id, last_sync_time)
    
    return PullResponse(
        success=True,
        changes=changes,
        total_changes=total_changes,
        last_sync_time=last_sync_time.isoformat(),
    )


@router.post(
    "/full",
    response_model=FullSyncResponse,
    summary="Full Sync",
    description="Perform full bidirectional sync. Requires authentication.",
)
async def full_sync(request: FullSyncRequest, current_user: CurrentUser):
    """
    Perform a full bidirectional sync.
    
    1. Push client changes to server
    2. Pull server changes since last sync
    
    This is the recommended sync method for most use cases.
    """
    sync_service = get_sync_service()
    
    # Convert request changes
    changes = []
    for change_req in request.changes:
        try:
            entity_type = SyncEntityType(change_req.entity_type)
        except ValueError:
            continue  # Skip invalid types
        
        try:
            local_updated_at = datetime.fromisoformat(
                change_req.local_updated_at.replace("Z", "+00:00")
            )
        except ValueError:
            local_updated_at = datetime.now(timezone.utc)
        
        changes.append(SyncChange(
            entity_type=entity_type,
            entity_id=change_req.entity_id,
            sync_id=change_req.sync_id,
            operation=change_req.operation,
            data=change_req.data,
            local_updated_at=local_updated_at,
            sync_version=change_req.sync_version,
            device_id=request.device_id,
        ))
    
    # Parse last sync time
    last_sync = None
    if request.last_sync:
        try:
            last_sync = datetime.fromisoformat(request.last_sync.replace("Z", "+00:00"))
        except ValueError:
            pass
    
    # Perform full sync
    result, server_changes = await sync_service.full_sync(
        device_id=request.device_id,
        client_changes=changes,
        last_sync=last_sync,
    )
    
    # Convert conflicts
    conflicts = [
        SyncConflictResponse(
            entity_type=c.entity_type.value,
            entity_id=c.entity_id,
            sync_id=c.sync_id,
            client_data=c.client_data,
            server_data=c.server_data,
            client_version=c.client_version,
            server_version=c.server_version,
        )
        for c in result.conflicts
    ]
    
    return FullSyncResponse(
        success=result.success,
        changes_pushed=result.changes_pushed,
        changes_pulled=result.changes_pulled,
        conflicts=conflicts,
        errors=result.errors,
        server_changes=server_changes,
        last_sync_time=result.last_sync_time.isoformat() if result.last_sync_time else "",
    )


@router.get(
    "/status",
    summary="Sync Status",
    description="Get sync status for a device. Requires authentication.",
)
async def get_sync_status(device_id: str = Query(..., description="Device ID"), current_user: CurrentUser):
    """
    Get the current sync status for a device.
    
    Returns information about pending changes and last sync time.
    """
    sync_service = get_sync_service()
    status = await sync_service.get_sync_status(device_id)
    return status


@router.post(
    "/resolve",
    summary="Resolve Conflict",
    description="Manually resolve a sync conflict. Requires authentication.",
)
async def resolve_conflict(request: ConflictResolution, current_user: CurrentUser):
    """
    Manually resolve a sync conflict.
    
    Provide the resolved data to be saved on the server.
    """
    sync_service = get_sync_service()
    
    try:
        entity_type = SyncEntityType(request.entity_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity_type: {request.entity_type}",
        )
    
    # Create a mock conflict for the resolver
    conflict = SyncConflict(
        entity_type=entity_type,
        entity_id="",
        sync_id=request.sync_id,
        client_data={},
        server_data={},
        client_version=0,
        server_version=0,
    )
    
    success = await sync_service.resolve_conflict(
        device_id=request.device_id,
        conflict=conflict,
        resolution=request.resolution,
    )
    
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Record not found or conflict resolution failed",
        )
    
    return {
        "success": True,
        "message": "Conflict resolved successfully",
    }


@router.get(
    "/devices",
    summary="List Devices",
    description="List all registered devices for the current user. Requires authentication.",
)
async def list_devices(current_user: CurrentUser):
    """List all registered devices for the authenticated user."""
    sync_service = get_sync_service()
    
    devices = await sync_service.get_all_devices(user_id=str(current_user.id))
    
    return {
        "devices": [
            {
                "device_id": d.device_id,
                "device_name": d.device_name,
                "device_type": d.device_type,
                "platform": d.platform,
                "last_sync": d.last_sync.isoformat() if d.last_sync else None,
                "registered_at": d.registered_at.isoformat(),
            }
            for d in devices
        ],
        "count": len(devices),
    }


@router.delete(
    "/devices/{device_id}",
    summary="Deactivate Device",
    description="Deactivate a registered device. Requires authentication.",
)
async def deactivate_device(device_id: str, current_user: CurrentUser):
    """Deactivate a device (soft delete)."""
    sync_service = get_sync_service()
    
    success = await sync_service.deactivate_device(device_id)
    
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Device not found or already deactivated",
        )
    
    return {"success": True, "message": "Device deactivated"}


@router.get(
    "/entity-types",
    summary="List Entity Types",
    description="List all syncable entity types. Requires authentication.",
)
async def list_entity_types(current_user: CurrentUser):
    """List all entity types that can be synced."""
    from app.services.sync_service import ENTITY_CONFLICT_STRATEGY
    
    return {
        "entity_types": [
            {
                "type": et.value,
                "conflict_strategy": ENTITY_CONFLICT_STRATEGY.get(
                    et, ConflictStrategy.LAST_WRITE_WINS
                ).value,
            }
            for et in SyncEntityType
        ]
    }


@router.get(
    "/connected",
    summary="Get Connected Devices",
    description="Get list of currently connected devices via WebSocket. Requires authentication.",
)
async def get_connected_devices(current_user: CurrentUser):
    """Get list of currently connected devices."""
    return {
        "connected_devices": sync_manager.get_connected_devices(),
        "count": len(sync_manager.get_connected_devices()),
    }


# =============================================================================
# WebSocket Sync Endpoint
# =============================================================================

async def verify_ws_token(token: str) -> Optional[str]:
    """Verify a WebSocket authentication token and return user_id."""
    if not token:
        return None
    
    # Use the same JWT decoding logic as HTTP auth (AuthService.decode_token)
    try:
        payload = AuthService.decode_token(token)
        if payload and payload.type == "access":
            return payload.sub  # user_id
        return None
    except Exception:
        return None


@router.websocket("/ws/{device_id}")
async def websocket_sync(
    websocket: WebSocket,
    device_id: str,
    device_name: str = Query(default="Unknown Device"),
    device_type: str = Query(default="unknown"),
    token: str = Query(..., description="JWT access token (required)"),
):
    """
    WebSocket endpoint for real-time sync.
    
    Connect to receive real-time updates when other devices make changes.
    Authentication is required: pass a valid JWT access token in the token query parameter.
    
    Query Parameters:
    - device_id: Unique device identifier (required, in path)
    - device_name: Human-readable device name
    - device_type: desktop, tablet, phone
    - token: JWT access token (required)
    
    Message Types (Received):
    - ping: Keep-alive ping
    - push: Push changes (same as REST /push)
    - pull: Request changes (same as REST /pull)
    
    Message Types (Sent):
    - connected: Connection established
    - pong: Response to ping
    - sync_change: A change was made on another device
    - device_connected: Another device connected
    - device_disconnected: Another device disconnected
    - error: An error occurred
    """
    # Require valid authentication token
    user_id = await verify_ws_token(token)
    if not user_id:
        await websocket.close(code=4001, reason="Unauthorized: valid JWT token required")
        return
    
    try:
        await sync_manager.connect(device_id, websocket, user_id)
    except Exception as e:
        await websocket.close(code=4001, reason=f"Connection failed: {str(e)}")
        return
    
    # Register device with sync service (associated with user)
    sync_service = get_sync_service()
    sync_service.register_device(
        device_id=device_id,
        device_name=device_name,
        device_type=device_type,
        platform="websocket",
        user_id=user_id,
    )
    
    # Send connection confirmation
    await websocket.send_json({
        "type": "connected",
        "device_id": device_id,
        "authenticated": True,
        "connected_devices": sync_manager.get_connected_devices(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    
    try:
        while True:
            # Wait for message
            try:
                data = await websocket.receive_json()
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON",
                })
                continue
            
            message_type = data.get("type", "")
            
            if message_type == "ping":
                # Respond to ping
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            
            elif message_type == "push":
                # Handle push request via WebSocket
                changes_data = data.get("changes", [])
                changes = []
                
                for change_data in changes_data:
                    try:
                        entity_type = SyncEntityType(change_data.get("entity_type", ""))
                        local_updated_at = datetime.fromisoformat(
                            change_data.get("local_updated_at", "").replace("Z", "+00:00")
                        )
                    except (ValueError, TypeError):
                        continue
                    
                    changes.append(SyncChange(
                        entity_type=entity_type,
                        entity_id=change_data.get("entity_id", ""),
                        sync_id=change_data.get("sync_id", ""),
                        operation=change_data.get("operation", "update"),
                        data=change_data.get("data", {}),
                        local_updated_at=local_updated_at,
                        sync_version=change_data.get("sync_version", 0),
                        device_id=device_id,
                    ))
                
                if changes:
                    result = await sync_service.apply_changes(device_id, changes)
                    
                    # Send result back
                    await websocket.send_json({
                        "type": "push_result",
                        "success": result.success,
                        "changes_pushed": result.changes_pushed,
                        "conflicts": [
                            {
                                "entity_type": c.entity_type.value,
                                "sync_id": c.sync_id,
                                "client_data": c.client_data,
                                "server_data": c.server_data,
                            }
                            for c in result.conflicts
                        ],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    
                    # Broadcast changes to other devices of this user
                    if user_id and result.success:
                        for change in changes:
                            await sync_manager.broadcast_sync_change(
                                change={
                                    "entity_type": change.entity_type.value,
                                    "entity_id": change.entity_id,
                                    "sync_id": change.sync_id,
                                    "operation": change.operation,
                                    "data": change.data,
                                    "sync_version": change.sync_version,
                                },
                                source_device_id=device_id,
                                user_id=user_id,
                            )
            
            elif message_type == "pull":
                # Handle pull request via WebSocket
                since_str = data.get("since")
                since = None
                if since_str:
                    try:
                        since = datetime.fromisoformat(since_str.replace("Z", "+00:00"))
                    except ValueError:
                        pass
                
                entity_types = None
                if data.get("entity_types"):
                    try:
                        entity_types = [SyncEntityType(t) for t in data["entity_types"]]
                    except ValueError:
                        pass
                
                changes = await sync_service.get_changes_since(
                    device_id=device_id,
                    since=since,
                    entity_types=entity_types,
                )
                
                await websocket.send_json({
                    "type": "pull_result",
                    "changes": changes,
                    "total_changes": sum(len(c) for c in changes.values()),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            
            elif message_type == "subscribe":
                # Subscribe to specific entity types
                await websocket.send_json({
                    "type": "subscribed",
                    "entity_types": data.get("entity_types", []),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            
            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {message_type}",
                })
    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
            })
        except Exception:
            pass
    finally:
        await sync_manager.disconnect(device_id)
