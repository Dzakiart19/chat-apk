"""
Shell execution tools for Dzeck AI Agent.
Upgraded to class-based architecture from Ai-DzeckV2 (Manus) pattern.
Provides: ShellTool class + backward-compatible functions.

Design:
- shell_exec: runs command synchronously, stores result in session dict
- shell_view: shows last result of a session (success if session not found: already done)
- shell_wait: sleeps N seconds then views session (success even if session not found)
- shell_write_to_process: sends stdin to a running Popen process
- shell_kill_process: terminates a session/process (success even if already gone)
"""
import subprocess
import os
import time
import threading
from typing import Optional, Dict, Any

from server.agent.models.tool_result import ToolResult
from server.agent.tools.base import BaseTool, tool


# ─── Session store (module-level singleton, thread-safe) ─────────────────────
# Maps session_id → {process, output, command, return_code, popen, lock}
_shell_sessions: Dict[str, Dict[str, Any]] = {}
_sessions_lock = threading.Lock()


def _get_or_create_session(sid: str) -> Dict[str, Any]:
    with _sessions_lock:
        if sid not in _shell_sessions:
            _shell_sessions[sid] = {
                "popen": None,
                "output": "",
                "command": "",
                "return_code": None,
                "lock": threading.Lock(),
            }
        return _shell_sessions[sid]


def _get_session(sid: str) -> Optional[Dict[str, Any]]:
    with _sessions_lock:
        return _shell_sessions.get(sid)


# ─── Backward-compatible functions ───────────────────────────────────────────

def shell_exec(command: str, exec_dir: str = "/tmp", id: str = "default") -> ToolResult:
    """Execute a shell command in a named session. Stores result for shell_view."""
    try:
        if not os.path.isdir(exec_dir):
            exec_dir = "/tmp"

        popen = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            text=True,
            cwd=exec_dir,
            env={**os.environ, "PYTHONUNBUFFERED": "1", "TERM": "xterm-256color"},
        )

        sess = _get_or_create_session(id)
        sess["popen"] = popen
        sess["command"] = command

        try:
            stdout, stderr = popen.communicate(timeout=90)
        except subprocess.TimeoutExpired:
            popen.kill()
            stdout, stderr = popen.communicate()
            return ToolResult(
                success=False,
                message="Command timed out after 90 seconds.\nstdout:\n{}\nstderr:\n{}".format(
                    stdout[:2000], stderr[:500]),
                data={"error": "timeout", "command": command, "id": id,
                      "stdout": stdout[:2000], "stderr": stderr[:500]},
            )

        max_chars = 8000
        if len(stdout) > max_chars:
            stdout = stdout[:max_chars] + "\n[Output truncated...]"
        if len(stderr) > max_chars:
            stderr = stderr[:max_chars] + "\n[Error output truncated...]"

        combined = ""
        if stdout.strip():
            combined += "stdout:\n{}".format(stdout)
        if stderr.strip():
            combined += "\nstderr:\n{}".format(stderr)
        combined += "\nreturn_code: {}".format(popen.returncode)

        sess["output"] = combined
        sess["return_code"] = popen.returncode
        sess["popen"] = None

        return ToolResult(
            success=popen.returncode == 0,
            message=combined,
            data={
                "stdout": stdout,
                "stderr": stderr,
                "return_code": popen.returncode,
                "command": command,
                "id": id,
            },
        )
    except Exception as e:
        return ToolResult(
            success=False,
            message="Shell execution failed: {}".format(str(e)),
            data={"error": str(e), "command": command, "id": id},
        )


