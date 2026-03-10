#!/usr/bin/env python3
"""
Dzeck AI Agent - Async Plan-Act Flow Engine
Upgraded from ai-manus architecture:

- Language:         Python async (AsyncGenerator)
- LLM:             Cloudflare Workers AI (via AI Gateway) with native tool calling
- Framework:       Pydantic BaseModel + async generator streaming
- Database:        MongoDB (motor async) for session/agent persistence
- Cache:           Redis (aioredis) for session state caching
- Browser:         Playwright real browser + HTTP fallback
- Architecture:    DDD: Domain / Application / Infrastructure layers
- Session mgmt:    Full session resume / rollback support
- Model:           llama-3-8b-instruct with native tool calling
"""
import os
import re
import sys
import json
import time
import asyncio
import traceback
import urllib.request
import urllib.error
from enum import Enum
from typing import AsyncGenerator, Optional, Dict, Any, List


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

# Force unbuffered stdout for real-time streaming to Node.js subprocess
sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]

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

from server.agent.models.plan import Plan, Step, ExecutionStatus
from server.agent.models.event import PlanStatus, StepStatus, ToolStatus
from server.agent.models.memory import Memory
from server.agent.models.tool_result import ToolResult

from server.agent.utils.robust_json_parser import RobustJsonParser

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
    account_id = os.environ.get("CF_ACCOUNT_ID", "")
    gateway_name = os.environ.get("CF_GATEWAY_NAME", "")
    model = (
        os.environ.get("CF_AGENT_MODEL")
        or os.environ.get("CF_MODEL")
        or "@cf/meta/llama-3.1-70b-instruct"
    )
    return (
        "https://gateway.ai.cloudflare.com/v1/"
        "{}/{}/workers-ai/run/{}".format(account_id, gateway_name, model)
    )


CF_API_KEY = os.environ.get("CF_API_KEY", "")

if not CF_API_KEY:
    sys.stderr.write("[agent] WARNING: CF_API_KEY is not set!\n")
    sys.stderr.flush()


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
        "description": "Save an image/screenshot from the current page.",
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


def make_event(event_type: str, **data: Any) -> Dict[str, Any]:
    """Create an event dict for streaming."""
    return {"type": event_type, **data}


def call_cf_streaming(messages: list) -> str:
    """Synchronous Cloudflare streaming call. Returns full text."""
    url = _get_cf_url()
    body: Dict[str, Any] = {"messages": messages, "max_tokens": 4096, "stream": True}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(CF_API_KEY),
            "User-Agent": "DzeckAI/2.0",
        },
        method="POST",
    )
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
                            or (parsed.get("choices", [{}])[0].get("delta", {}).get("content"))
                            or ""
                        )
                        if content:
                            full_text += content
                    except (json.JSONDecodeError, IndexError, KeyError):
                        pass
    except Exception as e:
        sys.stderr.write("CF streaming error: {}\n".format(e))
        sys.stderr.flush()
    return full_text


