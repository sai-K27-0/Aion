"""
API v1 Router - Aggregates all v1 endpoint routers.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import blocks, ai, sync, auth, ai_enhanced, voice, discovery, devices, ai_setup, hub

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["auth"],
)

api_router.include_router(
    blocks.router,
    prefix="/blocks",
    tags=["blocks"],
)

api_router.include_router(
    ai.router,
    prefix="/ai",
    tags=["ai"],
)

api_router.include_router(
    ai_enhanced.router,
    prefix="/ai/v2",
    tags=["ai-enhanced"],
)

api_router.include_router(
    voice.router,
    prefix="/voice",
    tags=["voice"],
)

api_router.include_router(
    sync.router,
    prefix="/sync",
    tags=["sync"],
)

api_router.include_router(
    discovery.router,
    prefix="/discovery",
    tags=["discovery"],
)

api_router.include_router(
    devices.router,
    prefix="/devices",
    tags=["devices"],
)

api_router.include_router(
    ai_setup.router,
    prefix="/ai/setup",
    tags=["ai-setup"],
)

api_router.include_router(
    hub.router,
    prefix="/hub",
    tags=["hub"],
)
