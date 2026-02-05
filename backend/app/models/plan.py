"""
Plan Model - Persistent planning with step tracking.
"""

from datetime import datetime
from typing import Optional, List
from uuid import uuid4

from sqlalchemy import String, Text, Integer, Boolean, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db.base import Base, TimestampMixin, UUIDMixin


class PlanStatus(str, enum.Enum):
    """Status of a plan."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, enum.Enum):
    """Status of a plan step."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled_back"


class Plan(Base, UUIDMixin, TimestampMixin):
    """
    A multi-step plan for achieving a goal.
    """
    
    __tablename__ = "plans"
    
    # Owner
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Plan details
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Status
    status: Mapped[PlanStatus] = mapped_column(
        SQLEnum(PlanStatus),
        default=PlanStatus.PENDING,
        nullable=False,
    )
    
    # Progress
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    completed_steps: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Metadata
    context: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    steps: Mapped[List["PlanStep"]] = relationship(
        "PlanStep",
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="PlanStep.order",
    )
    
    def __repr__(self) -> str:
        return f"<Plan {self.id[:8]}... [{self.status.value}] {self.completed_steps}/{self.total_steps}>"


class PlanStep(Base, UUIDMixin, TimestampMixin):
    """
    A single step in a plan.
    """
    
    __tablename__ = "plan_steps"
    
    # Parent plan
    plan_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Step details
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Action
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    action_params: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Status
    status: Mapped[StepStatus] = mapped_column(
        SQLEnum(StepStatus),
        default=StepStatus.PENDING,
        nullable=False,
    )
    
    # Result
    result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Rollback support
    can_rollback: Mapped[bool] = mapped_column(Boolean, default=False)
    rollback_action: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    rolled_back_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Dependencies
    depends_on: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)  # List of step IDs
    
    # Relationships
    plan: Mapped["Plan"] = relationship("Plan", back_populates="steps")
    
    def __repr__(self) -> str:
        return f"<PlanStep {self.order}. {self.name} [{self.status.value}]>"
