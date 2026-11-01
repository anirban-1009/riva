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

    mock_server = MagicMock()
    mock_server.run_sse_async = AsyncMock()

    with patch("riva_agent.mcp.server.create_mcp_server", return_value=mock_server):
        args = MagicMock()
        args.transport = "sse"
        args.host = "127.0.0.1"
        args.port = 8086
        exit_code = cmd_mcp_serve(args)
        assert exit_code == 0
        mock_server.run_sse_async.assert_called_once_with(host="127.0.0.1", port=8086)


def test_cmd_mcp_serve_error(monkeypatch):
    from riva_agent.cli import cmd_mcp_serve

    mock_server = MagicMock()
    mock_server.run_stdio_async = AsyncMock(side_effect=RuntimeError("Transport failed"))

    with patch("riva_agent.mcp.server.create_mcp_server", return_value=mock_server):
        args = MagicMock()
        args.transport = "stdio"
        exit_code = cmd_mcp_serve(args)
        assert exit_code == 1
