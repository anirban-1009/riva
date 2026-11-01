import argparse
import sys
from textwrap import dedent
from unittest.mock import patch

from riva_agent.cli import (
    cmd_mcp_add,
    cmd_mcp_call,
    cmd_mcp_list,
    cmd_mcp_remove,
    cmd_mcp_test,
    cmd_mcp_tools,
)

SERVER_SCRIPT = dedent(
    """
    import asyncio
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("cli-test")

    @server.tool(name="ping")
    def ping() -> str:
        '''Return pong.'''
        return "pong"

    if __name__ == "__main__":
        asyncio.run(server.run_stdio_async())
    """
)


def test_cli_mcp_add_and_remove(tmp_path, capsys):
    cfg_file = tmp_path / "config.yml"
    with patch("riva_agent.mcp.config.get_config_path", return_value=cfg_file):
        # 1. Add server
        args_add = argparse.Namespace(
            name="local_tool",
            transport="stdio",
            command="python",
            server_args=["-m", "mymodule"],
            env=["FOO=BAR", "DEBUG=1"],
            url=None,
            readonly=True,
            disabled=False,
            timeout=15.0,
        )
        rc = cmd_mcp_add(args_add)
        assert rc == 0
        captured = capsys.readouterr()
        assert "Added MCP server 'local_tool'" in captured.out
        assert "Transport: stdio" in captured.out
        assert "Read-Only: True" in captured.out

        # 2. List servers
        rc = cmd_mcp_list(argparse.Namespace())
        assert rc == 0
        captured = capsys.readouterr()
        assert "local_tool" in captured.out
        assert "stdio" in captured.out

        # 3. Remove server
        args_rm = argparse.Namespace(name="local_tool")
        rc = cmd_mcp_remove(args_rm)
        assert rc == 0
        captured = capsys.readouterr()
        assert "Removed MCP server 'local_tool'" in captured.out

        # 4. Remove again should return error code 1
        rc = cmd_mcp_remove(args_rm)
        assert rc == 1


def test_cli_mcp_add_error(tmp_path, capsys):
    cfg_file = tmp_path / "config.yml"
    with patch("riva_agent.mcp.config.get_config_path", return_value=cfg_file):
        args_invalid = argparse.Namespace(
            name="broken",
            transport="stdio",
            command=None,
            server_args=[],
            env=[],
            url=None,
            readonly=False,
            disabled=False,
            timeout=30.0,
        )
        rc = cmd_mcp_add(args_invalid)
        assert rc == 1
        captured = capsys.readouterr()
        assert "Error adding MCP server" in captured.err


def test_cli_mcp_list_empty(tmp_path, capsys):
    cfg_file = tmp_path / "config.yml"
    with patch("riva_agent.mcp.config.get_config_path", return_value=cfg_file):
        rc = cmd_mcp_list(argparse.Namespace())
        assert rc == 0
        captured = capsys.readouterr()
        assert "No MCP servers configured." in captured.out


def test_cli_mcp_test_and_tools_and_call(tmp_path, capsys):
    cfg_file = tmp_path / "config.yml"
    with patch("riva_agent.mcp.config.get_config_path", return_value=cfg_file):
        # Register a working test server
        args_add = argparse.Namespace(
            name="live_server",
            transport="stdio",
            command=sys.executable,
            server_args=["-c", SERVER_SCRIPT],
            env=[],
            url=None,
            readonly=False,
            disabled=False,
            timeout=10.0,
        )
        assert cmd_mcp_add(args_add) == 0
        capsys.readouterr()

        # Test connectivity
        rc_test = cmd_mcp_test(argparse.Namespace(server=None))
        assert rc_test == 0
        captured = capsys.readouterr()
        assert "Connected" in captured.out

        # List tools
        rc_tools = cmd_mcp_tools(argparse.Namespace(server="live_server"))
        assert rc_tools == 0
        captured = capsys.readouterr()
        assert "live_server__ping" in captured.out

        # Call tool
        rc_call = cmd_mcp_call(argparse.Namespace(server="live_server", tool="ping", args="{}"))
        assert rc_call == 0
        captured = capsys.readouterr()
        assert "pong" in captured.out

        # Call with invalid JSON
        rc_call_bad = cmd_mcp_call(argparse.Namespace(server="live_server", tool="ping", args="{invalid-json}"))
        assert rc_call_bad == 1

        # Call unknown server
        rc_unknown = cmd_mcp_call(argparse.Namespace(server="nonexistent", tool="ping", args="{}"))
        assert rc_unknown == 1
