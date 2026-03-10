#!/usr/bin/env python3
"""
Dzeck AI Agent - Plan-Act Flow Engine
Ported from ai-manus PlanActFlow architecture.

Uses Cloudflare Workers AI (via AI Gateway) for all LLM calls.
Supports native tool calling with real execution — no simulation.
"""
import os
import re
import sys
import json
import time
import traceback
import urllib.request
import urllib.error
from enum import Enum
from typing import Optional, Dict, Any, List


def _load_dotenv() -> None:
    """Load .env file into os.environ (for local/APK builds)."""
    env_path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


_load_dotenv()

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
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    UPDATING = "updating"
    SUMMARIZING = "summarizing"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"


# Tool registry
TOOLS: Dict[str, Any] = {
    "message_notify_user": message_notify_user,
    "message_ask_user": message_ask_user,
    "shell_exec": shell_exec,
    "shell_view": shell_view,
    "shell_wait": shell_wait,
    "shell_write_to_process": shell_write_to_process,
    "shell_kill_process": shell_kill_process,
    "file_read": file_read,
    "file_write": file_write,
    "file_str_replace": file_str_replace,
    "file_find_by_name": file_find_by_name,
    "file_find_in_content": file_find_in_content,
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
    "web_search": web_search,
    "web_browse": web_browse,
    "mcp_call_tool": mcp_call_tool,
    "mcp_list_tools": mcp_list_tools,
}

TOOL_ALIASES: Dict[str, str] = {
    "message_notify": "message_notify_user",
    "message_ask": "message_ask_user",
    "file_find": "file_find_by_name",
    "browser_open": "browser_navigate",
    "browse": "web_browse",
    "search": "web_search",
}

TOOLKIT_MAP: Dict[str, str] = {
    "shell_exec": "shell", "shell_view": "shell", "shell_wait": "shell",
    "shell_write_to_process": "shell", "shell_kill_process": "shell",
    "file_read": "file", "file_write": "file", "file_str_replace": "file",
    "file_find_by_name": "file", "file_find_in_content": "file",
    "browser_navigate": "browser", "browser_view": "browser",
    "browser_click": "browser", "browser_type": "browser",
    "browser_scroll": "browser", "browser_scroll_to_bottom": "browser",
    "browser_read_links": "browser", "browser_console_view": "browser",
    "browser_restart": "browser", "browser_save_image": "browser",
    "web_search": "search", "web_browse": "browser",
    "message_notify_user": "message", "message_ask_user": "message",
    "mcp_call_tool": "mcp", "mcp_list_tools": "mcp",
}


def _get_cf_url() -> str:
    """Build Cloudflare AI Gateway URL from env vars."""
    account_id = os.environ.get("CF_ACCOUNT_ID", "")
    gateway_name = os.environ.get("CF_GATEWAY_NAME", "")
    model = os.environ.get("CF_MODEL", "@cf/meta/llama-3-8b-instruct")
    return (
        "https://gateway.ai.cloudflare.com/v1/"
        "{}/{}/workers-ai/run/{}".format(account_id, gateway_name, model)
    )


CF_API_KEY = os.environ.get("CF_API_KEY", "")

if not CF_API_KEY:
    sys.stderr.write("[agent] WARNING: CF_API_KEY is not set!\n")
    sys.stderr.flush()


