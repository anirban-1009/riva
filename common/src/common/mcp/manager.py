import asyncio
import logging
from typing import Any

from common.mcp.client import MCPClient
from common.mcp.models import (
    ServerConfig,
    ServerStatus,
    ToolDefinition,
    ToolResult,
    decode_tool_name,
)

logger = logging.getLogger(__name__)


class MCPClientManager:
    """Coordinates and manages connections across multiple Model Context Protocol servers."""

    def __init__(self, server_configs: list[ServerConfig] | None = None) -> None:
        self.clients: dict[str, MCPClient] = {}
        if server_configs:
            for cfg in server_configs:
                self.register_server(cfg)

    def register_server(self, config: ServerConfig) -> MCPClient:
        """Register or update an MCP server configuration."""
        if config.name in self.clients:
            logger.info("Replacing existing MCP client for '%s'", config.name)
        client = MCPClient(config)
        self.clients[config.name] = client
        return client

    async def unregister_server(self, name: str) -> bool:
        """Close and remove an MCP server from management."""
        client = self.clients.pop(name, None)
        if client:
            await client.close()
            return True
        return False

    def get_client(self, name: str) -> MCPClient | None:
        """Retrieve client by server name."""
        return self.clients.get(name)

    async def connect_all(self) -> dict[str, bool]:
        """Connect to all registered and enabled servers concurrently."""
        tasks = [client.connect() for client in self.clients.values() if client.config.enabled]
        names = [client.config.name for client in self.clients.values() if client.config.enabled]

        if not tasks:
            return {}

        results = await asyncio.gather(*tasks, return_exceptions=True)
        outcome: dict[str, bool] = {}
        for name, res in zip(names, results):
            if isinstance(res, Exception):
                logger.warning("Error connecting to server '%s': %s", name, res)
                outcome[name] = False
            else:
                outcome[name] = bool(res)
        return outcome

    def get_all_tools(self) -> list[ToolDefinition]:
        """Collect all tools currently exposed across connected servers."""
        tools: list[ToolDefinition] = []
        for client in self.clients.values():
            if client.is_connected:
                tools.extend(client.tools.values())
        return tools

    def get_openai_tools(self) -> list[dict[str, Any]]:
        """Return all tools formatted as an OpenAI-compatible function definition array."""
        return [tool.to_openai_tool() for tool in self.get_all_tools()]

    async def call_tool(self, namespaced_name: str, arguments: dict[str, Any] | None = None) -> ToolResult:
        """Dispatch a tool call to the appropriate server based on namespaced name."""
        server_name, orig_name = decode_tool_name(namespaced_name)

        target_client: MCPClient | None = None
        if server_name and server_name in self.clients:
            target_client = self.clients[server_name]
        else:
            # Fallback search if passed without server prefix
            for client in self.clients.values():
                if namespaced_name in client.tools or orig_name in {t.name for t in client.tools.values()}:
                    target_client = client
                    break

        if not target_client:
            return ToolResult(
                name=namespaced_name,
                content=f"Error: No MCP server found for tool '{namespaced_name}'.",
                is_error=True,
            )

        return await target_client.call_tool(orig_name or namespaced_name, arguments)

    def get_server_statuses(self) -> list[ServerStatus]:
        """Retrieve status records for all registered servers."""
        return [client.status for client in self.clients.values()]

    async def close_all(self) -> None:
        """Gracefully close all active client sessions."""
        close_tasks = [client.close() for client in self.clients.values()]
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
