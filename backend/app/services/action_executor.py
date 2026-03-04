"""
Action Executor Service - Execute AI-generated actions in the app.

This service handles all actions that the AI can trigger:
- Block/Task management
- Timer control
- Calendar events
- Habits
- Browser opening
- Focus mode
- Study workflows
"""

import asyncio
import webbrowser
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum


class ActionType(str, Enum):
    """All available action types."""
    # Block Management
    CREATE_BLOCK = "create_block"
    UPDATE_BLOCK = "update_block"
    DELETE_BLOCK = "delete_block"
    OPEN_BLOCK = "open_block"
    
    # Task Management
    CREATE_TASK = "create_task"
    UPDATE_TASK = "update_task"
    COMPLETE_TASK = "complete_task"
    DELETE_TASK = "delete_task"
    
    # Timer/Pomodoro
    START_TIMER = "start_timer"
    PAUSE_TIMER = "pause_timer"
    STOP_TIMER = "stop_timer"
    START_POMODORO = "start_pomodoro"
    
    # Calendar
    ADD_CALENDAR_EVENT = "add_calendar_event"
    UPDATE_CALENDAR_EVENT = "update_calendar_event"
    DELETE_CALENDAR_EVENT = "delete_calendar_event"
    
    # Habits
    CREATE_HABIT = "create_habit"
    CHECK_HABIT = "check_habit"
    DELETE_HABIT = "delete_habit"
    
    # UI Control
    OPEN_PANEL = "open_panel"
    CLOSE_PANEL = "close_panel"
    CHANGE_THEME = "change_theme"
    SET_FOCUS = "set_focus"
    SHOW_NOTIFICATION = "show_notification"
    
    # External
    OPEN_BROWSER = "open_browser"
    OPEN_APP = "open_app"
    
    # Study
    CREATE_STUDY_PLAN = "create_study_plan"
    CREATE_TIMETABLE = "create_timetable"
    START_STUDY_SESSION = "start_study_session"
    GENERATE_FLASHCARDS = "generate_flashcards"
    START_QUIZ = "start_quiz"


@dataclass
class ActionResult:
    """Result of an action execution."""
    success: bool
    action_type: str
    message: str
    data: Optional[Dict[str, Any]] = None
    frontend_action: Optional[Dict[str, Any]] = None  # Action to send to frontend


@dataclass 
class ActionDefinition:
    """Definition of an action."""
    action_type: ActionType
    description: str
    parameters: Dict[str, str]  # param_name -> description
    required_params: List[str]
    examples: List[str]


