#!/usr/bin/env python3
"""
Dzeck AI Agent - Plan-Act Flow Engine
Inspired by ai-manus PlanActFlow architecture.

This is the core autonomous agent that:
1. Creates a plan from user's message (Planner)
2. Executes each step using tools (Executor)
3. Updates the plan based on results
4. Summarizes final results

Uses g4f (gpt4free) as the LLM provider - free, no API key required.
Streams events as JSON lines to stdout for the Express server to relay via SSE.
"""
import sys
import json
import re
import traceback

# Import tools
from server.agent.tools.search import web_search, web_browse
from server.agent.tools.shell import shell_exec
from server.agent.tools.file import file_read, file_write, file_find
from server.agent.tools.message import message_notify
from server.agent.models.plan import Plan, Step, ExecutionStatus

# Tool registry
TOOLS = {
    "web_search": web_search,
    "web_browse": web_browse,
    "shell_exec": shell_exec,
    "file_read": file_read,
    "file_write": file_write,
    "file_find": file_find,
    "message_notify": message_notify,
}


def emit_event(event_type: str, **data):
    """Emit a JSON event line to stdout for SSE streaming."""
    event = {"type": event_type, **data}
    sys.stdout.write(json.dumps(event, default=str) + "\n")
    sys.stdout.flush()


def parse_json_response(text: str) -> dict:
    """Robustly parse JSON from LLM output, handling markdown fences and quirks."""
    text = text.strip()

    # Remove markdown code fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find the first JSON object in the text
    brace_start = text.find("{")
    if brace_start >= 0:
        depth = 0
        for i in range(brace_start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[brace_start : i + 1])
                    except json.JSONDecodeError:
                        break

    # Last resort: try to fix common issues
    try:
        # Remove trailing commas before closing braces/brackets
        fixed = re.sub(r",\s*([}\]])", r"\1", text)
        return json.loads(fixed)
    except (json.JSONDecodeError, Exception):
        pass

    return {}


def call_llm(messages: list, model: str = "gpt-4o-mini") -> str:
    """Call the LLM using g4f and return the response text."""
    from g4f.client import Client
    from g4f.Provider import Yqcloud

    client = Client(provider=Yqcloud)
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        stream=False,
    )

    if hasattr(response, "choices") and response.choices:
        return response.choices[0].message.content or ""
    return ""


def call_llm_with_retry(messages: list, model: str = "gpt-4o-mini", max_retries: int = 3) -> str:
    """Call LLM with retry logic."""
    last_error = None
    for attempt in range(max_retries):
        try:
            return call_llm(messages, model)
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                import time
                time.sleep(1)
    raise last_error


class DzeckAgent:
    """
    Main agent class implementing the Plan-Act flow.
    """

    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self.conversation_history = []
        self.max_tool_iterations = 15
        self.plan = None

    def _build_system_prompt(self) -> str:
        return """You are Dzeck AI, an autonomous AI agent that can complete complex tasks independently.

You have access to these tools:
- web_search(query, num_results=5): Search the web using DuckDuckGo
- web_browse(url): Read and extract content from a web page
- shell_exec(command, exec_dir="/tmp"): Execute shell commands
- file_read(file, start_line=None, end_line=None): Read file contents
- file_write(file, content, append=False): Create or write files
- file_find(path, pattern="*"): Find files matching a pattern
- message_notify(text): Send a progress update to the user

You excel at: information gathering, data analysis, coding, web searching, file management, and executing tasks autonomously.

IMPORTANT:
- Execute the task yourself, don't tell the user how to do it
- Deliver the final result, not a todo list
- Use tools to accomplish the task step by step
- Always respond with valid JSON"""

    def run_planner(self, user_message: str) -> Plan:
        """Create a plan from the user's message."""
        emit_event("thinking", thinking="Analyzing your request and creating a plan...")

        system_prompt = self._build_system_prompt() + """

You are now in PLANNING mode. Create a plan for the user's task.

Respond with ONLY valid JSON:
{
    "message": "Brief response about what you'll do (in user's language)",
    "goal": "Overall goal",
    "title": "Short title",
    "language": "detected language code",
    "steps": [
        {"id": "1", "description": "Step description"}
    ]
}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        response_text = call_llm_with_retry(messages, self.model)
        parsed = parse_json_response(response_text)

        if not parsed:
            # Fallback: create a simple single-step plan
            return Plan(
                title="Task Execution",
                goal=user_message[:100],
                language="en",
                steps=[Step(description=user_message, step_id="1")],
                message="I'll work on this task for you.",
            )

        steps = []
        for s in parsed.get("steps", []):
            steps.append(
                Step(
                    step_id=str(s.get("id", "")),
                    description=s.get("description", ""),
                )
            )

        if not steps:
            steps = [Step(description=user_message, step_id="1")]

        return Plan(
            title=parsed.get("title", "Task"),
            goal=parsed.get("goal", user_message[:100]),
            language=parsed.get("language", "en"),
            steps=steps,
            message=parsed.get("message", ""),
        )

    def execute_step(self, plan: Plan, step: Step, user_message: str) -> None:
        """Execute a single step using tools iteratively."""
        step.status = ExecutionStatus.RUNNING
        emit_event("step", status="started", step=step.to_dict())

        system_prompt = self._build_system_prompt() + f"""

