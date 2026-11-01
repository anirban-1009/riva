import asyncio
import logging
import os
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client

from common.mcp.models import (
    ServerConfig,
    ServerStatus,
    ServerTransport,
    ToolDefinition,
    ToolResult,
    decode_tool_name,
    encode_tool_name,
)

logger = logging.getLogger(__name__)


def extract_tool_result_content(result: Any) -> str:
    """Extract clean string content from an MCP CallToolResult or return string representation."""
    if hasattr(result, "content") and isinstance(result.content, list):
        text_parts: list[str] = []
        for part in result.content:
            if hasattr(part, "text"):
                text_parts.append(str(part.text))
            elif isinstance(part, dict) and "text" in part:
                text_parts.append(str(part["text"]))
            else:
                text_parts.append(str(part))
        return "\n".join(text_parts).strip()
    return str(result).strip()


class MCPClient:
    """Manages connection and tool execution for a single Model Context Protocol server."""

    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self.status = ServerStatus(
            name=config.name,
            connected=False,
            status="disabled" if not config.enabled else "disconnected",
            transport=config.transport,
        )
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tools: dict[str, ToolDefinition] = {}
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        return self._session is not None and self.status.connected

    @property
    def tools(self) -> dict[str, ToolDefinition]:
        return self._tools

    async def connect(self) -> bool:
        """Establish connection to the MCP server and discover exposed tools."""
        if not self.config.enabled:
            self.status.status = "disabled"
            self.status.connected = False
            return False

        async with self._lock:
            if self.is_connected:
                return True

            stack = AsyncExitStack()
            try:
                if self.config.transport == ServerTransport.STDIO.value:
                    if not self.config.command:
                        raise ValueError(f"Server '{self.config.name}' requires a 'command' for stdio transport")

                    merged_env = dict(os.environ)
                    if self.config.env:
                        merged_env.update(self.config.env)

                    params = StdioServerParameters(
                        command=self.config.command,
                        args=self.config.args,
                        env=merged_env,
                    )
                    read_stream, write_stream = await stack.enter_async_context(stdio_client(params))

                elif self.config.transport == ServerTransport.SSE.value:
                    if not self.config.url:
                        raise ValueError(f"Server '{self.config.name}' requires a 'url' for sse transport")

                    read_stream, write_stream = await stack.enter_async_context(
                        sse_client(
                            url=self.config.url,
                            headers=self.config.headers or None,
                            timeout=self.config.timeout,
                        )
                    )
                else:
                    raise ValueError(f"Unsupported transport '{self.config.transport}' for server '{self.config.name}'")

                session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
                await asyncio.wait_for(session.initialize(), timeout=self.config.timeout)

                self._stack = stack
                self._session = session
                await self.refresh_tools()

                self.status = ServerStatus(
                    name=self.config.name,
                    connected=True,
                    status="connected",
                    transport=self.config.transport,
                    tool_count=len(self._tools),
                    error=None,
                )
                logger.info(
                    "Connected to MCP server '%s' (%s, %d tools)",
                    self.config.name,
                    self.config.transport,
                    len(self._tools),
                )
                return True

            except Exception as e:
                logger.warning("Failed to connect to MCP server '%s': %s", self.config.name, e)
                await stack.aclose()
                self._stack = None
                self._session = None
                self.status = ServerStatus(
                    name=self.config.name,
                    connected=False,
                    status="unhealthy",
                    transport=self.config.transport,
                    tool_count=0,
                    error=str(e),
                )
                return False

    async def refresh_tools(self) -> list[ToolDefinition]:
        """Fetch available tools from the server and update the local registry."""
        if not self._session:
            raise RuntimeError(f"Cannot refresh tools on unconnected server '{self.config.name}'")

        result = await asyncio.wait_for(self._session.list_tools(), timeout=self.config.timeout)
        new_tools: dict[str, ToolDefinition] = {}

        raw_tools = getattr(result, "tools", []) or []
        for t in raw_tools:
            name = getattr(t, "name", "")
            desc = getattr(t, "description", "") or ""
            input_schema = getattr(t, "input_schema", None)
            if input_schema is None:
                input_schema = getattr(t, "inputSchema", {"type": "object", "properties": {}})

            namespaced = encode_tool_name(self.config.name, name)
            tool_def = ToolDefinition(
                server=self.config.name,
                name=name,
                namespaced_name=namespaced,
                description=desc,
                parameters=dict(input_schema) if isinstance(input_schema, dict) else {},
                readonly=self.config.readonly,
            )
            new_tools[namespaced] = tool_def

        self._tools = new_tools
        self.status.tool_count = len(new_tools)
        return list(new_tools.values())

    async def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> ToolResult:
        """Execute a tool call on this MCP server."""
        if not self.is_connected:
            connected = await self.connect()
            if not connected or not self._session:
                err_detail = self.status.error or "connection failed"
                return ToolResult(
                    name=tool_name,
                    content=f"Error: Server '{self.config.name}' is unreachable ({err_detail}).",
                    is_error=True,
                )

        # Allow passing either namespaced or original tool name
        server, orig_name = decode_tool_name(tool_name)
        target_name = orig_name if server == self.config.name else tool_name

        try:
            call_res = await asyncio.wait_for(
                self._session.call_tool(target_name, arguments or {}),
                timeout=self.config.timeout,
            )
            content = extract_tool_result_content(call_res)
            is_error = bool(getattr(call_res, "is_error", False))
            return ToolResult(
                name=tool_name,
                content=content,
                is_error=is_error,
                raw=call_res,
            )
        except Exception as e:
            logger.warning("Tool call '%s' failed on server '%s': %s", tool_name, self.config.name, e)
            return ToolResult(
                name=tool_name,
                content=f"Error executing tool '{tool_name}': {e}",
                is_error=True,
            )

    async def ping(self) -> bool:
        """Send a ping to check server liveness."""
        if not self.is_connected or not self._session:
            return False
        try:
            await asyncio.wait_for(self._session.send_ping(), timeout=min(5.0, self.config.timeout))
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Gracefully terminate connection and cleanup subprocess / streams."""
        async with self._lock:
            if self._stack:
                try:
                    await self._stack.aclose()
                except Exception as e:
                    logger.debug("Error closing MCP client stack for '%s': %s", self.config.name, e)
                finally:
                    self._stack = None
                    self._session = None
            self.status.connected = False
            if self.status.status != "disabled":
                self.status.status = "disconnected"
