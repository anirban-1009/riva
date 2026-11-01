"""Tests for MCP-enriched digest generation and CLI integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from lighthouse_genie.models import LighthouseBriefing, TechTrendItem

from riva_agent.cli import cmd_digest_generate
from riva_agent.digest.generator import (
    build_digest_prompt,
    enrich_context_with_mcp,
    generate_digest_async,
)
from riva_agent.digest.models import DigestConfig, DigestContext


@pytest.mark.asyncio
async def test_enrich_context_with_mcp():
    mock_mgr = MagicMock()
    mock_coord = MagicMock()
    mock_coord.gather_briefing_context = AsyncMock(
        return_value=LighthouseBriefing(
            trends=[TechTrendItem(title="Llama 3.3 Released", url="https://llama.meta.com", snippet="70B model")],
            notion_items=[],
        )
    )

    ctx = DigestContext(date="2026-11-01")
    with patch("lighthouse_genie.coordinator.LighthouseCoordinator", return_value=mock_coord):
        await enrich_context_with_mcp(ctx, mock_mgr)

    assert len(ctx.external_insights) == 1
    assert "Trend: Llama 3.3 Released" in ctx.external_insights[0]
    assert "https://llama.meta.com" in ctx.external_insights[0]


@pytest.mark.asyncio
async def test_enrich_context_with_mcp_error_graceful():
    mock_mgr = MagicMock()
    mock_coord = MagicMock()
    mock_coord.gather_briefing_context = AsyncMock(side_effect=RuntimeError("MCP crash"))

    ctx = DigestContext(date="2026-11-01")
    with patch("lighthouse_genie.coordinator.LighthouseCoordinator", return_value=mock_coord):
        # Should not raise exception
        await enrich_context_with_mcp(ctx, mock_mgr)

    assert ctx.external_insights == []


def test_build_digest_prompt_with_external_insights():
    ctx = DigestContext(
        date="2026-11-01",
        profile_goals=[{"key": "career", "value": "AI Engineer"}],
        external_insights=["Trend: Apple Silicon M4 Pro benchmark", "Notion: Reading list"],
    )
    messages = build_digest_prompt(ctx)
    user_content = messages[1]["content"]

    assert "[External Knowledge & Tech Highlights (MCP)]" in user_content
    assert "Trend: Apple Silicon M4 Pro benchmark" in user_content
    assert "Notion: Reading list" in user_content


@pytest.mark.asyncio
async def test_generate_digest_async_with_mcp_dry_run(tmp_path):
    cfg = DigestConfig(output_dir=tmp_path)
    ctx = DigestContext(date="2026-11-01")

    mock_mgr = MagicMock()
    mock_coord = MagicMock()
    mock_coord.gather_briefing_context = AsyncMock(
        return_value=LighthouseBriefing(
            trends=[TechTrendItem(title="Gemma 4 Updates", url="https://ai.google.dev")],
        )
    )

    with patch("lighthouse_genie.coordinator.LighthouseCoordinator", return_value=mock_coord):
        record = await generate_digest_async(
            context=ctx,
            config_obj=cfg,
            dry_run=True,
            mcp_manager=mock_mgr,
        )

    assert "### 🌐 External Insights (MCP)" in record.content_markdown
    assert "Gemma 4 Updates" in record.content_markdown


def test_cmd_digest_generate_with_mcp(tmp_path, capsys):
    args = MagicMock()
    args.date = "2026-11-01"
    args.dry_run = True
    args.no_notify = True
    args.with_mcp = True
    args.channel = None

    mock_mgr = MagicMock()
    mock_mgr.initialize_all = AsyncMock()
    mock_mgr.close_all = AsyncMock()

    with (
        patch("riva_agent.mcp.config.get_mcp_servers", return_value=[MagicMock()]),
        patch("common.mcp.manager.MCPClientManager", return_value=mock_mgr),
    ):
        exit_code = cmd_digest_generate(args)
        assert exit_code == 0
        mock_mgr.initialize_all.assert_called_once()
        mock_mgr.close_all.assert_called_once()
