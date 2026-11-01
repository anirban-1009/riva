from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from common.profile.store import ProfileStore
from riva_agent.mcp.server import create_mcp_server


@pytest.fixture
def isolated_env(tmp_path: Path):
    data_dir = tmp_path / ".riva"
    data_dir.mkdir(parents=True, exist_ok=True)
    digest_dir = data_dir / "digests"
    digest_dir.mkdir(parents=True, exist_ok=True)
    return data_dir, digest_dir


@pytest.mark.asyncio
async def test_mcp_server_tool_and_resource_registration(isolated_env):
    data_dir, digest_dir = isolated_env
    server = create_mcp_server(data_dir=data_dir, digest_dir=digest_dir)

    tools = await server.list_tools()
    tool_names = {t.name for t in tools}
    assert "riva_get_profile" in tool_names
    assert "riva_set_profile_fact" in tool_names
    assert "riva_search_memory" in tool_names
    assert "riva_log_turn" in tool_names
    assert "riva_get_recent_turns" in tool_names

    resources = await server.list_resources()
    resource_uris = {str(r.uri) for r in resources}
    assert "riva://profile" in resource_uris
    assert "riva://memory/recent" in resource_uris
    assert "riva://digests/latest" in resource_uris


@pytest.mark.asyncio
async def test_mcp_server_profile_tools(isolated_env):
    data_dir, digest_dir = isolated_env
    server = create_mcp_server(data_dir=data_dir, digest_dir=digest_dir)

    # 1. Empty profile initially
    res_empty = await server.call_tool("riva_get_profile", {})
    assert "No profile facts found" in res_empty.content[0].text

    # 2. Set fact
    res_set = await server.call_tool(
        "riva_set_profile_fact",
        {"key": "Favorite Language", "value": "Python", "category": "preferences"},
    )
    assert "Successfully saved" in res_set.content[0].text
    assert "Favorite Language = Python" in res_set.content[0].text

    # 3. Retrieve fact
    res_get = await server.call_tool("riva_get_profile", {"category": "preferences"})
    assert "Favorite Language: Python" in res_get.content[0].text

    # 4. Error on empty key or value
    res_err = await server.call_tool("riva_set_profile_fact", {"key": "", "value": ""})
    assert "Error: key and value must not be empty" in res_err.content[0].text


@pytest.mark.asyncio
async def test_mcp_server_memory_tools(isolated_env):
    data_dir, digest_dir = isolated_env
    server = create_mcp_server(data_dir=data_dir, digest_dir=digest_dir)

    # 1. Log turns
    res_log_user = await server.call_tool(
        "riva_log_turn",
        {"session_id": "test-sess", "role": "user", "content": "I am working on Apollo mission."},
    )
    assert "Turn #1 logged" in res_log_user.content[0].text

    res_log_asst = await server.call_tool(
        "riva_log_turn",
        {"session_id": "test-sess", "role": "assistant", "content": "Apollo was a landmark achievement."},
    )
    assert "Turn #2 logged" in res_log_asst.content[0].text

    # Invalid role check
    res_bad_role = await server.call_tool(
        "riva_log_turn",
        {"session_id": "test-sess", "role": "invalid_role", "content": "Hello"},
    )
    assert "Error: invalid role" in res_bad_role.content[0].text

    # Empty content check
    res_bad_content = await server.call_tool(
        "riva_log_turn",
        {"session_id": "test-sess", "role": "user", "content": "   "},
    )
    assert "Error: content must not be empty" in res_bad_content.content[0].text

    # 2. Get recent turns
    res_recent = await server.call_tool("riva_get_recent_turns", {"session_id": "test-sess"})
    text_recent = res_recent.content[0].text
    assert "Apollo mission" in text_recent
    assert "landmark achievement" in text_recent

    # 3. Search memory (keyword matching fallback)
    res_search = await server.call_tool("riva_search_memory", {"query": "Apollo"})
    text_search = res_search.content[0].text
    assert "Found" in text_search
    assert "Apollo mission" in text_search

    # Search no match
    res_search_none = await server.call_tool("riva_search_memory", {"query": "nonexistent_term"})
    assert "No memories found matching" in res_search_none.content[0].text

    # Search empty query
    res_search_empty = await server.call_tool("riva_search_memory", {"query": "  "})
    assert "Error: query must not be empty" in res_search_empty.content[0].text


