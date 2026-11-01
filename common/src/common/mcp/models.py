from dataclasses import dataclass, field
from enum import Enum
from typing import Any

NAMESPACE_SEPARATOR = "__"


class ServerTransport(str, Enum):
    STDIO = "stdio"
    SSE = "sse"


def encode_tool_name(server_name: str, tool_name: str) -> str:
    """Encode server and tool name into a namespaced identifier (e.g. 'notion__search')."""
    return f"{server_name}{NAMESPACE_SEPARATOR}{tool_name}"


def decode_tool_name(namespaced_name: str) -> tuple[str, str]:
    """Decode a namespaced identifier back into (server_name, tool_name).

    If no separator is present, returns ("", namespaced_name).
    """
    if NAMESPACE_SEPARATOR in namespaced_name:
        server, tool = namespaced_name.split(NAMESPACE_SEPARATOR, 1)
        return server, tool
    return "", namespaced_name


@dataclass
class ServerConfig:
    """Configuration for an MCP server."""

    name: str
    transport: str = "stdio"
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    readonly: bool = False
    enabled: bool = True
    timeout: float = 30.0

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> "ServerConfig":
        return cls(
            name=name,
            transport=data.get("transport", "stdio").lower(),
            command=data.get("command"),
            args=list(data.get("args", [])),
            env=dict(data.get("env", {})),
            url=data.get("url"),
            headers=dict(data.get("headers", {})),
            readonly=bool(data.get("readonly", False)),
            enabled=bool(data.get("enabled", True)),
            timeout=float(data.get("timeout", data.get("timeout_seconds", 30.0))),
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "transport": self.transport,
            "readonly": self.readonly,
            "enabled": self.enabled,
            "timeout": self.timeout,
        }
        if self.transport == "stdio":
            if self.command:
                data["command"] = self.command
            if self.args:
                data["args"] = self.args
            if self.env:
                data["env"] = self.env
        elif self.transport == "sse":
            if self.url:
                data["url"] = self.url
            if self.headers:
                data["headers"] = self.headers
        return data


@dataclass
class ToolDefinition:
    """Represents an executable tool exposed by an MCP server."""

    server: str
    name: str
    namespaced_name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})
    readonly: bool = False

    def to_openai_tool(self) -> dict[str, Any]:
        """Convert to OpenAI-compatible function definition format."""
        return {
            "type": "function",
            "function": {
                "name": self.namespaced_name,
                "description": self.description or f"Tool {self.name} on {self.server}",
                "parameters": self.parameters or {"type": "object", "properties": {}},
            },
        }


@dataclass
class ToolResult:
    """Result of an executed tool call."""

    name: str
    content: str
    tool_call_id: str | None = None
    is_error: bool = False
    raw: Any = None


@dataclass
class ServerStatus:
    """Health and discovery status of an MCP server."""

    name: str
    connected: bool
    status: str  # "connected", "unhealthy", "disconnected", "disabled"
    transport: str
    tool_count: int = 0
    error: str | None = None