You are now in EXECUTION mode. Execute this specific task step.

Current step: {step.description}
User's original request: {user_message}
Working language: {plan.language}

To use a tool, respond with ONLY this JSON:
{{
    "tool": "tool_name",
    "args": {{"param1": "value1"}}
}}

When the step is COMPLETE, respond with:
{{
    "done": true,
    "success": true,
    "result": "What was accomplished"
}}

Available tools: web_search, web_browse, shell_exec, file_read, file_write, file_find, message_notify

Execute now. Choose ONE tool to start with."""

        exec_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Execute this step: {step.description}"},
        ]

        for iteration in range(self.max_tool_iterations):
            try:
                response_text = call_llm_with_retry(exec_messages, self.model)
                parsed = parse_json_response(response_text)

                if not parsed:
                    # LLM returned non-JSON, treat as completion
                    step.status = ExecutionStatus.COMPLETED
                    step.success = True
                    step.result = response_text[:500]
                    emit_event("step", status="completed", step=step.to_dict())
                    return

                # Check if step is done
                if parsed.get("done"):
                    step.status = ExecutionStatus.COMPLETED
                    step.success = parsed.get("success", True)
                    step.result = parsed.get("result", "Step completed")
                    step.attachments = parsed.get("attachments", [])
                    emit_event("step", status="completed", step=step.to_dict())
                    if step.result:
                        emit_event("message", message=step.result, role="assistant")
                    return

                # Check if it's a thinking message
                if parsed.get("thinking"):
                    emit_event("thinking", thinking=parsed["thinking"])
                    exec_messages.append({"role": "assistant", "content": response_text})
                    exec_messages.append(
                        {"role": "user", "content": "Good analysis. Now execute using a tool."}
                    )
                    continue

                # Execute tool call
                tool_name = parsed.get("tool", "")
                tool_args = parsed.get("args", {})

                if tool_name not in TOOLS:
                    exec_messages.append({"role": "assistant", "content": response_text})
                    exec_messages.append(
                        {
                            "role": "user",
                            "content": f"Unknown tool '{tool_name}'. Available: {', '.join(TOOLS.keys())}. Try again.",
                        }
                    )
                    continue

                # Emit tool calling event
                tool_call_id = f"tc_{iteration}"
                emit_event(
                    "tool",
                    status="calling",
                    tool_name=tool_name,
                    function_name=tool_name,
                    function_args=tool_args,
                    tool_call_id=tool_call_id,
                )

                # Execute the tool
                tool_fn = TOOLS[tool_name]
                tool_result = tool_fn(**tool_args)

                # Determine tool content for frontend display
                tool_content = None
                if tool_name == "shell_exec":
                    console_output = tool_result.get("stdout", "")
                    if tool_result.get("stderr"):
                        console_output += "\n" + tool_result["stderr"]
                    tool_content = {"type": "shell", "console": console_output}
                elif tool_name == "web_search":
                    tool_content = {"type": "search", "results": tool_result.get("results", [])}
                elif tool_name == "web_browse":
                    tool_content = {
                        "type": "browser",
                        "title": tool_result.get("title", ""),
                        "content": tool_result.get("content", "")[:2000],
                    }
                elif tool_name in ("file_read", "file_write", "file_find"):
                    tool_content = {"type": "file", "content": str(tool_result)[:2000]}

                # Handle message_notify specially
                if tool_name == "message_notify":
                    emit_event("message", message=tool_args.get("text", ""), role="assistant")

                # Emit tool called event
                emit_event(
                    "tool",
                    status="called",
                    tool_name=tool_name,
                    function_name=tool_name,
                    function_args=tool_args,
                    tool_call_id=tool_call_id,
                    function_result=str(tool_result)[:3000],
                    tool_content=tool_content,
                )

                # Feed result back to LLM
                result_summary = json.dumps(tool_result, default=str)
                if len(result_summary) > 4000:
                    result_summary = result_summary[:4000] + "...[truncated]"

                exec_messages.append({"role": "assistant", "content": response_text})
                exec_messages.append(
                    {
                        "role": "user",
                        "content": f"Tool result:\n{result_summary}\n\nContinue executing the step. Use another tool or respond with done:true if the step is complete.",
                    }
                )

            except Exception as e:
                emit_event("error", error=f"Step execution error: {str(e)}")
                step.status = ExecutionStatus.FAILED
                step.error = str(e)
                emit_event("step", status="failed", step=step.to_dict())
                return

        # Max iterations reached
        step.status = ExecutionStatus.COMPLETED
        step.success = True
        step.result = "Step completed (max iterations reached)"
        emit_event("step", status="completed", step=step.to_dict())

    def update_plan(self, plan: Plan, completed_step: Step) -> None:
        """Update the plan based on the completed step result."""
        system_prompt = self._build_system_prompt() + """

