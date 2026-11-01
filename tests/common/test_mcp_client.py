import sys
from textwrap import dedent

import pytest

from common.mcp.client import MCPClient
from common.mcp.manager import MCPClientManager
from common.mcp.models import ServerConfig

SERVER_SCRIPT = dedent(
    """
    import asyncio
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("test-server")

    @server.tool(name="echo")
    def echo(message: str) -> str:
        '''Echo back a string message.'''
        return f"echo: {message}"

    @server.tool(name="add")
    def add(a: int, b: int) -> int:
        '''Add two integers.'''
        return a + b

    if __name__ == "__main__":
        asyncio.run(server.run_stdio_async())
    """
)


@pytest.fixture
def test_server_config():
    return ServerConfig(
        name="test_srv",
        transport="stdio",
        command=sys.executable,
        args=["-c", SERVER_SCRIPT],
        timeout=10.0,
    )


@pytest.mark.asyncio
async def test_mcp_client_lifecycle(test_server_config):
    client = MCPClient(test_server_config)
    assert not client.is_connected
    assert client.status.status == "disconnected"

    try:
        connected = await client.connect()
        assert connected is True
        assert client.is_connected is True
        assert client.status.status == "connected"
        assert client.status.tool_count == 2

        # Verify discovered tools
        tool_names = set(client.tools.keys())
        assert "test_srv__echo" in tool_names
        assert "test_srv__add" in tool_names

        # Verify ping
        assert await client.ping() is True

        # Call tool with namespaced name
        res_echo = await client.call_tool("test_srv__echo", {"message": "riva test"})
        assert not res_echo.is_error
        assert "echo: riva test" in res_echo.content

        # Call tool with original name
        res_add = await client.call_tool("add", {"a": 5, "b": 7})
        assert not res_add.is_error
        assert "12" in res_add.content

    finally:
        await client.close()
        assert not client.is_connected
        assert client.status.status == "disconnected"


@pytest.mark.asyncio
async def test_mcp_client_disabled():
    cfg = ServerConfig(
        name="disabled_srv",
        transport="stdio",
        command=sys.executable,
        args=["-c", "pass"],
        enabled=False,
    )
    client = MCPClient(cfg)
    connected = await client.connect()
    assert connected is False
    assert client.status.status == "disabled"
    await client.close()


@pytest.mark.asyncio
async def test_mcp_client_unreachable():
    cfg = ServerConfig(
        name="broken_srv",
        transport="stdio",
        command="non_existent_executable_12345",
        timeout=2.0,
    )
    client = MCPClient(cfg)
    connected = await client.connect()
    assert connected is False
    assert client.status.status == "unhealthy"

    res = await client.call_tool("any_tool", {})
    assert res.is_error is True
    assert "unreachable" in res.content
    await client.close()


@pytest.mark.asyncio
async def test_mcp_client_manager_coordination(test_server_config):
    manager = MCPClientManager([test_server_config])
    assert len(manager.clients) == 1
    assert manager.get_client("test_srv") is not None

    try:
        outcome = await manager.connect_all()
        assert outcome.get("test_srv") is True

        # Check tools aggregation
        all_tools = manager.get_all_tools()
        assert len(all_tools) == 2

        openai_tools = manager.get_openai_tools()
        assert len(openai_tools) == 2
        names = [t["function"]["name"] for t in openai_tools]
        assert "test_srv__echo" in names
        assert "test_srv__add" in names

        # Execute call through manager
        res = await manager.call_tool("test_srv__echo", {"message": "hello from manager"})
        assert not res.is_error
        assert "echo: hello from manager" in res.content

        # Test call to unknown tool
        res_unknown = await manager.call_tool("nonexistent__action", {})
        assert res_unknown.is_error is True

        # Check server statuses
        statuses = manager.get_server_statuses()
        assert len(statuses) == 1
        assert statuses[0].connected is True
        assert statuses[0].tool_count == 2

        # Unregister server
        removed = await manager.unregister_server("test_srv")
        assert removed is True
        assert len(manager.clients) == 0

    finally:
        await manager.close_all()
