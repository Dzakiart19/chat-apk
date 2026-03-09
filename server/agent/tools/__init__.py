"""
Tools package for the AI agent.
Ported from ai-manus tool architecture with BaseToolkit pattern.
All tools return ToolResult for consistent handling.
"""
from server.agent.tools.search import web_search, web_browse
from server.agent.tools.shell import shell_exec
from server.agent.tools.file import (
    file_read, file_write, file_str_replace,
    file_find_by_name, file_find_in_content,
)
from server.agent.tools.message import message_notify_user, message_ask_user
from server.agent.tools.browser import browser_navigate, browser_view, browser_restart
from server.agent.tools.mcp import mcp_call_tool, mcp_list_tools, get_mcp_manager

# Tool registry matching ai-manus tool naming convention
TOOLS = {
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

# Tool descriptions for LLM prompts
TOOL_DESCRIPTIONS = {
    "web_search": "Search the web for information using DuckDuckGo. Args: query (str), num_results (int, default 5)",
    "web_browse": "Read and extract content from a web page URL. Args: url (str)",
    "shell_exec": "Execute shell commands (bash). Args: command (str), exec_dir (str, default /tmp)",
    "file_read": "Read file contents with line numbers. Args: file (str), start_line (int, optional), end_line (int, optional)",
    "file_write": "Create or write to a file. Args: file (str), content (str), append (bool, default false)",
    "file_str_replace": "Replace a specific string in a file. Args: file (str), old_str (str), new_str (str)",
    "file_find_by_name": "Find files matching a glob pattern. Args: path (str), glob (str, default '*')",
    "file_find_in_content": "Search for regex pattern in a file. Args: file (str), regex (str)",
    "message_notify_user": "Send a progress notification to the user. Args: text (str)",
    "message_ask_user": "Ask the user a question and wait for response. Args: text (str), attachments (list, optional)",
    "browser_navigate": "Navigate browser to a URL. Args: url (str)",
    "browser_view": "Get current browser page content. No args.",
    "browser_restart": "Restart browser session. Args: url (str, optional)",
    "mcp_call_tool": "Call an MCP (Model Context Protocol) tool. Args: tool_name (str), arguments (dict)",
    "mcp_list_tools": "List all available MCP tools. No args.",
}

# Backward compatibility aliases
message_notify = message_notify_user
file_find = file_find_by_name
