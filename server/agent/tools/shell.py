"""
Shell execution tool for the AI agent.
Provides sandboxed command execution.
"""
import subprocess
import os


def shell_exec(command: str, exec_dir: str = "/tmp") -> dict:
    """Execute a shell command and return the output.

    Args:
        command: Shell command to execute
        exec_dir: Working directory (default /tmp)

    Returns:
        dict with success status, stdout, stderr, and return code
    """
    try:
        # Ensure exec_dir exists
        if not os.path.isdir(exec_dir):
            exec_dir = "/tmp"

        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=exec_dir,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )

        stdout = result.stdout
        stderr = result.stderr

        # Truncate long output
        max_chars = 5000
        if len(stdout) > max_chars:
            stdout = stdout[:max_chars] + "\n[Output truncated...]"
        if len(stderr) > max_chars:
            stderr = stderr[:max_chars] + "\n[Error output truncated...]"

        return {
            "success": result.returncode == 0,
            "stdout": stdout,
            "stderr": stderr,
            "return_code": result.returncode,
            "command": command,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Command timed out after 60 seconds",
            "command": command,
            "stdout": "",
            "stderr": "",
            "return_code": -1,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "command": command,
            "stdout": "",
            "stderr": "",
            "return_code": -1,
        }