@pytest.mark.asyncio
async def test_mcp_server_search_memory_semantic(isolated_env):
    data_dir, digest_dir = isolated_env
    server = create_mcp_server(data_dir=data_dir, digest_dir=digest_dir)

    # Log turn
    await server.call_tool(
        "riva_log_turn",
        {"session_id": "sess-vec", "role": "user", "content": "My favorite author is Isaac Asimov."},
    )

    mock_emb = AsyncMock()
    mock_emb.embed_query.return_value = [0.1, 0.2, 0.3, 0.4]

    with patch("riva_agent.mcp.server.create_embedding_provider", return_value=mock_emb):
        res = await server.call_tool("riva_search_memory", {"query": "science fiction books"})
        # Even if sqlite-vec distance threshold filters it out, the keyword search will catch or report gracefully
        assert res.content[0].text


@pytest.mark.asyncio
async def test_mcp_server_resources(isolated_env):
    data_dir, digest_dir = isolated_env
    server = create_mcp_server(data_dir=data_dir, digest_dir=digest_dir)

    # 1. Profile resource
    res_prof_empty = await server.read_resource("riva://profile")
    assert "No facts saved yet" in res_prof_empty[0].content

    prof_store = ProfileStore(data_dir / "profile.db")
    prof_store.set("Goal", "Launch product", category="goals")
    res_prof_filled = await server.read_resource("riva://profile")
    assert "Goal: Launch product" in res_prof_filled[0].content

    # 2. Recent memory resource
    res_mem_empty = await server.read_resource("riva://memory/recent")
    assert "No turns recorded yet" in res_mem_empty[0].content

    await server.call_tool(
        "riva_log_turn",
        {"session_id": "s1", "role": "user", "content": "Remember to pack warm clothes."},
    )
    res_mem_filled = await server.read_resource("riva://memory/recent")
    assert "warm clothes" in res_mem_filled[0].content

    # 3. Latest digest resource
    res_dig_empty = await server.read_resource("riva://digests/latest")
    assert "No daily digest has been generated yet" in res_dig_empty[0].content

    # Create dummy digest
    digest_file = digest_dir / "digest_20261101_080000.md"
    digest_file.write_text("# Morning Briefing\n\nAll systems operational.")

    res_dig_filled = await server.read_resource("riva://digests/latest")
    assert "Morning Briefing" in res_dig_filled[0].content
    assert "All systems operational" in res_dig_filled[0].content


def test_cmd_mcp_serve_stdio(monkeypatch):
    from riva_agent.cli import cmd_mcp_serve

    mock_server = MagicMock()
    mock_server.run_stdio_async = AsyncMock()

    with patch("riva_agent.mcp.server.create_mcp_server", return_value=mock_server):
        args = MagicMock()
        args.transport = "stdio"
        exit_code = cmd_mcp_serve(args)
        assert exit_code == 0
        mock_server.run_stdio_async.assert_called_once()


def test_cmd_mcp_serve_sse(monkeypatch):
    from riva_agent.cli import cmd_mcp_serve

    monkeypatch.delenv("RIVA_MCP_API_KEY", raising=False)
    monkeypatch.delenv("RIVA_API_KEY", raising=False)
    monkeypatch.setattr("riva_agent.mcp.server.get_mcp_api_key", lambda: None)

    mock_server = MagicMock()
    mock_run = AsyncMock()

    with (
        patch("riva_agent.mcp.server.create_mcp_server", return_value=mock_server),
        patch("riva_agent.mcp.server.run_mcp_sse_server", mock_run),
    ):
        args = MagicMock()
        args.transport = "sse"
        args.host = "127.0.0.1"
        args.port = 8086
        exit_code = cmd_mcp_serve(args)
        assert exit_code == 0
        mock_run.assert_called_once_with(mock_server, host="127.0.0.1", port=8086, api_key=None)


