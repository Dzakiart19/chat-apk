"""
Shell execution tools for the AI agent.
Ported from ai-manus: app/domain/services/tools/shell.py
Provides shell command execution with session management.
"""
import subprocess
import os
from typing import Optional

from server.agent.models.tool_result import ToolResult


# Simple session store for persistent shell sessions
_shell_sessions: dict = {}


def shell_exec(command: str, exec_dir: str = "/tmp", session_id: str = "default") -> ToolResult:
    """Execute a shell command and return the output.

    Matching ai-manus shell_exec tool interface.

    Args:
        command: Shell command to execute
        exec_dir: Working directory (default /tmp)
        session_id: Shell session identifier

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

        # Truncate long output
        max_chars = 10000
        if len(stdout) > max_chars:
            stdout = stdout[:max_chars] + "\n[Output truncated...]"
        if len(stderr) > max_chars:
            stderr = stderr[:max_chars] + "\n[Error output truncated...]"

        output_parts = []
        if stdout:
            output_parts.append(f"stdout:\n{stdout}")
        if stderr:
            output_parts.append(f"stderr:\n{stderr}")
        output_parts.append(f"return_code: {result.returncode}")

        return ToolResult(
            success=result.returncode == 0,
            message="\n".join(output_parts),
            data={
                "stdout": stdout,
                "stderr": stderr,
                "return_code": result.returncode,
                "command": command,
            },
        )

    except subprocess.TimeoutExpired:
        return ToolResult(
            success=False,
            message="Command timed out after 120 seconds",
            data={"error": "timeout", "command": command},
        )
    except Exception as e:
        return ToolResult(
            success=False,
            message=f"Shell execution failed: {str(e)}",
            data={"error": str(e), "command": command},
        )
