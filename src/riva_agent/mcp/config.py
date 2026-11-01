import logging
from pathlib import Path
from typing import Any

import yaml

from common.mcp.manager import MCPClientManager
from common.mcp.models import ServerConfig
from riva_agent.config import _CONFIG_PATH

logger = logging.getLogger(__name__)


def get_config_path() -> Path:
    """Return the resolved path to config.yml."""
    return _CONFIG_PATH


def load_raw_config(path: Path | None = None) -> dict[str, Any]:
    """Load the raw config dictionary from config.yml."""
    target_path = path or get_config_path()
    if not target_path.exists():
        return {}
    try:
        with target_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning("Failed to parse config file at %s: %s", target_path, e)
        return {}


def save_raw_config(data: dict[str, Any], path: Path | None = None) -> None:
    """Safely persist updated dictionary into config.yml."""
    target_path = path or get_config_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def load_mcp_config(path: Path | None = None) -> dict[str, Any]:
    """Retrieve the 'mcp' configuration section."""
    raw = load_raw_config(path)
    return dict(raw.get("mcp", {}))


def get_mcp_servers(path: Path | None = None) -> list[ServerConfig]:
    """Parse and return all configured MCP server definitions."""
    mcp_cfg = load_mcp_config(path)
    servers_dict = mcp_cfg.get("servers", {}) or {}
    servers: list[ServerConfig] = []
    for name, s_data in servers_dict.items():
        if isinstance(s_data, dict):
            servers.append(ServerConfig.from_dict(name, s_data))
    return servers


def add_mcp_server(
    name: str,
    transport: str = "stdio",
    *,
    command: str | None = None,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    url: str | None = None,
    headers: dict[str, str] | None = None,
    readonly: bool = False,
    enabled: bool = True,
    timeout: float = 30.0,
    path: Path | None = None,
) -> ServerConfig:
    """Add or update an MCP server in config.yml."""
    clean_name = name.strip()
    clean_transport = transport.strip().lower()

    if clean_transport == "stdio" and not command:
        raise ValueError("Stdio transport requires a valid executable 'command'.")
    if clean_transport == "sse" and not url:
        raise ValueError("SSE transport requires a valid 'url'.")

    cfg_data = load_raw_config(path)
    if "mcp" not in cfg_data or not isinstance(cfg_data["mcp"], dict):
        cfg_data["mcp"] = {"enabled": True, "servers": {}}
    if "servers" not in cfg_data["mcp"] or not isinstance(cfg_data["mcp"]["servers"], dict):
        cfg_data["mcp"]["servers"] = {}

    server_obj = ServerConfig(
        name=clean_name,
        transport=clean_transport,
        command=command,
        args=args or [],
        env=env or {},
        url=url,
        headers=headers or {},
        readonly=readonly,
        enabled=enabled,
        timeout=timeout,
    )

    cfg_data["mcp"]["servers"][clean_name] = server_obj.to_dict()
    save_raw_config(cfg_data, path)
    logger.info("Configured MCP server '%s' (%s) saved to %s", clean_name, clean_transport, path or get_config_path())
    return server_obj


def remove_mcp_server(name: str, path: Path | None = None) -> bool:
    """Remove an MCP server from config.yml. Returns True if removed, False if not found."""
    clean_name = name.strip()
    cfg_data = load_raw_config(path)
    servers = (cfg_data.get("mcp") or {}).get("servers", {})
    if not isinstance(servers, dict) or clean_name not in servers:
        return False

    del servers[clean_name]
    save_raw_config(cfg_data, path)
    logger.info("Removed MCP server '%s' from %s", clean_name, path or get_config_path())
    return True


_manager_instance: MCPClientManager | None = None


def get_mcp_client_manager() -> MCPClientManager:
    """Retrieve or lazily instantiate the global MCPClientManager from config."""
    global _manager_instance
    if _manager_instance is None:
        servers = get_mcp_servers()
        _manager_instance = MCPClientManager(servers)
    return _manager_instance


def reset_mcp_client_manager() -> None:
    """Reset the singleton instance (useful for testing or config reloads)."""
    global _manager_instance
    _manager_instance = None
