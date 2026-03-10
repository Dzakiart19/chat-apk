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
import concurrent.futures
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

from server.agent.tools.registry import (
    TOOLS,
    TOOL_ALIASES,
    TOOLKIT_MAP,
    resolve_tool_name,
    get_toolkit_name,
    execute_tool,
    get_all_tool_schemas,
)
# Individual function imports for backward compatibility
from server.agent.tools.search import web_search, web_browse, info_search_web
from server.agent.tools.shell import shell_exec, shell_view, shell_wait, shell_write_to_process, shell_kill_process
from server.agent.tools.file import file_read, file_write, file_str_replace, file_find_by_name, file_find_in_content, image_view
from server.agent.tools.message import message_notify_user, message_ask_user
from server.agent.tools.browser import browser_navigate, browser_view, browser_click, browser_input, browser_move_mouse, browser_press_key, browser_select_option, browser_scroll_up, browser_scroll_down, browser_console_exec, browser_console_view, browser_save_image
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


def _build_tool_schemas() -> List[Dict[str, Any]]:
    """Build TOOL_SCHEMAS dynamically from class-based tool registry.
    Adds the special 'idle' tool and converts OpenAI format to CF-native format.
    """
    idle_schema = {
        "name": "idle",
        "description": (
            "Alat khusus untuk menandakan bahwa semua tugas telah selesai dan agen siap kembali ke idle.\n\n"
            "Hanya gunakan saat SEMUA kondisi ini terpenuhi:\n"
            "1. Semua tugas sudah selesai sempurna, ditest, dan terverifikasi\n"
            "2. Semua hasil dan output sudah dikirim ke user melalui message tools\n"
            "3. Tidak ada tindakan lanjut yang diperlukan"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean", "description": "Apakah langkah berhasil"},
                "result": {"type": "string", "description": "Ringkasan apa yang sudah dikerjakan"},
            },
            "required": ["success", "result"],
        },
    }
    schemas = [idle_schema]
    for openai_schema in get_all_tool_schemas():
        fn = openai_schema.get("function", openai_schema)
        schemas.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters", {"type": "object"}),
        })
    return schemas


TOOL_SCHEMAS: List[Dict[str, Any]] = _build_tool_schemas()



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


async def call_cf_streaming_realtime(
    messages: list,
) -> AsyncGenerator[str, None]:
    """
    True async streaming from Cloudflare AI.
    Yields text chunks as they arrive in real-time using asyncio.Queue.
    """
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _stream_worker() -> None:
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
                            loop.call_soon_threadsafe(queue.put_nowait, None)
                            return
                        try:
                            parsed = json.loads(payload)
                            content = (
                                parsed.get("response")
                                or (parsed.get("choices", [{}])[0].get("delta", {}).get("content"))
                                or ""
                            )
                            if content:
                                loop.call_soon_threadsafe(queue.put_nowait, content)
                        except (json.JSONDecodeError, IndexError, KeyError):
                            pass
        except Exception as e:
            sys.stderr.write("CF realtime streaming error: {}\n".format(e))
            sys.stderr.flush()
        loop.call_soon_threadsafe(queue.put_nowait, None)

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = loop.run_in_executor(executor, _stream_worker)
    try:
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk
    finally:
        try:
            await future
        except Exception:
            pass
        executor.shutdown(wait=False)


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
    elif tool_name in ("info_search_web", "web_search"):
        return {"type": "search", "query": data.get("query", ""), "results": data.get("results", [])}
    elif tool_name in (
        "web_browse", "browser_navigate", "browser_view",
        "browser_click", "browser_input", "browser_move_mouse",
        "browser_press_key", "browser_select_option",
        "browser_scroll_up", "browser_scroll_down",
        "browser_console_exec", "browser_console_view",
        "browser_save_image",
    ):
        return {
            "type": "browser",
            "url": data.get("url", ""),
            "title": data.get("title", ""),
            "content": str(data.get("content", data.get("content_snippet", "")))[:2000],
            "save_path": data.get("save_path", ""),
            "screenshot_b64": data.get("screenshot_b64", ""),
        }
    elif tool_name in ("file_read", "file_write", "file_str_replace",
                       "file_find_by_name", "file_find_in_content",
                       "image_view"):
        return {
            "type": "file",
            "file": data.get("file", data.get("image", data.get("path", ""))),
            "content": str(data.get("content", ""))[:2000],
            "operation": tool_name.replace("file_", ""),
        }
    elif tool_name in ("mcp_call_tool", "mcp_list_tools"):
        return {"type": "mcp", "tool": data.get("tool_name", ""), "result": str(data)[:2000]}

    return None