# Registry of all available actions
ACTION_REGISTRY: Dict[str, ActionDefinition] = {
    # Block Management
    "create_block": ActionDefinition(
        action_type=ActionType.CREATE_BLOCK,
        description="Create a new block/project in the mind map",
        parameters={
            "name": "Name of the block",
            "type": "Type: note, task, project, idea",
            "parent_id": "Optional parent block ID for sub-blocks",
            "notes": "Optional initial notes content",
        },
        required_params=["name"],
        examples=[
            "Create a block called 'Math Study'",
            "Add a new project named 'Website Redesign'",
        ],
    ),
    "update_block": ActionDefinition(
        action_type=ActionType.UPDATE_BLOCK,
        description="Update an existing block's content",
        parameters={
            "block_id": "ID of the block to update",
            "name": "New name (optional)",
            "notes": "New notes content (optional)",
            "icon": "New icon (optional)",
        },
        required_params=["block_id"],
        examples=["Update the notes in my Math block"],
    ),
    "delete_block": ActionDefinition(
        action_type=ActionType.DELETE_BLOCK,
        description="Delete a block and its children",
        parameters={"block_id": "ID of the block to delete"},
        required_params=["block_id"],
        examples=["Delete the old project block"],
    ),
    
    # Task Management
    "create_task": ActionDefinition(
        action_type=ActionType.CREATE_TASK,
        description="Create a new task/todo item",
        parameters={
            "text": "Task description",
            "block_id": "Block to add the task to",
            "priority": "Priority: none, low, medium, high",
            "due_date": "Due date (YYYY-MM-DD format)",
            "status": "Status: not_started, in_progress, on_hold, completed",
            "tags": "Comma-separated tags",
        },
        required_params=["text"],
        examples=[
            "Add a task 'Review chapter 5' to my Math block",
            "Create a high priority task 'Submit assignment' due tomorrow",
        ],
    ),
    "complete_task": ActionDefinition(
        action_type=ActionType.COMPLETE_TASK,
        description="Mark a task as completed",
        parameters={"task_id": "ID of the task"},
        required_params=["task_id"],
        examples=["Mark 'Review chapter 5' as done"],
    ),
    
    # Timer/Pomodoro
    "start_timer": ActionDefinition(
        action_type=ActionType.START_TIMER,
        description="Start a focus timer",
        parameters={
            "minutes": "Duration in minutes (default: 25)",
            "task_id": "Optional task to associate with timer",
        },
        required_params=[],
        examples=["Start a 30 minute timer", "Begin focus timer for studying"],
    ),
    "start_pomodoro": ActionDefinition(
        action_type=ActionType.START_POMODORO,
        description="Start a Pomodoro session",
        parameters={
            "mode": "Mode: work, short_break, long_break (default: work)",
        },
        required_params=[],
        examples=["Start a pomodoro", "Begin work session"],
    ),
    "stop_timer": ActionDefinition(
        action_type=ActionType.STOP_TIMER,
        description="Stop the current timer",
        parameters={},
        required_params=[],
        examples=["Stop the timer", "End the focus session"],
    ),
    
    # Calendar
    "add_calendar_event": ActionDefinition(
        action_type=ActionType.ADD_CALENDAR_EVENT,
        description="Add an event to the calendar",
        parameters={
            "title": "Event title",
            "start": "Start date (YYYY-MM-DD)",
            "end": "End date (YYYY-MM-DD, optional)",
            "status": "Status: not_started, in_progress, completed",
        },
        required_params=["title", "start"],
        examples=["Add 'Math exam' on February 15th"],
    ),
    
    # Habits
    "create_habit": ActionDefinition(
        action_type=ActionType.CREATE_HABIT,
        description="Create a daily habit to track",
        parameters={
            "name": "Habit name",
            "icon": "Emoji icon",
            "frequency": "Frequency: daily, weekdays, weekends",
        },
        required_params=["name"],
        examples=["Create a habit 'Study 1 hour' daily"],
    ),
    "check_habit": ActionDefinition(
        action_type=ActionType.CHECK_HABIT,
        description="Mark a habit as done for today",
        parameters={"habit_id": "ID of the habit"},
        required_params=["habit_id"],
        examples=["Check off my reading habit"],
    ),
    
    # UI Control
    "open_panel": ActionDefinition(
        action_type=ActionType.OPEN_PANEL,
        description="Open a panel in the app",
        parameters={
            "panel": "Panel name: mindmap, tasks, calendar, pomodoro, stats, habits, chat, settings",
        },
        required_params=["panel"],
        examples=["Open the calendar", "Show me the mind map"],
    ),
    "change_theme": ActionDefinition(
        action_type=ActionType.CHANGE_THEME,
        description="Change the app color theme",
        parameters={
            "theme": "Theme: sky, forest, sunset, ocean, lavender, rose, mint, gold",
        },
        required_params=["theme"],
        examples=["Change theme to forest", "Make it ocean blue"],
    ),
    "set_focus": ActionDefinition(
        action_type=ActionType.SET_FOCUS,
        description="Set the current focus text",
        parameters={"text": "Focus text to display"},
        required_params=["text"],
        examples=["Set focus to 'Studying Calculus'"],
    ),
    "show_notification": ActionDefinition(
        action_type=ActionType.SHOW_NOTIFICATION,
        description="Show a notification to the user",
        parameters={
            "title": "Notification title",
            "message": "Notification message",
            "icon": "Emoji icon (optional)",
        },
        required_params=["title", "message"],
        examples=["Notify me when timer ends"],
    ),
    
    # External
    "open_browser": ActionDefinition(
        action_type=ActionType.OPEN_BROWSER,
        description="Open a URL in the web browser",
        parameters={
            "url": "URL to open",
            "instructions": "Optional guidance for the user",
        },
        required_params=["url"],
        examples=[
            "Open Khan Academy for calculus",
            "Search YouTube for calculus tutorials",
        ],
    ),
    
    # Study
    "create_study_plan": ActionDefinition(
        action_type=ActionType.CREATE_STUDY_PLAN,
        description="Generate a comprehensive study plan",
        parameters={
            "subject": "Subject to study",
            "topics": "Comma-separated list of topics",
            "exam_date": "Exam date (YYYY-MM-DD)",
            "daily_hours": "Hours available per day",
        },
        required_params=["subject"],
        examples=[
            "Create a study plan for Math exam on Feb 15",
            "Help me prepare for Physics covering thermodynamics and waves",
        ],
    ),
    "create_timetable": ActionDefinition(
        action_type=ActionType.CREATE_TIMETABLE,
        description="Create a study timetable/schedule",
        parameters={
            "activities": "List of activities with durations",
            "start_time": "Start time (HH:MM)",
            "include_breaks": "Include breaks (default: true)",
        },
        required_params=["activities"],
        examples=["Create a timetable for today's study session"],
    ),
    "start_study_session": ActionDefinition(
        action_type=ActionType.START_STUDY_SESSION,
        description="Start an automated study session with timer and guidance",
        parameters={
            "topic": "Topic to study",
            "duration": "Session duration in minutes",
            "block_id": "Block to use (optional)",
        },
        required_params=["topic"],
        examples=["Start a study session on Derivatives"],
    ),
    "generate_flashcards": ActionDefinition(
        action_type=ActionType.GENERATE_FLASHCARDS,
        description="Generate flashcards from notes or a topic",
        parameters={
            "block_id": "Block to generate from (optional)",
            "topic": "Topic to generate flashcards for",
            "count": "Number of flashcards (default: 10)",
        },
        required_params=[],
        examples=["Create flashcards from my Calculus notes"],
    ),
}


