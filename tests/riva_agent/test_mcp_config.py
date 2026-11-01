import pytest
import yaml

from riva_agent.mcp.config import (
    add_mcp_server,
    get_mcp_client_manager,
    get_mcp_servers,
    load_mcp_config,
    remove_mcp_server,
    reset_mcp_client_manager,
)


def test_mcp_config_add_and_get(tmp_path):
    cfg_file = tmp_path / "config.yml"
    cfg_file.write_text("provider: openai\nmodel: gemma\n", encoding="utf-8")

    # Add stdio server
    server = add_mcp_server(
        name="notes",
        transport="stdio",
        command="npx",
        args=["-y", "@mcp/fs", "/tmp"],
        env={"NOTE_PATH": "/tmp"},
        readonly=True,
        timeout=25.0,
        path=cfg_file,
    )
    assert server.name == "notes"
    assert server.transport == "stdio"
    assert server.command == "npx"
    assert server.readonly is True

    # Verify loaded
    mcp_cfg = load_mcp_config(cfg_file)
    assert "notes" in mcp_cfg["servers"]

    servers = get_mcp_servers(cfg_file)
    assert len(servers) == 1
    assert servers[0].name == "notes"
    assert servers[0].command == "npx"
    assert servers[0].args == ["-y", "@mcp/fs", "/tmp"]

    # Verify original keys were preserved
    with cfg_file.open("r", encoding="utf-8") as f:
        full_data = yaml.safe_load(f)
    assert full_data["provider"] == "openai"
    assert full_data["model"] == "gemma"


def test_mcp_config_add_validation_errors(tmp_path):
    cfg_file = tmp_path / "config.yml"

    # stdio without command
    with pytest.raises(ValueError, match="command"):
        add_mcp_server("invalid_stdio", transport="stdio", command=None, path=cfg_file)

    # sse without url
    with pytest.raises(ValueError, match="url"):
        add_mcp_server("invalid_sse", transport="sse", url=None, path=cfg_file)


def test_mcp_config_remove(tmp_path):
    cfg_file = tmp_path / "config.yml"

    add_mcp_server("srv1", transport="stdio", command="python", path=cfg_file)
    add_mcp_server("srv2", transport="sse", url="http://localhost:8080", path=cfg_file)

    assert len(get_mcp_servers(cfg_file)) == 2

    # Remove existing
    removed = remove_mcp_server("srv1", path=cfg_file)
    assert removed is True
    assert len(get_mcp_servers(cfg_file)) == 1
    assert get_mcp_servers(cfg_file)[0].name == "srv2"

    # Remove non-existent
    assert remove_mcp_server("non_existent", path=cfg_file) is False


def test_get_mcp_client_manager_singleton():
    reset_mcp_client_manager()
    mgr1 = get_mcp_client_manager()
    mgr2 = get_mcp_client_manager()
    assert mgr1 is mgr2
    reset_mcp_client_manager()
