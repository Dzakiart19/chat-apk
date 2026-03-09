"""
Plan and Step models for the AI agent.
Matching ai-manus Plan-Act architecture with Pydantic models.
"""
import uuid
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Step(BaseModel):
    """A single step in an execution plan."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    status: ExecutionStatus = ExecutionStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    success: bool = False
    attachments: List[str] = Field(default_factory=list)

    def is_done(self) -> bool:
        return self.status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Step":
        return cls(**data)


class Plan(BaseModel):
    """Execution plan containing multiple steps."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str = ""
    goal: str = ""
    language: Optional[str] = "en"
    steps: List[Step] = Field(default_factory=list)
    message: Optional[str] = None
    status: ExecutionStatus = ExecutionStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def is_done(self) -> bool:
        return self.status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED)

    def get_next_step(self) -> Optional[Step]:
        for step in self.steps:
            if not step.is_done():
                return step
        return None

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Plan":
        return cls(**data)

    def dump_json(self) -> str:
        return self.model_dump_json(include={"goal", "language", "steps"})
