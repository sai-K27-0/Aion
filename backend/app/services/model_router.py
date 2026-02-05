"""
Model Router - Intelligent model selection and response caching.

Features:
- Task-specific model routing
- Response caching with semantic similarity
- Cost-aware model selection
- Fallback handling
"""

import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from enum import Enum

from app.config import settings


class TaskType(str, Enum):
    """Types of tasks for routing."""
    CHAT = "chat"
    INTENT = "intent"
    SUMMARIZE = "summarize"
    EXTRACT = "extract"
    EMBED = "embed"
    CODE = "code"
    CREATIVE = "creative"
    ANALYSIS = "analysis"


@dataclass
class ModelConfig:
    """Configuration for a model."""
    name: str
    cost_per_1k_tokens: float  # Relative cost
    max_tokens: int
    strengths: List[TaskType]
    speed: int  # 1-10, 10 being fastest
    quality: int  # 1-10, 10 being best


@dataclass
class CachedResponse:
    """A cached AI response."""
    query_hash: str
    response: str
    model: str
    task_type: TaskType
    created_at: datetime
    hit_count: int = 0


class ModelRouter:
    """
    Routes requests to appropriate models and caches responses.
    """
    
    # Model configurations
    MODELS = {
        "llama3.2": ModelConfig(
            name="llama3.2",
            cost_per_1k_tokens=0.1,
            max_tokens=8192,
            strengths=[TaskType.CHAT, TaskType.ANALYSIS, TaskType.CODE],
            speed=7,
            quality=8,
        ),
        "llama3.2:1b": ModelConfig(
            name="llama3.2:1b",
            cost_per_1k_tokens=0.02,
            max_tokens=4096,
            strengths=[TaskType.INTENT, TaskType.EXTRACT, TaskType.SUMMARIZE],
            speed=10,
            quality=5,
        ),
        "mistral": ModelConfig(
            name="mistral",
            cost_per_1k_tokens=0.08,
            max_tokens=8192,
            strengths=[TaskType.CHAT, TaskType.CODE, TaskType.ANALYSIS],
            speed=8,
            quality=7,
        ),
        "phi3": ModelConfig(
            name="phi3",
            cost_per_1k_tokens=0.05,
            max_tokens=4096,
            strengths=[TaskType.INTENT, TaskType.EXTRACT, TaskType.CODE],
            speed=9,
            quality=6,
        ),
        "codellama": ModelConfig(
            name="codellama",
            cost_per_1k_tokens=0.1,
            max_tokens=8192,
            strengths=[TaskType.CODE],
            speed=6,
            quality=9,
        ),
    }
    
    # Default model
    DEFAULT_MODEL = "llama3.2"
    
    # Cache settings
    CACHE_MAX_SIZE = 1000
    CACHE_TTL_HOURS = 24
    
    def __init__(self):
        self.cache: Dict[str, CachedResponse] = {}
        self.available_models: List[str] = [self.DEFAULT_MODEL]
        self.usage_stats: Dict[str, Dict[str, int]] = {}  # model -> {requests, tokens}
    
    async def refresh_available_models(self, ai_service) -> List[str]:
        """Refresh the list of available models from Ollama."""
        try:
            models = await ai_service.list_models()
            self.available_models = [
                m.get("name", m) if isinstance(m, dict) else m
                for m in models
            ]
            # Filter to known models
            self.available_models = [
                m for m in self.available_models
                if any(m.startswith(known) for known in self.MODELS.keys())
            ] or [self.DEFAULT_MODEL]
            return self.available_models
        except Exception:
            return self.available_models
    
    def select_model(
        self,
        task_type: TaskType,
        prefer_speed: bool = False,
        prefer_quality: bool = False,
        max_cost: Optional[float] = None,
    ) -> str:
        """
        Select the best model for a task.
        
        Args:
            task_type: Type of task to perform
            prefer_speed: Prioritize speed over quality
            prefer_quality: Prioritize quality over speed
            max_cost: Maximum cost per 1k tokens
            
        Returns:
            Model name to use
        """
        # Filter to available models
        candidates = [
            (name, config) for name, config in self.MODELS.items()
            if any(name.startswith(avail.split(":")[0]) for avail in self.available_models)
        ]
        
        if not candidates:
            return self.DEFAULT_MODEL
        
        # Filter by cost if specified
        if max_cost is not None:
            candidates = [(n, c) for n, c in candidates if c.cost_per_1k_tokens <= max_cost]
        
        if not candidates:
            return self.DEFAULT_MODEL
        
        # Score each candidate
        def score_model(config: ModelConfig) -> float:
            score = 0.0
            
            # Task strength bonus
            if task_type in config.strengths:
                score += 30
            
            # Speed vs quality
            if prefer_speed:
                score += config.speed * 5
            elif prefer_quality:
                score += config.quality * 5
            else:
                score += (config.speed + config.quality) * 2.5
            
            # Cost penalty
            score -= config.cost_per_1k_tokens * 10
            
            return score
        
        # Sort by score
        candidates.sort(key=lambda x: score_model(x[1]), reverse=True)
        
        return candidates[0][0]
    
    def get_cache_key(
        self,
        query: str,
        system_prompt: Optional[str] = None,
        task_type: TaskType = TaskType.CHAT,
    ) -> str:
        """Generate a cache key for a query."""
        content = f"{task_type.value}:{system_prompt or ''}:{query}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def get_cached_response(
        self,
        query: str,
        system_prompt: Optional[str] = None,
        task_type: TaskType = TaskType.CHAT,
    ) -> Optional[str]:
        """Get a cached response if available."""
        key = self.get_cache_key(query, system_prompt, task_type)
        cached = self.cache.get(key)
        
        if cached:
            # Check TTL
            age = datetime.now(timezone.utc) - cached.created_at
            if age < timedelta(hours=self.CACHE_TTL_HOURS):
                cached.hit_count += 1
                return cached.response
            else:
                # Expired
                del self.cache[key]
        
        return None
    
    def cache_response(
        self,
        query: str,
        response: str,
        model: str,
        system_prompt: Optional[str] = None,
        task_type: TaskType = TaskType.CHAT,
    ):
        """Cache a response."""
        # Check if cacheable (not too long, not error, etc.)
        if len(response) > 10000 or response.startswith("Error"):
            return
        
        # Evict if cache is full
        if len(self.cache) >= self.CACHE_MAX_SIZE:
            self._evict_old_entries()
        
        key = self.get_cache_key(query, system_prompt, task_type)
        self.cache[key] = CachedResponse(
            query_hash=key,
            response=response,
            model=model,
            task_type=task_type,
            created_at=datetime.now(timezone.utc),
        )
    
    def _evict_old_entries(self):
        """Remove old cache entries."""
        # Sort by hit count (keep frequently used) and age
        entries = list(self.cache.items())
        entries.sort(key=lambda x: (x[1].hit_count, x[1].created_at))
        
        # Remove bottom 20%
        to_remove = len(entries) // 5
        for key, _ in entries[:to_remove]:
            del self.cache[key]
    
    def track_usage(self, model: str, tokens: int):
        """Track model usage for analytics."""
        if model not in self.usage_stats:
            self.usage_stats[model] = {"requests": 0, "tokens": 0}
        
        self.usage_stats[model]["requests"] += 1
        self.usage_stats[model]["tokens"] += tokens
    
    def get_usage_stats(self) -> Dict[str, Dict[str, int]]:
        """Get usage statistics."""
        return self.usage_stats.copy()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_hits = sum(c.hit_count for c in self.cache.values())
        return {
            "size": len(self.cache),
            "max_size": self.CACHE_MAX_SIZE,
            "total_hits": total_hits,
            "oldest_entry": min(
                (c.created_at for c in self.cache.values()),
                default=None,
            ),
        }


# Singleton
_model_router: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    """Get the model router singleton."""
    global _model_router
    if _model_router is None:
        _model_router = ModelRouter()
    return _model_router
