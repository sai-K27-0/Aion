"""
Discovery API Endpoints - Server information and network discovery.

Provides endpoints for:
- Server info (for clients to verify connection)
- Network address discovery
- Service status
"""

from fastapi import APIRouter
from app.services.discovery_service import get_discovery_service

router = APIRouter()


@router.get(
    "/info",
    summary="Server Info",
    description="Get information about this Aion server.",
)
async def get_server_info():
    """
    Get server information for clients to verify connection.
    
    Returns server name, version, and available endpoints.
    """
    service = get_discovery_service()
    info = service.get_server_info()
    
    if info:
        return {
            "name": info.name,
            "host": info.host,
            "port": info.port,
            "version": info.version,
            "api_path": info.api_path,
            "endpoints": {
                "sync": "/api/v1/sync",
                "blocks": "/api/v1/blocks",
                "ai": "/api/v1/ai",
                "voice": "/api/v1/voice",
            },
            "mdns_available": True,
        }
    
    return {
        "name": "Aion Server",
        "version": "0.1.0",
        "api_path": "/api/v1",
        "endpoints": {
            "sync": "/api/v1/sync",
            "blocks": "/api/v1/blocks",
            "ai": "/api/v1/ai",
            "voice": "/api/v1/voice",
        },
        "mdns_available": False,
    }


@router.get(
    "/ping",
    summary="Ping",
    description="Simple ping endpoint to check server availability.",
)
async def ping():
    """Simple ping to verify server is running."""
    return {"status": "ok", "message": "pong"}


@router.get(
    "/status",
    summary="Server Status",
    description="Get detailed server status including all services.",
)
async def get_status():
    """Get comprehensive server status."""
    from app.services.ai_service import get_ai_service
    
    ai_service = get_ai_service()
    
    # Check AI availability and get models
    try:
        ai_available = await ai_service.is_available()
        models = await ai_service.list_models() if ai_available else []
    except Exception:
        ai_available = False
        models = []
    
    ai_status = {
        "ollama": {
            "available": ai_available,
            "models": models,
        }
    }
    
    return {
        "server": "running",
        "version": "0.1.0",
        "services": {
            "api": "online",
            "sync": "online",
            "ai": "online" if ai_available else "offline",
            "voice": "online",
        },
        "ai": ai_status,
    }
