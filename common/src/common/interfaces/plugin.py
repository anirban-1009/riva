"""Plugin Interface - Officially Superseded by Model Context Protocol (MCP).

Milestone 6 (M6) originally envisioned a bespoke Plugin protocol (PluginContext, Tool, etc.).
This bespoke abstraction has been officially superseded by the open Model Context Protocol (MCP)
standard implemented under `common.mcp` and managed via `common.mcp.MCPClientManager`.

Domain capabilities (such as `lighthouse-genie`) now act as lightweight MCP Coordinators
that discover, compose, and execute standard MCP tools rather than maintaining proprietary
tool-calling implementations.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from common.mcp.models import ToolDefinition, ToolResult

__all__ = [
    "GenieCoordinator",
    "PluginContext",
    "ToolDefinition",
    "ToolResult",
]


@dataclass
class PluginContext:
    """Historical context container for plugin execution.

    Superseded by MCP tool parameters and dynamic memory injection.
    """

    domain: str
    data: dict[str, Any] = field(default_factory=dict)
    memories: list[dict[str, Any]] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)


@runtime_checkable
class GenieCoordinator(Protocol):
    """Protocol for Genie domain coordinators consuming or exposing standard MCP tools."""

    name: str

    async def initialize(self) -> None:
        """Initialize connections to configured MCP servers or local data sources."""
        ...

    async def gather_context(self, **kwargs: Any) -> dict[str, Any]:
        """Gather domain-specific context from MCP tools or stores."""
        ...
