import pytest

from common.llm.providers import AssistantTurn, ToolCall
from common.mcp.manager import MCPClientManager
from common.mcp.models import ToolResult
from riva_agent.intelligence.agent_loop import (
    ensure_source_citations,
    extract_sources_from_tool_result,
    is_tool_readonly,
    parse_prompt_tool_call,
    run_agent_loop,
)


def test_is_tool_readonly():
    assert is_tool_readonly("search__search") is True
    assert is_tool_readonly("fs__read_file") is True
    assert is_tool_readonly("notes__fetch_content") is True
    assert is_tool_readonly("custom_tool", is_marked_readonly=True) is True

    # Mutating verbs
    assert is_tool_readonly("fs__delete_file") is False
    assert is_tool_readonly("db__drop_table") is False
    assert is_tool_readonly("mail__send_message") is False
    assert is_tool_readonly("notes__create_page") is False
    assert is_tool_readonly("api__update_record") is False


def test_extract_sources_and_citation_formatting():
    search_output = (
        "Found 2 search results:\n\n"
        "1. Apple Open Source MLX\n"
        "   URL: https://opensource.apple.com/projects/mlx/\n"
        "   Summary: MLX is an array framework...\n\n"
        "2. GitHub - ml-explore/mlx\n"
        "   URL: https://github.com/ml-explore/mlx\n"
        "   Summary: An array framework for Apple silicon."
    )
    sources = extract_sources_from_tool_result("search__search", {"query": "mlx"}, search_output)
    assert len(sources) == 2
    assert sources[0].url == "https://opensource.apple.com/projects/mlx/"
    assert "Apple Open Source MLX" in sources[0].title
    assert sources[1].url == "https://github.com/ml-explore/mlx"

    # Test file source extraction
    file_sources = extract_sources_from_tool_result("fs__read_file", {"path": "/Users/test/notes.md"}, "content")
    assert len(file_sources) == 1
    assert file_sources[0].identifier == "/Users/test/notes.md"
    assert "notes.md" in file_sources[0].title

    # Test citation enforcement in text
    raw_response = "MLX is Apple's open source machine learning framework."
    cited = ensure_source_citations(raw_response, sources)
    assert "### Sources" in cited
    assert "[Apple Open Source MLX](https://opensource.apple.com/projects/mlx/)" in cited

    # Test idempotent: does not duplicate if already cited
    already_cited = f"{raw_response}\n\n### Sources\n- [Apple](https://apple.com)"
    not_duplicated = ensure_source_citations(already_cited, sources)
    assert not_duplicated == already_cited


def test_parse_prompt_tool_call():
    # JSON in code fence
    fence_text = '```json\n{"tool_call": {"name": "search__search", "arguments": {"query": "riva"}}}\n```'
    tc = parse_prompt_tool_call(fence_text)
    assert tc is not None
    assert tc.name == "search__search"
    assert tc.arguments == {"query": "riva"}

    # Standard JSON
    json_text = 'I will call the tool: {"name": "fs__read_file", "arguments": {"path": "a.txt"}}'
    tc2 = parse_prompt_tool_call(json_text)
    assert tc2 is not None
    assert tc2.name == "fs__read_file"
    assert tc2.arguments == {"path": "a.txt"}

    # Invalid JSON
    assert parse_prompt_tool_call("Just normal text without any json") is None


class MockMultiTurnProvider:
    """Mock LLM Provider that simulates a multi-turn ReAct tool loop."""

    def __init__(self, turns: list[AssistantTurn]) -> None:
        self.turns = list(turns)
        self.call_history: list[list[dict]] = []

    async def chat_turn_async(self, messages, **kwargs):
        self.call_history.append(messages)
        if self.turns:
            return self.turns.pop(0)
        return AssistantTurn(content="Done.")

    async def chat_async(self, messages, **kwargs):
        self.call_history.append(messages)
        if self.turns:
            return self.turns.pop(0).content or "Done."
        return "Done."


class MockMCPManager(MCPClientManager):
    """Mock MCP Manager returning deterministic tool outputs."""

    def __init__(self) -> None:
        super().__init__([])
        self.calls_received: list[tuple[str, dict]] = []

    def get_openai_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "search__search",
                    "description": "Search the web",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
                },
            }
        ]

    async def call_tool(self, namespaced_name: str, arguments: dict | None = None) -> ToolResult:
        self.calls_received.append((namespaced_name, arguments or {}))
        if namespaced_name == "search__search":
            return ToolResult(
                name=namespaced_name,
                content="1. Official Docs\nURL: https://example.com/docs\nSummary: Documentation for project.",
                is_error=False,
            )
        return ToolResult(name=namespaced_name, content="OK", is_error=False)


@pytest.mark.asyncio
async def test_run_agent_loop_with_tool_call_and_sources():
    # Turn 1: requests search tool
    # Turn 2: answers user question based on tool result
    provider = MockMultiTurnProvider(
        [
            AssistantTurn(
                content=None,
                tool_calls=[ToolCall(id="call_1", name="search__search", arguments={"query": "riva docs"})],
            ),
            AssistantTurn(
                content="Here is the documentation from the official source.",
                tool_calls=[],
            ),
        ]
    )

    manager = MockMCPManager()
    tool_events: list[str] = []

    res = await run_agent_loop(
        messages=[{"role": "user", "content": "Where are the docs?"}],
        provider=provider,
        mcp_manager=manager,
        on_tool_call=lambda tc: tool_events.append(f"call:{tc.name}"),
        on_tool_result=lambda tr: tool_events.append(f"result:{tr.name}"),
    )

    # Verify ReAct iterations
    assert res.iterations == 2
    assert len(res.tool_calls_executed) == 1
    assert tool_events == ["call:search__search", "result:search__search"]
    assert len(manager.calls_received) == 1

    # Verify source citation
    assert len(res.sources) == 1
    assert res.sources[0].url == "https://example.com/docs"
    assert "### Sources" in res.content
    assert "[Official Docs](https://example.com/docs)" in res.content


@pytest.mark.asyncio
async def test_run_agent_loop_direct_answer():
    provider = MockMultiTurnProvider(
        [
            AssistantTurn(content="2 + 2 is 4.", tool_calls=[]),
        ]
    )
    res = await run_agent_loop(
        messages=[{"role": "user", "content": "What is 2+2?"}],
        provider=provider,
        mcp_manager=None,
    )
    assert res.iterations == 1
    assert res.content == "2 + 2 is 4."
    assert len(res.tool_calls_executed) == 0
    assert "### Sources" not in res.content


@pytest.mark.asyncio
async def test_run_agent_loop_mutating_safety_guard():
    # Turn 1: attempts mutating call
    provider = MockMultiTurnProvider(
        [
            AssistantTurn(
                content=None,
                tool_calls=[ToolCall(id="call_del", name="fs__delete_file", arguments={"path": "important.txt"})],
            ),
            AssistantTurn(content="Understood.", tool_calls=[]),
        ]
    )
    manager = MockMCPManager()

    res = await run_agent_loop(
        messages=[{"role": "user", "content": "Delete important.txt"}],
        provider=provider,
        mcp_manager=manager,
        auto_approve_readonly=False,  # Enforce confirmation for mutating tools
    )

    assert len(res.tool_calls_executed) == 1
    tc, tr = res.tool_calls_executed[0]
    assert tr.is_error is True
    assert "Action halted" in tr.content
    assert "mutating" in tr.content
