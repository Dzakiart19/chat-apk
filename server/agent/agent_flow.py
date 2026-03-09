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

Uses g4f (gpt4free) as default LLM provider - free, no API key required.
Supports OpenAI-compatible API as alternative when API key is configured.
"""
import sys
import json
import os
import time
import traceback
from enum import Enum
from typing import Optional, Dict, Any, List

# Import tools
from server.agent.tools.search import web_search, web_browse
from server.agent.tools.shell import shell_exec
from server.agent.tools.file import (
    file_read, file_write, file_str_replace,
    file_find_by_name, file_find_in_content,
)
from server.agent.tools.message import message_notify_user, message_ask_user
from server.agent.tools.browser import browser_navigate, browser_view, browser_restart
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


# Tool registry - all tools matching ai-manus architecture
TOOLS: Dict[str, Any] = {
    "web_search": web_search,
    "web_browse": web_browse,
    "shell_exec": shell_exec,
    "file_read": file_read,
    "file_write": file_write,
    "file_str_replace": file_str_replace,
    "file_find_by_name": file_find_by_name,
    "file_find_in_content": file_find_in_content,
    "message_notify_user": message_notify_user,
    "message_ask_user": message_ask_user,
    "browser_navigate": browser_navigate,
    "browser_view": browser_view,
    "browser_restart": browser_restart,
    "mcp_call_tool": mcp_call_tool,
    "mcp_list_tools": mcp_list_tools,
}

# Backward compatibility aliases
TOOL_ALIASES: Dict[str, str] = {
    "message_notify": "message_notify_user",
    "message_ask": "message_ask_user",
    "file_find": "file_find_by_name",
}


def emit_event(event_type: str, **data: Any) -> None:
    """Emit a JSON event line to stdout for SSE streaming."""
    event: Dict[str, Any] = {"type": event_type, **data}
    sys.stdout.write(json.dumps(event, default=str) + "\n")
    sys.stdout.flush()


def call_llm(messages: list, model: str = "gpt-4o-mini",
             response_format: Optional[str] = None) -> str:
    """Call the LLM using g4f or OpenAI-compatible API."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    api_base = os.environ.get("OPENAI_API_BASE", "")

    if api_key:
        return _call_openai_api(messages, model, api_key, api_base,
                                response_format)
    else:
        return _call_g4f(messages, model)


def _call_g4f(messages: list, model: str = "gpt-4o-mini") -> str:
    """Call LLM using g4f (gpt4free)."""
    from g4f.client import Client

    client = Client()
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        stream=False,
    )

    if hasattr(response, "choices") and response.choices:
        return response.choices[0].message.content or ""
    return ""


def _call_openai_api(messages: list, model: str, api_key: str,
                     api_base: str = "",
                     response_format: Optional[str] = None) -> str:
    """Call OpenAI-compatible API."""
    import urllib.request

    base_url = api_base or "https://api.openai.com/v1"
    url = f"{base_url}/chat/completions"

    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 4096,
    }

    if response_format == "json_object":
        body["response_format"] = {"type": "json_object"}

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    if "choices" in result and result["choices"]:
        return result["choices"][0]["message"]["content"] or ""
    return ""


