"""
Event models for the AI agent SSE streaming.
Inspired by ai-manus event system.
"""
import uuid
import time
import json
from enum import Enum
from typing import Dict, Any, Optional, List


class PlanStatus(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    COMPLETED = "completed"


class StepStatus(str, Enum):
    STARTED = "started"
    FAILED = "failed"
    COMPLETED = "completed"


class ToolStatus(str, Enum):
    CALLING = "calling"
    CALLED = "called"


class AgentEvent:
    """Base event class for agent SSE streaming."""

    def __init__(self, event_type: str, **kwargs):
        self.type = event_type
        self.id = str(uuid.uuid4())[:8]
        self.timestamp = time.time()
        self.data = kwargs

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "timestamp": self.timestamp,
            **self.data,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


class PlanEvent(AgentEvent):
    def __init__(self, status: PlanStatus, plan: Dict[str, Any]):
        super().__init__("plan", status=status.value, plan=plan)


class StepEvent(AgentEvent):
    def __init__(self, status: StepStatus, step: Dict[str, Any]):
        super().__init__("step", status=status.value, step=step)


class ToolEvent(AgentEvent):
    def __init__(
        self,
        status: ToolStatus,
        tool_name: str,
        function_name: str,
        function_args: Dict[str, Any],
        tool_call_id: str = "",
        function_result: Optional[Any] = None,
        tool_content: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            "tool",
            status=status.value,
            tool_name=tool_name,
            function_name=function_name,
            function_args=function_args,
            tool_call_id=tool_call_id or str(uuid.uuid4())[:8],
            function_result=function_result,
            tool_content=tool_content,
        )


class MessageEvent(AgentEvent):
    def __init__(self, message: str, role: str = "assistant"):
        super().__init__("message", message=message, role=role)


class ErrorEvent(AgentEvent):
    def __init__(self, error: str):
        super().__init__("error", error=error)


class DoneEvent(AgentEvent):
    def __init__(self):
        super().__init__("done")


class TitleEvent(AgentEvent):
    def __init__(self, title: str):
        super().__init__("title", title=title)


class ThinkingEvent(AgentEvent):
    def __init__(self, thinking: str):
        super().__init__("thinking", thinking=thinking)
