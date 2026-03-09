from server.agent.tools.search import web_search, web_browse
from server.agent.tools.shell import shell_exec
from server.agent.tools.file import file_read, file_write, file_find
from server.agent.tools.message import message_notify

TOOLS = {
    "web_search": web_search,
    "web_browse": web_browse,
    "shell_exec": shell_exec,
    "file_read": file_read,
    "file_write": file_write,
    "file_find": file_find,
    "message_notify": message_notify,
}

TOOL_DESCRIPTIONS = {
    "web_search": "Search the web for information using DuckDuckGo",
    "web_browse": "Read and extract content from a web page URL",
    "shell_exec": "Execute shell commands (bash). Use for running code, installing packages, etc.",
    "file_read": "Read the contents of a file",
    "file_write": "Create or overwrite a file with content",
    "file_find": "Find files matching a pattern in a directory",
    "message_notify": "Send a progress message to the user",
}
