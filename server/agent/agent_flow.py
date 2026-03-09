#!/usr/bin/env python3
"""
Dzeck AI Agent - Plan-Act Flow Engine
Ported from ai-manus PlanActFlow architecture.

This is the core autonomous agent implementing:
1. Plan-Act state machine (IDLE -> PLANNING -> EXECUTING -> UPDATING -> SUMMARIZING -> DONE)
2. Robust JSON parsing with 5-stage repair pipeline (anti-hallucination)
3. Memory management with compaction
4. Full tool system matching ai-manus (shell, file, search, browser, message, mcp)
5. Event streaming via JSON lines to stdout for SSE relay

Uses airforce API (OpenAI-compatible) for all LLM calls.
"""
import re
import sys
import json
import time
import traceback
import urllib.request
from enum import Enum
from typing import Optional, Dict, Any, List

# Import tools
from server.agent.tools.search import web_search, web_browse
from server.agent.tools.shell import (
    shell_exec, shell_view, shell_wait,
    shell_write_to_process, shell_kill_process,
)
from server.agent.tools.file import (
    file_read, file_write, file_str_replace,
    file_find_by_name, file_find_in_content,
)
from server.agent.tools.message import message_notify_user, message_ask_user
from server.agent.tools.browser import (
    browser_navigate, browser_view, browser_click, browser_type,
    browser_scroll, browser_scroll_to_bottom, browser_read_links,
    browser_console_view, browser_restart, browser_save_image,
)
from server.agent.tools.mcp import mcp_call_tool, mcp_list_tools

# Import models
from server.agent.models.plan import Plan, Step, ExecutionStatus
from server.agent.models.event import (
    PlanStatus, StepStatus, ToolStatus,
)
from server.agent.models.memory import Memory
from server.agent.models.tool_result import ToolResult

# Import utilities
from server.agent.utils.robust_json_parser import RobustJsonParser

# Import prompts
from server.agent.prompts.system import SYSTEM_PROMPT
from server.agent.prompts.planner import (
    PLANNER_SYSTEM_PROMPT,
    CREATE_PLAN_PROMPT,
    UPDATE_PLAN_PROMPT,
)
from server.agent.prompts.execution import (
    EXECUTION_SYSTEM_PROMPT,
    EXECUTION_PROMPT,
    SUMMARIZE_PROMPT,
)


class FlowState(str, Enum):
    """State machine states matching ai-manus PlanActFlow."""
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    UPDATING = "updating"
    SUMMARIZING = "summarizing"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"


# Tool registry - full Dzeck agent tool set
TOOLS: Dict[str, Any] = {
    # Messaging
    "message_notify_user": message_notify_user,
    "message_ask_user": message_ask_user,
    # Shell
    "shell_exec": shell_exec,
    "shell_view": shell_view,
    "shell_wait": shell_wait,
    "shell_write_to_process": shell_write_to_process,
    "shell_kill_process": shell_kill_process,
    # File
    "file_read": file_read,
    "file_write": file_write,
    "file_str_replace": file_str_replace,
    "file_find_by_name": file_find_by_name,
    "file_find_in_content": file_find_in_content,
    # Browser
    "browser_navigate": browser_navigate,
    "browser_view": browser_view,
    "browser_click": browser_click,
    "browser_type": browser_type,
    "browser_scroll": browser_scroll,
    "browser_scroll_to_bottom": browser_scroll_to_bottom,
    "browser_read_links": browser_read_links,
    "browser_console_view": browser_console_view,
    "browser_restart": browser_restart,
    "browser_save_image": browser_save_image,
    # Search / Web
    "web_search": web_search,
    "web_browse": web_browse,
    # MCP
    "mcp_call_tool": mcp_call_tool,
    "mcp_list_tools": mcp_list_tools,
}

# Backward compatibility aliases
TOOL_ALIASES: Dict[str, str] = {
    "message_notify": "message_notify_user",
    "message_ask": "message_ask_user",
    "file_find": "file_find_by_name",
    "browser_open": "browser_navigate",
    "browse": "web_browse",
    "search": "web_search",
}

# Toolkit type mapping (function_name -> toolkit name) matching ai-manus
# In ai-manus, each tool belongs to a toolkit with a name like "shell", "browser", etc.
# The ToolEvent uses tool_name for the toolkit name and function_name for the specific function.
TOOLKIT_MAP: Dict[str, str] = {
    # Shell toolkit
    "shell_exec": "shell",
    "shell_view": "shell",
    "shell_wait": "shell",
    "shell_write_to_process": "shell",
    "shell_kill_process": "shell",
    # File toolkit
    "file_read": "file",
    "file_write": "file",
    "file_str_replace": "file",
    "file_find_by_name": "file",
    "file_find_in_content": "file",
    # Browser toolkit
    "browser_navigate": "browser",
    "browser_view": "browser",
    "browser_click": "browser",
    "browser_type": "browser",
    "browser_scroll": "browser",
    "browser_scroll_to_bottom": "browser",
    "browser_read_links": "browser",
    "browser_console_view": "browser",
    "browser_restart": "browser",
    "browser_save_image": "browser",
    # Search toolkit
    "web_search": "search",
    "web_browse": "browser",
    # Message toolkit
    "message_notify_user": "message",
    "message_ask_user": "message",
    # MCP toolkit
    "mcp_call_tool": "mcp",
    "mcp_list_tools": "mcp",
}