def call_cf_api(
    messages: list,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Synchronous Cloudflare API call. Returns full response dict."""
    url = _get_cf_url()
    body: Dict[str, Any] = {"messages": messages, "max_tokens": 4096, "stream": False}
    if tools:
        body["tools"] = tools
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(CF_API_KEY),
            "User-Agent": "DzeckAI/2.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read().decode("utf-8")
    result = json.loads(raw)
    if "success" in result and not result["success"]:
        errors = result.get("errors", [])
        raise urllib.error.HTTPError(url, 500, "CF API error: {}".format(errors), {}, None)
    return result


def call_cf_text(messages: list) -> str:
    result = call_cf_api(messages)
    cf_result = result.get("result", result)
    text = cf_result.get("response") or ""
    if not text:
        choices = result.get("choices", [])
        if choices:
            text = choices[0].get("message", {}).get("content", "") or ""
    return text


def call_text_with_retry(messages: list, max_retries: int = 5) -> str:
    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return call_cf_text(messages)
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code == 429 or e.code >= 500:
                time.sleep(2 ** attempt)
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
    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return call_cf_api(messages, tools=tools)
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code == 429 or e.code >= 500:
                time.sleep(2 ** attempt)
            else:
                raise
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError("LLM call failed")


def _extract_cf_response(api_result: Dict[str, Any]) -> tuple:
    """Extract (text, tool_calls) from Cloudflare response."""
    cf_result = api_result.get("result", api_result)
    text = cf_result.get("response") or ""
    tool_calls = cf_result.get("tool_calls")

    if not text and not tool_calls:
        choices = api_result.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            text = msg.get("content", "") or ""
            oa_calls = msg.get("tool_calls")
            if oa_calls:
                tool_calls = []
                for tc in oa_calls:
                    fn = tc.get("function", {})
                    try:
                        args = json.loads(fn.get("arguments", "{}"))
                    except Exception:
                        args = {}
                    tool_calls.append({"name": fn.get("name", ""), "arguments": args})

    return text, tool_calls


def resolve_tool_name(name: str) -> Optional[str]:
    if name in TOOLS:
        return name
    if name in TOOL_ALIASES:
        return TOOL_ALIASES[name]
    return None


def get_toolkit_name(function_name: str) -> str:
    return TOOLKIT_MAP.get(function_name, "unknown")


def execute_tool(tool_name: str, tool_args: Dict[str, Any]) -> ToolResult:
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
        return ToolResult(success=False, message="Invalid args for '{}': {}".format(tool_name, e))
    except Exception as e:
        return ToolResult(success=False, message="Tool '{}' failed: {}".format(tool_name, e))


def build_tool_content(tool_name: str, tool_result: ToolResult) -> Optional[Dict[str, Any]]:
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
        return {"type": "search", "query": data.get("query", ""), "results": data.get("results", [])}
    elif tool_name in ("web_browse", "browser_navigate", "browser_view",
                       "browser_click", "browser_type", "browser_scroll",
                       "browser_scroll_to_bottom", "browser_read_links",
                       "browser_console_view", "browser_save_image", "browser_restart"):
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
        return {"type": "mcp", "tool": data.get("tool_name", ""), "result": str(data)[:2000]}

    return None


def safe_plan_dict(plan: Plan) -> Dict[str, Any]:
    d = plan.to_dict()
    d.pop("goal", None)
    return d


class DzeckAgent:
    """
    Async AI Agent implementing Plan-Act flow.
    
    Upgraded from synchronous to AsyncGenerator-based streaming.
    Supports:
    - Full session persistence (MongoDB)
    - Redis state caching
    - Session resume / rollback
    - Real Playwright browser automation
    - DDD architecture (domain / application / infrastructure)
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        max_tool_iterations: int = 20,
    ) -> None:
        self.session_id = session_id
        self.memory = Memory()
        self.max_tool_iterations = max_tool_iterations
        self.plan: Optional[Plan] = None
        self.state = FlowState.IDLE
        self.parser = RobustJsonParser()
        self._session_service: Any = None

    async def _get_session_service(self) -> Any:
        """Lazy-load session service."""
        if self._session_service is None:
            try:
                from server.agent.services.session_service import get_session_service
                self._session_service = await get_session_service()
            except Exception as e:
                sys.stderr.write("[agent] Session service unavailable: {}\n".format(e))
                sys.stderr.flush()
        return self._session_service

    async def _persist_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Persist event to MongoDB (non-blocking, best-effort)."""
        if not self.session_id:
            return
        try:
            svc = await self._get_session_service()
            if svc:
                await svc._get_session_store().then(
                    lambda s: s.save_event(self.session_id, event_type, data)
                )
        except Exception:
            pass

    def _parse_response(self, text: str) -> Dict[str, Any]:
        result, _ = self.parser.parse(text)
        return result if result is not None else {}

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

    def _is_simple_query(self, user_message: str) -> bool:
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
                r"\bwho are you\b", r"\bsiapa kamu\b",
                r"\bhow are you\b", r"\bapa kabar\b",
            ]
            for pattern in simple_patterns:
                if re.search(pattern, msg):
                    return True

        knowledge_starters = [
            "what is", "what are", "who is", "who are",
            "when was", "when is", "where is",
            "explain", "define", "describe",
            "apa itu", "siapa", "kapan", "dimana",
            "jelaskan", "ceritakan",
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

    async def run_planner_async(
        self,
        user_message: str,
        attachments: Optional[List[str]] = None,
    ) -> Plan:
        """Create plan asynchronously (runs sync LLM call in thread pool)."""
        self.state = FlowState.PLANNING
        language = self._detect_language(user_message)
        attachments_info = "Attachments: {}".format(", ".join(attachments)) if attachments else ""
        prompt = CREATE_PLAN_PROMPT.format(
            message=user_message,
            language=language,
            attachments_info=attachments_info,
        )
        json_instruction = "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown, no explanation."
        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT + json_instruction},
            {"role": "user", "content": prompt},
        ]

        loop = asyncio.get_event_loop()
        response_text = await loop.run_in_executor(
            None, lambda: call_text_with_retry(messages)
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

        steps = [
            Step(id=str(s.get("id", "")), description=s.get("description", ""))
            for s in parsed.get("steps", [])
        ]
        if not steps:
            steps = [Step(id="1", description=user_message)]

        return Plan(
            title=parsed.get("title", "Task"),
            goal=parsed.get("goal", user_message[:100]),
            language=parsed.get("language", language),
            steps=steps,
            message=parsed.get("message", ""),
        )

    async def _handle_tool_call_async(
        self,
        fn_name: str,
        fn_args: Dict[str, Any],
        tool_call_id: str,
        step: Step,
        iteration: int,
    ) -> tuple:
        """Execute tool call and yield events. Returns (result_str, events_list)."""
        events = []

        if fn_name == "task_complete":
            step.status = ExecutionStatus.COMPLETED
            step.success = fn_args.get("success", True)
            step.result = fn_args.get("result", "Step completed")
            if not step.success:
                step.status = ExecutionStatus.FAILED
            status_enum = StepStatus.COMPLETED if step.success else StepStatus.FAILED
            events.append(make_event("step", status=status_enum.value, step=step.to_dict()))
            return "STEP_DONE", events

        resolved = resolve_tool_name(fn_name)
        if resolved is None:
            return "Unknown tool '{}'.".format(fn_name), events

        toolkit_name = get_toolkit_name(resolved)
        events.append(make_event(
            "tool",
            status=ToolStatus.CALLING.value,
            tool_name=toolkit_name,
            function_name=resolved,
            function_args=fn_args,
            tool_call_id=tool_call_id,
        ))

        loop = asyncio.get_event_loop()
        tool_result = await loop.run_in_executor(
            None, lambda: execute_tool(resolved, fn_args)
        )
        tool_content = build_tool_content(resolved, tool_result)
        result_status = ToolStatus.CALLED if tool_result.success else ToolStatus.ERROR
        fn_result = str(tool_result.message)[:3000] if tool_result.message else ""

        events.append(make_event(
            "tool",
            status=result_status.value,
            tool_name=toolkit_name,
            function_name=resolved,
            function_args=fn_args,
            tool_call_id=tool_call_id,
            function_result=fn_result,
            tool_content=tool_content,
        ))

        result_summary = tool_result.message or "No result"
        if len(result_summary) > 4000:
            result_summary = result_summary[:4000] + "...[truncated]"
        return result_summary, events

    async def execute_step_async(
        self,
        plan: Plan,
        step: Step,
        user_message: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute a step and yield SSE events as they happen (AsyncGenerator)."""
        self.state = FlowState.EXECUTING
        step.status = ExecutionStatus.RUNNING
        yield make_event("step", status=StepStatus.RUNNING.value, step=step.to_dict())

        context_parts: List[str] = []
        for s in plan.steps:
            if s.is_done() and s.result:
                context_parts.append("- {}: {}".format(s.description, s.result))
        context = "\n".join(context_parts) if context_parts else "No previous context."

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

        loop = asyncio.get_event_loop()

        for iteration in range(self.max_tool_iterations):
            try:
                api_result = await loop.run_in_executor(
                    None,
                    lambda: call_api_with_retry(exec_messages, tools=TOOL_SCHEMAS),
                )
                text, tool_calls = _extract_cf_response(api_result)

                if tool_calls:
                    step_done = False
                    for tc_idx, tc in enumerate(tool_calls):
                        fn_name = tc.get("name", "")
                        fn_args = tc.get("arguments", {})
                        if isinstance(fn_args, str):
                            try:
                                fn_args = json.loads(fn_args)
                            except Exception:
                                fn_args = {}

                        tc_id = "tc_{}_{}_{}".format(step.id, iteration, tc_idx)

                        result_str, tool_events = await self._handle_tool_call_async(
                            fn_name, fn_args, tc_id, step, iteration
                        )
                        for ev in tool_events:
                            yield ev

                        if result_str == "STEP_DONE":
                            step_done = True
                            break

                        exec_messages.append({
                            "role": "user",
                            "content": (
                                "Result of {}: {}\n\n"
                                "Continue. Call task_complete when step is fully done."
                            ).format(fn_name, result_str or "Done"),
                        })

                    if step_done:
                        return
                    if iteration > 0 and iteration % 5 == 0:
                        self.memory.compact()
                    continue

                if text:
                    parsed = self._parse_response(text)

                    if parsed.get("done"):
                        step.status = ExecutionStatus.COMPLETED
                        step.success = parsed.get("success", True)
                        step.result = parsed.get("result", "Step completed")
                        if not step.success:
                            step.status = ExecutionStatus.FAILED
                        status_enum = StepStatus.COMPLETED if step.success else StepStatus.FAILED
                        yield make_event("step", status=status_enum.value, step=step.to_dict())
                        return

                    if parsed.get("thinking"):
                        exec_messages.append({"role": "assistant", "content": text})
                        exec_messages.append({"role": "user", "content": "Good. Now execute using a tool."})
                        continue

                    if parsed.get("tool"):
                        tool_name = parsed["tool"]
                        tool_args = parsed.get("args", {})
                        resolved_name = resolve_tool_name(tool_name)

                        if resolved_name is None:
                            exec_messages.append({"role": "assistant", "content": text})
                            exec_messages.append({
                                "role": "user",
                                "content": "Unknown tool '{}'. Available: {}. Try again.".format(
                                    tool_name, ", ".join(TOOLS.keys()))
                            })
                            continue

                        tc_id = "tc_{}_{}_json".format(step.id, iteration)
                        result_str, tool_events = await self._handle_tool_call_async(
                            resolved_name, tool_args, tc_id, step, iteration
                        )
                        for ev in tool_events:
                            yield ev

                        if result_str == "STEP_DONE":
                            return

                        exec_messages.append({
                            "role": "user",
                            "content": "Result of {}: {}\n\nContinue. Use another tool or call task_complete.".format(resolved_name, result_str)
                        })
                        if iteration > 0 and iteration % 5 == 0:
                            self.memory.compact()
                        continue

                step.status = ExecutionStatus.COMPLETED
                step.success = True
                step.result = text[:500] if text else "Step completed"
                yield make_event("step", status=StepStatus.COMPLETED.value, step=step.to_dict())
                return

            except Exception as e:
                yield make_event("error", error="Step execution error: {}".format(e))
                step.status = ExecutionStatus.FAILED
                step.error = str(e)
                yield make_event("step", status=StepStatus.FAILED.value, step=step.to_dict())
                return

        step.status = ExecutionStatus.FAILED
        step.result = "Step incomplete (max iterations reached)"
        yield make_event("step", status=StepStatus.FAILED.value, step=step.to_dict())

    async def update_plan_async(
        self,
        plan: Plan,
        completed_step: Step,
    ) -> Optional[Dict[str, Any]]:
        """Update plan based on completed step. Returns plan event or None."""
        self.state = FlowState.UPDATING
        completed_steps_info = []
        for s in plan.steps:
            if s.is_done():
                status = "Success" if s.success else "Failed"
                completed_steps_info.append(
                    "Step {} ({}): {} - {}".format(s.id, s.description, status, s.result or ""))

        current_step_info = "Step {}: {}".format(completed_step.id, completed_step.description)
        step_result_info = completed_step.result or "No result"
        remaining = [s for s in plan.steps if not s.is_done()]
        plan_info = json.dumps({
            "language": plan.language,
            "completed_steps": [s.to_dict() for s in plan.steps if s.is_done()],
            "remaining_steps": [s.to_dict() for s in remaining],
        }, default=str)

        json_instruction = "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown, no explanation."
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

        loop = asyncio.get_event_loop()
        try:
            response_text = await loop.run_in_executor(
                None, lambda: call_text_with_retry(messages)
            )
            parsed = self._parse_response(response_text)
            if parsed and "steps" in parsed:
                new_steps = [
                    Step(id=str(s.get("id", "")), description=s.get("description", ""))
                    for s in parsed["steps"]
                ]
                first_pending = None
                for i, s in enumerate(plan.steps):
                    if not s.is_done():
                        first_pending = i
                        break
                if first_pending is not None and new_steps:
                    plan.steps = plan.steps[:first_pending] + new_steps
                return make_event("plan", status=PlanStatus.UPDATED.value, plan=safe_plan_dict(plan))
        except Exception as e:
            sys.stderr.write("Plan update error: {}\n".format(e))
        return None

    async def summarize_async(
        self,
        plan: Plan,
        user_message: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Generate summary and yield streaming message events."""
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
        summarize_system = (
            SYSTEM_PROMPT + "\n\nIMPORTANT: Respond with plain text only. "
            "Do NOT output JSON. Give a clear, helpful summary of the results."
        )
        messages = [
            {"role": "system", "content": summarize_system},
            {"role": "user", "content": prompt},
        ]

        loop = asyncio.get_event_loop()
        try:
            raw = await loop.run_in_executor(
                None, lambda: call_cf_streaming(messages)
            )
            if not raw:
                raw = "Task completed successfully."

            full_text = raw
            clean = raw.strip()
            if clean.startswith("{"):
                try:
                    parsed_summary = json.loads(clean)
                    if "message" in parsed_summary:
                        full_text = parsed_summary["message"]
                except (json.JSONDecodeError, ValueError):
                    pass
            elif clean.startswith("```"):
                try:
                    inner = re.search(r"```(?:json)?\s*([\s\S]*?)```", clean)
                    if inner:
                        parsed_summary = json.loads(inner.group(1).strip())
                        if "message" in parsed_summary:
                            full_text = parsed_summary["message"]
                except (json.JSONDecodeError, ValueError, AttributeError):
                    pass

            yield make_event("message_start", role="assistant")
            buf = ""
            for ch in full_text:
                buf += ch
                if ch in (" ", "\n", ".", ",", "!", "?", ":", ";"):
                    if buf:
                        yield make_event("message_chunk", chunk=buf, role="assistant")
                        await asyncio.sleep(0.005)
                        buf = ""
            if buf:
                yield make_event("message_chunk", chunk=buf, role="assistant")
            yield make_event("message_end", role="assistant")

        except Exception:
            yield make_event("message_start", role="assistant")
            yield make_event("message_chunk", chunk="Task completed.", role="assistant")
            yield make_event("message_end", role="assistant")

    async def respond_directly_async(
        self,
        user_message: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Respond directly without Plan-Act for simple queries."""
        messages = [
            {"role": "system", "content": (
                "You are Dzeck, an AI assistant. Respond naturally and helpfully. "
                "Be concise but informative. Respond in the same language as the user. "
                "Do NOT output JSON — respond with plain text only."
            )},
            {"role": "user", "content": user_message},
        ]
        loop = asyncio.get_event_loop()
        try:
            raw = await loop.run_in_executor(
                None, lambda: call_cf_streaming(messages)
            )
            if not raw:
                raw = "I'm sorry, I couldn't generate a response."

            full_text = raw
            clean = raw.strip()
            if clean.startswith("{"):
                try:
                    parsed_direct = json.loads(clean)
                    full_text = (
                        parsed_direct.get("message")
                        or parsed_direct.get("response")
                        or parsed_direct.get("content")
                        or raw
                    )
                except (json.JSONDecodeError, ValueError):
                    pass

            yield make_event("message_start", role="assistant")
            buf = ""
            for ch in full_text:
                buf += ch
                if ch in (" ", "\n", ".", ",", "!", "?", ":", ";"):
                    if buf:
                        yield make_event("message_chunk", chunk=buf, role="assistant")
                        await asyncio.sleep(0.005)
                        buf = ""
            if buf:
                yield make_event("message_chunk", chunk=buf, role="assistant")
            yield make_event("message_end", role="assistant")
        except Exception as e:
            yield make_event("error", error="Response error: {}".format(e))

    async def run_async(
        self,
        user_message: str,
        attachments: Optional[List[str]] = None,
        resume_from_session: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Main async agent flow using AsyncGenerator.
        
        Yields SSE events as they happen:
        - plan events (creating/created/running/updated/completed)
        - step events (running/completed/failed)
        - tool events (calling/called/error)
        - message events (start/chunk/end)
        - done event
        
        Supports:
        - Session persistence (MongoDB + Redis)
        - Resume from saved session state
        """
        svc = await self._get_session_service()

        try:
            if resume_from_session and svc:
                session = await svc.resume_session(resume_from_session)
                if session and session.get("plan"):
                    self.plan = Plan.from_dict(session["plan"])
                    yield make_event("session", action="resumed", session_id=resume_from_session)

            if self.session_id and svc:
                await svc.create_session(user_message, session_id=self.session_id)

            if not attachments and self._is_simple_query(user_message):
                async for event in self.respond_directly_async(user_message):
                    yield event
                yield make_event("done", success=True, session_id=self.session_id)
                return

            self.state = FlowState.PLANNING
            yield make_event("plan", status=PlanStatus.CREATING.value)

            self.plan = await self.run_planner_async(user_message, attachments)

            if self.session_id and svc:
                await svc.save_plan_snapshot(self.session_id, self.plan.to_dict())

            yield make_event("title", title=self.plan.title)

            if self.plan.message:
                yield make_event("message_start", role="assistant")
                buf = ""
                for ch in self.plan.message:
                    buf += ch
                    if ch in (" ", "\n", ".", ","):
                        if buf:
                            yield make_event("message_chunk", chunk=buf, role="assistant")
                            await asyncio.sleep(0.005)
                            buf = ""
                if buf:
                    yield make_event("message_chunk", chunk=buf, role="assistant")
                yield make_event("message_end", role="assistant")

            yield make_event("plan", status=PlanStatus.CREATED.value, plan=safe_plan_dict(self.plan))

            if not self.plan.steps:
                yield make_event("message_start", role="assistant")
                yield make_event("message_chunk", chunk="No actionable steps needed.", role="assistant")
                yield make_event("message_end", role="assistant")
                yield make_event("done", success=True, session_id=self.session_id)
                return

            yield make_event("plan", status=PlanStatus.RUNNING.value, plan=safe_plan_dict(self.plan))

            while True:
                step = self.plan.get_next_step()
                if not step:
                    break

                async for event in self.execute_step_async(self.plan, step, user_message):
                    yield event

                if self.session_id and svc:
                    await svc.save_step_completed(self.session_id, step.to_dict())

                next_step = self.plan.get_next_step()
                if next_step:
                    yield make_event("plan", status=PlanStatus.UPDATING.value,
                                     plan=safe_plan_dict(self.plan))
                    plan_event = await self.update_plan_async(self.plan, step)
                    if plan_event:
                        yield plan_event

            self.plan.status = ExecutionStatus.COMPLETED
            yield make_event("plan", status=PlanStatus.COMPLETED.value,
                             plan=safe_plan_dict(self.plan))

            async for event in self.summarize_async(self.plan, user_message):
                yield event

            self.state = FlowState.COMPLETED

            if self.session_id and svc:
                await svc.complete_session(self.session_id, success=True)

            yield make_event("done", success=True, session_id=self.session_id)

        except Exception as e:
            self.state = FlowState.FAILED
            if self.session_id:
                try:
                    svc2 = await self._get_session_service()
                    if svc2:
                        await svc2.complete_session(self.session_id, success=False)
                except Exception:
                    pass
            yield make_event("error", error="Agent error: {}".format(e))
            traceback.print_exc(file=sys.stderr)
            yield make_event("done", success=False, session_id=self.session_id)


async def run_agent_async(
    user_message: str,
    attachments: Optional[List[str]] = None,
    session_id: Optional[str] = None,
    resume_from_session: Optional[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Public entry point for running the agent as an async generator.
    Used by both the CLI main() and the Node.js subprocess bridge.
    """
    agent = DzeckAgent(session_id=session_id)
    async for event in agent.run_async(
        user_message,
        attachments=attachments,
        resume_from_session=resume_from_session,
    ):
        yield event


def main() -> None:
    """
    Synchronous entry point for Node.js subprocess bridge.
    Reads JSON from stdin, runs async agent, writes events to stdout.
    """
    try:
        raw_input = sys.stdin.read()
        input_data = json.loads(raw_input)

        user_message = input_data.get("message", "")
        messages = input_data.get("messages", [])
        attachments = input_data.get("attachments", [])
        session_id = input_data.get("session_id")
        resume_from_session = input_data.get("resume_from_session")

        if messages and not user_message:
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    user_message = msg.get("content", "")
                    break

        if not user_message:
            event = json.dumps({"type": "error", "error": "No user message provided"})
            sys.stdout.write(event + "\n")
            sys.stdout.flush()
            event = json.dumps({"type": "done", "success": False})
            sys.stdout.write(event + "\n")
            sys.stdout.flush()
            return

        async def _run():
            async for event in run_agent_async(
                user_message,
                attachments=attachments or [],
                session_id=session_id,
                resume_from_session=resume_from_session,
            ):
                line = json.dumps(event, default=str)
                sys.stdout.write(line + "\n")
                sys.stdout.flush()

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, _run())
                    future.result()
            else:
                loop.run_until_complete(_run())
        except RuntimeError:
            asyncio.run(_run())

    except Exception as e:
        event = json.dumps({"type": "error", "error": "Fatal error: {}".format(e)})
        sys.stdout.write(event + "\n")
        sys.stdout.flush()
        traceback.print_exc(file=sys.stderr)
        event = json.dumps({"type": "done", "success": False})
        sys.stdout.write(event + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