class ActionExecutor:
    """
    Executes actions triggered by the AI.
    
    Actions can be:
    - Executed directly on the backend (DB operations)
    - Sent to the frontend via WebSocket (UI operations)
    - Both (create in DB and update UI)
    """
    
    def __init__(self):
        self._pending_frontend_actions: List[Dict[str, Any]] = []
    
    def get_tools_description(self) -> str:
        """Get a description of all available tools for the AI."""
        lines = ["Available actions you can perform:\n"]
        
        for name, defn in ACTION_REGISTRY.items():
            params_str = ", ".join([
                f"{k}" + ("*" if k in defn.required_params else "")
                for k in defn.parameters.keys()
            ])
            lines.append(f"- {name}({params_str}): {defn.description}")
        
        lines.append("\n* = required parameter")
        return "\n".join(lines)
    
    def get_tools_for_llm(self) -> List[Dict[str, Any]]:
        """Get tools in a format suitable for LLM function calling."""
        tools = []
        for name, defn in ACTION_REGISTRY.items():
            tool = {
                "name": name,
                "description": defn.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        k: {"type": "string", "description": v}
                        for k, v in defn.parameters.items()
                    },
                    "required": defn.required_params,
                },
            }
            tools.append(tool)
        return tools
    
    async def execute(
        self,
        action_type: str,
        parameters: Dict[str, Any],
    ) -> ActionResult:
        """
        Execute an action.
        
        Returns ActionResult with success status and any frontend actions to dispatch.
        """
        if action_type not in ACTION_REGISTRY:
            return ActionResult(
                success=False,
                action_type=action_type,
                message=f"Unknown action: {action_type}",
            )
        
        defn = ACTION_REGISTRY[action_type]
        
        # Validate required parameters
        for param in defn.required_params:
            if param not in parameters or not parameters[param]:
                return ActionResult(
                    success=False,
                    action_type=action_type,
                    message=f"Missing required parameter: {param}",
                )
        
        # Execute based on action type
        try:
            handler = getattr(self, f"_execute_{action_type}", None)
            if handler:
                return await handler(parameters)
            else:
                # Default: send to frontend
                return ActionResult(
                    success=True,
                    action_type=action_type,
                    message=f"Action {action_type} queued for frontend",
                    frontend_action={
                        "type": action_type,
                        "params": parameters,
                    },
                )
        except Exception as e:
            return ActionResult(
                success=False,
                action_type=action_type,
                message=f"Action failed: {str(e)}",
            )
    
    async def execute_batch(
        self,
        actions: List[Dict[str, Any]],
    ) -> List[ActionResult]:
        """Execute multiple actions in sequence."""
        results = []
        for action in actions:
            result = await self.execute(
                action.get("type", ""),
                action.get("params", {}),
            )
            results.append(result)
        return results
    
    # ========================================================================
    # Action Handlers
    # ========================================================================
    
    async def _execute_create_block(self, params: Dict[str, Any]) -> ActionResult:
        """Create a new block. Sanitize name so full user message is not used as block title."""
        raw_name = (params.get("name") or "New Block").strip()
        if len(raw_name) > 100 or any(
            phrase in raw_name.lower() for phrase in ("clear the block", "delete the block", "remove the block")
        ):
            raw_name = "New Block"
        return ActionResult(
            success=True,
            action_type="create_block",
            message=f"Created block: {raw_name}",
            frontend_action={
                "type": "create_block",
                "params": {
                    "name": raw_name,
                    "type": params.get("type", "note"),
                    "parent_id": params.get("parent_id"),
                    "notes": params.get("notes", ""),
                },
            },
        )
    
    async def _execute_create_task(self, params: Dict[str, Any]) -> ActionResult:
        """Create a new task."""
        return ActionResult(
            success=True,
            action_type="create_task",
            message=f"Created task: {params.get('text')}",
            frontend_action={
                "type": "create_task",
                "params": {
                    "text": params.get("text"),
                    "block_id": params.get("block_id"),
                    "priority": params.get("priority", "none"),
                    "due_date": params.get("due_date", ""),
                    "status": params.get("status", "not_started"),
                    "tags": params.get("tags", "").split(",") if params.get("tags") else [],
                },
            },
        )
    
    async def _execute_start_timer(self, params: Dict[str, Any]) -> ActionResult:
        """Start a focus timer."""
        minutes = int(params.get("minutes", 25))
        return ActionResult(
            success=True,
            action_type="start_timer",
            message=f"Started {minutes} minute timer",
            frontend_action={
                "type": "start_timer",
                "params": {"minutes": minutes, "task_id": params.get("task_id")},
            },
        )
    
    async def _execute_start_pomodoro(self, params: Dict[str, Any]) -> ActionResult:
        """Start a Pomodoro session."""
        mode = params.get("mode", "work")
        return ActionResult(
            success=True,
            action_type="start_pomodoro",
            message=f"Started Pomodoro ({mode})",
            frontend_action={
                "type": "start_pomodoro",
                "params": {"mode": mode},
            },
        )
    
    async def _execute_stop_timer(self, params: Dict[str, Any]) -> ActionResult:
        """Stop the timer."""
        return ActionResult(
            success=True,
            action_type="stop_timer",
            message="Timer stopped",
            frontend_action={"type": "stop_timer", "params": {}},
        )
    
    async def _execute_open_panel(self, params: Dict[str, Any]) -> ActionResult:
        """Open a UI panel."""
        panel = params.get("panel", "").lower()
        valid_panels = ["mindmap", "tasks", "calendar", "pomodoro", "stats", "habits", "chat", "settings"]
        
        if panel not in valid_panels:
            return ActionResult(
                success=False,
                action_type="open_panel",
                message=f"Unknown panel: {panel}. Valid: {', '.join(valid_panels)}",
            )
        
        return ActionResult(
            success=True,
            action_type="open_panel",
            message=f"Opening {panel}",
            frontend_action={"type": "open_panel", "params": {"panel": panel}},
        )
    
    async def _execute_change_theme(self, params: Dict[str, Any]) -> ActionResult:
        """Change the app theme."""
        theme = params.get("theme", "").lower()
        valid_themes = ["sky", "forest", "sunset", "ocean", "lavender", "rose", "mint", "gold"]
        
        if theme not in valid_themes:
            return ActionResult(
                success=False,
                action_type="change_theme",
                message=f"Unknown theme: {theme}. Valid: {', '.join(valid_themes)}",
            )
        
        return ActionResult(
            success=True,
            action_type="change_theme",
            message=f"Changed theme to {theme}",
            frontend_action={"type": "change_theme", "params": {"theme": theme}},
        )
    
    async def _execute_set_focus(self, params: Dict[str, Any]) -> ActionResult:
        """Set the focus text."""
        text = params.get("text", "")
        return ActionResult(
            success=True,
            action_type="set_focus",
            message=f"Focus set to: {text}",
            frontend_action={"type": "set_focus", "params": {"text": text}},
        )
    
    async def _execute_show_notification(self, params: Dict[str, Any]) -> ActionResult:
        """Show a notification."""
        return ActionResult(
            success=True,
            action_type="show_notification",
            message="Notification shown",
            frontend_action={
                "type": "show_notification",
                "params": {
                    "title": params.get("title"),
                    "message": params.get("message"),
                    "icon": params.get("icon", "🔔"),
                },
            },
        )
    
    async def _execute_open_browser(self, params: Dict[str, Any]) -> ActionResult:
        """Open a URL in the browser."""
        url = params.get("url", "")
        if not url:
            return ActionResult(
                success=False,
                action_type="open_browser",
                message="No URL provided",
            )
        
        # Add https if missing
        if not url.startswith("http"):
            url = "https://" + url
        
        return ActionResult(
            success=True,
            action_type="open_browser",
            message=f"Opening: {url}",
            frontend_action={
                "type": "open_browser",
                "params": {
                    "url": url,
                    "instructions": params.get("instructions", ""),
                },
            },
        )
    
    async def _execute_add_calendar_event(self, params: Dict[str, Any]) -> ActionResult:
        """Add a calendar event."""
        return ActionResult(
            success=True,
            action_type="add_calendar_event",
            message=f"Added event: {params.get('title')}",
            frontend_action={
                "type": "add_calendar_event",
                "params": {
                    "title": params.get("title"),
                    "start": params.get("start"),
                    "end": params.get("end", params.get("start")),
                    "status": params.get("status", "not_started"),
                },
            },
        )
    
    async def _execute_create_habit(self, params: Dict[str, Any]) -> ActionResult:
        """Create a habit."""
        return ActionResult(
            success=True,
            action_type="create_habit",
            message=f"Created habit: {params.get('name')}",
            frontend_action={
                "type": "create_habit",
                "params": {
                    "name": params.get("name"),
                    "icon": params.get("icon", "🎯"),
                    "frequency": params.get("frequency", "daily"),
                },
            },
        )
    
    async def _execute_create_study_plan(self, params: Dict[str, Any]) -> ActionResult:
        """Create a comprehensive study plan."""
        # This will be handled by the study service
        return ActionResult(
            success=True,
            action_type="create_study_plan",
            message=f"Creating study plan for: {params.get('subject')}",
            data={
                "subject": params.get("subject"),
                "topics": params.get("topics", "").split(",") if params.get("topics") else [],
                "exam_date": params.get("exam_date"),
                "daily_hours": params.get("daily_hours", "2"),
            },
            frontend_action={
                "type": "show_notification",
                "params": {
                    "title": "Study Plan",
                    "message": f"Creating study plan for {params.get('subject')}...",
                    "icon": "📚",
                },
            },
        )
    
    async def _execute_start_study_session(self, params: Dict[str, Any]) -> ActionResult:
        """Start an automated study session."""
        topic = params.get("topic", "")
        duration = int(params.get("duration", 25))
        
        # This triggers multiple actions
        return ActionResult(
            success=True,
            action_type="start_study_session",
            message=f"Starting study session: {topic} for {duration} min",
            frontend_action={
                "type": "start_study_session",
                "params": {
                    "topic": topic,
                    "duration": duration,
                    "block_id": params.get("block_id"),
                },
            },
        )


# Singleton
_action_executor: Optional[ActionExecutor] = None


def get_action_executor() -> ActionExecutor:
    """Get the action executor singleton."""
    global _action_executor
    if _action_executor is None:
        _action_executor = ActionExecutor()
    return _action_executor