def call_llm_with_retry(messages: list, model: str = "gpt-4o-mini",
                         max_retries: int = 3,
                         response_format: Optional[str] = None) -> str:
    """Call LLM with retry logic and exponential backoff."""
    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return call_llm(messages, model, response_format)
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

    if tool_name == "shell_exec":
        console = data.get("stdout", "")
        if data.get("stderr"):
            console += "\n" + data["stderr"]
        return {
            "type": "shell",
            "command": data.get("command", ""),
            "console": console,
            "return_code": data.get("return_code", 0),
        }
    elif tool_name == "web_search":
        return {
            "type": "search",
            "query": data.get("query", ""),
            "results": data.get("results", []),
        }
    elif tool_name in ("web_browse", "browser_navigate", "browser_view"):
        return {
            "type": "browser",
            "url": data.get("url", ""),
            "title": data.get("title", ""),
            "content": str(data.get("content", ""))[:2000],
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


class DzeckAgent:
    """
    Main agent class implementing the Plan-Act flow.

    Ported from ai-manus PlanActFlow architecture with:
    - State machine for flow control
    - Robust JSON parsing (5-stage pipeline)
    - Memory management with compaction
    - Full tool system
    - Event streaming
    """

    def __init__(self, model: str = "gpt-4o-mini"):
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

        response_text = call_llm_with_retry(
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

    def execute_step(self, plan: Plan, step: Step,
                     user_message: str) -> None:
        """Execute a single step using tools iteratively.

        Matching ai-manus ExecutionAgent with tool calling loop.
        """
        self.state = FlowState.EXECUTING
        step.status = ExecutionStatus.RUNNING
        emit_event("step", status=StepStatus.RUNNING.value,
                   step=step.to_dict())

        # Build context from previous step results
        context_parts = []
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

        exec_messages: List[Dict[str, str]] = [
            {"role": "system", "content": EXECUTION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        self.memory.add_message(
            {"role": "system",
             "content": "Executing step: {}".format(step.description)}
        )

        for iteration in range(self.max_tool_iterations):
            try:
                response_text = call_llm_with_retry(
                    exec_messages, self.model)
                parsed = self._parse_response(response_text)

                if not parsed:
                    step.status = ExecutionStatus.COMPLETED
                    step.success = True
                    step.result = response_text[:500]
                    emit_event("step",
                               status=StepStatus.COMPLETED.value,
                               step=step.to_dict())
                    return

                # Check if step is done
                if parsed.get("done"):
                    step.status = ExecutionStatus.COMPLETED
                    step.success = parsed.get("success", True)
                    step.result = parsed.get("result", "Step completed")
                    step.attachments = parsed.get("attachments", [])

                    if not step.success:
                        step.status = ExecutionStatus.FAILED
                    status = (StepStatus.COMPLETED if step.success
                              else StepStatus.FAILED)
                    emit_event("step", status=status.value,
                               step=step.to_dict())

                    if step.result:
                        emit_event("message", message=step.result,
                                   role="assistant")
                    return

                # Thinking message
                if parsed.get("thinking"):
                    emit_event("thinking", content=parsed["thinking"])
                    exec_messages.append(
                        {"role": "assistant", "content": response_text})
                    exec_messages.append(
                        {"role": "user",
                         "content": "Good analysis. Now execute using a tool."})
                    continue

                # Message to user (no tool)
                if parsed.get("message") and not parsed.get("tool"):
                    emit_event("message", message=parsed["message"],
                               role="assistant")
                    exec_messages.append(
                        {"role": "assistant", "content": response_text})
                    exec_messages.append(
                        {"role": "user",
                         "content": ("Continue executing the step using "
                                     "tools, or respond with done:true "
                                     "if complete.")})
                    continue

                # Tool call
                tool_name = parsed.get("tool", "")
                tool_args = parsed.get("args", {})

                if not tool_name:
                    exec_messages.append(
                        {"role": "assistant", "content": response_text})
                    exec_messages.append(
                        {"role": "user",
                         "content": ('Please respond with a tool call or '
                                     'done:true. Format: '
                                     '{"tool": "name", "args": {...}}')})
                    continue

                resolved_name = resolve_tool_name(tool_name)
                if resolved_name is None:
                    exec_messages.append(
                        {"role": "assistant", "content": response_text})
                    available = ", ".join(TOOLS.keys())
                    exec_messages.append(
                        {"role": "user",
                         "content": ("Unknown tool '{}'. Available: {}. "
                                     "Try again."
                                     .format(tool_name, available))})
                    continue

                # Emit tool calling event
                tool_call_id = "tc_{}_{}".format(step.id, iteration)
                emit_event(
                    "tool",
                    status=ToolStatus.CALLING.value,
                    tool_name=resolved_name,
                    function_name=resolved_name,
                    function_args=tool_args,
                    tool_call_id=tool_call_id,
                )

                # Execute the tool
                tool_result = execute_tool(resolved_name, tool_args)
                tool_content = build_tool_content(
                    resolved_name, tool_result)

                # Handle message tools specially
                if resolved_name == "message_notify_user":
                    emit_event("message",
                               message=tool_args.get("text", ""),
                               role="assistant")
                elif resolved_name == "message_ask_user":
                    emit_event("wait",
                               prompt=tool_args.get("text", ""))
                    emit_event("message",
                               message=tool_args.get("text", ""),
                               role="assistant")

                # Emit tool result event
                result_status = (ToolStatus.RESULT if tool_result.success
                                 else ToolStatus.ERROR)
                fn_result = (str(tool_result.message)[:3000]
                             if tool_result.message else "")
                emit_event(
                    "tool",
                    status=result_status.value,
                    tool_name=resolved_name,
                    function_name=resolved_name,
                    function_args=tool_args,
                    tool_call_id=tool_call_id,
                    function_result=fn_result,
                    tool_content=tool_content,
                )

                # Add to memory
                self.memory.add_message({
                    "role": "tool",
                    "tool_name": resolved_name,
                    "content": tool_result.message or "",
                })

                # Feed result back to LLM
                result_summary = tool_result.message or "No result"
                if len(result_summary) > 4000:
                    result_summary = (result_summary[:4000]
                                      + "...[truncated]")

                exec_messages.append(
                    {"role": "assistant", "content": response_text})
                exec_messages.append(
                    {"role": "user",
                     "content": (
                         "Tool result:\n{}\n\n"
                         "Continue executing the step. Use another "
                         "tool or respond with "
                         '{{"done": true, "success": true, '
                         '"result": "..."}} if the step is complete.'
                     ).format(result_summary)})

                # Compact memory periodically
                if iteration > 0 and iteration % 5 == 0:
                    self.memory.compact()

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
                "goal": plan.goal,
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
            response_text = call_llm_with_retry(
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
                           plan=plan.to_dict())

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
            response_text = call_llm_with_retry(messages, self.model)
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

    def run(self, user_message: str,
            attachments: Optional[List[str]] = None) -> None:
        """Main agent flow: Plan -> Execute -> Update -> Summarize.

        Implements ai-manus PlanActFlow state machine:
        IDLE -> PLANNING -> EXECUTING -> UPDATING -> SUMMARIZING -> COMPLETED
        """
        try:
            # Phase 1: Planning
            self.state = FlowState.PLANNING
            emit_event("plan", status=PlanStatus.CREATING.value)

            self.plan = self.run_planner(user_message, attachments)

            emit_event("title", title=self.plan.title)
            if self.plan.message:
                emit_event("message", message=self.plan.message,
                           role="assistant")
            emit_event("plan", status=PlanStatus.CREATED.value,
                       plan=self.plan.to_dict())

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
                       plan=self.plan.to_dict())

            while True:
                step = self.plan.get_next_step()
                if not step:
                    break

                self.execute_step(self.plan, step, user_message)

                next_step = self.plan.get_next_step()
                if next_step:
                    emit_event("plan",
                               status=PlanStatus.UPDATING.value,
                               plan=self.plan.to_dict())
                    self.update_plan(self.plan, step)

            # Phase 3: Summarize
            self.plan.status = ExecutionStatus.COMPLETED
            emit_event("plan", status=PlanStatus.COMPLETED.value,
                       plan=self.plan.to_dict())
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
        model = input_data.get("model", "gpt-4o-mini")
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
