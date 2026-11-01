from common.mcp.models import (
    ServerConfig,
    ServerStatus,
    ServerTransport,
    ToolDefinition,
    ToolResult,
    decode_tool_name,
    encode_tool_name,
)


def test_encode_decode_tool_name():
    encoded = encode_tool_name("notion", "search_pages")
    assert encoded == "notion__search_pages"

    server, tool = decode_tool_name(encoded)
    assert server == "notion"
    assert tool == "search_pages"

    # Edge case: no namespace prefix
    s, t = decode_tool_name("standalone_tool")
    assert s == ""
    assert t == "standalone_tool"


def test_server_config_stdio_roundtrip():
    data = {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-notion", "--flag"],
        "env": {"API_KEY": "secret"},
        "readonly": True,
        "enabled": True,
        "timeout": 45.0,
    }
    cfg = ServerConfig.from_dict("notion", data)
    assert cfg.name == "notion"
    assert cfg.transport == "stdio"
    assert cfg.command == "uvx"
    assert cfg.args == ["mcp-server-notion", "--flag"]
    assert cfg.env == {"API_KEY": "secret"}
    assert cfg.readonly is True
    assert cfg.enabled is True
    assert cfg.timeout == 45.0

    out = cfg.to_dict()
    assert out["transport"] == "stdio"
    assert out["command"] == "uvx"
    assert out["args"] == ["mcp-server-notion", "--flag"]
    assert out["env"] == {"API_KEY": "secret"}
    assert out["readonly"] is True
    assert out["timeout"] == 45.0


def test_server_config_sse_roundtrip():
    data = {
        "transport": "sse",
        "url": "http://localhost:8000/sse",
        "headers": {"Authorization": "Bearer token"},
        "readonly": False,
        "enabled": False,
        "timeout_seconds": 15.0,
    }
    cfg = ServerConfig.from_dict("remote", data)
    assert cfg.name == "remote"
    assert cfg.transport == "sse"
    assert cfg.url == "http://localhost:8000/sse"
    assert cfg.headers == {"Authorization": "Bearer token"}
    assert cfg.readonly is False
    assert cfg.enabled is False
    assert cfg.timeout == 15.0

    out = cfg.to_dict()
    assert out["transport"] == "sse"
    assert out["url"] == "http://localhost:8000/sse"
    assert out["headers"] == {"Authorization": "Bearer token"}


def test_tool_definition_to_openai_tool():
    tool = ToolDefinition(
        server="fs",
        name="read_file",
        namespaced_name="fs__read_file",
        description="Read file contents from disk",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        readonly=True,
    )
    openai_tool = tool.to_openai_tool()
    assert openai_tool["type"] == "function"
    assert openai_tool["function"]["name"] == "fs__read_file"
    assert openai_tool["function"]["description"] == "Read file contents from disk"
    assert "path" in openai_tool["function"]["parameters"]["properties"]


def test_tool_result_and_server_status():
    res = ToolResult(name="fs__read_file", content="file contents", is_error=False)
    assert res.name == "fs__read_file"
    assert res.content == "file contents"
    assert res.is_error is False

    status = ServerStatus(
        name="fs",
        connected=True,
        status="connected",
        transport=ServerTransport.STDIO.value,
        tool_count=3,
    )
    assert status.connected is True
    assert status.status == "connected"
    assert status.tool_count == 3