# -- Cloudflare Workers AI Tool Schemas --
# Format: {name, description, parameters} — no OpenAI "type: function" wrapper
TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "name": "task_complete",
        "description": "Signal that the current task step is complete.",
        "parameters": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean", "description": "Whether the step succeeded"},
                "result": {"type": "string", "description": "Summary of what was accomplished"},
            },
            "required": ["success", "result"],
        },
    },
    {
        "name": "message_notify_user",
        "description": "Send a progress update or result to the user (non-blocking).",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Message text"},
                "attachments": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["text"],
        },
    },
    {
        "name": "message_ask_user",
        "description": "Ask the user a question and wait for response (blocking).",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Question to ask"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "shell_exec",
        "description": "Execute a shell command. Use -y/-f flags to avoid prompts.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"},
                "exec_dir": {"type": "string", "description": "Working directory"},
                "id": {"type": "string", "description": "Shell session ID"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "shell_view",
        "description": "View current output of a running shell session.",
        "parameters": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
    {
        "name": "shell_wait",
        "description": "Wait for a running process to complete.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "seconds": {"type": "integer"},
            },
            "required": ["id"],
        },
    },
    {
        "name": "shell_write_to_process",
        "description": "Write input to a running process.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "input": {"type": "string"},
                "press_enter": {"type": "boolean"},
            },
            "required": ["id", "input", "press_enter"],
        },
    },
    {
        "name": "shell_kill_process",
        "description": "Kill a running process.",
        "parameters": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
    {
        "name": "file_read",
        "description": "Read content from a text file.",
        "parameters": {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            },
            "required": ["file"],
        },
    },
    {
        "name": "file_write",
        "description": "Write content to a file (creates or overwrites).",
        "parameters": {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "content": {"type": "string"},
                "append": {"type": "boolean"},
            },
            "required": ["file", "content"],
        },
    },
    {
        "name": "file_str_replace",
        "description": "Replace a specific string in a file (exact match).",
        "parameters": {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "old_str": {"type": "string"},
                "new_str": {"type": "string"},
            },
            "required": ["file", "old_str", "new_str"],
        },
    },
    {
        "name": "file_find_by_name",
        "description": "Find files by name/glob pattern in a directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "glob": {"type": "string"},
            },
            "required": ["path", "glob"],
        },
    },
    {
        "name": "file_find_in_content",
        "description": "Search for regex patterns inside a file's content.",
        "parameters": {
            "type": "object",
            "properties": {
                "file": {"type": "string"},
                "regex": {"type": "string"},
            },
            "required": ["file", "regex"],
        },
    },
    {
        "name": "browser_navigate",
        "description": "Navigate browser to a URL and load the page.",
        "parameters": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "browser_view",
        "description": "Get the current page content as text.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "browser_click",
        "description": "Click at (x, y) coordinates on the current page.",
        "parameters": {
            "type": "object",
            "properties": {
                "coordinate_x": {"type": "integer"},
                "coordinate_y": {"type": "integer"},
                "button": {"type": "string"},
            },
            "required": ["coordinate_x", "coordinate_y"],
        },
    },
    {
        "name": "browser_type",
        "description": "Type text into the currently focused element.",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "browser_scroll",
        "description": "Scroll the page in a direction.",
        "parameters": {
            "type": "object",
            "properties": {
                "coordinate_x": {"type": "integer"},
                "coordinate_y": {"type": "integer"},
                "direction": {"type": "string"},
                "amount": {"type": "integer"},
            },
            "required": ["coordinate_x", "coordinate_y", "direction", "amount"],
        },
    },
    {
        "name": "browser_scroll_to_bottom",
        "description": "Scroll the page to the bottom.",
        "parameters": {
            "type": "object",
            "properties": {
                "coordinate_x": {"type": "integer"},
                "coordinate_y": {"type": "integer"},
            },
        },
    },
    {
        "name": "browser_read_links",
        "description": "Get all hyperlinks from the current page.",
        "parameters": {
            "type": "object",
            "properties": {"max_links": {"type": "integer"}},
        },
    },
    {
        "name": "browser_console_view",
        "description": "View browser console logs from the current page.",
        "parameters": {
            "type": "object",
            "properties": {"max_lines": {"type": "integer"}},
        },
    },
    {
        "name": "browser_restart",
        "description": "Restart the browser session.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "browser_save_image",
        "description": "Save an image from the current page by coordinates.",
        "parameters": {
            "type": "object",
            "properties": {
                "coordinate_x": {"type": "integer"},
                "coordinate_y": {"type": "integer"},
                "save_dir": {"type": "string"},
                "base_name": {"type": "string"},
            },
            "required": ["coordinate_x", "coordinate_y", "save_dir", "base_name"],
        },
    },
    {
        "name": "web_search",
        "description": "Search the web using DuckDuckGo and return results.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "num_results": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "web_browse",
        "description": "Fetch and extract readable text from a URL.",
        "parameters": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "mcp_call_tool",
        "description": "Call an external MCP tool by name.",
        "parameters": {
            "type": "object",
            "properties": {
                "tool_name": {"type": "string"},
                "arguments": {"type": "object"},
            },
            "required": ["tool_name"],
        },
    },
    {
        "name": "mcp_list_tools",
        "description": "List all available MCP tools.",
        "parameters": {"type": "object", "properties": {}},
    },
]


