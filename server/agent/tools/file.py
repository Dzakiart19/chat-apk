"""
File operation tools for the AI agent.
Ported from ai-manus: app/domain/services/tools/file.py
"""
import os
import re
import glob as glob_module
from typing import Optional, Any

from server.agent.models.tool_result import ToolResult


def _to_bool(v: Any, default: bool = False) -> bool:
    """Safely coerce a value to bool (handles string 'false'/'true')."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() not in ("false", "0", "no", "none", "null", "")
    if v is None:
        return default
    return bool(v)


def _to_int_or_none(v: Any) -> Optional[int]:
    """Safely coerce a value to int or None (handles string 'null')."""
    if v is None:
        return None
    if isinstance(v, str) and v.strip().lower() in ("null", "none", ""):
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def file_read(
    file: str,
    start_line: Optional[Any] = None,
    end_line: Optional[Any] = None,
    **kwargs,
) -> ToolResult:
    """Read the contents of a file.

    Args:
        file: Absolute path to the file
        start_line: Optional starting line (1-based)
        end_line: Optional ending line (inclusive)
    """
    start_line = _to_int_or_none(start_line)
    end_line = _to_int_or_none(end_line)

    try:
        if not os.path.isfile(file):
            return ToolResult(
                success=False,
                message=f"File not found: {file}",
                data={"error": "not_found", "file": file},
            )

        with open(file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total_lines = len(lines)

        if start_line is not None or end_line is not None:
            start = (start_line or 1) - 1
            end = end_line if end_line is not None else total_lines
            selected_lines = lines[start:end]
            numbered = [f"{i:4d} | {line.rstrip()}" for i, line in enumerate(selected_lines, start=start + 1)]
            content = "\n".join(numbered)
        else:
            numbered = [f"{i:4d} | {line.rstrip()}" for i, line in enumerate(lines, start=1)]
            content = "\n".join(numbered)

        max_chars = 15000
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n[File truncated...]"

        return ToolResult(
            success=True,
            message=f"File: {file} ({total_lines} lines)\n\n{content}",
            data={"file": file, "content": content, "total_lines": total_lines},
        )

    except Exception as e:
        return ToolResult(
            success=False,
            message=f"Failed to read file: {str(e)}",
            data={"error": str(e), "file": file},
        )


def file_write(
    file: str,
    content: str,
    append: Any = False,
    leading_newline: Any = False,
    trailing_newline: Any = True,
    **kwargs,
) -> ToolResult:
    """Overwrite or append content to a file.

    Args:
        file: Absolute path to the file
        content: Content to write
        append: Whether to append instead of overwrite (default False)
        leading_newline: Add newline before content
        trailing_newline: Add newline after content
    """
    append = _to_bool(append, default=False)
    leading_newline = _to_bool(leading_newline, default=False)
    trailing_newline = _to_bool(trailing_newline, default=True)

    try:
        parent_dir = os.path.dirname(file)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        write_content = content
        if leading_newline:
            write_content = "\n" + write_content
        if trailing_newline and not write_content.endswith("\n"):
            write_content = write_content + "\n"

        mode = "a" if append else "w"
        with open(file, mode, encoding="utf-8") as f:
            f.write(write_content)

        operation = "appended" if append else "written"
        return ToolResult(
            success=True,
            message=f"File {operation} successfully: {file} ({len(write_content)} bytes)",
            data={"file": file, "operation": operation, "bytes_written": len(write_content)},
        )

    except Exception as e:
        return ToolResult(
            success=False,
            message=f"Failed to write file: {str(e)}",
            data={"error": str(e), "file": file},
        )


def file_str_replace(
    file: str,
    old_str: str,
    new_str: str,
    **kwargs,
) -> ToolResult:
    """Replace a string in a file.

    Args:
        file: Absolute path to the file
        old_str: String to find and replace
        new_str: Replacement string
    """
    try:
        if not os.path.isfile(file):
            return ToolResult(
                success=False,
                message=f"File not found: {file}",
                data={"error": "not_found", "file": file},
            )

        with open(file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        if old_str not in content:
            return ToolResult(
                success=False,
                message=f"String not found in file: {file}",
                data={"error": "not_found", "file": file, "search_string": old_str[:100]},
            )

        count = content.count(old_str)
        new_content = content.replace(old_str, new_str)

        with open(file, "w", encoding="utf-8") as f:
            f.write(new_content)

        return ToolResult(
            success=True,
            message=f"Replaced {count} occurrence(s) in {file}",
            data={"file": file, "replacements": count},
        )

    except Exception as e:
        return ToolResult(
            success=False,
            message=f"Failed to replace in file: {str(e)}",
            data={"error": str(e), "file": file},
        )


def file_find_in_content(
    path: str,
    glob: str = "**/*",
    pattern: str = "",
    **kwargs,
) -> ToolResult:
    """Search for pattern in files matching glob under path.

    Args:
        path: Directory path to search in
        glob: Glob pattern to filter files (e.g., '*.py', '**/*.ts')
        pattern: Text/regex pattern to search for in file content
    """
    try:
        if not os.path.isdir(path):
            return ToolResult(
                success=False,
                message=f"Directory not found: {path}",
                data={"error": "not_found", "path": path},
            )

        search_pattern = os.path.join(path, glob)
        files = glob_module.glob(search_pattern, recursive=True)
        files = [f for f in files if os.path.isfile(f)]

        if not pattern:
            file_list = "\n".join(files[:50])
            return ToolResult(
                success=True,
                message=f"Found {len(files)} files matching '{glob}' in {path}:\n{file_list}",
                data={"path": path, "glob": glob, "files": files[:50], "count": len(files)},
            )

        try:
            regex = re.compile(pattern)
        except re.error:
            regex = re.compile(re.escape(pattern))

        matches = []
        for fpath in files[:200]:
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, start=1):
                        if regex.search(line):
                            matches.append(f"{fpath}:{i}: {line.rstrip()}")
                            if len(matches) >= 100:
                                break
            except Exception:
                continue
            if len(matches) >= 100:
                break

        if not matches:
            return ToolResult(
                success=True,
                message=f"No matches found for '{pattern}' in {path}/{glob}",
                data={"path": path, "glob": glob, "pattern": pattern, "matches": [], "count": 0},
            )

        result_text = "\n".join(matches[:50])
        return ToolResult(
            success=True,
            message=f"Found {len(matches)} match(es) for '{pattern}':\n{result_text}",
            data={"path": path, "glob": glob, "pattern": pattern, "matches": matches[:50], "count": len(matches)},
        )

    except Exception as e:
        return ToolResult(
            success=False,
            message=f"Failed to search: {str(e)}",
            data={"error": str(e), "path": path},
        )


def file_find_by_name(
    path: str,
    glob: str = "*",
    **kwargs,
) -> ToolResult:
    """Find files matching a glob pattern in a directory.

    Args:
        path: Directory path to search in
        glob: Glob pattern (e.g., '*.py', '**/*.ts')
    """
    try:
        if not os.path.isdir(path):
            return ToolResult(
                success=False,
                message=f"Directory not found: {path}",
                data={"error": "not_found", "path": path},
            )

        search_pattern = os.path.join(path, glob)
        files = glob_module.glob(search_pattern, recursive=True)

        max_files = 100
        truncated = len(files) > max_files
        files = sorted(files)[:max_files]

        file_list = "\n".join(files)
        msg = f"Found {len(files)} file(s) matching '{glob}' in {path}"
        if truncated:
            msg += f" (truncated to {max_files})"
        msg += f":\n{file_list}"

        return ToolResult(
            success=True,
            message=msg,
            data={"path": path, "pattern": glob, "files": files, "count": len(files), "truncated": truncated},
        )

    except Exception as e:
        return ToolResult(
            success=False,
            message=f"Failed to find files: {str(e)}",
            data={"error": str(e), "path": path},
        )
