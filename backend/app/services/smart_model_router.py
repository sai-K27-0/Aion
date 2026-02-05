"""
Smart Model Router - Automatically selects the optimal Ollama model for each task.

Model Selection Strategy:
- llama3.2: Fast general tasks, quick actions, simple questions
- deepseek-r1: Complex reasoning, study plans, detailed explanations
- llava: Vision tasks, screen analysis, image understanding
- nomic-embed-text: Embeddings for semantic search

This ensures the best balance of speed and quality for each use case.
"""

import asyncio
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from app.services.ai_service import get_ai_service


class TaskType(str, Enum):
    """Types of tasks for model selection."""
    # Fast tasks - use lightweight model
    QUICK_ACTION = "quick_action"       # Start timer, create task, change theme
    SIMPLE_CHAT = "simple_chat"         # Short questions, greetings
    INTENT_PARSE = "intent_parse"       # Parse user intent
    
    # Medium tasks - use balanced model
    GENERAL_CHAT = "general_chat"       # Normal conversation
    TASK_PLANNING = "task_planning"     # Create tasks, organize
    VOICE_CHAT = "voice_chat"           # Voice conversation (needs fast + quality)
    
    # Complex tasks - use reasoning model
    STUDY_PLAN = "study_plan"           # Create comprehensive study plans
    TOPIC_EXPLAIN = "topic_explain"     # Detailed explanations
    FLASHCARDS = "flashcards"           # Generate flashcards
    QUIZ = "quiz"                       # Generate quiz questions
    REASONING = "reasoning"             # Complex problem solving
    CODE_HELP = "code_help"             # Programming assistance
    
    # Vision tasks - use vision model
    SCREEN_ANALYSIS = "screen_analysis" # Analyze screenshots
    IMAGE_UNDERSTAND = "image_understand" # Understand images
    
    # Embedding tasks
    EMBEDDING = "embedding"             # Generate embeddings


@dataclass
class ModelConfig:
    """Configuration for a model."""
    name: str
    description: str
    max_context: int
    speed_rating: int  # 1-5 (5 = fastest)
    quality_rating: int  # 1-5 (5 = best)
    best_for: List[TaskType]


# Model configurations
MODEL_CONFIGS: Dict[str, ModelConfig] = {
    "llama3.2": ModelConfig(
        name="llama3.2",
        description="Fast, general-purpose model",
        max_context=4096,
        speed_rating=5,
        quality_rating=3,
        best_for=[
            TaskType.QUICK_ACTION,
            TaskType.SIMPLE_CHAT,
            TaskType.INTENT_PARSE,
            TaskType.GENERAL_CHAT,
            TaskType.TASK_PLANNING,
        ],
    ),
    "deepseek-r1": ModelConfig(
        name="deepseek-r1",
        description="Advanced reasoning model",
        max_context=4096,
        speed_rating=3,
        quality_rating=5,
        best_for=[
            TaskType.STUDY_PLAN,
            TaskType.TOPIC_EXPLAIN,
            TaskType.FLASHCARDS,
            TaskType.QUIZ,
            TaskType.REASONING,
            TaskType.CODE_HELP,
        ],
    ),
    "llava": ModelConfig(
        name="llava",
        description="Vision and image understanding model",
        max_context=4096,
        speed_rating=3,
        quality_rating=4,
        best_for=[
            TaskType.SCREEN_ANALYSIS,
            TaskType.IMAGE_UNDERSTAND,
        ],
    ),
    "nomic-embed-text": ModelConfig(
        name="nomic-embed-text",
        description="Fast embedding model",
        max_context=8192,
        speed_rating=5,
        quality_rating=4,
        best_for=[
            TaskType.EMBEDDING,
        ],
    ),
}

# Task to model mapping
TASK_MODEL_MAP: Dict[TaskType, str] = {
    # Fast model for quick tasks
    TaskType.QUICK_ACTION: "llama3.2",
    TaskType.SIMPLE_CHAT: "llama3.2",
    TaskType.INTENT_PARSE: "llama3.2",
    TaskType.GENERAL_CHAT: "llama3.2",
    TaskType.TASK_PLANNING: "llama3.2",
    TaskType.VOICE_CHAT: "llama3.2",  # Fast for real-time conversation
    
    # Reasoning model for complex tasks
    TaskType.STUDY_PLAN: "deepseek-r1",
    TaskType.TOPIC_EXPLAIN: "deepseek-r1",
    TaskType.FLASHCARDS: "deepseek-r1",
    TaskType.QUIZ: "deepseek-r1",
    TaskType.REASONING: "deepseek-r1",
    TaskType.CODE_HELP: "deepseek-r1",
    
    # Vision model
    TaskType.SCREEN_ANALYSIS: "llava",
    TaskType.IMAGE_UNDERSTAND: "llava",
    
    # Embedding model
    TaskType.EMBEDDING: "nomic-embed-text",
}

