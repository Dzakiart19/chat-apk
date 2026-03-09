"""
Plan and Step models for the AI agent.
Inspired by ai-manus Plan-Act architecture.
"""
import uuid
from enum import Enum
from typing import List, Optional, Dict, Any


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Step:
    def __init__(
        self,
        description: str = "",
        step_id: str = "",
        status: ExecutionStatus = ExecutionStatus.PENDING,
        result: Optional[str] = None,
        error: Optional[str] = None,
        success: bool = False,
        attachments: Optional[List[str]] = None,
    ):
        self.id = step_id or str(uuid.uuid4())[:8]
        self.description = description
        self.status = status
        self.result = result
        self.error = error
        self.success = success
        self.attachments = attachments or []

    def is_done(self) -> bool:
        return self.status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "success": self.success,
            "attachments": self.attachments,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Step":
        return cls(
            step_id=data.get("id", ""),
            description=data.get("description", ""),
            status=ExecutionStatus(data.get("status", "pending")),
            result=data.get("result"),
            error=data.get("error"),
            success=data.get("success", False),
            attachments=data.get("attachments", []),
        )


class Plan:
    def __init__(
        self,
        title: str = "",
        goal: str = "",
        language: str = "en",
        steps: Optional[List[Step]] = None,
        message: Optional[str] = None,
        status: ExecutionStatus = ExecutionStatus.PENDING,
    ):
        self.id = str(uuid.uuid4())[:8]
        self.title = title
        self.goal = goal
        self.language = language
        self.steps = steps or []
        self.message = message
        self.status = status

    def is_done(self) -> bool:
        return self.status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED)

    def get_next_step(self) -> Optional[Step]:
        for step in self.steps:
            if not step.is_done():
                return step
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "goal": self.goal,
            "language": self.language,
            "steps": [s.to_dict() for s in self.steps],
            "message": self.message,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Plan":
        steps = [Step.from_dict(s) for s in data.get("steps", [])]
        return cls(
            title=data.get("title", ""),
            goal=data.get("goal", ""),
            language=data.get("language", "en"),
            steps=steps,
            message=data.get("message"),
            status=ExecutionStatus(data.get("status", "pending")),
        )
