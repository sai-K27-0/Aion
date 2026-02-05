"""
Evaluation Service - AI quality monitoring and metrics.

Tracks:
- Response latency
- User satisfaction (thumbs up/down)
- Error rates
- Model performance
"""

import time
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum


class FeedbackType(str, Enum):
    """Types of user feedback."""
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    FLAG = "flag"
    EDIT = "edit"


@dataclass
class AIMetric:
    """A single AI interaction metric."""
    id: str
    timestamp: datetime
    model: str
    task_type: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    success: bool
    error: Optional[str] = None
    feedback: Optional[FeedbackType] = None
    feedback_comment: Optional[str] = None


@dataclass
class MetricsSummary:
    """Summary of metrics over a time period."""
    period_start: datetime
    period_end: datetime
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    total_input_tokens: int
    total_output_tokens: int
    thumbs_up: int
    thumbs_down: int
    satisfaction_rate: float  # thumbs_up / (thumbs_up + thumbs_down)
    by_model: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    by_task: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class EvaluationService:
    """Service for tracking and evaluating AI performance."""
    
    MAX_METRICS = 10000  # Keep last N metrics
    
    def __init__(self):
        self.metrics: List[AIMetric] = []
        self.active_requests: Dict[str, float] = {}  # request_id -> start_time
    
    # ========================================================================
    # Request Tracking
    # ========================================================================
    
    def start_request(self, request_id: str):
        """Mark the start of an AI request."""
        self.active_requests[request_id] = time.time()
    
    def end_request(
        self,
        request_id: str,
        model: str,
        task_type: str,
        input_tokens: int,
        output_tokens: int,
        success: bool = True,
        error: Optional[str] = None,
    ) -> AIMetric:
        """Mark the end of an AI request and record metrics."""
        start_time = self.active_requests.pop(request_id, time.time())
        latency_ms = int((time.time() - start_time) * 1000)
        
        metric = AIMetric(
            id=request_id,
            timestamp=datetime.now(timezone.utc),
            model=model,
            task_type=task_type,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            success=success,
            error=error,
        )
        
        self._add_metric(metric)
        return metric
    
    def _add_metric(self, metric: AIMetric):
        """Add a metric, maintaining max size."""
        self.metrics.append(metric)
        if len(self.metrics) > self.MAX_METRICS:
            self.metrics = self.metrics[-self.MAX_METRICS:]
    
    # ========================================================================
    # Feedback
    # ========================================================================
    
    def add_feedback(
        self,
        request_id: str,
        feedback_type: FeedbackType,
        comment: Optional[str] = None,
    ) -> bool:
        """Add user feedback for a request."""
        for metric in reversed(self.metrics):
            if metric.id == request_id:
                metric.feedback = feedback_type
                metric.feedback_comment = comment
                return True
        return False
    
    # ========================================================================
    # Analytics
    # ========================================================================
    
    def get_summary(
        self,
        hours: int = 24,
        model: Optional[str] = None,
        task_type: Optional[str] = None,
    ) -> MetricsSummary:
        """Get a summary of metrics."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        # Filter metrics
        filtered = [
            m for m in self.metrics
            if m.timestamp >= cutoff
            and (model is None or m.model == model)
            and (task_type is None or m.task_type == task_type)
        ]
        
        if not filtered:
            return MetricsSummary(
                period_start=cutoff,
                period_end=datetime.now(timezone.utc),
                total_requests=0,
                successful_requests=0,
                failed_requests=0,
                avg_latency_ms=0,
                p50_latency_ms=0,
                p95_latency_ms=0,
                p99_latency_ms=0,
                total_input_tokens=0,
                total_output_tokens=0,
                thumbs_up=0,
                thumbs_down=0,
                satisfaction_rate=0,
            )
        
        # Calculate metrics
        latencies = sorted([m.latency_ms for m in filtered])
        thumbs_up = sum(1 for m in filtered if m.feedback == FeedbackType.THUMBS_UP)
        thumbs_down = sum(1 for m in filtered if m.feedback == FeedbackType.THUMBS_DOWN)
        
        # By model breakdown
        by_model = defaultdict(lambda: {"requests": 0, "success": 0, "latency_sum": 0})
        for m in filtered:
            by_model[m.model]["requests"] += 1
            by_model[m.model]["success"] += 1 if m.success else 0
            by_model[m.model]["latency_sum"] += m.latency_ms
        
        for model_name, stats in by_model.items():
            stats["avg_latency_ms"] = stats["latency_sum"] / stats["requests"]
            stats["success_rate"] = stats["success"] / stats["requests"]
        
        # By task breakdown
        by_task = defaultdict(lambda: {"requests": 0, "success": 0, "latency_sum": 0})
        for m in filtered:
            by_task[m.task_type]["requests"] += 1
            by_task[m.task_type]["success"] += 1 if m.success else 0
            by_task[m.task_type]["latency_sum"] += m.latency_ms
        
        for task_name, stats in by_task.items():
            stats["avg_latency_ms"] = stats["latency_sum"] / stats["requests"]
            stats["success_rate"] = stats["success"] / stats["requests"]
        
        return MetricsSummary(
            period_start=cutoff,
            period_end=datetime.now(timezone.utc),
            total_requests=len(filtered),
            successful_requests=sum(1 for m in filtered if m.success),
            failed_requests=sum(1 for m in filtered if not m.success),
            avg_latency_ms=sum(latencies) / len(latencies),
            p50_latency_ms=self._percentile(latencies, 50),
            p95_latency_ms=self._percentile(latencies, 95),
            p99_latency_ms=self._percentile(latencies, 99),
            total_input_tokens=sum(m.input_tokens for m in filtered),
            total_output_tokens=sum(m.output_tokens for m in filtered),
            thumbs_up=thumbs_up,
            thumbs_down=thumbs_down,
            satisfaction_rate=thumbs_up / (thumbs_up + thumbs_down) if (thumbs_up + thumbs_down) > 0 else 0,
            by_model=dict(by_model),
            by_task=dict(by_task),
        )
    
    def _percentile(self, sorted_list: List[int], p: int) -> float:
        """Calculate percentile from sorted list."""
        if not sorted_list:
            return 0
        k = (len(sorted_list) - 1) * p / 100
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_list) else f
        return sorted_list[f] + (k - f) * (sorted_list[c] - sorted_list[f])
    
    def get_recent_errors(self, limit: int = 10) -> List[AIMetric]:
        """Get recent failed requests."""
        errors = [m for m in reversed(self.metrics) if not m.success]
        return errors[:limit]
    
    def get_low_satisfaction(self, limit: int = 10) -> List[AIMetric]:
        """Get requests with negative feedback."""
        negative = [
            m for m in reversed(self.metrics)
            if m.feedback in (FeedbackType.THUMBS_DOWN, FeedbackType.FLAG)
        ]
        return negative[:limit]
    
    def export_metrics(self) -> List[Dict[str, Any]]:
        """Export all metrics for external analysis."""
        return [
            {
                "id": m.id,
                "timestamp": m.timestamp.isoformat(),
                "model": m.model,
                "task_type": m.task_type,
                "latency_ms": m.latency_ms,
                "input_tokens": m.input_tokens,
                "output_tokens": m.output_tokens,
                "success": m.success,
                "error": m.error,
                "feedback": m.feedback.value if m.feedback else None,
            }
            for m in self.metrics
        ]


# Singleton
_evaluation_service: Optional[EvaluationService] = None


def get_evaluation_service() -> EvaluationService:
    """Get the evaluation service singleton."""
    global _evaluation_service
    if _evaluation_service is None:
        _evaluation_service = EvaluationService()
    return _evaluation_service
