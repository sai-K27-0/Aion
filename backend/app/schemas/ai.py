from typing import Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID, uuid4

class TaskStep(BaseModel):
    """A single step in an autonomous plan."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    description: str
    action_type: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    status: str = "pending"  # pending, running, completed, failed
    result: Optional[Any] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    reasoning: Optional[str] = None

class Plan(BaseModel):
    """A collection of steps to achieve a goal."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    goal: str
    steps: List[TaskStep] = Field(default_factory=list)
    status: str = "pending"  # pending, active, completed, failed
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class PlanCreate(BaseModel):
    """Schema for creating a new plan."""
    goal: str

class PlanExecute(BaseModel):
    """Schema for starting plan execution."""
    plan_id: str
    autonomous: bool = False