def shell_view(id: str = "default") -> ToolResult:
    """View the current output/status of a shell session.
    Returns success=True even if session not found (already completed or not started).
    """
    session = _get_session(id)
    if not session:
        available = []
        with _sessions_lock:
            available = list(_shell_sessions.keys())
        return ToolResult(
            success=True,
            message="Shell session '{}' tidak ditemukan (sudah selesai atau belum dimulai). Session aktif: {}".format(
                id, available or ["(tidak ada)"]),
            data={"id": id, "found": False, "available_sessions": available},
        )

    popen = session.get("popen")
    if popen and popen.poll() is None:
        status = "running"
    else:
        status = "completed"

    output = session.get("output", "(belum ada output)")
    return ToolResult(
        success=True,
        message="Session '{}' [{}] (perintah: {})\n\n{}".format(
            id, status, session.get("command", ""), output),
        data={
            "id": id,
            "status": status,
            "command": session.get("command", ""),
            "output": output,
            "return_code": session.get("return_code"),
            "found": True,
        },
    )


def shell_wait(id: str = "default", seconds: int = 5) -> ToolResult:
    """Wait for N seconds then show session status.
    Always returns success=True — even if session not found (already done).
    """
    seconds = max(1, min(int(seconds) if seconds else 5, 120))

    session = _get_session(id)
    if session:
        popen = session.get("popen")
        if popen and popen.poll() is None:
            try:
                popen.wait(timeout=seconds)
            except subprocess.TimeoutExpired:
                pass
        else:
            time.sleep(min(seconds, 2))
    else:
        time.sleep(min(seconds, 2))

    return shell_view(id)


def shell_write_to_process(id: str, input: str, press_enter: bool = True) -> ToolResult:
    """Write input to a running Popen process in a shell session.
    If session has a live process, send stdin to it.
    If session has a completed command, re-run it with the input piped.
    If session doesn't exist, execute input as a shell command.
    """
    session = _get_session(id)

    if not session:
        return ToolResult(
            success=True,
            message="Session '{}' tidak ditemukan. Jalankan shell_exec terlebih dahulu untuk memulai session.".format(id),
            data={"id": id, "found": False, "input": input},
        )

    popen: Optional[subprocess.Popen] = session.get("popen")

    if popen and popen.poll() is None:
        try:
            text_to_send = input + ("\n" if press_enter else "")
            popen.stdin.write(text_to_send)
            popen.stdin.flush()
            time.sleep(0.5)

            output_lines = []
            if popen.stdout:
                import select
                ready, _, _ = select.select([popen.stdout], [], [], 2.0)
                if ready:
                    chunk = popen.stdout.read(4096)
                    if chunk:
                        output_lines.append(chunk)

            out = "".join(output_lines)
            session["output"] += "\n[stdin: {}]\n{}".format(input, out)
            return ToolResult(
                success=True,
                message="Input '{}' dikirim ke process. Output: {}".format(input, out[:500] if out else "(menunggu)"),
                data={"id": id, "input": input, "output": out},
            )
        except Exception as e:
            return ToolResult(
                success=False,
                message="Gagal menulis ke process: {}".format(e),
                data={"id": id, "error": str(e)},
            )
    else:
        last_command = session.get("command", "")
        if last_command:
            try:
                stdin_data = (input + "\n") if press_enter else input
                result = subprocess.run(
                    last_command,
                    shell=True,
                    input=stdin_data,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd="/tmp",
                )
                out = (result.stdout or "") + (result.stderr or "")
                session["output"] = out
                session["return_code"] = result.returncode
                return ToolResult(
                    success=result.returncode == 0,
                    message="Re-ran '{}' with input. Output: {}".format(last_command, out[:500]),
                    data={"id": id, "input": input, "output": out, "return_code": result.returncode},
                )
            except Exception as e:
                return ToolResult(
                    success=False,
                    message="Gagal menjalankan ulang command dengan input: {}".format(e),
                    data={"id": id, "error": str(e)},
                )
        else:
            return ToolResult(
                success=True,
                message="Session '{}' tidak memiliki process aktif. Input '{}' diabaikan.".format(id, input),
                data={"id": id, "input": input, "found": True, "active": False},
            )


