"""Tests for LighthouseCoordinator and data models."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from lighthouse_genie.coordinator import LighthouseCoordinator
from lighthouse_genie.models import LighthouseBriefing, NotionItem, TechTrendItem

from common.interfaces.plugin import GenieCoordinator
from common.mcp.models import ToolDefinition, ToolResult


def test_models_instantiation():
    trend = TechTrendItem(title="New MLX 0.22 Released", url="https://github.com/ml-explore/mlx")
    assert trend.title == "New MLX 0.22 Released"
    assert trend.url == "https://github.com/ml-explore/mlx"
    assert trend.source == "search"

    notion = NotionItem(title="Q4 Research Goals", url="https://notion.so/123", item_type="page")
    assert notion.title == "Q4 Research Goals"

    briefing = LighthouseBriefing(trends=[trend], notion_items=[notion])
    assert len(briefing.trends) == 1
    assert len(briefing.notion_items) == 1


def test_genie_coordinator_protocol_compliance():
    coord = LighthouseCoordinator()
    assert isinstance(coord, GenieCoordinator)
    assert coord.name == "lighthouse"


@pytest.mark.asyncio
async def test_fetch_tech_trends_no_manager():
    coord = LighthouseCoordinator(mcp_manager=None)
    items = await coord.fetch_tech_trends()
    assert items == []


@pytest.mark.asyncio
async def test_fetch_tech_trends_no_search_tool():
    mock_mgr = MagicMock()
    mock_mgr.list_tools.return_value = [
        ToolDefinition(
            server="fs",
            name="read_file",
            namespaced_name="fs__read_file",
            description="Read file",
            parameters={},
        )
    ]
    coord = LighthouseCoordinator(mcp_manager=mock_mgr)
    items = await coord.fetch_tech_trends()
    assert items == []


@pytest.mark.asyncio
async def test_fetch_tech_trends_json_response():
    mock_mgr = MagicMock()
    search_tool = ToolDefinition(
        server="brave",
        name="search",
        namespaced_name="brave__search",
        description="Search web",
        parameters={"properties": {"query": {"type": "string"}, "count": {"type": "integer"}}},
    )
    mock_mgr.list_tools.return_value = [search_tool]

    results_data = [
        {"title": "Gemma 4 Released", "url": "https://example.com/gemma4", "snippet": "New model weights"},
        {"title": "Apple M4 Benchmarks", "url": "https://example.com/m4", "snippet": "Unified memory speedup"},
    ]
    mock_mgr.call_tool = AsyncMock(return_value=ToolResult(name="brave__search", content=json.dumps(results_data)))

    coord = LighthouseCoordinator(mcp_manager=mock_mgr)
    items = await coord.fetch_tech_trends(query="AI news", limit=2)

    assert len(items) == 2
    assert items[0].title == "Gemma 4 Released"
    assert items[0].url == "https://example.com/gemma4"
    assert items[0].snippet == "New model weights"
    mock_mgr.call_tool.assert_called_once_with("brave__search", {"query": "AI news", "count": 2})


@pytest.mark.asyncio
async def test_fetch_tech_trends_markdown_links():
    mock_mgr = MagicMock()
    search_tool = ToolDefinition(
        server="search",
        name="search",
        namespaced_name="search__search",
        description="Search",
        parameters={"properties": {"query": {}, "max_results": {}}},
    )
    mock_mgr.list_tools.return_value = [search_tool]

    text_content = (
        "Here are search results:\n"
        "- [DeepSeek v3 Architecture](https://arxiv.org/abs/12345)\n"
        "- [MLX Community Models](https://huggingface.co/mlx-community)\n"
    )
    mock_mgr.call_tool = AsyncMock(return_value=ToolResult(name="search__search", content=text_content))

    coord = LighthouseCoordinator(mcp_manager=mock_mgr)
    items = await coord.fetch_tech_trends(limit=5)
    assert len(items) == 2
    assert items[0].title == "DeepSeek v3 Architecture"
    assert items[0].url == "https://arxiv.org/abs/12345"


@pytest.mark.asyncio
async def test_fetch_tech_trends_tool_error():
    mock_mgr = MagicMock()
    search_tool = ToolDefinition(
        server="search",
        name="search",
        namespaced_name="search__search",
        description="Search",
        parameters={},
    )
    mock_mgr.list_tools.return_value = [search_tool]
    mock_mgr.call_tool = AsyncMock(
        return_value=ToolResult(name="search__search", content="Network timeout", is_error=True)
    )

    coord = LighthouseCoordinator(mcp_manager=mock_mgr)
    items = await coord.fetch_tech_trends()
    assert items == []


@pytest.mark.asyncio
async def test_fetch_notion_updates():
    mock_mgr = MagicMock()
    notion_tool = ToolDefinition(
        server="notion",
        name="search",
        namespaced_name="notion__search",
        description="Search Notion",
        parameters={"properties": {"query": {}, "page_size": {}}},
    )
    mock_mgr.list_tools.return_value = [notion_tool]

    notion_data = {
        "results": [
            {
                "object": "page",
                "url": "https://notion.so/ai-roadmap",
                "properties": {"title": {"title": [{"plain_text": "2026 AI Roadmap"}]}},
                "last_edited_time": "2026-11-01T10:00:00Z",
            }
        ]
    }
    mock_mgr.call_tool = AsyncMock(return_value=ToolResult(name="notion__search", content=json.dumps(notion_data)))

    coord = LighthouseCoordinator(mcp_manager=mock_mgr)
    items = await coord.fetch_notion_updates(limit=1)
    assert len(items) == 1
    assert items[0].title == "2026 AI Roadmap"
    assert items[0].url == "https://notion.so/ai-roadmap"


@pytest.mark.asyncio
async def test_gather_briefing_context():
    mock_mgr = MagicMock()
    coord = LighthouseCoordinator(mcp_manager=mock_mgr)

    trend = TechTrendItem(title="MLX Fast Attention", url="https://example.com/mlx-attn")
    notion = NotionItem(title="Agent Notes", url="https://notion.so/notes")

    coord.fetch_tech_trends = AsyncMock(return_value=[trend])
    coord.fetch_notion_updates = AsyncMock(return_value=[notion])

    briefing = await coord.gather_briefing_context(include_notion=True)
    assert len(briefing.trends) == 1
    assert len(briefing.notion_items) == 1
    assert "[MLX Fast Attention](https://example.com/mlx-attn)" in briefing.citations
    assert "[Notion: Agent Notes](https://notion.so/notes)" in briefing.citations
    assert "Identified 1 recent tech/AI trend" in briefing.summary

    # Test gather_context (GenieCoordinator protocol)
    context_dict = await coord.gather_context()
    assert "summary" in context_dict
    assert "trends" in context_dict
    assert "notion_items" in context_dict
    assert "citations" in context_dict
    assert len(context_dict["trends"]) == 1
