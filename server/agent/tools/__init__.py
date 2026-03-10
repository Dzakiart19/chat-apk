"""
Tools package for the AI agent.
All tools return ToolResult for consistent handling.
"""
from server.agent.tools.search import web_search, web_browse, info_search_web
from server.agent.tools.shell import shell_exec
from server.agent.tools.file import (
    file_read, file_write, file_str_replace,
    file_find_by_name, file_find_in_content,
)
from server.agent.tools.message import message_notify_user, message_ask_user
from server.agent.tools.browser import (
    browser_navigate, browser_view, browser_click,
    browser_input, browser_move_mouse, browser_press_key,
    browser_select_option, browser_scroll_up, browser_scroll_down,
    browser_console_exec, browser_console_view, browser_save_image,
    image_view,
)
from server.agent.tools.mcp import mcp_call_tool, mcp_list_tools, get_mcp_manager

TOOLS = {
    "info_search_web": info_search_web,
    "web_search": web_search,
    "web_browse": web_browse,
    "shell_exec": shell_exec,
    "file_read": file_read,
    "file_write": file_write,
    "file_str_replace": file_str_replace,
    "file_find_by_name": file_find_by_name,
    "file_find_in_content": file_find_in_content,
    "image_view": image_view,
    "message_notify_user": message_notify_user,
    "message_ask_user": message_ask_user,
    "browser_navigate": browser_navigate,
    "browser_view": browser_view,
    "browser_click": browser_click,
    "browser_input": browser_input,
    "browser_move_mouse": browser_move_mouse,
    "browser_press_key": browser_press_key,
    "browser_select_option": browser_select_option,
    "browser_scroll_up": browser_scroll_up,
    "browser_scroll_down": browser_scroll_down,
    "browser_console_exec": browser_console_exec,
    "browser_console_view": browser_console_view,
    "browser_save_image": browser_save_image,
    "mcp_call_tool": mcp_call_tool,
    "mcp_list_tools": mcp_list_tools,
}

message_notify = message_notify_user
file_find = file_find_by_name
