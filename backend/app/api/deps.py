"""
API Dependencies - Dependency injection for API endpoints.
"""

from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.block_service import BlockService
from app.models.user import User

# Security scheme
security = HTTPBearer(auto_error=False)


from app.services.search_service import SearchService, get_search_service
from app.services.voice_service import VoiceService, get_voice_service
from app.services.browser_service import BrowserService, get_browser_service
from app.services.trigger_service import TriggerService, get_trigger_service
from app.services.ai_service import AIService, get_ai_service
from app.services.vector_service import VectorService, get_vector_service
from app.services.action_service import ActionService


async def get_block_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    trigger_service: Annotated[TriggerService, Depends(get_trigger_service)]
) -> BlockService:
    """Provide BlockService instance with database session."""
    return BlockService(db, trigger_service)


# Type alias for dependency injection
BlockServiceDep = Annotated[BlockService, Depends(get_block_service)]
SearchServiceDep = Annotated[SearchService, Depends(get_search_service)]
VoiceServiceDep = Annotated[VoiceService, Depends(get_voice_service)]
BrowserServiceDep = Annotated[BrowserService, Depends(get_browser_service)]
TriggerServiceDep = Annotated[TriggerService, Depends(get_trigger_service)]

# AI & Action Service providers
def get_action_service(
    blocks: BlockService = Depends(get_block_service),
    search: SearchService = Depends(get_search_service),
    browser: BrowserService = Depends(get_browser_service)
) -> ActionService:
    return ActionService(blocks, search, browser)

ActionServiceDep = Annotated[ActionService, Depends(get_action_service)]

from app.services.planning_service import PlanningService

_planning_service = None

def get_planning_service(
    ai: AIService = Depends(get_ai_service),
    actions: ActionService = Depends(get_action_service)
) -> PlanningService:
    global _planning_service
    if _planning_service is None:
        _planning_service = PlanningService(ai, actions)
    return _planning_service


from app.services.realtime_voice_service import RealtimeVoiceService, get_realtime_voice_service

def get_realtime_voice_service_dep(
    voice: VoiceService = Depends(get_voice_service)
) -> RealtimeVoiceService:
    return get_realtime_voice_service(voice)

RealtimeVoiceServiceDep = Annotated[RealtimeVoiceService, Depends(get_realtime_voice_service_dep)]

from app.services.stt_service import STTService, get_stt_service
STTServiceDep = Annotated[STTService, Depends(get_stt_service)]


# ============================================================================
# Authentication Dependencies
# ============================================================================

async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Get the current authenticated user from JWT token.
    
    Raises 401 if not authenticated.
    """
    from app.services.auth_service import AuthService
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    payload = AuthService.decode_token(token)
    
    if not payload or payload.type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    service = AuthService(db)
    user = await service.get_user_by_id(payload.sub)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )
    
    return user


async def get_current_user_optional(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Optional[User]:
    """
    Get the current user if authenticated, otherwise return None.
    
    Use this for endpoints that work with or without authentication.
    """
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None


# Type aliases for auth dependencies
CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[Optional[User], Depends(get_current_user_optional)]
