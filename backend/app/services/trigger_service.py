"""
Trigger Service - Business logic for automated actions.
"""

from typing import Any, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trigger import Trigger
import logging

logger = logging.getLogger(__name__)

class TriggerService:
    """
    Manages Aion's Trigger-Action rules.
    
    Responsibilities:
    - CRUD for Triggers
    - Event dispatching (checking triggers when events occur)
    - Action execution via ActionService
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_triggers(self, active_only: bool = True) -> List[Trigger]:
        """List all triggers."""
        query = select(Trigger)
        if active_only:
            query = query.where(Trigger.is_active == True)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_trigger(self, data: dict) -> Trigger:
        """Create a new trigger."""
        trigger = Trigger(**data)
        self.db.add(trigger)
        await self.db.commit()
        await self.db.refresh(trigger)
        return trigger

    async def check_triggers(self, event_type: str, context: dict):
        """
        Check if any active triggers match the incoming event.
        
        Args:
            event_type: 'block_created', 'field_updated', etc.
            context: Data about the event (e.g., {'block_name': 'Urgent', 'block_id': '...'})
        """
        logger.info(f"Checking triggers for event: {event_type}")
        triggers = await self.list_triggers(active_only=True)
        
        for trigger in triggers:
            if trigger.event_type != event_type:
                continue
                
            # Basic condition matching
            if self._matches_condition(trigger.condition, context):
                logger.info(f"Trigger fired: {trigger.name}")
                await self._fire_action(trigger)

    def _matches_condition(self, condition: dict, context: dict) -> bool:
        """
        Evaluate if event context matches trigger condition.
        Currently supports basic key-value matching.
        """
        if not condition:
            return True
            
        for key, value in condition.items():
            if context.get(key) != value:
                return False
        return True

    async def _fire_action(self, trigger: Trigger):
        """Execute the action associated with the trigger."""
        try:
            # Import and instantiate services directly (not via FastAPI DI)
            from app.services.action_service import ActionService
            from app.services.block_service import BlockService
            from app.services.search_service import get_search_service
            from app.services.browser_service import get_browser_service
            
            # Create BlockService with db and self (TriggerService)
            block_service = BlockService(self.db, self)
            search_service = get_search_service()
            browser_service = get_browser_service()
            
            action_service = ActionService(block_service, search_service, browser_service)
            
            await action_service.execute_action(
                action_type=trigger.action_type,
                parameters=trigger.action_params
            )
        except Exception as e:
            logger.error(f"Failed to fire trigger action '{trigger.name}': {e}")

# FastAPI dependency function
from typing import Annotated
from fastapi import Depends
from app.db.session import get_db

async def get_trigger_service(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> TriggerService:
    return TriggerService(db)