def emit_event(event_type: str, **data: Any) -> None:
    """Emit a JSON event line to stdout for SSE streaming."""
    event: Dict[str, Any] = {"type": event_type, **data}
    sys.stdout.write(json.dumps(event, default=str) + "\n")
    sys.stdout.flush()


def emit_streaming_message(text: str, role: str = "assistant") -> None:
    """Emit a message word-by-word for smooth streaming effect."""
    if not text or not text.strip():
        return
    emit_event("message_start", role=role)
    # Stream character-by-character for more natural feel
    buf = ""
    for ch in text:
        buf += ch
        # Emit on word boundaries or punctuation for smoother streaming
        if ch in (" ", "\n", ".", ",", "!", "?", ":", ";"):
            if buf:
                emit_event("message_chunk", chunk=buf, role=role)
                buf = ""
                time.sleep(0.008)
    if buf:
        emit_event("message_chunk", chunk=buf, role=role)
    emit_event("message_end", role=role)


def call_cf_streaming(messages: list) -> None:
    """Call Cloudflare Workers AI with stream=True and emit chunks in real-time.

    Emits message_start, message_chunk, message_end events as SSE.
    """
    url = _get_cf_url()
    body: Dict[str, Any] = {
        "messages": messages,
        "max_tokens": 4096,
        "stream": True,
    }

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(CF_API_KEY),
            "User-Agent": "DzeckAI/1.0",
        },
        method="POST",
    )

    emit_event("message_start", role="assistant")
    full_text = ""

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            buf = ""
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace")
                buf += line
                while "\n" in buf:
                    chunk_line, buf = buf.split("\n", 1)
                    chunk_line = chunk_line.strip()
                    if not chunk_line or not chunk_line.startswith("data: "):
                        continue
                    payload = chunk_line[6:]
                    if payload == "[DONE]":
                        break
                    try:
                        parsed = json.loads(payload)
                        content = (
                            parsed.get("response")
                            or (parsed.get("choices", [{}])[0]
                                .get("delta", {})
                                .get("content"))
                            or ""
                        )
                        if content:
                            emit_event("message_chunk", chunk=content, role="assistant")
                            full_text += content
                    except (json.JSONDecodeError, IndexError, KeyError):
                        pass
    except Exception as e:
        if not full_text:
            emit_event("message_chunk",
                       chunk="I'm sorry, I encountered an error.",
                       role="assistant")
        sys.stderr.write("Streaming error: {}\n".format(e))
        sys.stderr.flush()

    emit_event("message_end", role="assistant")
    return full_text


def call_cf_streaming_with_retry(
    messages: list,
    max_retries: int = 3,
) -> str:
    """Call CF streaming API with retry on failure."""
    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            result = call_cf_streaming(messages)
            if result:
                return result
            # Empty result, retry
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return result or ""
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    if last_error is not None:
        sys.stderr.write("Streaming retry failed: {}\n".format(last_error))
        sys.stderr.flush()
    return ""


