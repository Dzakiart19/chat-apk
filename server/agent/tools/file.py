"""
File operation tools for the AI agent.
Provides file read, write, and find capabilities.
"""
import os
import glob as glob_module


def file_read(file: str, start_line: int = None, end_line: int = None) -> dict:
    """Read the contents of a file.

    Args:
        file: Absolute path to the file
        start_line: Optional starting line (0-based)
        end_line: Optional ending line (exclusive)

    Returns:
        dict with success status and file content
    """
    try:
        if not os.path.isfile(file):
            return {"success": False, "error": f"File not found: {file}", "content": ""}

        with open(file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        if start_line is not None or end_line is not None:
            start = start_line or 0
            end = end_line or len(lines)
            lines = lines[start:end]

        content = "".join(lines)

        # Truncate very large files
        max_chars = 10000
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n[File truncated...]"

        return {
            "success": True,
            "file": file,
            "content": content,
            "total_lines": len(lines),
        }

    except Exception as e:
        return {"success": False, "error": str(e), "file": file, "content": ""}


def file_write(file: str, content: str, append: bool = False) -> dict:
    """Write content to a file (create or overwrite).

    Args:
        file: Absolute path to the file
        content: Content to write
        append: Whether to append instead of overwrite

    Returns:
        dict with success status
    """
    try:
        # Ensure parent directory exists
        parent_dir = os.path.dirname(file)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        mode = "a" if append else "w"
        with open(file, mode, encoding="utf-8") as f:
            f.write(content)

        return {
            "success": True,
            "file": file,
            "message": f"File {'appended' if append else 'written'} successfully",
            "bytes_written": len(content),
        }

    except Exception as e:
        return {"success": False, "error": str(e), "file": file}


def file_find(path: str, pattern: str = "*") -> dict:
    """Find files matching a glob pattern in a directory.

    Args:
        path: Directory path to search in
        pattern: Glob pattern (e.g., '*.py', '**/*.ts')

    Returns:
        dict with success status and matching files
    """
    try:
        if not os.path.isdir(path):
            return {"success": False, "error": f"Directory not found: {path}", "files": []}

        search_pattern = os.path.join(path, pattern)
        files = glob_module.glob(search_pattern, recursive=True)

        # Limit results
        max_files = 50
        truncated = len(files) > max_files
        files = files[:max_files]

        return {
            "success": True,
            "path": path,
            "pattern": pattern,
            "files": files,
            "count": len(files),
            "truncated": truncated,
        }

    except Exception as e:
        return {"success": False, "error": str(e), "path": path, "files": []}