# -- Airforce API Configuration --
AIRFORCE_API_URL = "https://api.airforce/v1/chat/completions"
AIRFORCE_API_KEY = (
    "sk-air-QzarypeWD8oB4vEUy5ucuVl1Efef6NSFepurPPiQaeChKQEQxTT7u03T09ikagyg"
)
DEFAULT_MODEL = "gpt-4o-mini"

# -- OpenAI Function Calling Tool Schemas --
TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {"type": "function", "function": {"name": "task_complete", "description": "Signal that the current task step is complete.", "parameters": {"type": "object", "properties": {"success": {"type": "boolean", "description": "Whether the step succeeded"}, "result": {"type": "string", "description": "Summary of what was accomplished"}}, "required": ["success", "result"]}}},
    {"type": "function", "function": {"name": "message_notify_user", "description": "Send a progress update or result to the user (non-blocking)", "parameters": {"type": "object", "properties": {"text": {"type": "string", "description": "Message text"}, "attachments": {"type": "array", "items": {"type": "string"}, "description": "File paths to attach"}}, "required": ["text"]}}},
    {"type": "function", "function": {"name": "message_ask_user", "description": "Ask the user a question and wait for response (blocking)", "parameters": {"type": "object", "properties": {"text": {"type": "string", "description": "Question to ask"}, "attachments": {"type": "array", "items": {"type": "string"}}}, "required": ["text"]}}},
    {"type": "function", "function": {"name": "shell_exec", "description": "Execute a shell command. Use -y/-f flags to avoid prompts.", "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "Shell command"}, "exec_dir": {"type": "string", "description": "Working directory"}, "id": {"type": "string", "description": "Shell session ID"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "shell_view", "description": "View current output of a running shell session", "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}}},
    {"type": "function", "function": {"name": "shell_wait", "description": "Wait for a running process to complete", "parameters": {"type": "object", "properties": {"id": {"type": "string"}, "seconds": {"type": "integer"}}, "required": ["id"]}}},
    {"type": "function", "function": {"name": "shell_write_to_process", "description": "Write input to a running process", "parameters": {"type": "object", "properties": {"id": {"type": "string"}, "input": {"type": "string"}, "press_enter": {"type": "boolean"}}, "required": ["id", "input", "press_enter"]}}},
    {"type": "function", "function": {"name": "shell_kill_process", "description": "Kill a running process", "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}}},
    {"type": "function", "function": {"name": "file_read", "description": "Read content from a text file", "parameters": {"type": "object", "properties": {"file": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, "required": ["file"]}}},
    {"type": "function", "function": {"name": "file_write", "description": "Write content to a file", "parameters": {"type": "object", "properties": {"file": {"type": "string"}, "content": {"type": "string"}, "append": {"type": "boolean"}, "leading_newline": {"type": "boolean"}, "trailing_newline": {"type": "boolean"}}, "required": ["file", "content"]}}},
    {"type": "function", "function": {"name": "file_str_replace", "description": "Replace a specific string in a file (exact match)", "parameters": {"type": "object", "properties": {"file": {"type": "string"}, "old_str": {"type": "string"}, "new_str": {"type": "string"}}, "required": ["file", "old_str", "new_str"]}}},
    {"type": "function", "function": {"name": "file_find_by_name", "description": "Find files by name/glob pattern", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "glob": {"type": "string"}}, "required": ["path", "glob"]}}},
    {"type": "function", "function": {"name": "file_find_in_content", "description": "Search for regex patterns in a file", "parameters": {"type": "object", "properties": {"file": {"type": "string"}, "regex": {"type": "string"}}, "required": ["file", "regex"]}}},
    {"type": "function", "function": {"name": "browser_navigate", "description": "Navigate to a URL", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "browser_view", "description": "Get current page content", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "browser_click", "description": "Click at (x,y) coordinates", "parameters": {"type": "object", "properties": {"coordinate_x": {"type": "integer"}, "coordinate_y": {"type": "integer"}, "button": {"type": "string"}}, "required": ["coordinate_x", "coordinate_y"]}}},
    {"type": "function", "function": {"name": "browser_type", "description": "Type text into focused element", "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}},
    {"type": "function", "function": {"name": "browser_scroll", "description": "Scroll the page", "parameters": {"type": "object", "properties": {"coordinate_x": {"type": "integer"}, "coordinate_y": {"type": "integer"}, "direction": {"type": "string"}, "amount": {"type": "integer"}}, "required": ["coordinate_x", "coordinate_y", "direction", "amount"]}}},
    {"type": "function", "function": {"name": "browser_scroll_to_bottom", "description": "Scroll to bottom", "parameters": {"type": "object", "properties": {"coordinate_x": {"type": "integer"}, "coordinate_y": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "browser_read_links", "description": "Get all links from page", "parameters": {"type": "object", "properties": {"max_links": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "browser_console_view", "description": "View browser console logs", "parameters": {"type": "object", "properties": {"max_lines": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "browser_restart", "description": "Restart browser session", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "browser_save_image", "description": "Save an image from page", "parameters": {"type": "object", "properties": {"coordinate_x": {"type": "integer"}, "coordinate_y": {"type": "integer"}, "save_dir": {"type": "string"}, "base_name": {"type": "string"}}, "required": ["coordinate_x", "coordinate_y", "save_dir", "base_name"]}}},
    {"type": "function", "function": {"name": "web_search", "description": "Search the web (DuckDuckGo)", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "num_results": {"type": "integer"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "web_browse", "description": "Browse and extract text from a URL", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "mcp_call_tool", "description": "Call an MCP tool", "parameters": {"type": "object", "properties": {"tool_name": {"type": "string"}, "arguments": {"type": "object"}}, "required": ["tool_name"]}}},
    {"type": "function", "function": {"name": "mcp_list_tools", "description": "List available MCP tools", "parameters": {"type": "object", "properties": {}}}},
]


def emit_event(event_type: str, **data: Any) -> None:
    """Emit a JSON event line to stdout for SSE streaming."""
    event: Dict[str, Any] = {"type": event_type, **data}
    sys.stdout.write(json.dumps(event, default=str) + "\n")
    sys.stdout.flush()


def call_airforce_api(
    messages: list,
    model: str = DEFAULT_MODEL,
    tools: Optional[List[Dict[str, Any]]] = None,
    response_format: Optional[str] = None,
) -> Dict[str, Any]:
    """Call the airforce API (OpenAI-compatible). Returns full response dict."""
    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 4096,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    if response_format == "json_object":
        body["response_format"] = {"type": "json_object"}

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        AIRFORCE_API_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(AIRFORCE_API_KEY),
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def call_airforce_text(
    messages: list,
    model: str = DEFAULT_MODEL,
    response_format: Optional[str] = None,
) -> str:
    """Convenience wrapper that returns only the text content."""
    result = call_airforce_api(messages, model,
                               response_format=response_format)
    if "choices" in result and result["choices"]:
        return result["choices"][0]["message"].get("content") or ""
    return ""


def call_text_with_retry(
    messages: list,
    model: str = DEFAULT_MODEL,
    max_retries: int = 3,
    response_format: Optional[str] = None,
) -> str:
    """Call airforce text API with retry + exponential backoff."""
    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return call_airforce_text(messages, model, response_format)
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(1 * (attempt + 1))
    if last_error is not None:
        raise last_error
    raise RuntimeError("LLM call failed after retries")


def call_api_with_retry(
    messages: list,
    model: str = DEFAULT_MODEL,
    tools: Optional[List[Dict[str, Any]]] = None,
    max_retries: int = 3,
) -> Dict[str, Any]:
    """Call airforce API (full response) with retry + exponential backoff."""
    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return call_airforce_api(messages, model, tools=tools)
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(1 * (attempt + 1))
    if last_error is not None:
        raise last_error
    raise RuntimeError("LLM call failed after retries")


def resolve_tool_name(name: str) -> Optional[str]:
    """Resolve a tool name, handling aliases."""
    if name in TOOLS:
        return name
    if name in TOOL_ALIASES:
        return TOOL_ALIASES[name]
    return None


def get_toolkit_name(function_name: str) -> str:
    """Get the toolkit name for a function (matching ai-manus toolkit naming)."""
    return TOOLKIT_MAP.get(function_name, "unknown")


def execute_tool(tool_name: str, tool_args: Dict[str, Any]) -> ToolResult:
    """Execute a tool and return ToolResult."""
    resolved = resolve_tool_name(tool_name)
    if resolved is None:
        return ToolResult(
            success=False,
            message=("Unknown tool '{}'. Available: {}"
                     .format(tool_name, ", ".join(TOOLS.keys()))),
        )

    tool_fn = TOOLS[resolved]
    try:
        result = tool_fn(**tool_args)
        if isinstance(result, ToolResult):
            return result
        if isinstance(result, dict):
            return ToolResult(
                success=result.get("success", True),
                message=json.dumps(result, default=str),
                data=result,
            )
        return ToolResult(success=True, message=str(result))
    except TypeError as e:
        return ToolResult(
            success=False,
            message="Invalid arguments for '{}': {}".format(tool_name, e),
        )
    except Exception as e:
        return ToolResult(
            success=False,
            message="Tool '{}' failed: {}".format(tool_name, e),
        )


def build_tool_content(
    tool_name: str, tool_result: ToolResult
) -> Optional[Dict[str, Any]]:
    """Build tool-specific content for frontend display."""
    data = tool_result.data or {}

    # Shell tools
    if tool_name in ("shell_exec", "shell_view", "shell_wait",
                      "shell_write_to_process", "shell_kill_process"):
        console = data.get("stdout", "") or data.get("output", "")
        if data.get("stderr"):
            console += "\n" + data["stderr"]
        return {
            "type": "shell",
            "command": data.get("command", ""),
            "console": console,
            "return_code": data.get("return_code", 0),
            "id": data.get("id", ""),
        }

    # Search
    elif tool_name == "web_search":
        return {
            "type": "search",
            "query": data.get("query", ""),
            "results": data.get("results", []),
        }

    # Browser tools
    elif tool_name in ("web_browse", "browser_navigate", "browser_view",
                        "browser_click", "browser_type", "browser_scroll",
                        "browser_scroll_to_bottom", "browser_read_links",
                        "browser_console_view", "browser_save_image",
                        "browser_restart"):
        return {
            "type": "browser",
            "url": data.get("url", ""),
            "title": data.get("title", ""),
            "content": str(data.get("content", data.get("content_snippet", "")))[:2000],
            "links": data.get("links", [])[:10],
            "save_path": data.get("save_path", ""),
        }

    # File tools
    elif tool_name in ("file_read", "file_write", "file_str_replace",
                        "file_find_by_name", "file_find_in_content"):
        return {
            "type": "file",
            "file": data.get("file", data.get("path", "")),
            "content": str(data.get("content", ""))[:2000],
            "operation": tool_name.replace("file_", ""),
        }

    # MCP tools
    elif tool_name in ("mcp_call_tool", "mcp_list_tools"):
        return {
            "type": "mcp",
            "tool": data.get("tool_name", ""),
            "result": str(data)[:2000],
        }

    return None


def safe_plan_dict(plan: Plan) -> Dict[str, Any]:
    """Return plan dict with goal stripped to prevent leaking."""
    d = plan.to_dict()
    d.pop("goal", None)
    return d


class DzeckAgent:
    """
    Main agent class implementing the Plan-Act flow.
    Uses OpenAI function calling for smart tool execution (ai-manus style).
    """

    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        self.memory = Memory()
        self.max_tool_iterations = 20
        self.plan: Optional[Plan] = None
        self.state = FlowState.IDLE
        self.parser = RobustJsonParser()

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """Parse LLM response using robust 5-stage JSON parser.

        Key anti-hallucination mechanism from ai-manus.
        """
        result, error = self.parser.parse(text)
        if result is not None:
            return result
        emit_event("error", error="JSON parse failed: {}".format(error),
                   details=text[:200])
        return {}

    def _detect_language(self, text: str) -> str:
        """Simple language detection from text."""
        id_words = [
            "saya", "anda", "untuk", "yang", "dengan", "dari", "ini",
            "itu", "bisa", "akan", "sudah", "tidak", "ada", "juga",
            "atau", "harus", "karena", "supaya", "seperti", "bantu",
            "tolong", "projek", "bagaimana", "silakan", "terima", "kasih",
        ]
        text_lower = text.lower()
        id_count = sum(1 for w in id_words if w in text_lower)
        if id_count >= 2:
            return "id"
        if any("\u4e00" <= c <= "\u9fff" for c in text):
            return "zh"
        if any("\u3040" <= c <= "\u309f" or "\u30a0" <= c <= "\u30ff"
               for c in text):
            return "ja"
        if any("\uac00" <= c <= "\ud7af" for c in text):
            return "ko"
        return "en"

    def run_planner(self, user_message: str,
                    attachments: Optional[List[str]] = None) -> Plan:
        """Create a plan from the user's message.

        Uses PLANNER_SYSTEM_PROMPT + CREATE_PLAN_PROMPT from ai-manus.
        """
        self.state = FlowState.PLANNING
        emit_event("thinking",
                   content="Analyzing your request and creating a plan...")

        language = self._detect_language(user_message)

        attachments_info = ""
        if attachments:
            attachments_info = "Attachments: {}".format(
                ", ".join(attachments))

        prompt = CREATE_PLAN_PROMPT.format(
            message=user_message,
            language=language,
            attachments_info=attachments_info,
        )

        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        response_text = call_text_with_retry(
            messages, self.model, response_format="json_object"
        )
        parsed = self._parse_response(response_text)

        if not parsed:
            return Plan(
                title="Task Execution",
                goal=user_message[:100],
                language=language,
                steps=[Step(id="1", description=user_message)],
                message="I'll work on this task for you.",
            )

        steps = []
        for s in parsed.get("steps", []):
            steps.append(Step(
                id=str(s.get("id", "")),
                description=s.get("description", ""),
            ))

        if not steps:
            steps = [Step(id="1", description=user_message)]

        return Plan(
            title=parsed.get("title", "Task"),
            goal=parsed.get("goal", user_message[:100]),
            language=parsed.get("language", language),
            steps=steps,
            message=parsed.get("message", ""),
        )

    def _handle_tool_call(
        self,
        fn_name: str,
        fn_args: Dict[str, Any],
        tool_call_id: str,
        step: Step,
        iteration: int,
    ) -> Optional[str]:
        """Execute a single function-call tool and return the result string.

        Returns "STEP_DONE" for task_complete. Otherwise returns result text.
        """
        # task_complete pseudo-tool
        if fn_name == "task_complete":
            step.status = ExecutionStatus.COMPLETED
            step.success = fn_args.get("success", True)
            step.result = fn_args.get("result", "Step completed")
            if not step.success:
                step.status = ExecutionStatus.FAILED
            status_enum = (StepStatus.COMPLETED if step.success
                           else StepStatus.FAILED)
            emit_event("step", status=status_enum.value,
                       step=step.to_dict())
            if step.result:
                emit_event("message", message=step.result,
                           role="assistant")
            return "STEP_DONE"

        resolved = resolve_tool_name(fn_name)
        if resolved is None:
            return ("Unknown tool '{}'. Available: {}"
                    .format(fn_name, ", ".join(TOOLS.keys())))

        toolkit_name = get_toolkit_name(resolved)
        emit_event(
            "tool",
            status=ToolStatus.CALLING.value,
            tool_name=toolkit_name,
            function_name=resolved,
            function_args=fn_args,
            tool_call_id=tool_call_id,
        )

        tool_result = execute_tool(resolved, fn_args)
        tool_content = build_tool_content(resolved, tool_result)

        if resolved == "message_notify_user":
            emit_event("message",
                       message=fn_args.get("text", ""),
                       role="assistant")
        elif resolved == "message_ask_user":
            emit_event("wait", prompt=fn_args.get("text", ""))
            emit_event("message",
                       message=fn_args.get("text", ""),
                       role="assistant")

        result_status = (ToolStatus.CALLED if tool_result.success
                         else ToolStatus.ERROR)
        fn_result = (str(tool_result.message)[:3000]
                     if tool_result.message else "")
        emit_event(
            "tool",
            status=result_status.value,
            tool_name=toolkit_name,
            function_name=resolved,
            function_args=fn_args,
            tool_call_id=tool_call_id,
            function_result=fn_result,
            tool_content=tool_content,
        )

        self.memory.add_message({
            "role": "tool",
            "tool_name": resolved,
            "content": tool_result.message or "",
        })

        result_summary = tool_result.message or "No result"
        if len(result_summary) > 4000:
            result_summary = result_summary[:4000] + "...[truncated]"
        return result_summary

    def execute_step(self, plan: Plan, step: Step,
                     user_message: str) -> None:
        """Execute a single step using tools iteratively.

        Uses OpenAI function calling (ai-manus style). The model decides
        whether to call tools or not. Falls back to JSON parsing when
        the model responds with plain text.
        """
        self.state = FlowState.EXECUTING
        step.status = ExecutionStatus.RUNNING
        emit_event("step", status=StepStatus.RUNNING.value,
                   step=step.to_dict())

        context_parts: List[str] = []
        for s in plan.steps:
            if s.is_done() and s.result:
                context_parts.append("- {}: {}".format(
                    s.description, s.result))
        context = ("\n".join(context_parts)
                   if context_parts else "No previous context.")

        prompt = EXECUTION_PROMPT.format(
            step=step.description,
            message=user_message,
            language=plan.language or "en",
            context=context,
            attachments_info="",
        )

        exec_messages: List[Dict[str, Any]] = [
            {"role": "system", "content": EXECUTION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        self.memory.add_message(
            {"role": "system",
             "content": "Executing step: {}".format(step.description)}
        )

        for iteration in range(self.max_tool_iterations):
            try:
                # Call API with tools for native function calling
                api_result = call_api_with_retry(
                    exec_messages, self.model, tools=TOOL_SCHEMAS)

                if ("choices" not in api_result
                        or not api_result["choices"]):
                    step.status = ExecutionStatus.FAILED
                    step.result = "Empty LLM response"
                    emit_event("step", status=StepStatus.FAILED.value,
                               step=step.to_dict())
                    return

                choice = api_result["choices"][0]
                message = choice.get("message", {})
                content = message.get("content") or ""
                tool_calls = message.get("tool_calls")

                # -- Native function calling path --
                if tool_calls:
                    assistant_msg: Dict[str, Any] = {
                        "role": "assistant",
                        "content": content if content else None,
                    }
                    assistant_msg["tool_calls"] = tool_calls
                    exec_messages.append(assistant_msg)

                    step_done = False
                    for tc in tool_calls:
                        fn_name = tc["function"]["name"]
                        try:
                            fn_args = json.loads(
                                tc["function"]["arguments"])
                        except (json.JSONDecodeError, KeyError):
                            fn_args = {}

                        tc_id = tc.get("id", "tc_{}_{}".format(
                            step.id, iteration))

                        result_str = self._handle_tool_call(
                            fn_name, fn_args, tc_id, step, iteration)

                        if result_str == "STEP_DONE":
                            step_done = True
                            exec_messages.append({
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "content": "Step marked complete.",
                            })
                            break

                        exec_messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": result_str or "Done",
                        })

                    if step_done:
                        return

                    if iteration > 0 and iteration % 5 == 0:
                        self.memory.compact()
                    continue

                # -- Fallback: plain text response (no tool_calls) --
                if content:
                    parsed = self._parse_response(content)

                    if parsed.get("done"):
                        step.status = ExecutionStatus.COMPLETED
                        step.success = parsed.get("success", True)
                        step.result = parsed.get(
                            "result", "Step completed")
                        step.attachments = parsed.get(
                            "attachments", [])
                        if not step.success:
                            step.status = ExecutionStatus.FAILED
                        status_enum = (
                            StepStatus.COMPLETED if step.success
                            else StepStatus.FAILED)
                        emit_event("step", status=status_enum.value,
                                   step=step.to_dict())
                        if step.result:
                            emit_event("message",
                                       message=step.result,
                                       role="assistant")
                        return

                    if parsed.get("thinking"):
                        emit_event("thinking",
                                   content=parsed["thinking"])
                        exec_messages.append(
                            {"role": "assistant", "content": content})
                        exec_messages.append(
                            {"role": "user",
                             "content": ("Good analysis. Now execute "
                                         "using a tool.")})
                        continue

                    if parsed.get("tool"):
                        tool_name = parsed["tool"]
                        tool_args = parsed.get("args", {})
                        resolved_name = resolve_tool_name(tool_name)

                        if resolved_name is None:
                            exec_messages.append(
                                {"role": "assistant",
                                 "content": content})
                            available = ", ".join(TOOLS.keys())
                            exec_messages.append(
                                {"role": "user",
                                 "content": (
                                     "Unknown tool '{}'. Available: "
                                     "{}. Try again."
                                     .format(tool_name, available))})
                            continue

                        tc_id = "tc_{}_{}".format(step.id, iteration)
                        result_str = self._handle_tool_call(
                            resolved_name, tool_args, tc_id,
                            step, iteration)

                        if result_str == "STEP_DONE":
                            return

                        exec_messages.append(
                            {"role": "assistant", "content": content})
                        exec_messages.append(
                            {"role": "user",
                             "content": (
                                 "Tool result:\n{}\n\nContinue "
                                 "executing the step. Use another "
                                 "tool or call task_complete when "
                                 "finished."
                             ).format(result_str)})

                        if iteration > 0 and iteration % 5 == 0:
                            self.memory.compact()
                        continue

                    if parsed.get("message"):
                        emit_event("message",
                                   message=parsed["message"],
                                   role="assistant")

                # Text with no actionable JSON = step complete
                step.status = ExecutionStatus.COMPLETED
                step.success = True
                step.result = content[:500] if content else "Step completed"
                emit_event("step",
                           status=StepStatus.COMPLETED.value,
                           step=step.to_dict())
                if content:
                    emit_event("message", message=content[:2000],
                               role="assistant")
                return

            except Exception as e:
                emit_event("error",
                           error="Step execution error: {}".format(e))
                step.status = ExecutionStatus.FAILED
                step.error = str(e)
                emit_event("step", status=StepStatus.FAILED.value,
                           step=step.to_dict())
                return

        # Max iterations reached
        step.status = ExecutionStatus.FAILED
        step.success = False
        step.result = "Step incomplete (max iterations reached)"
        emit_event("step", status=StepStatus.FAILED.value,
                   step=step.to_dict())

    def update_plan(self, plan: Plan, completed_step: Step) -> None:
        """Update the plan based on completed step result."""
        self.state = FlowState.UPDATING

        completed_steps_info = []
        for s in plan.steps:
            if s.is_done():
                status = "Success" if s.success else "Failed"
                completed_steps_info.append(
                    "Step {} ({}): {} - {}".format(
                        s.id, s.description, status,
                        s.result or "No result"))

        current_step_info = "Step {}: {}".format(
            completed_step.id, completed_step.description)
        step_result_info = completed_step.result or "No result"

        remaining = [s for s in plan.steps if not s.is_done()]
        plan_info = json.dumps(
            {
                "language": plan.language,
                "completed_steps": [
                    s.to_dict() for s in plan.steps if s.is_done()
                ],
                "remaining_steps": [s.to_dict() for s in remaining],
            },
            default=str,
        )

        prompt = UPDATE_PLAN_PROMPT.format(
            current_plan=plan_info,
            completed_steps="\n".join(completed_steps_info),
            current_step=current_step_info,
            step_result=step_result_info,
        )

        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        try:
            response_text = call_text_with_retry(
                messages, self.model, response_format="json_object")
            parsed = self._parse_response(response_text)

            if parsed and "steps" in parsed:
                new_steps = [
                    Step(id=str(s.get("id", "")),
                         description=s.get("description", ""))
                    for s in parsed["steps"]
                ]

                first_pending = None
                for i, s in enumerate(plan.steps):
                    if not s.is_done():
                        first_pending = i
                        break

                if first_pending is not None and new_steps:
                    completed_list = plan.steps[:first_pending]
                    completed_list.extend(new_steps)
                    plan.steps = completed_list

                emit_event("plan", status=PlanStatus.UPDATED.value,
                           plan=safe_plan_dict(plan))

        except Exception as e:
            emit_event("error",
                       error="Plan update skipped: {}".format(e))

    def summarize(self, plan: Plan, user_message: str) -> None:
        """Generate a final summary of the completed task."""
        self.state = FlowState.SUMMARIZING

        step_results = []
        for s in plan.steps:
            status = "Success" if s.success else "Failed"
            step_results.append(
                "- Step {} ({}): {} - {}".format(
                    s.id, s.description, status,
                    s.result or "No result"))

        prompt = SUMMARIZE_PROMPT.format(
            step_results="\n".join(step_results),
            message=user_message,
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        try:
            response_text = call_text_with_retry(messages, self.model)
            parsed = self._parse_response(response_text)

            if parsed and parsed.get("message"):
                emit_event(
                    "message", message=parsed["message"],
                    role="assistant",
                    attachments=parsed.get("attachments", []))
            else:
                emit_event("message", message=response_text[:2000],
                           role="assistant")
        except Exception as e:
            emit_event(
                "message",
                message="Task completed. Summary unavailable: {}".format(e),
                role="assistant",
            )

    def _is_simple_query(self, user_message: str) -> bool:
        """Detect if the user message is a simple query that doesn't need tools.

        Matching ai-manus behavior: the agent should be smart about when
        to use tools vs. when to respond directly. Simple greetings,
        casual questions, and basic knowledge queries don't need the
        full Plan-Act flow.

        Uses word-boundary matching via regex to avoid false positives
        (e.g. "hai" should not match inside "chain").
        """
        msg = user_message.strip().lower()
        words = msg.split()
        word_count = len(words)

        if word_count <= 3:
            # Check for greetings and simple phrases using word boundaries
            simple_patterns = [
                r"\bhi\b", r"\bhello\b", r"\bhey\b",
                r"\bhalo\b", r"\bhai\b", r"\bhei\b",
                r"\bthanks\b", r"\bthank you\b",
                r"\bterima kasih\b", r"\bmakasih\b",
                r"\bok\b", r"\bokay\b", r"\boke\b",
                r"\bbaik\b", r"\bsiap\b",
                r"\byes\b", r"\bno\b", r"\bya\b", r"\btidak\b",
                r"\bbye\b", r"\bgoodbye\b", r"\bsampai jumpa\b",
                r"\bgood morning\b", r"\bgood night\b",
                r"\bselamat pagi\b", r"\bselamat malam\b",
                r"\bselamat siang\b",
                r"\bwho are you\b", r"\bsiapa kamu\b",
                r"\bsiapa anda\b",
                r"\bwhat can you do\b", r"\bapa yang bisa\b",
                r"\bhow are you\b", r"\bapa kabar\b",
            ]
            for pattern in simple_patterns:
                if re.search(pattern, msg):
                    return True

        # Detect simple knowledge questions (no tool needed)
        knowledge_starters = [
            "what is", "what are", "who is", "who are",
            "when was", "when is", "where is", "where are",
            "why is", "why are", "how does", "how do",
            "explain", "define", "describe",
            "apa itu", "siapa", "kapan", "dimana", "mengapa",
            "jelaskan", "ceritakan", "bagaimana cara",
        ]
        # Use word-boundary check for action keywords too
        action_patterns = [
            r"\bhttp", r"[/\\]", r"```",
            r"\bfile\b", r"\binstall\b", r"\brun\b",
            r"\bcreate\b", r"\bbuild\b", r"\bwrite\b",
            r"\bbuat\b", r"\btulis\b", r"\bjalankan\b",
        ]
        for starter in knowledge_starters:
            if msg.startswith(starter):
                # Only if there's no URL, file path, or code/action indication
                if not any(re.search(p, msg) for p in action_patterns):
                    return True

        return False

    def _respond_directly(self, user_message: str) -> None:
        """Respond directly without Plan-Act flow for simple queries.

        Uses the LLM to generate a direct response without tool calling.
        This matches ai-manus behavior where the agent is smart about
        not always creating a plan.
        """
        messages = [
            {"role": "system", "content": (
                "You are Dzeck, an AI assistant created by the Dzeck team. "
                "Respond naturally and helpfully to the user's message. "
                "Be concise but informative. "
                "Respond in the same language as the user's message."
            )},
            {"role": "user", "content": user_message},
        ]

        try:
            response_text = call_text_with_retry(messages, self.model)
            if response_text:
                emit_event("message", message=response_text[:4000],
                           role="assistant")
            else:
                emit_event("message",
                           message="I'm sorry, I couldn't generate a response.",
                           role="assistant")
        except Exception as e:
            emit_event("error",
                       error="Response error: {}".format(e))

    def run(self, user_message: str,
            attachments: Optional[List[str]] = None) -> None:
        """Main agent flow: Smart routing + Plan -> Execute -> Update -> Summarize.

        Implements ai-manus PlanActFlow state machine:
        IDLE -> PLANNING -> EXECUTING -> UPDATING -> SUMMARIZING -> COMPLETED

        Smart routing: Simple queries are handled directly without creating
        a plan. Complex tasks go through the full Plan-Act flow.
        """
        try:
            # Smart routing: detect if this is a simple query
            if not attachments and self._is_simple_query(user_message):
                self._respond_directly(user_message)
                emit_event("done", success=True)
                return

            # Phase 1: Planning
            self.state = FlowState.PLANNING
            emit_event("plan", status=PlanStatus.CREATING.value)

            self.plan = self.run_planner(user_message, attachments)

            emit_event("title", title=self.plan.title)
            if self.plan.message:
                emit_event("message", message=self.plan.message,
                           role="assistant")
            emit_event("plan", status=PlanStatus.CREATED.value,
                       plan=safe_plan_dict(self.plan))

            if not self.plan.steps:
                emit_event(
                    "message",
                    message="No actionable steps needed.",
                    role="assistant",
                )
                emit_event("done", success=True)
                return

            # Phase 2: Execute each step
            emit_event("plan", status=PlanStatus.RUNNING.value,
                       plan=safe_plan_dict(self.plan))

            while True:
                step = self.plan.get_next_step()
                if not step:
                    break

                self.execute_step(self.plan, step, user_message)

                next_step = self.plan.get_next_step()
                if next_step:
                    emit_event("plan",
                               status=PlanStatus.UPDATING.value,
                               plan=safe_plan_dict(self.plan))
                    self.update_plan(self.plan, step)

            # Phase 3: Summarize
            self.plan.status = ExecutionStatus.COMPLETED
            emit_event("plan", status=PlanStatus.COMPLETED.value,
                       plan=safe_plan_dict(self.plan))
            self.summarize(self.plan, user_message)

            self.state = FlowState.COMPLETED
            emit_event("done", success=True)

        except Exception as e:
            self.state = FlowState.FAILED
            emit_event("error",
                       error="Agent error: {}".format(e))
            traceback.print_exc(file=sys.stderr)
            emit_event("done", success=False)


def main() -> None:
    """Entry point - reads task from stdin, runs agent, streams events."""
    try:
        raw_input = sys.stdin.read()
        input_data = json.loads(raw_input)

        user_message = input_data.get("message", "")
        model = input_data.get("model", DEFAULT_MODEL)
        messages = input_data.get("messages", [])
        attachments = input_data.get("attachments", [])

        if messages and not user_message:
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    user_message = msg.get("content", "")
                    break

        if not user_message:
            emit_event("error", error="No user message provided")
            emit_event("done", success=False)
            return

        agent = DzeckAgent(model=model)
        agent.run(user_message, attachments)

    except Exception as e:
        emit_event("error",
                   error="Fatal error: {}".format(e))
        traceback.print_exc(file=sys.stderr)
        emit_event("done", success=False)


if __name__ == "__main__":
    main()
