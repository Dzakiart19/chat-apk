"""
File operation tools for Dzeck AI Agent.
Upgraded to class-based architecture from Ai-DzeckV2 (Manus) pattern.
Provides: FileTool class + backward-compatible functions.
"""
import os
import re
import base64
import glob as glob_module
from typing import Optional, Any

from server.agent.models.tool_result import ToolResult
from server.agent.tools.base import BaseTool, tool


# ─── Utility helpers ─────────────────────────────────────────────────────────

def _to_bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() not in ("false", "0", "no", "none", "null", "")
    if v is None:
        return default
    return bool(v)


def _to_int_or_none(v: Any) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, str) and v.strip().lower() in ("null", "none", ""):
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


# ─── Backward-compatible functions ───────────────────────────────────────────

def file_read(
    file: str,
    start_line: Optional[Any] = None,
    end_line: Optional[Any] = None,
    sudo: Optional[Any] = None,
    **kwargs,
) -> ToolResult:
    """Read the contents of a file."""
    start_line = _to_int_or_none(start_line)
    end_line = _to_int_or_none(end_line)
    try:
        if not os.path.isfile(file):
            return ToolResult(success=False, message=f"File not found: {file}", data={"error": "not_found", "file": file})

        with open(file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total_lines = len(lines)

        if start_line is not None or end_line is not None:
            start = max(0, (start_line or 1) - 1)
            end = end_line if end_line is not None else total_lines
            selected_lines = lines[start:end]
            numbered = [f"{i:4d} | {line.rstrip()}" for i, line in enumerate(selected_lines, start=start + 1)]
        else:
            numbered = [f"{i:4d} | {line.rstrip()}" for i, line in enumerate(lines, start=1)]

        content = "\n".join(numbered)
        max_chars = 15000
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n[File truncated - use start_line/end_line to read more]"

        return ToolResult(
            success=True,
            message=f"File: {file} ({total_lines} lines)\n\n{content}",
            data={"file": file, "content": content, "total_lines": total_lines},
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to read file: {str(e)}", data={"error": str(e), "file": file})


def file_write(
    file: str,
    content: str,
    append: Any = False,
    leading_newline: Any = False,
    trailing_newline: Any = True,
    sudo: Optional[Any] = None,
    **kwargs,
) -> ToolResult:
    """Overwrite or append content to a file."""
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
        return ToolResult(success=False, message=f"Failed to write file: {str(e)}", data={"error": str(e), "file": file})


def file_str_replace(
    file: str,
    old_str: str,
    new_str: str,
    sudo: Optional[Any] = None,
    **kwargs,
) -> ToolResult:
    """Replace a string in a file."""
    try:
        if not os.path.isfile(file):
            return ToolResult(success=False, message=f"File not found: {file}", data={"error": "not_found", "file": file})

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
        return ToolResult(success=False, message=f"Failed to replace in file: {str(e)}", data={"error": str(e), "file": file})


def file_find_in_content(
    path: str,
    glob: str = "**/*",
    pattern: str = "",
    **kwargs,
) -> ToolResult:
    """Search for pattern in files matching glob under path."""
    try:
        if not os.path.isdir(path):
            return ToolResult(success=False, message=f"Directory not found: {path}", data={"error": "not_found", "path": path})

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
        return ToolResult(success=False, message=f"Failed to search: {str(e)}", data={"error": str(e), "path": path})


def file_find_by_name(
    path: str,
    glob: str = "*",
    **kwargs,
) -> ToolResult:
    """Find files matching a glob pattern in a directory."""
    try:
        if not os.path.isdir(path):
            return ToolResult(success=False, message=f"Directory not found: {path}", data={"error": "not_found", "path": path})

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
        return ToolResult(success=False, message=f"Failed to find files: {str(e)}", data={"error": str(e), "path": path})


def image_view(image: str, **kwargs) -> ToolResult:
    """View an image file (returns base64 encoded content)."""
    try:
        if not os.path.isfile(image):
            return ToolResult(success=False, message=f"Image not found: {image}", data={"error": "not_found", "image": image})

        ext = os.path.splitext(image)[1].lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                    ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml"}
        mime = mime_map.get(ext, "image/png")
        size = os.path.getsize(image)

        with open(image, "rb") as f:
            data = f.read(102400)  # Read up to 100KB
        b64 = base64.b64encode(data).decode()
        data_uri = f"data:{mime};base64,{b64}"

        return ToolResult(
            success=True,
            message=f"Image: {image} ({size} bytes, {mime})",
            data={"image": image, "size": size, "mime": mime, "data_uri": data_uri},
        )
    except Exception as e:
        return ToolResult(success=False, message=f"Failed to view image: {str(e)}", data={"error": str(e), "image": image})


# ─── Class-based FileTool (Ai-DzeckV2 / Manus pattern) ──────────────────────

class FileTool(BaseTool):
    """File tool class - provides file system operation capabilities."""

    name: str = "file"

    def __init__(self) -> None:
        super().__init__()

    @tool(
        name="file_read",
        description="Read file content. Use for checking file contents, analyzing logs, or reading configuration files.",
        parameters={
            "file": {"type": "string", "description": "Absolute path of the file to read"},
            "start_line": {"type": "integer", "description": "(Optional) Starting line number (1-based)"},
            "end_line": {"type": "integer", "description": "(Optional) Ending line number (inclusive)"},
            "sudo": {"type": "boolean", "description": "(Optional) Whether to use sudo privileges"},
        },
        required=["file"],
    )
    def _file_read(self, file: str, start_line: Optional[int] = None, end_line: Optional[int] = None, sudo: Optional[bool] = False) -> ToolResult:
        return file_read(file=file, start_line=start_line, end_line=end_line)

    @tool(
        name="file_write",
        description="Overwrite or append content to a file. Use for creating new files, appending content, or modifying existing files.",
        parameters={
            "file": {"type": "string", "description": "Absolute path of the file to write to"},
            "content": {"type": "string", "description": "Text content to write"},
            "append": {"type": "boolean", "description": "(Optional) Whether to use append mode (default: false)"},
            "leading_newline": {"type": "boolean", "description": "(Optional) Whether to add a leading newline"},
            "trailing_newline": {"type": "boolean", "description": "(Optional) Whether to add a trailing newline (default: true)"},
            "sudo": {"type": "boolean", "description": "(Optional) Whether to use sudo privileges"},
        },
        required=["file", "content"],
    )
    def _file_write(self, file: str, content: str, append: Optional[bool] = False, leading_newline: Optional[bool] = False, trailing_newline: Optional[bool] = True, sudo: Optional[bool] = False) -> ToolResult:
        return file_write(file=file, content=content, append=append, leading_newline=leading_newline, trailing_newline=trailing_newline)

    @tool(
        name="file_str_replace",
        description="Replace specific string in file. Use for making targeted edits to files.",
        parameters={
            "file": {"type": "string", "description": "Absolute path of the file to modify"},
            "old_str": {"type": "string", "description": "String to find and replace"},
            "new_str": {"type": "string", "description": "Replacement string"},
            "sudo": {"type": "boolean", "description": "(Optional) Whether to use sudo privileges"},
        },
        required=["file", "old_str", "new_str"],
    )
    def _file_str_replace(self, file: str, old_str: str, new_str: str, sudo: Optional[bool] = False) -> ToolResult:
        return file_str_replace(file=file, old_str=old_str, new_str=new_str)

    @tool(
        name="file_find_by_name",
        description="Find files by name pattern under a directory. Use for locating files by their names.",
        parameters={
            "path": {"type": "string", "description": "Directory path to search in"},
            "glob": {"type": "string", "description": "Glob pattern e.g. *.py, **/*.ts, *.json"},
        },
        required=["path"],
    )
    def _file_find_by_name(self, path: str, glob: str = "*") -> ToolResult:
        return file_find_by_name(path=path, glob=glob)

    @tool(
        name="file_find_in_content",
        description="Search for text or regex pattern inside files matching a glob pattern under a directory.",
        parameters={
            "path": {"type": "string", "description": "Directory path to search in"},
            "glob": {"type": "string", "description": "Glob pattern to filter files e.g. **/*.py"},
            "pattern": {"type": "string", "description": "Text or regex pattern to search for in file content"},
        },
        required=["path", "pattern"],
    )
    def _file_find_in_content(self, path: str, pattern: str, glob: str = "**/*") -> ToolResult:
        return file_find_in_content(path=path, pattern=pattern, glob=glob)

    @tool(
        name="image_view",
        description="View an image file. Returns the image content as base64 for display.",
        parameters={"image": {"type": "string", "description": "Absolute path to the image file"}},
        required=["image"],
    )
    def _image_view(self, image: str) -> ToolResult:
        return image_view(image=image)