def shell_kill_process(id: str = "default") -> ToolResult:
    """Terminate and remove a shell session.
    Returns success=True even if session already gone (already done).
    """
    with _sessions_lock:
        session = _shell_sessions.pop(id, None)

    if not session:
        return ToolResult(
            success=True,
            message="Session '{}' tidak ada atau sudah dihentikan.".format(id),
            data={"id": id, "found": False},
        )

    popen: Optional[subprocess.Popen] = session.get("popen")
    command = session.get("command", "")

    try:
        if popen and popen.poll() is None:
            popen.terminate()
            try:
                popen.wait(timeout=3)
            except subprocess.TimeoutExpired:
                popen.kill()
                popen.wait()

        return ToolResult(
            success=True,
            message="Session '{}' (perintah: {}) berhasil dihentikan.".format(id, command),
            data={"id": id, "command": command, "found": True},
        )
    except Exception as e:
        return ToolResult(
            success=True,
            message="Session '{}' dihapus (dengan error: {}).".format(id, e),
            data={"id": id, "error": str(e), "found": True},
        )


# ─── Class-based ShellTool (Ai-DzeckV2 / Manus pattern) ─────────────────────

class ShellTool(BaseTool):
    """Shell tool class - provides shell interaction capabilities."""

    name: str = "shell"

    def __init__(self) -> None:
        super().__init__()

    @tool(
        name="shell_exec",
        description=(
            "Execute commands in a specified shell session. "
            "Use for: running code/scripts, installing packages, file management, "
            "starting services, checking system status. "
            "Commands run synchronously and output is captured."
        ),
        parameters={
            "id": {"type": "string", "description": "Unique identifier of the target shell session (e.g. 'main', 'build', 'test')"},
            "exec_dir": {"type": "string", "description": "Working directory for command execution (must be absolute path, e.g. /home/user/project)"},
            "command": {"type": "string", "description": "Shell command to execute (bash syntax supported)"},
        },
        required=["id", "exec_dir", "command"],
    )
    def _shell_exec(self, id: str, exec_dir: str, command: str) -> ToolResult:
        return shell_exec(command=command, exec_dir=exec_dir, id=id)

    @tool(
        name="shell_view",
        description=(
            "View the content of a specified shell session. "
            "Use for: checking command output, monitoring progress, reading results."
        ),
        parameters={"id": {"type": "string", "description": "Unique identifier of the target shell session"}},
        required=["id"],
    )
    def _shell_view(self, id: str) -> ToolResult:
        return shell_view(id=id)

    @tool(
        name="shell_wait",
        description=(
            "Wait for the running process in a shell session to complete. "
            "Use after shell_exec for long-running commands (builds, installs, etc.)."
        ),
        parameters={
            "id": {"type": "string", "description": "Unique identifier of the target shell session"},
            "seconds": {"type": "integer", "description": "Maximum seconds to wait (1-120, default 5)"},
        },
        required=["id"],
    )
    def _shell_wait(self, id: str, seconds: Optional[int] = None) -> ToolResult:
        return shell_wait(id=id, seconds=seconds or 5)

    @tool(
        name="shell_write_to_process",
        description=(
            "Write input to a running process in a shell session. "
            "Use for: responding to interactive prompts, sending keystrokes to running programs."
        ),
        parameters={
            "id": {"type": "string", "description": "Unique identifier of the target shell session"},
            "input": {"type": "string", "description": "Input content to write to the process"},
            "press_enter": {"type": "boolean", "description": "Whether to press Enter after input (default true)"},
        },
        required=["id", "input", "press_enter"],
    )
    def _shell_write_to_process(self, id: str, input: str, press_enter: bool = True) -> ToolResult:
        return shell_write_to_process(id=id, input=input, press_enter=press_enter)

    @tool(
        name="shell_kill_process",
        description=(
            "Terminate the running process in a specified shell session. "
            "Use for: stopping hung commands, cleaning up background processes."
        ),
        parameters={"id": {"type": "string", "description": "Unique identifier of the target shell session"}},
        required=["id"],
    )
    def _shell_kill_process(self, id: str) -> ToolResult:
        return shell_kill_process(id=id)
