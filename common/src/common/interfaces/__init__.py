"""Interfaces package for Riva Agent.

Historically planned protocols (like the bespoke Plugin protocol) reside here
with explicit documentation of their supersession by Model Context Protocol (MCP).
"""

from common.interfaces.plugin import (
    GenieCoordinator,
    PluginContext,
    ToolDefinition,
    ToolResult,
)

__all__ = [
    "GenieCoordinator",
    "PluginContext",
    "ToolDefinition",
    "ToolResult",
]