def _coerce_bool(value: Any, default: bool = True) -> bool:
    """Safely coerce a value (including LLM string 'true'/'false') to Python bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "0", "no", "")
    if value is None:
        return default
    return bool(value)


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
        """
        Determine if a query can be answered directly without Plan-Act tools.
        
        Returns True (respond directly) when:
        - Conversational / social messages
        - Knowledge/explanation questions answerable from training data
        - Math, translations, creative writing, code explanation
        
        Returns False (use Plan-Act) when:
        - Real-time info needed (news, prices, weather, current events)
        - Web browsing / URL access requested
        - File system operations
        - Shell/code execution
        - Complex multi-step creation tasks
        - Research tasks that need web search
        - Any URL present in the message
        """
        msg = user_message.strip().lower()
        raw = user_message.strip()

        # 0. Any URL in message → needs browser/search tool
        if re.search(r'https?://', raw):
            return False

        # 1. Explicit tool-requiring patterns → ALWAYS use Plan-Act
        tool_required_patterns = [
            # Real-time / current info
            r'\b(today|sekarang|hari ini|saat ini|terbaru|latest|current|now|live)\b',
            r'\b(news|berita|harga|price|cuaca|weather|stock|saham|kurs|exchange rate)\b',
            r'\b(trending|viral|populer|terkini|breaking)\b',
            # Action-based tasks
            r'\b(buka|buka situs|browse|visit|navigat|go to|open|akses|cek website|kunjungi)\b',
            r'\b(download|unduh|upload|scrape|crawl)\b',
            r'\b(install|uninstall|pip install|apt-get|npm install)\b',
            r'\b(run|execute|jalankan|eksekusi|exec)\b',
            r'\b(buat file|create file|write file|tulis file|simpan file|save file)\b',
            r'\b(buat folder|create folder|mkdir|hapus file|delete file)\b',
            r'\b(deploy|publish|hosting|server|api endpoint)\b',
            r'\b(bash|shell|command|cmd|terminal|script\.sh|\.py|\.js|\.ts)\b',
            # Complex creation
            r'\b(buat website|create website|build website|buat aplikasi|create app|build app)\b',
            r'\b(buat program|create program|tulis program|write program|code this|coding)\b',
            r'\b(research|riset|investigasi|investigate|analisis mendalam|analyze)\b',
            # File references (paths)
            r'[/\\][a-zA-Z0-9_.-]+\.[a-zA-Z]{2,4}',
        ]
        for pattern in tool_required_patterns:
            if re.search(pattern, msg):
                return False

        # 2. Pure conversational → always direct
        conversational = [
            r'^\s*(hi|hello|hey|halo|hai|hei|howdy)\s*[!.]?\s*$',
            r'^\s*(thanks?|thank you|terima kasih|makasih|thx)\s*[!.]?\s*$',
            r'^\s*(ok|okay|oke|baik|siap|noted|got it|paham)\s*[!.]?\s*$',
            r'^\s*(yes|no|ya|tidak|nope|yep|sure)\s*[!.]?\s*$',
            r'^\s*(bye|goodbye|sampai jumpa|dadah|see you)\s*[!.]?\s*$',
            r'^\s*(good morning|good night|selamat pagi|selamat malam|selamat siang|selamat sore)\s*[!.]?\s*$',
            r'\b(how are you|apa kabar|kabar gimana|how\'s it going)\b',
            r'\b(who are you|siapa kamu|siapa anda|kamu siapa|anda siapa)\b',
            r'\b(what can you do|apa yang bisa kamu|kemampuan kamu|fitur kamu)\b',
            r'\b(are you (an )?ai|kamu ai|kamu robot|apakah kamu)\b',
        ]
        for pattern in conversational:
            if re.search(pattern, msg):
                return True

        # 3. Knowledge/explanation questions — answerable from training data
        #    Only if they don't contain real-time signals
        knowledge_starters = [
            "what is", "what are", "what does", "what was",
            "who is", "who are", "who was",
            "when was", "when did", "where is", "where was",
            "why is", "why are", "why does", "why did",
            "how does", "how do", "how is", "how was",
            "explain", "define", "describe", "tell me about",
            "what's the difference", "compare",
            "apa itu", "apa yang", "apa bedanya",
            "siapa", "kapan", "dimana", "mengapa", "kenapa",
            "jelaskan", "ceritakan", "definisikan", "apa artinya",
            "bagaimana cara", "bagaimana",
        ]
        # Signals that a "what is" question still needs real-time data
        realtime_signals = [
            r'\b(now|today|current|latest|2024|2025|2026|terbaru|sekarang|hari ini|saat ini)\b',
            r'\b(price|harga|cost|biaya|rate|nilai|kurs)\b',
            r'\b(news|berita|update|terkini|terbaru)\b',
        ]
        for starter in knowledge_starters:
            if msg.startswith(starter) or f' {starter} ' in msg:
                if not any(re.search(p, msg) for p in realtime_signals):
                    return True

        # 4. Math/calculation questions → direct
        if re.search(r'(\d+[\s]*[\+\-\*\/\^%][\s]*\d+|berapa|calculate|hitung|compute|convert)', msg):
            if not re.search(r'\b(currency|mata uang|kurs|exchange|rate)\b', msg):
                return True

        # 5. Translation requests → direct
        if re.search(r'\b(translate|terjemahkan|translation|terjemahan|in english|dalam bahasa|ke bahasa)\b', msg):
            return True

        # 6. Creative writing (short) → direct
        if re.search(r'\b(write a poem|write a story|puisi|cerita pendek|story about|poem about|buat puisi|buat cerita)\b', msg):
            word_count = len(msg.split())
            if word_count < 20:  # Only short creative prompts — long ones might need research
                return True

        # 7. Code explanation (not execution) → direct
        if re.search(r'\b(explain (this )?code|what does this code|apa fungsi|fungsi dari|code ini|kode ini)\b', msg):
            return True

        # 8. Short simple messages (≤ 6 words with no action signals) → direct
        word_count = len(msg.split())
        if word_count <= 6:
            simple_action = re.search(
                r'\b(cari|search|find|buka|open|buat|create|make|build|tulis|write|jalankan|run)\b',
                msg
            )
            if not simple_action:
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

    async def _run_tool_streaming(
        self,
        fn_name: str,
        fn_args: Dict[str, Any],
        tool_call_id: str,
        step: Step,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute a single tool call and yield events in real-time:
        1. Yields "calling" event IMMEDIATELY (shows spinner to user)
        2. Awaits tool execution
        3. Yields "called" or "error" event with results
        4. Yields a special "__result__" event with result_summary for exec_messages
        5. If idle/task_complete, yields "__step_done__" sentinel
        """
        if fn_name in ("idle", "task_complete"):
            step.status = ExecutionStatus.COMPLETED
            step.success = _coerce_bool(fn_args.get("success"), default=True)
            step.result = fn_args.get("result", "Step completed")
            if not step.success:
                step.status = ExecutionStatus.FAILED
            status_enum = StepStatus.COMPLETED if step.success else StepStatus.FAILED
            yield make_event("step", status=status_enum.value, step=step.to_dict())
            yield {"type": "__step_done__"}
            return

        resolved = resolve_tool_name(fn_name)
        if resolved is None:
            yield {"type": "__result__", "value": "Unknown tool '{}'.".format(fn_name)}
            return

        # ── Special: message tools → emit as streaming chat bubbles, not tool cards ──
        if resolved in ("message_notify_user", "message_ask_user"):
            text = fn_args.get("text", "") or fn_args.get("message", "")
            if text:
                yield make_event("message_start", role="assistant")
                chunk_size = 10
                for i in range(0, len(text), chunk_size):
                    yield make_event("message_chunk", chunk=text[i:i + chunk_size], role="assistant")
                    await asyncio.sleep(0.008)
                yield make_event("message_end", role="assistant")
            # Execute the tool silently (returns ToolResult.success=True)
            _res = resolved
            _args = dict(fn_args)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: execute_tool(_res, _args))
            yield {"type": "__result__", "value": text or "Done"}
            return

        toolkit_name = get_toolkit_name(resolved)

        # ── 1. Emit "calling" IMMEDIATELY so user sees the spinner right away ──
        yield make_event(
            "tool",
            status=ToolStatus.CALLING.value,
            tool_name=toolkit_name,
            function_name=resolved,
            function_args=fn_args,
            tool_call_id=tool_call_id,
        )

        # ── 2. Execute the tool (await = real async, unblocks event loop) ──
        loop = asyncio.get_event_loop()
        _res = resolved
        _args = dict(fn_args)
        tool_result = await loop.run_in_executor(
            None, lambda: execute_tool(_res, _args)
        )

        tool_content = build_tool_content(resolved, tool_result)
        result_status = ToolStatus.CALLED if tool_result.success else ToolStatus.ERROR
        fn_result = str(tool_result.message)[:3000] if tool_result.message else ""

        # ── 3. Emit result event ──
        yield make_event(
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

        yield {"type": "__result__", "value": result_summary}

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
                _msgs = list(exec_messages)
                api_result = await loop.run_in_executor(
                    None,
                    lambda: call_api_with_retry(_msgs, tools=TOOL_SCHEMAS),
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
                        result_str = "Done"

                        async for ev in self._run_tool_streaming(fn_name, fn_args, tc_id, step):
                            if ev.get("type") == "__step_done__":
                                step_done = True
                                break
                            elif ev.get("type") == "__result__":
                                result_str = ev.get("value", "Done")
                            else:
                                yield ev

                        if step_done:
                            break

                        exec_messages.append({
                            "role": "user",
                            "content": (
                                "Result of {}: {}\n\n"
                                "Continue. Call idle when step is fully done."
                            ).format(fn_name, result_str),
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
                        step.success = _coerce_bool(parsed.get("success"), default=True)
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
                        result_str = "Done"
                        step_done = False

                        async for ev in self._run_tool_streaming(resolved_name, tool_args, tc_id, step):
                            if ev.get("type") == "__step_done__":
                                step_done = True
                                break
                            elif ev.get("type") == "__result__":
                                result_str = ev.get("value", "Done")
                            else:
                                yield ev

                        if step_done:
                            return

                        exec_messages.append({
                            "role": "user",
                            "content": "Result of {}: {}\n\nContinue. Use another tool or call idle when step is fully done.".format(resolved_name, result_str)
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
        """Generate summary and yield streaming message events (real-time streaming)."""
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
            "You are Dzeck, a helpful AI assistant. "
            "Write a clear, natural summary in plain text. "
            "Never output JSON or code blocks. "
            "Use the same language as the user."
        )
        messages = [
            {"role": "system", "content": summarize_system},
            {"role": "user", "content": prompt},
        ]

        def _strip_json_wrapper(text: str) -> str:
            """If the model accidentally wraps response in JSON, extract the text value."""
            t = text.strip()
            if t.startswith("{") and t.endswith("}"):
                try:
                    obj = json.loads(t)
                    for key in ("message", "text", "response", "content", "summary", "result"):
                        if key in obj and isinstance(obj[key], str):
                            return obj[key]
                except Exception:
                    pass
            if t.startswith("```") and t.endswith("```"):
                inner = t[3:]
                if inner.startswith("json"):
                    inner = inner[4:]
                inner = inner.rstrip("`").strip()
                try:
                    obj = json.loads(inner)
                    for key in ("message", "text", "response", "content", "summary", "result"):
                        if key in obj and isinstance(obj[key], str):
                            return obj[key]
                except Exception:
                    pass
                return inner
            return text

        try:
            loop = asyncio.get_event_loop()
            full_text = await loop.run_in_executor(
                None, lambda: call_cf_streaming(messages)
            )

            if not full_text:
                full_text = "Task completed successfully."

            cleaned = _strip_json_wrapper(full_text)

            yield make_event("message_start", role="assistant")
            chunk_size = 12
            for i in range(0, len(cleaned), chunk_size):
                yield make_event("message_chunk", chunk=cleaned[i:i + chunk_size], role="assistant")
                await asyncio.sleep(0.01)
            yield make_event("message_end", role="assistant")
        except Exception:
            yield make_event("message_start", role="assistant")
            yield make_event("message_chunk", chunk="Task completed.", role="assistant")
            yield make_event("message_end", role="assistant")

    async def respond_directly_async(
        self,
        user_message: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Respond directly without Plan-Act for simple queries (real-time streaming)."""
        messages = [
            {"role": "system", "content": (
                "You are Dzeck, an AI assistant. Respond naturally and helpfully. "
                "Be concise but informative. Respond in the same language as the user. "
                "Do NOT output JSON — respond with plain text only."
            )},
            {"role": "user", "content": user_message},
        ]
        try:
            yield make_event("message_start", role="assistant")
            got_any = False
            async for chunk in call_cf_streaming_realtime(messages):
                if chunk:
                    got_any = True
                    yield make_event("message_chunk", chunk=chunk, role="assistant")
            if not got_any:
                yield make_event("message_chunk", chunk="I'm sorry, I couldn't generate a response.", role="assistant")
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
                yield make_event("message_chunk", chunk=self.plan.message, role="assistant")
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