def call_cf_api(
    messages: list,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Call Cloudflare Workers AI. Returns full response dict.

    Response format:
      {"result": {"response": "...", "tool_calls": [...] or null}, "success": true}
    """
    url = _get_cf_url()
    body: Dict[str, Any] = {
        "messages": messages,
        "max_tokens": 4096,
        "stream": False,
    }
    if tools:
        body["tools"] = tools

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(CF_API_KEY),
            "User-Agent": "DzeckAI/1.0",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read().decode("utf-8")

    result = json.loads(raw)

    # Raise on Cloudflare-level errors (wrapped gateway format only)
    if "success" in result and not result["success"]:
        errors = result.get("errors", [])
        raise urllib.error.HTTPError(
            url, 500, "CF API error: {}".format(errors), {}, None)

    return result


def call_cf_text(messages: list) -> str:
    """Convenience wrapper: returns only the text response string.

    Handles both response formats:
    - Direct Workers AI: {"response": "...", "usage": {...}}
    - Wrapped Gateway:   {"result": {"response": "..."}, "success": true}
    """
    result = call_cf_api(messages)
    # Use "result" sub-dict if present, else use top-level directly
    cf_result = result.get("result", result)
    text = cf_result.get("response") or ""
    # Fallback: OpenAI-compatible format
    if not text:
        choices = result.get("choices", [])
        if choices:
            text = choices[0].get("message", {}).get("content", "") or ""
    return text


def call_text_with_retry(
    messages: list,
    max_retries: int = 5,
) -> str:
    """Call CF text API with exponential backoff retry."""
    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return call_cf_text(messages)
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code == 429 or e.code >= 500:
                wait = 2 ** attempt
                time.sleep(wait)
            else:
                raise
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError("LLM call failed after {} retries".format(max_retries))


def call_api_with_retry(
    messages: list,
    tools: Optional[List[Dict[str, Any]]] = None,
    max_retries: int = 5,
) -> Dict[str, Any]:
    """Call CF API (full response) with exponential backoff retry."""
    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return call_cf_api(messages, tools=tools)
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code == 429 or e.code >= 500:
                wait = 2 ** attempt
                time.sleep(wait)
            else:
                raise
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError("LLM call failed after {} retries".format(max_retries))


def resolve_tool_name(name: str) -> Optional[str]:
    if name in TOOLS:
        return name
    if name in TOOL_ALIASES:
        return TOOL_ALIASES[name]
    return None


def get_toolkit_name(function_name: str) -> str:
    return TOOLKIT_MAP.get(function_name, "unknown")


def execute_tool(tool_name: str, tool_args: Dict[str, Any]) -> ToolResult:
    """Execute a tool and return ToolResult."""
    resolved = resolve_tool_name(tool_name)
    if resolved is None:
        return ToolResult(
            success=False,
            message="Unknown tool '{}'. Available: {}".format(
                tool_name, ", ".join(TOOLS.keys())),
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
    """Build tool-specific content dict for frontend display."""
    data = tool_result.data or {}

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

    elif tool_name == "web_search":
        return {
            "type": "search",
            "query": data.get("query", ""),
            "results": data.get("results", []),
        }

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

    elif tool_name in ("file_read", "file_write", "file_str_replace",
                       "file_find_by_name", "file_find_in_content"):
        return {
            "type": "file",
            "file": data.get("file", data.get("path", "")),
            "content": str(data.get("content", ""))[:2000],
            "operation": tool_name.replace("file_", ""),
        }

    elif tool_name in ("mcp_call_tool", "mcp_list_tools"):
        return {
            "type": "mcp",
            "tool": data.get("tool_name", ""),
            "result": str(data)[:2000],
        }

    return None


def safe_plan_dict(plan: Plan) -> Dict[str, Any]:
    d = plan.to_dict()
    d.pop("goal", None)
    return d


def _extract_cf_response(api_result: Dict[str, Any]) -> tuple:
    """Extract (text, tool_calls) from a Cloudflare Workers AI response.

    Handles both formats:
    - Direct Workers AI: {"response": "...", "tool_calls": [...], "usage": {...}}
    - Wrapped Gateway:   {"result": {"response": "...", "tool_calls": [...]}, "success": true}

    Returns:
        (text: str, tool_calls: list[dict] | None)
        tool_calls items: {"name": "...", "arguments": {...}}
    """
    # Use "result" sub-dict if present, else use top-level directly
    cf_result = api_result.get("result", api_result)
    text = cf_result.get("response") or ""
    tool_calls = cf_result.get("tool_calls")  # list or None

    # Fallback: OpenAI-compatible format
    if not text and not tool_calls:
        choices = api_result.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            text = msg.get("content", "") or ""
            oa_calls = msg.get("tool_calls")
            if oa_calls:
                # Convert OpenAI format → Cloudflare format
                tool_calls = []
                for tc in oa_calls:
                    fn = tc.get("function", {})
                    try:
                        args = json.loads(fn.get("arguments", "{}"))
                    except Exception:
                        args = {}
                    tool_calls.append({
                        "name": fn.get("name", ""),
                        "arguments": args,
                    })

    return text, tool_calls


class DzeckAgent:
    """
    Main agent class implementing the Plan-Act flow.
    Uses Cloudflare Workers AI with native tool calling.
    """

    def __init__(self) -> None:
        self.memory = Memory()
        self.max_tool_iterations = 20
        self.plan: Optional[Plan] = None
        self.state = FlowState.IDLE
        self.parser = RobustJsonParser()

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """Parse LLM response using robust 5-stage JSON parser."""
        result, error = self.parser.parse(text)
        if result is not None:
            return result
        return {}

    def _detect_language(self, text: str) -> str:
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
        if any("\u3040" <= c <= "\u309f" or "\u30a0" <= c <= "\u30ff" for c in text):
            return "ja"
        if any("\uac00" <= c <= "\ud7af" for c in text):
            return "ko"
        return "en"

    def run_planner(self, user_message: str,
                    attachments: Optional[List[str]] = None) -> Plan:
        """Create a plan from the user's message."""
        self.state = FlowState.PLANNING

        language = self._detect_language(user_message)

        attachments_info = ""
        if attachments:
            attachments_info = "Attachments: {}".format(", ".join(attachments))

        prompt = CREATE_PLAN_PROMPT.format(
            message=user_message,
            language=language,
            attachments_info=attachments_info,
        )

        # Instruct model to respond with JSON (CF doesn't support response_format)
        json_instruction = (
            "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown, no explanation."
        )

        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT + json_instruction},
            {"role": "user", "content": prompt},
        ]

        response_text = call_text_with_retry(messages)
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
        """Execute a single tool call and return the result string.

        Returns "STEP_DONE" for task_complete. Otherwise returns result text.
        """
        if fn_name == "task_complete":
            step.status = ExecutionStatus.COMPLETED
            step.success = fn_args.get("success", True)
            step.result = fn_args.get("result", "Step completed")
            if not step.success:
                step.status = ExecutionStatus.FAILED
            status_enum = (StepStatus.COMPLETED if step.success
                           else StepStatus.FAILED)
            emit_event("step", status=status_enum.value, step=step.to_dict())
            return "STEP_DONE"

        resolved = resolve_tool_name(fn_name)
        if resolved is None:
            return "Unknown tool '{}'. Available: {}".format(
                fn_name, ", ".join(TOOLS.keys()))

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

        result_summary = tool_result.message or "No result"
        if len(result_summary) > 4000:
            result_summary = result_summary[:4000] + "...[truncated]"
        return result_summary

    def execute_step(self, plan: Plan, step: Step, user_message: str) -> None:
        """Execute a single step using Cloudflare Workers AI tool calling.

        Agentic loop: call LLM → if tool_calls → execute → add result → loop.
        Real tool execution, no simulation.
        """
        self.state = FlowState.EXECUTING
        step.status = ExecutionStatus.RUNNING
        emit_event("step", status=StepStatus.RUNNING.value, step=step.to_dict())

        context_parts: List[str] = []
        for s in plan.steps:
            if s.is_done() and s.result:
                context_parts.append("- {}: {}".format(s.description, s.result))
        context = ("\n".join(context_parts) if context_parts else "No previous context.")

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

        for iteration in range(self.max_tool_iterations):
            try:
                api_result = call_api_with_retry(
                    exec_messages, tools=TOOL_SCHEMAS)

                text, tool_calls = _extract_cf_response(api_result)

                # -- Native tool calling path --
                if tool_calls:
                    step_done = False
                    for tc in tool_calls:
                        fn_name = tc.get("name", "")
                        fn_args = tc.get("arguments", {})
                        if isinstance(fn_args, str):
                            try:
                                fn_args = json.loads(fn_args)
                            except Exception:
                                fn_args = {}

                        tc_id = "tc_{}_{}".format(step.id, iteration)

                        # Add assistant turn (shows which tool was called)
                        exec_messages.append({
                            "role": "assistant",
                            "content": "[Calling tool: {}]".format(fn_name),
                        })

                        result_str = self._handle_tool_call(
                            fn_name, fn_args, tc_id, step, iteration)

                        if result_str == "STEP_DONE":
                            step_done = True
                            break

                        # Add tool result back for next iteration
                        exec_messages.append({
                            "role": "user",
                            "content": (
                                "Tool '{}' result:\n{}\n\n"
                                "Continue executing the step. "
                                "Call task_complete when done."
                            ).format(fn_name, result_str or "Done"),
                        })

                    if step_done:
                        return

                    if iteration > 0 and iteration % 5 == 0:
                        self.memory.compact()
                    continue

                # -- Plain text response (no tool calls) --
                if text:
                    parsed = self._parse_response(text)

                    if parsed.get("done"):
                        step.status = ExecutionStatus.COMPLETED
                        step.success = parsed.get("success", True)
                        step.result = parsed.get("result", "Step completed")
                        step.attachments = parsed.get("attachments", [])
                        if not step.success:
                            step.status = ExecutionStatus.FAILED
                        status_enum = (StepStatus.COMPLETED if step.success
                                       else StepStatus.FAILED)
                        emit_event("step", status=status_enum.value,
                                   step=step.to_dict())
                        return

                    if parsed.get("thinking"):
                        exec_messages.append(
                            {"role": "assistant", "content": text})
                        exec_messages.append(
                            {"role": "user",
                             "content": "Good. Now execute using a tool."})
                        continue

                    if parsed.get("tool"):
                        tool_name = parsed["tool"]
                        tool_args = parsed.get("args", {})
                        resolved_name = resolve_tool_name(tool_name)

                        if resolved_name is None:
                            exec_messages.append(
                                {"role": "assistant", "content": text})
                            exec_messages.append(
                                {"role": "user",
                                 "content": "Unknown tool '{}'. Available: {}. Try again.".format(
                                     tool_name, ", ".join(TOOLS.keys()))})
                            continue

                        tc_id = "tc_{}_{}".format(step.id, iteration)
                        result_str = self._handle_tool_call(
                            resolved_name, tool_args, tc_id, step, iteration)

                        if result_str == "STEP_DONE":
                            return

                        exec_messages.append(
                            {"role": "assistant", "content": text})
                        exec_messages.append(
                            {"role": "user",
                             "content": (
                                 "Tool result:\n{}\n\n"
                                 "Continue executing. Use another tool or "
                                 "call task_complete when finished."
                             ).format(result_str)})

                        if iteration > 0 and iteration % 5 == 0:
                            self.memory.compact()
                        continue

                # No tool call, no actionable JSON → step complete
                step.status = ExecutionStatus.COMPLETED
                step.success = True
                step.result = text[:500] if text else "Step completed"
                emit_event("step", status=StepStatus.COMPLETED.value,
                           step=step.to_dict())
                return

            except Exception as e:
                emit_event("error", error="Step execution error: {}".format(e))
                step.status = ExecutionStatus.FAILED
                step.error = str(e)
                emit_event("step", status=StepStatus.FAILED.value,
                           step=step.to_dict())
                return

        # Max iterations reached
        step.status = ExecutionStatus.FAILED
        step.success = False
        step.result = "Step incomplete (max iterations reached)"
        emit_event("step", status=StepStatus.FAILED.value, step=step.to_dict())

    def update_plan(self, plan: Plan, completed_step: Step) -> None:
        """Update the plan based on completed step result."""
        self.state = FlowState.UPDATING

        completed_steps_info = []
        for s in plan.steps:
            if s.is_done():
                status = "Success" if s.success else "Failed"
                completed_steps_info.append(
                    "Step {} ({}): {} - {}".format(
                        s.id, s.description, status, s.result or "No result"))

        current_step_info = "Step {}: {}".format(
            completed_step.id, completed_step.description)
        step_result_info = completed_step.result or "No result"

        remaining = [s for s in plan.steps if not s.is_done()]
        plan_info = json.dumps(
            {
                "language": plan.language,
                "completed_steps": [s.to_dict() for s in plan.steps if s.is_done()],
                "remaining_steps": [s.to_dict() for s in remaining],
            },
            default=str,
        )

        json_instruction = (
            "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown, no explanation."
        )

        prompt = UPDATE_PLAN_PROMPT.format(
            current_plan=plan_info,
            completed_steps="\n".join(completed_steps_info),
            current_step=current_step_info,
            step_result=step_result_info,
        )

        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT + json_instruction},
            {"role": "user", "content": prompt},
        ]

        try:
            response_text = call_text_with_retry(messages)
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
            emit_event("error", error="Plan update skipped: {}".format(e))

    def summarize(self, plan: Plan, user_message: str) -> None:
        """Generate a final summary of the completed task.

        Uses real streaming for smooth output.
        """
        self.state = FlowState.SUMMARIZING

        step_results = []
        for s in plan.steps:
            status = "Success" if s.success else "Failed"
            step_results.append("- Step {} ({}): {} - {}".format(
                s.id, s.description, status, s.result or "No result"))

        prompt = SUMMARIZE_PROMPT.format(
            step_results="\n".join(step_results),
            message=user_message,
        )

        # Use a system prompt that enforces plain text
        summarize_system = (
            SYSTEM_PROMPT + "\n\nIMPORTANT: Respond with plain text only. "
            "Do NOT output JSON. Give a clear, helpful summary of the results."
        )

        messages = [
            {"role": "system", "content": summarize_system},
            {"role": "user", "content": prompt},
        ]

        try:
            result = call_cf_streaming_with_retry(messages)
            if not result:
                emit_streaming_message("Task completed.")
        except Exception as e:
            emit_streaming_message("Task completed.")

    def _is_simple_query(self, user_message: str) -> bool:
        """Detect if the user message is a simple query that doesn't need tools."""
        msg = user_message.strip().lower()
        word_count = len(msg.split())

        if word_count <= 4:
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

        math_patterns = [
            r"^berapa\s+[\d\s\+\-\*\/\(\)\.]+\??$",
            r"^hitung\s+[\d\s\+\-\*\/\(\)\.]+\??$",
            r"^calculate\s+[\d\s\+\-\*\/\(\)\.]+\??$",
            r"^what is\s+[\d\s\+\-\*\/\(\)\.]+\??$",
            r"^\d[\d\s\+\-\*\/\(\)\.]+\=?\??$",
        ]
        for pattern in math_patterns:
            if re.search(pattern, msg):
                return True

        knowledge_starters = [
            "what is", "what are", "who is", "who are",
            "when was", "when is", "where is", "where are",
            "why is", "why are", "how does", "how do",
            "explain", "define", "describe",
            "apa itu", "siapa", "kapan", "dimana", "mengapa",
            "jelaskan", "ceritakan", "bagaimana cara",
        ]
        action_patterns = [
            r"\bhttp", r"[/\\]", r"```",
            r"\bfile\b", r"\binstall\b", r"\brun\b",
            r"\bcreate\b", r"\bbuild\b", r"\bwrite\b",
            r"\bbuat\b", r"\btulis\b", r"\bjalankan\b",
        ]
        for starter in knowledge_starters:
            if msg.startswith(starter):
                if not any(re.search(p, msg) for p in action_patterns):
                    return True

        return False

    def _respond_directly(self, user_message: str) -> None:
        """Respond directly without Plan-Act flow for simple queries.

        Uses real streaming from Cloudflare API for smooth character-by-character output.
        """
        messages = [
            {"role": "system", "content": (
                "You are Dzeck, an AI assistant created by the Dzeck team. "
                "Respond naturally and helpfully. Be concise but informative. "
                "Respond in the same language as the user's message. "
                "Do NOT output JSON — respond with plain text only."
            )},
            {"role": "user", "content": user_message},
        ]

        try:
            result = call_cf_streaming_with_retry(messages)
            if not result:
                emit_streaming_message("I'm sorry, I couldn't generate a response.")
        except Exception as e:
            emit_event("error", error="Response error: {}".format(e))

    def run(self, user_message: str,
            attachments: Optional[List[str]] = None) -> None:
        """Main agent flow: Smart routing → Plan → Execute → Summarize.

        Follows ai-manus pattern:
        1. Detect simple queries → respond directly with streaming
        2. Complex tasks → Plan with streaming intro → Execute with tool cards → Summarize
        """
        try:
            if not attachments and self._is_simple_query(user_message):
                self._respond_directly(user_message)
                emit_event("done", success=True)
                return

            # Phase 1: Planning
            self.state = FlowState.PLANNING
            emit_event("plan", status=PlanStatus.CREATING.value)

            self.plan = self.run_planner(user_message, attachments)

            emit_event("title", title=self.plan.title)

            # Stream the plan intro message for smooth UX (like ai-manus)
            if self.plan.message:
                emit_streaming_message(self.plan.message)

            emit_event("plan", status=PlanStatus.CREATED.value,
                       plan=safe_plan_dict(self.plan))

            if not self.plan.steps:
                emit_streaming_message("No actionable steps needed.")
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
                    emit_event("plan", status=PlanStatus.UPDATING.value,
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
            emit_event("error", error="Agent error: {}".format(e))
            traceback.print_exc(file=sys.stderr)
            emit_event("done", success=False)


def main() -> None:
    """Entry point — reads task from stdin, runs agent, streams events."""
    try:
        raw_input = sys.stdin.read()
        input_data = json.loads(raw_input)

        user_message = input_data.get("message", "")
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

        agent = DzeckAgent()
        agent.run(user_message, attachments)

    except Exception as e:
        emit_event("error", error="Fatal error: {}".format(e))
        traceback.print_exc(file=sys.stderr)
        emit_event("done", success=False)


if __name__ == "__main__":
    main()