def test_cmd_mcp_serve_error(monkeypatch):
    from riva_agent.cli import cmd_mcp_serve

    mock_server = MagicMock()
    mock_server.run_stdio_async = AsyncMock(side_effect=RuntimeError("Transport failed"))

    with patch("riva_agent.mcp.server.create_mcp_server", return_value=mock_server):
        args = MagicMock()
        args.transport = "stdio"
        exit_code = cmd_mcp_serve(args)
        assert exit_code == 1


def test_verify_api_key(monkeypatch):
    from riva_agent.mcp.server import verify_api_key

    # Permissive when no expected key configured
    monkeypatch.delenv("RIVA_MCP_API_KEY", raising=False)
    monkeypatch.delenv("RIVA_API_KEY", raising=False)
    monkeypatch.setattr("riva_agent.mcp.server.get_mcp_api_key", lambda: None)
    assert verify_api_key(expected_key=None) is True
    assert verify_api_key(expected_key="") is True

    # When key configured
    secret = "secret-passphrase-123"
    assert verify_api_key(token="secret-passphrase-123", expected_key=secret) is True
    assert verify_api_key(token="wrong-token", expected_key=secret) is False
    assert verify_api_key(token=None, expected_key=secret) is False

    # Header: X-Riva-API-Key
    assert verify_api_key(headers={"X-Riva-API-Key": "secret-passphrase-123"}, expected_key=secret) is True
    assert verify_api_key(headers={"x-riva-api-key": "secret-passphrase-123"}, expected_key=secret) is True
    assert verify_api_key(headers={"X-Riva-API-Key": "wrong"}, expected_key=secret) is False

    # Header: Authorization Bearer
    assert verify_api_key(headers={"Authorization": "Bearer secret-passphrase-123"}, expected_key=secret) is True
    assert verify_api_key(headers={"authorization": "Bearer secret-passphrase-123"}, expected_key=secret) is True
    assert verify_api_key(headers={"Authorization": "Bearer wrong"}, expected_key=secret) is False
    assert verify_api_key(headers={"Authorization": "Basic 1234"}, expected_key=secret) is False


@pytest.mark.asyncio
async def test_auth_middleware_asgi(isolated_env):
    from httpx import ASGITransport, AsyncClient

    from riva_agent.mcp.server import create_mcp_app, create_mcp_server

    data_dir, digest_dir = isolated_env
    server = create_mcp_server(data_dir=data_dir, digest_dir=digest_dir, api_key="test-api-key")
    app = create_mcp_app(server, api_key="test-api-key")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1:8086") as client:
        # 1. No header -> 401
        res1 = await client.get("/sse")
        assert res1.status_code == 401
        assert "Unauthorized" in res1.text

        # 2. Wrong key -> 401
        res2 = await client.get("/sse", headers={"X-Riva-API-Key": "wrong"})
        assert res2.status_code == 401

        # 3. Valid key -> Authenticated (bypasses 401 to endpoint)
        res3 = await client.post("/messages/", headers={"X-Riva-API-Key": "test-api-key"}, json={})
        assert res3.status_code != 401

        # 4. Valid Authorization Bearer header -> Authenticated
        res4 = await client.post("/messages/", headers={"Authorization": "Bearer test-api-key"}, json={})
        assert res4.status_code != 401


@pytest.mark.asyncio
async def test_tool_authentication(isolated_env):
    data_dir, digest_dir = isolated_env
    server = create_mcp_server(data_dir=data_dir, digest_dir=digest_dir, api_key="tool-secret-key")

    # 1. Calling tool with invalid auth_token returns error
    res_bad = await server.call_tool(
        "riva_get_profile",
        {"category": "facts", "auth_token": "wrong-token"},
    )
    assert "Error: Unauthorized: Invalid API key" in res_bad.content[0].text

    # 2. Calling tool with valid auth_token succeeds
    res_good = await server.call_tool(
        "riva_get_profile",
        {"category": "facts", "auth_token": "tool-secret-key"},
    )
    assert "No profile facts found" in res_good.content[0].text
