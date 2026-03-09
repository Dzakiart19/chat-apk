"""
Shell execution tools for Dzeck AI agent.
Based on the official Dzeck function calls specification.
Provides shell command execution with session management.
"""
import subprocess
import os
import time
import signal
from typing import Optional

from server.agent.models.tool_result import ToolResult


# Session store: id -> {"process": Popen, "output": str, "command": str}
_shell_sessions: dict = {}


def shell_exec(command: str, exec_dir: str = "/tmp",
               id: str = "default") -> ToolResult:
    """Execute a shell command in a named session and return the output.

    Args:
        command: Shell command to execute
        exec_dir: Working directory for command execution (absolute path)
        id: Unique identifier of the target shell session

    Returns:
        ToolResult with command output
    """
    try:
        if not os.path.isdir(exec_dir):
            exec_dir = "/tmp"

        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=exec_dir,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )

        stdout = result.stdout
        stderr = result.stderr

        max_chars = 10000
        if len(stdout) > max_chars:
            stdout = stdout[:max_chars] + "\n[Output truncated...]"
        if len(stderr) > max_chars:
            stderr = stderr[:max_chars] + "\n[Error output truncated...]"

        combined = ""
        if stdout:
            combined += f"stdout:\n{stdout}"
        if stderr:
            combined += f"\nstderr:\n{stderr}"
        combined += f"\nreturn_code: {result.returncode}"

        # Store in session
        _shell_sessions[id] = {
            "output": combined,
            "command": command,
            "return_code": result.returncode,
        }

        return ToolResult(
            success=result.returncode == 0,
            message=combined,
            data={
                "stdout": stdout,
                "stderr": stderr,
                "return_code": result.returncode,
                "command": command,
                "id": id,
            },
        )

    except subprocess.TimeoutExpired:
        _shell_sessions[id] = {
            "output": "Command timed out after 120 seconds",
            "command": command,
            "return_code": -1,
        }
        return ToolResult(
            success=False,
            message="Command timed out after 120 seconds",
            data={"error": "timeout", "command": command, "id": id},
        )
    except Exception as e:
        return ToolResult(
            success=False,
            message=f"Shell execution failed: {str(e)}",
            data={"error": str(e), "command": command, "id": id},
        )


def shell_view(id: str = "default") -> ToolResult:
    """View the current output/status of a shell session.

    Args:
        id: Unique identifier of the target shell session

    Returns:
        ToolResult with session output
    """
    session = _shell_sessions.get(id)
    if not session:
        return ToolResult(
            success=False,
            message=f"No shell session found with id '{id}'. Run shell_exec first.",
            data={"id": id, "available_sessions": list(_shell_sessions.keys())},
        )

    return ToolResult(
        success=True,
        message=f"Session '{id}' (command: {session.get('command', '')})\n\n{session.get('output', '')}",
        data={
            "id": id,
            "command": session.get("command", ""),
            "output": session.get("output", ""),
            "return_code": session.get("return_code"),
        },
    )


def shell_wait(id: str = "default", seconds: int = 5) -> ToolResult:
    """Wait for a specified number of seconds and then return session status.

    Recommended after running commands that need additional time to complete.

    Args:
        id: Unique identifier of the target shell session
        seconds: Wait duration in seconds (default 5)

    Returns:
        ToolResult with session status after waiting
    """
    seconds = max(1, min(seconds, 60))
    time.sleep(seconds)
    return shell_view(id)


def shell_write_to_process(id: str, input: str,
                            press_enter: bool = True) -> ToolResult:
    """Write input to a running process via a follow-up shell command.

    Note: Since we use one-shot subprocess, this runs a new command in the session context.

    Args:
        id: Unique identifier of the target shell session
        input: Input content to write to the process
        press_enter: Whether to press Enter key after input

    Returns:
        ToolResult with execution result
    """
    session = _shell_sessions.get(id)
    if not session:
        return ToolResult(
            success=False,
            message=f"No shell session found with id '{id}'.",
            data={"id": id},
        )

    # Re-run with echoed input (best-effort for non-interactive sessions)
    last_command = session.get("command", "")
    input_text = input + ("\n" if press_enter else "")

    return shell_exec(
        f"echo {repr(input_text)} | {last_command}",
        id=id,
    )


def shell_kill_process(id: str = "default") -> ToolResult:
    """Terminate processes associated with a shell session.

    Args:
        id: Unique identifier of the target shell session

    Returns:
        ToolResult with termination status
    """
    session = _shell_sessions.get(id)
    if not session:
        return ToolResult(
            success=False,
            message=f"No shell session found with id '{id}'.",
            data={"id": id},
        )

    command = session.get("command", "")
    # Try to kill by command name
    try:
        proc_name = command.split()[0] if command else ""
        if proc_name:
            result = subprocess.run(
                f"pkill -f {repr(proc_name)} 2>/dev/null; echo killed",
                shell=True, capture_output=True, text=True, timeout=10,
            )

        _shell_sessions.pop(id, None)
        return ToolResult(
            success=True,
            message=f"Session '{id}' terminated.",
            data={"id": id, "command": command},
        )
    except Exception as e:
        return ToolResult(
            success=False,
            message=f"Failed to kill session '{id}': {str(e)}",
            data={"id": id, "error": str(e)},
        )
