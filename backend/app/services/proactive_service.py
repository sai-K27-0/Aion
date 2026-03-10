"""
Proactive Service - Time-based triggers and contextual suggestions.

Provides:
- Scheduled reminders and notifications
- Context-aware proactive suggestions
- Daily briefings
- Pattern detection
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Callable, Awaitable
from dataclasses import dataclass
from enum import Enum

from app.services.ai_service import get_ai_service
from app.services.prompt_service import get_prompt_service

logger = logging.getLogger(__name__)


class TriggerType(str, Enum):
    """Types of proactive triggers."""
    TIME_BASED = "time_based"  # Fire at specific times
    INTERVAL = "interval"  # Fire at regular intervals
    CONTEXT = "context"  # Fire based on context changes
    PATTERN = "pattern"  # Fire based on detected patterns


@dataclass
class ProactiveTrigger:
    """A trigger for proactive suggestions."""
    id: str
    type: TriggerType
    name: str
    description: str
    enabled: bool = True
    
    # Time-based config
    time: Optional[str] = None  # HH:MM format
    days: Optional[List[int]] = None  # 0=Monday, 6=Sunday
    interval_minutes: Optional[int] = None
    
    # Context config
    context_condition: Optional[str] = None  # e.g., "active_window contains 'code'"
    
    # Action
    action: Optional[Callable[..., Awaitable[str]]] = None
    prompt_template: Optional[str] = None
    
    # State
    last_fired: Optional[datetime] = None
    fire_count: int = 0


@dataclass
class Suggestion:
    """A proactive suggestion to show the user."""
    id: str
    type: str
    title: str
    content: str
    priority: int  # 1=low, 5=high
    context: Dict[str, Any]
    timestamp: datetime
    actionable: bool = False
    action_type: Optional[str] = None
    action_params: Optional[Dict] = None


class ProactiveService:
    """Service for generating proactive suggestions and managing triggers."""
    
    DEFAULT_TRIGGERS = [
        ProactiveTrigger(
            id="morning_briefing",
            type=TriggerType.TIME_BASED,
            name="Morning Briefing",
            description="Daily summary of tasks and events",
            time="08:00",
            days=[0, 1, 2, 3, 4],  # Weekdays
            prompt_template="morning_briefing",
        ),
        ProactiveTrigger(
            id="meeting_reminder",
            type=TriggerType.INTERVAL,
            name="Meeting Check",
            description="Check for upcoming meetings",
            interval_minutes=15,
            prompt_template="meeting_reminder",
        ),
        ProactiveTrigger(
            id="focus_suggestion",
            type=TriggerType.CONTEXT,
            name="Focus Mode Suggestion",
            description="Suggest focus mode when starting work",
            context_condition="time_of_day == 'morning' and is_work_day",
            prompt_template="focus_suggestion",
        ),
    ]
    
    def __init__(self):
        self.ai_service = get_ai_service()
        self.prompt_service = get_prompt_service()
        self.triggers: Dict[str, ProactiveTrigger] = {}
        self.suggestions_queue: List[Suggestion] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Register default triggers
        for trigger in self.DEFAULT_TRIGGERS:
            self.triggers[trigger.id] = trigger
    
    def start(self):
        """Start the proactive service background task."""
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._run_loop())
    
    def stop(self):
        """Stop the proactive service."""
        self._running = False
        if self._task:
            self._task.cancel()
    
    async def _run_loop(self):
        """Background loop that checks triggers."""
        while self._running:
            try:
                await self._check_triggers()
                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Proactive service error: %s", e)
                await asyncio.sleep(60)
    
    async def _check_triggers(self):
        """Check all triggers and fire if conditions are met."""
        now = datetime.now(timezone.utc)
        
        for trigger in self.triggers.values():
            if not trigger.enabled:
                continue
            
            should_fire = False
            
            if trigger.type == TriggerType.TIME_BASED:
                should_fire = self._check_time_trigger(trigger, now)
            elif trigger.type == TriggerType.INTERVAL:
                should_fire = self._check_interval_trigger(trigger, now)
            elif trigger.type == TriggerType.CONTEXT:
                should_fire = await self._check_context_trigger(trigger)
            
            if should_fire:
                await self._fire_trigger(trigger, now)
    
    def _check_time_trigger(self, trigger: ProactiveTrigger, now: datetime) -> bool:
        """Check if a time-based trigger should fire."""
        if not trigger.time:
            return False
        
        # Check day of week
        if trigger.days and now.weekday() not in trigger.days:
            return False
        
        # Parse trigger time
        hour, minute = map(int, trigger.time.split(":"))
        trigger_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # Check if within the minute window
        if abs((now - trigger_time).total_seconds()) > 60:
            return False
        
        # Check if already fired today
        if trigger.last_fired:
            if trigger.last_fired.date() == now.date():
                return False
        
        return True
    
    def _check_interval_trigger(self, trigger: ProactiveTrigger, now: datetime) -> bool:
        """Check if an interval trigger should fire."""
        if not trigger.interval_minutes:
            return False
        
        if trigger.last_fired:
            elapsed = (now - trigger.last_fired).total_seconds() / 60
            return elapsed >= trigger.interval_minutes
        
        return True  # First fire
    
    async def _check_context_trigger(self, trigger: ProactiveTrigger) -> bool:
        """Check if a context trigger should fire."""
        # This would integrate with system state detection
        # For now, return False
        return False
    
    async def _fire_trigger(self, trigger: ProactiveTrigger, now: datetime):
        """Fire a trigger and generate suggestion."""
        trigger.last_fired = now
        trigger.fire_count += 1
        
        # Generate suggestion
        suggestion = await self._generate_suggestion_for_trigger(trigger)
        if suggestion:
            self.suggestions_queue.append(suggestion)
            # Keep queue bounded
            if len(self.suggestions_queue) > 50:
                self.suggestions_queue = self.suggestions_queue[-50:]
    
    async def _generate_suggestion_for_trigger(
        self,
        trigger: ProactiveTrigger,
    ) -> Optional[Suggestion]:
        """Generate a suggestion based on trigger type."""
        now = datetime.now(timezone.utc)
        
        if trigger.id == "morning_briefing":
            return await self._generate_morning_briefing()
        elif trigger.id == "meeting_reminder":
            return await self._generate_meeting_reminder()
        elif trigger.id == "focus_suggestion":
            return await self._generate_focus_suggestion()
        
        return None
    
    async def _generate_morning_briefing(self) -> Suggestion:
        """Generate a morning briefing suggestion."""
        # In real implementation, this would gather tasks, events, etc.
        content = await self.ai_service.chat(
            message="Generate a brief, friendly morning greeting and ask what I'd like to focus on today.",
            system_prompt="Be warm and concise. 2-3 sentences max.",
            temperature=0.7,
        )
        
        return Suggestion(
            id=f"briefing_{datetime.now().timestamp()}",
            type="briefing",
            title="Good Morning!",
            content=content,
            priority=3,
            context={"trigger": "morning_briefing"},
            timestamp=datetime.now(timezone.utc),
        )
    
    async def _generate_meeting_reminder(self) -> Optional[Suggestion]:
        """Generate a meeting reminder if there's an upcoming meeting."""
        # In real implementation, this would check calendar
        return None
    
    async def _generate_focus_suggestion(self) -> Suggestion:
        """Generate a focus mode suggestion."""
        return Suggestion(
            id=f"focus_{datetime.now().timestamp()}",
            type="focus",
            title="Ready to Focus?",
            content="It looks like a good time to start focused work. Would you like to enable focus mode?",
            priority=2,
            context={"trigger": "focus_suggestion"},
            timestamp=datetime.now(timezone.utc),
            actionable=True,
            action_type="enable_focus_mode",
            action_params={},
        )
    
    # ========================================================================
    # Public API
    # ========================================================================
    
    async def get_contextual_suggestion(
        self,
        context: Dict[str, Any],
    ) -> Optional[Suggestion]:
        """
        Generate a suggestion based on current context.
        
        Args:
            context: Current context including:
                - active_window: Current active window title
                - time_of_day: morning, afternoon, evening, night
                - recent_activity: Recent user actions
                - location: Optional location
        """
        now = datetime.now(timezone.utc)
        
        prompt = self.prompt_service.render(
            "proactive_suggestion",
            recent_activity=context.get("recent_activity", "Unknown"),
            upcoming_events=context.get("upcoming_events", "None"),
            goals=context.get("goals", "None"),
        )
        
        response = await self.ai_service.chat(
            message=prompt,
            temperature=0.7,
        )
        
        if response.strip().lower() == "none":
            return None
        
        return Suggestion(
            id=f"contextual_{now.timestamp()}",
            type="contextual",
            title="Suggestion",
            content=response.strip(),
            priority=2,
            context=context,
            timestamp=now,
        )
    
    def get_pending_suggestions(self) -> List[Suggestion]:
        """Get all pending suggestions."""
        return self.suggestions_queue.copy()
    
    def dismiss_suggestion(self, suggestion_id: str):
        """Dismiss a suggestion."""
        self.suggestions_queue = [
            s for s in self.suggestions_queue if s.id != suggestion_id
        ]
    
    def add_trigger(self, trigger: ProactiveTrigger):
        """Add a custom trigger."""
        self.triggers[trigger.id] = trigger
    
    def remove_trigger(self, trigger_id: str):
        """Remove a trigger."""
        self.triggers.pop(trigger_id, None)
    
    def enable_trigger(self, trigger_id: str, enabled: bool = True):
        """Enable or disable a trigger."""
        if trigger_id in self.triggers:
            self.triggers[trigger_id].enabled = enabled


# Singleton
_proactive_service: Optional[ProactiveService] = None


def get_proactive_service() -> ProactiveService:
    """Get the proactive service singleton."""
    global _proactive_service
    if _proactive_service is None:
        _proactive_service = ProactiveService()
    return _proactive_service