You are now in PLAN UPDATE mode. Update the remaining steps based on the completed step.

Respond with ONLY valid JSON:
{
    "steps": [
        {"id": "next_id", "description": "Updated step description"}
    ]
}"""

        step_info = json.dumps(completed_step.to_dict(), default=str)
        plan_info = json.dumps(
            {
                "goal": plan.goal,
                "language": plan.language,
                "steps": [s.to_dict() for s in plan.steps],
            },
            default=str,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Completed step:\n{step_info}\n\nCurrent plan:\n{plan_info}\n\nUpdate the remaining uncompleted steps.",
            },
        ]

        try:
            response_text = call_llm_with_retry(messages, self.model)
            parsed = parse_json_response(response_text)

            if parsed and "steps" in parsed:
                new_steps = [
                    Step(step_id=str(s.get("id", "")), description=s.get("description", ""))
                    for s in parsed["steps"]
                ]

                # Find first pending step index
                first_pending = None
                for i, s in enumerate(plan.steps):
                    if not s.is_done():
                        first_pending = i
                        break

                if first_pending is not None and new_steps:
                    completed_steps = plan.steps[:first_pending]
                    completed_steps.extend(new_steps)
                    plan.steps = completed_steps

                emit_event("plan", status="updated", plan=plan.to_dict())

        except Exception as e:
            # Plan update failure is non-fatal, continue with existing plan
            emit_event("error", error=f"Plan update skipped: {str(e)}")

    def summarize(self, plan: Plan, user_message: str) -> None:
        """Generate a final summary of the completed task."""
        system_prompt = self._build_system_prompt() + """

You are now in SUMMARY mode. Summarize everything that was accomplished.

Respond with ONLY valid JSON:
{
    "message": "Detailed summary of what was accomplished (in user's language)",
    "attachments": []
}"""

        step_results = []
        for s in plan.steps:
            step_results.append(f"- {s.description}: {'Success' if s.success else 'Failed'} - {s.result or 'No result'}")

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Original request: {user_message}\n\nPlan: {plan.title}\n\nStep results:\n"
                + "\n".join(step_results)
                + "\n\nProvide a comprehensive summary.",
            },
        ]

        try:
            response_text = call_llm_with_retry(messages, self.model)
            parsed = parse_json_response(response_text)

            if parsed and parsed.get("message"):
                emit_event("message", message=parsed["message"], role="assistant")
            else:
                emit_event("message", message=response_text[:2000], role="assistant")
        except Exception as e:
            emit_event("message", message=f"Task completed. Summary unavailable: {str(e)}", role="assistant")

    def run(self, user_message: str) -> None:
        """Main agent flow: Plan -> Execute -> Summarize."""
        try:
            # Phase 1: Planning
            emit_event("thinking", thinking="Creating execution plan...")
            self.plan = self.run_planner(user_message)

            # Emit plan created event
            emit_event("title", title=self.plan.title)
            if self.plan.message:
                emit_event("message", message=self.plan.message, role="assistant")
            emit_event("plan", status="created", plan=self.plan.to_dict())

            if not self.plan.steps:
                emit_event("message", message="No actionable steps needed for this request.", role="assistant")
                emit_event("done")
                return

            # Phase 2: Execute each step
            while True:
                step = self.plan.get_next_step()
                if not step:
                    break

                # Execute the step
                self.execute_step(self.plan, step, user_message)

                # Update plan after step completion (skip for last step)
                if self.plan.get_next_step():
                    self.update_plan(self.plan, step)

            # Phase 3: Summarize
            self.plan.status = ExecutionStatus.COMPLETED
            emit_event("plan", status="completed", plan=self.plan.to_dict())
            self.summarize(self.plan, user_message)

            # Done
            emit_event("done")

        except Exception as e:
            emit_event("error", error=f"Agent error: {str(e)}")
            traceback.print_exc(file=sys.stderr)
            emit_event("done")


def main():
    """Entry point - reads task from stdin, runs agent, streams events to stdout."""
    try:
        raw_input = sys.stdin.read()
        input_data = json.loads(raw_input)

        user_message = input_data.get("message", "")
        model = input_data.get("model", "gpt-4o-mini")
        messages = input_data.get("messages", [])

        # If messages provided, use the last user message
        if messages and not user_message:
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    user_message = msg.get("content", "")
                    break

        if not user_message:
            emit_event("error", error="No user message provided")
            emit_event("done")
            return

        agent = DzeckAgent(model=model)
        agent.run(user_message)

    except Exception as e:
        emit_event("error", error=f"Fatal error: {str(e)}")
        traceback.print_exc(file=sys.stderr)
        emit_event("done")


if __name__ == "__main__":
    main()