# Keywords to detect task type
TASK_KEYWORDS: Dict[TaskType, List[str]] = {
    TaskType.QUICK_ACTION: [
        "start timer", "stop timer", "create task", "add task", "open",
        "change theme", "set focus", "start pomodoro", "pause",
    ],
    TaskType.STUDY_PLAN: [
        "study plan", "help me study", "prepare for exam", "learning plan",
        "schedule study", "exam preparation", "study schedule",
    ],
    TaskType.TOPIC_EXPLAIN: [
        "explain", "what is", "how does", "teach me", "understand",
        "definition of", "describe", "tell me about",
    ],
    TaskType.FLASHCARDS: [
        "flashcard", "flash card", "create cards", "study cards",
        "make flashcards", "generate flashcards",
    ],
    TaskType.QUIZ: [
        "quiz", "test me", "practice questions", "exam questions",
        "multiple choice", "assessment",
    ],
    TaskType.REASONING: [
        "solve", "calculate", "figure out", "analyze", "compare",
        "why", "reason", "logic", "think through",
    ],
    TaskType.CODE_HELP: [
        "code", "programming", "function", "debug", "script",
        "python", "javascript", "algorithm",
    ],
}


class SmartModelRouter:
    """
    Intelligently routes requests to the optimal Ollama model.
    
    Features:
    - Automatic task type detection
    - Model selection based on task requirements
    - Fallback handling when preferred model unavailable
    - Performance tracking
    """
    
    def __init__(self):
        self.ai_service = get_ai_service()
        self._available_models: List[str] = []
        self._model_stats: Dict[str, Dict[str, Any]] = {}
        self._last_model_check = 0
    
    async def get_available_models(self, force_refresh: bool = False) -> List[str]:
        """Get list of available models, with caching."""
        current_time = time.time()
        
        # Cache for 60 seconds
        if not force_refresh and self._available_models and (current_time - self._last_model_check) < 60:
            return self._available_models
        
        try:
            self._available_models = await self.ai_service.list_models()
            self._last_model_check = current_time
        except:
            # Return cached or default
            if not self._available_models:
                self._available_models = ["llama3.2"]
        
        return self._available_models
    
    def detect_task_type(self, message: str, context: Optional[Dict[str, Any]] = None) -> TaskType:
        """
        Detect the type of task from the message.
        
        Args:
            message: The user's message
            context: Optional context (e.g., has_image, previous_task)
        """
        message_lower = message.lower()
        
        # Check for vision context
        if context and context.get("has_image"):
            return TaskType.IMAGE_UNDERSTAND
        
        # Check keywords for each task type
        for task_type, keywords in TASK_KEYWORDS.items():
            for keyword in keywords:
                if keyword in message_lower:
                    return task_type
        
        # Check message length for simple vs general chat
        if len(message) < 50:
            return TaskType.SIMPLE_CHAT
        
        # Default to general chat
        return TaskType.GENERAL_CHAT
    
    async def get_model_for_task(
        self,
        task_type: TaskType,
        prefer_speed: bool = False,
        prefer_quality: bool = False,
    ) -> str:
        """
        Get the optimal model for a task type.
        
        Args:
            task_type: The type of task
            prefer_speed: Override to prefer faster model
            prefer_quality: Override to prefer higher quality model
        """
        available = await self.get_available_models()
        
        # Get preferred model
        preferred = TASK_MODEL_MAP.get(task_type, "llama3.2")
        
        # Check if preferred model is available
        if preferred in available or any(m.startswith(preferred) for m in available):
            # Find exact match or versioned match
            for m in available:
                if m == preferred or m.startswith(preferred + ":"):
                    return m
        
        # Fallback logic
        if prefer_speed:
            # Prefer smallest/fastest model
            for fallback in ["llama3.2", "phi3", "qwen2.5"]:
                for m in available:
                    if m.startswith(fallback):
                        return m
        
        if prefer_quality:
            # Prefer reasoning models
            for fallback in ["deepseek-r1", "dolphin-mixtral", "llama3.2"]:
                for m in available:
                    if m.startswith(fallback):
                        return m
        
        # Default fallback
        return available[0] if available else "llama3.2"
    
    async def route(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        force_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Route a request to the optimal model.
        
        Args:
            message: The user's message
            context: Optional context
            force_model: Force a specific model (bypasses routing)
            
        Returns:
            Dict with model name and task type
        """
        if force_model:
            return {
                "model": force_model,
                "task_type": TaskType.GENERAL_CHAT,
                "routing_reason": "forced",
            }
        
        # Detect task type
        task_type = self.detect_task_type(message, context)
        
        # Get optimal model
        model = await self.get_model_for_task(task_type)
        
        # Determine routing reason
        reason = f"Selected {model} for {task_type.value}"
        
        return {
            "model": model,
            "task_type": task_type,
            "routing_reason": reason,
        }
    
    async def chat_with_routing(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        context: Optional[List[Dict]] = None,
        task_context: Optional[Dict[str, Any]] = None,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """
        Chat with automatic model routing.
        
        Returns response with model info.
        """
        # Route to optimal model
        routing = await self.route(message, task_context)
        model = routing["model"]
        task_type = routing["task_type"]
        
        # Adjust temperature based on task
        if task_type in [TaskType.QUIZ, TaskType.FLASHCARDS]:
            temperature = 0.4  # More deterministic
        elif task_type in [TaskType.QUICK_ACTION, TaskType.INTENT_PARSE]:
            temperature = 0.3  # Very deterministic
        elif task_type in [TaskType.TOPIC_EXPLAIN]:
            temperature = 0.6  # Slightly creative
        
        # Start timing
        start_time = time.time()
        
        # Call AI service with selected model
        response = await self.ai_service.chat(
            message=message,
            system_prompt=system_prompt,
            context=context,
            temperature=temperature,
            model=model,
        )
        
        # Track timing
        elapsed = time.time() - start_time
        self._track_model_usage(model, task_type, elapsed)
        
        return {
            "response": response,
            "model": model,
            "task_type": task_type.value,
            "routing_reason": routing["routing_reason"],
            "response_time_ms": int(elapsed * 1000),
        }
    
    def _track_model_usage(self, model: str, task_type: TaskType, elapsed: float):
        """Track model usage statistics."""
        if model not in self._model_stats:
            self._model_stats[model] = {
                "total_calls": 0,
                "total_time": 0,
                "by_task": {},
            }
        
        stats = self._model_stats[model]
        stats["total_calls"] += 1
        stats["total_time"] += elapsed
        
        task_key = task_type.value
        if task_key not in stats["by_task"]:
            stats["by_task"][task_key] = {"calls": 0, "time": 0}
        stats["by_task"][task_key]["calls"] += 1
        stats["by_task"][task_key]["time"] += elapsed
    
    def get_stats(self) -> Dict[str, Any]:
        """Get model usage statistics."""
        stats = {}
        for model, data in self._model_stats.items():
            avg_time = data["total_time"] / data["total_calls"] if data["total_calls"] > 0 else 0
            stats[model] = {
                "total_calls": data["total_calls"],
                "avg_response_time_ms": int(avg_time * 1000),
                "by_task": {
                    task: {
                        "calls": info["calls"],
                        "avg_time_ms": int((info["time"] / info["calls"]) * 1000) if info["calls"] > 0 else 0,
                    }
                    for task, info in data["by_task"].items()
                },
            }
        return stats
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about model routing configuration."""
        return {
            "task_model_map": {k.value: v for k, v in TASK_MODEL_MAP.items()},
            "model_configs": {
                name: {
                    "description": cfg.description,
                    "speed_rating": cfg.speed_rating,
                    "quality_rating": cfg.quality_rating,
                    "best_for": [t.value for t in cfg.best_for],
                }
                for name, cfg in MODEL_CONFIGS.items()
            },
        }


# Singleton
_smart_router: Optional[SmartModelRouter] = None


def get_smart_router() -> SmartModelRouter:
    """Get the smart model router singleton."""
    global _smart_router
    if _smart_router is None:
        _smart_router = SmartModelRouter()
    return _smart_router
