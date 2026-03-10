"""
MCP (Model Context Protocol) tools for the AI agent.
Supports calling external MCP servers via HTTP using AIRFORCE_API_KEY for auth.
"""
import os
import json
import urllib.request
import urllib.error
import ssl
from typing import Optional, List, Dict, Any

from server.agent.models.tool_result import ToolResult


def _load_dotenv() -> None:
    env_path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


_load_dotenv()

AIRFORCE_API_KEY = os.environ.get("AIRFORCE_API_KEY", "")
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "")


class MCPClientManager:
    """Manages MCP server connections and tool execution via HTTP."""

    def __init__(self) -> None:
        self._servers: Dict[str, Dict[str, Any]] = {}
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register_server(self, name: str, config: Dict[str, Any]) -> None:
        self._servers[name] = config

    def register_tool(self, name: str, description: str, server: str,
                      parameters: Optional[Dict[str, Any]] = None) -> None:
        self._tools[name] = {
            "name": name,
            "description": description,
            "server": server,
            "parameters": parameters or {},
        }

    def get_all_tools(self) -> List[Dict[str, Any]]:
        return list(self._tools.values())

    def _call_http_mcp(self, server_url: str, tool_name: str,
                       arguments: Dict[str, Any]) -> ToolResult:
        """Call an HTTP MCP server endpoint using Airforce API key as Bearer auth."""
        body = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }).encode("utf-8")

        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if AIRFORCE_API_KEY:
            headers["Authorization"] = "Bearer {}".format(AIRFORCE_API_KEY)

        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            server_url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            if "result" in result:
                content = result["result"].get("content", result["result"])
                return ToolResult(
                    success=True,
                    message="MCP '{}' result: {}".format(
                        tool_name, json.dumps(content, default=str)[:2000]),
                    data={"tool_name": tool_name, "content": content},
                )
            elif "error" in result:
                return ToolResult(
                    success=False,
                    message="MCP error: {}".format(result["error"]),
                    data={"error": result["error"]},
                )
        except urllib.error.HTTPError as e:
            return ToolResult(
                success=False,
                message="MCP HTTP {}: {}".format(e.code, e.reason),
                data={"error": str(e)},
            )
        except Exception as e:
            return ToolResult(
                success=False,
                message="MCP call failed: {}".format(str(e)),
                data={"error": str(e)},
            )
        return ToolResult(success=False, message="MCP call returned no result")

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """Execute an MCP tool via registered server or MCP_SERVER_URL env var."""
        if tool_name in self._tools:
            tool = self._tools[tool_name]
            server_name = tool.get("server", "")
            server_cfg = self._servers.get(server_name, {})
            server_url = server_cfg.get("url", "")
            if server_url:
                return self._call_http_mcp(server_url, tool_name, arguments)

        if MCP_SERVER_URL:
            return self._call_http_mcp(MCP_SERVER_URL, tool_name, arguments)

        return ToolResult(
            success=False,
            message=(
                "MCP tool '{}' called but no server configured. "
                "Set MCP_SERVER_URL in .env to enable external MCP tools."
            ).format(tool_name),
            data={"tool_name": tool_name, "arguments": arguments},
        )

    def list_remote_tools(self) -> ToolResult:
        """Fetch available tools from the configured MCP server."""
        if not MCP_SERVER_URL:
            local = self.get_all_tools()
            return ToolResult(
                success=True,
                message="No remote MCP server configured (set MCP_SERVER_URL in .env). "
                        "Local tools: {}".format(json.dumps(local, indent=2)),
                data={"tools": local, "count": len(local)},
            )

        body = json.dumps({
            "jsonrpc": "2.0", "id": 1,
            "method": "tools/list", "params": {},
        }).encode("utf-8")
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if AIRFORCE_API_KEY:
            headers["Authorization"] = "Bearer {}".format(AIRFORCE_API_KEY)

        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            MCP_SERVER_URL, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            tools = result.get("result", {}).get("tools", [])
            return ToolResult(
                success=True,
                message="MCP tools from {}: {}".format(
                    MCP_SERVER_URL, json.dumps(tools, indent=2)[:2000]),
                data={"tools": tools, "count": len(tools)},
            )
        except Exception as e:
            return ToolResult(
                success=False,
                message="Failed to list MCP tools: {}".format(str(e)),
                data={"error": str(e)},
            )

    def cleanup(self) -> None:
        self._servers.clear()
        self._tools.clear()


_mcp_manager = MCPClientManager()


def mcp_call_tool(tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> ToolResult:
    """Call an MCP tool by name. Uses AIRFORCE_API_KEY for Bearer auth."""
    return _mcp_manager.call_tool(tool_name, arguments or {})


def mcp_list_tools() -> ToolResult:
    """List available MCP tools (remote if MCP_SERVER_URL set, else local)."""
    return _mcp_manager.list_remote_tools()


def get_mcp_manager() -> MCPClientManager:
    return _mcp_manager
