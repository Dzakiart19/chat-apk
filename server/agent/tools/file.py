"""
File operation tools for the AI agent.
Ported from ai-manus: app/domain/services/tools/file.py
Provides file read, write, string replace, and find capabilities.
"""
import os
import re
import glob as glob_module
from typing import Optional

from server.agent.models.tool_result import ToolResult


def file_read(file: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> ToolResult:
    """Read the contents of a file.

    Matching ai-manus file_read tool interface.

    Args:
        file: Absolute path to the file
        start_line: Optional starting line (1-based)
        end_line: Optional ending line (inclusive)

    Returns:
        ToolResult with file content
    """
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
            start = (start_line or 1) - 1  # Convert to 0-based
            end = end_line or total_lines
            selected_lines = lines[start:end]
            # Add line numbers
            numbered = []
            for i, line in enumerate(selected_lines, start=start + 1):
                numbered.append(f"{i:4d} | {line.rstrip()}")
            content = "\n".join(numbered)
        else:
            numbered = []
            for i, line in enumerate(lines, start=1):
                numbered.append(f"{i:4d} | {line.rstrip()}")
            content = "\n".join(numbered)

        # Truncate very large files
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
    append: bool = False,
    leading_newline: bool = False,
    trailing_newline: bool = True,
) -> ToolResult:
    """Write content to a file (create or overwrite).

    Matching ai-manus file_write tool interface.

    Args:
        file: Absolute path to the file
        content: Content to write
        append: Whether to append instead of overwrite
        leading_newline: Add newline before content
        trailing_newline: Add newline after content

    Returns:
        ToolResult with write status
    """
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


def file_str_replace(file: str, old_str: str, new_str: str) -> ToolResult:
    """Replace a string in a file.

    Matching ai-manus file_str_replace tool interface.

    Args:
        file: Absolute path to the file
        old_str: String to find and replace
        new_str: Replacement string

    Returns:
        ToolResult with replacement status
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


def file_find_in_content(file: str, regex: str) -> ToolResult:
    """Search for a pattern in a file using regex.

    Matching ai-manus file_find_in_content tool interface.

    Args:
        file: Absolute path to the file
        regex: Regular expression pattern to search for

    Returns:
        ToolResult with matching lines
    """
    try:
        if not os.path.isfile(file):
            return ToolResult(
                success=False,
                message=f"File not found: {file}",
                data={"error": "not_found", "file": file},
            )

        with open(file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        pattern = re.compile(regex)
        matches = []
        for i, line in enumerate(lines, start=1):
            if pattern.search(line):
                matches.append(f"{i:4d} | {line.rstrip()}")

        if not matches:
            return ToolResult(
                success=True,
                message=f"No matches found for '{regex}' in {file}",
                data={"file": file, "regex": regex, "matches": [], "count": 0},
            )

        result_text = "\n".join(matches[:50])  # Limit to 50 matches
        return ToolResult(
            success=True,
            message=f"Found {len(matches)} match(es) in {file}:\n{result_text}",
            data={"file": file, "regex": regex, "matches": matches[:50], "count": len(matches)},
        )

    except Exception as e:
        return ToolResult(
            success=False,
            message=f"Failed to search file: {str(e)}",
            data={"error": str(e), "file": file},
        )


def file_find_by_name(path: str, glob: str = "*") -> ToolResult:
    """Find files matching a glob pattern in a directory.

    Matching ai-manus file_find_by_name tool interface.

    Args:
        path: Directory path to search in
        glob: Glob pattern (e.g., '*.py', '**/*.ts')

    Returns:
        ToolResult with matching files
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

        # Limit results
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
