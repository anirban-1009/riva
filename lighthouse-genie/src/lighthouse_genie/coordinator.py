"""Lighthouse Genie Coordinator.

Coordinates domain intelligence (tech trends, research, Notion notes) by discovering
and orchestrating standard Model Context Protocol (MCP) servers and tools.
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from common.mcp.manager import MCPClientManager
from common.mcp.models import ToolDefinition
from lighthouse_genie.models import (
    LighthouseBriefing,
    NotionItem,
    TechTrendItem,
)

logger = logging.getLogger(__name__)


class LighthouseCoordinator:
    """Domain coordinator for Lighthouse Genie capabilities.

    Discovers and orchestrates tools across configured MCP servers (e.g., search,
    Notion, GitHub) to assemble strategic intelligence and daily briefings.
    """

    name: str = "lighthouse"

    def __init__(
        self,
        mcp_manager: MCPClientManager | None = None,
    ) -> None:
        self.mcp_manager = mcp_manager

    async def initialize(self) -> None:
        """Initialize the underlying MCP client manager if not already active."""
        if self.mcp_manager is not None and not self.mcp_manager.clients:
            await self.mcp_manager.initialize_all()

    def find_search_tool(self) -> ToolDefinition | None:
        """Locate an available search tool across configured MCP servers."""
        if not self.mcp_manager:
            return None

        tools = self.mcp_manager.list_tools()
        # Prefer exact names or tools with 'search' in tool name
        for t in tools:
            name_lower = t.namespaced_name.lower()
            if "search" in name_lower or "brave" in name_lower or "duckduckgo" in name_lower:
                return t
        return None

    def find_notion_tool(self) -> ToolDefinition | None:
        """Locate an available Notion tool across configured MCP servers."""
        if not self.mcp_manager:
            return None

        tools = self.mcp_manager.list_tools()
        for t in tools:
            name_lower = t.namespaced_name.lower()
            if "notion" in name_lower and ("search" in name_lower or "query" in name_lower):
                return t
        return None

    async def fetch_tech_trends(
        self,
        query: str = "AI tech news and breakthrough research",
        limit: int = 5,
    ) -> list[TechTrendItem]:
        """Query available MCP search tools for recent tech news and research."""
        tool = self.find_search_tool()
        if not tool or not self.mcp_manager:
            logger.debug("No MCP search tool available for tech trends.")
            return []

        # Prepare parameters according to tool schema
        tool_args: dict[str, Any] = {"query": query}
        props = tool.parameters.get("properties", {})
        if "max_results" in props:
            tool_args["max_results"] = limit
        elif "limit" in props:
            tool_args["limit"] = limit
        elif "count" in props:
            tool_args["count"] = limit

        try:
            result = await self.mcp_manager.call_tool(tool.namespaced_name, tool_args)
            if result.is_error or not result.content:
                logger.warning(
                    "Search tool '%s' returned an error: %s",
                    tool.namespaced_name,
                    result.content,
                )
                return []

            return self._parse_search_results(result.content, limit=limit)
        except Exception as exc:
            logger.warning("Error calling search tool '%s': %s", tool.namespaced_name, exc)
            return []

    async def fetch_notion_updates(
        self,
        query: str = "",
        limit: int = 5,
    ) -> list[NotionItem]:
        """Query available MCP Notion tools for recently edited pages or notes."""
        tool = self.find_notion_tool()
        if not tool or not self.mcp_manager:
            logger.debug("No MCP Notion tool available.")
            return []

        tool_args: dict[str, Any] = {}
        props = tool.parameters.get("properties", {})
        if "query" in props and query:
            tool_args["query"] = query
        if "page_size" in props:
            tool_args["page_size"] = limit
        elif "limit" in props:
            tool_args["limit"] = limit

        try:
            result = await self.mcp_manager.call_tool(tool.namespaced_name, tool_args)
            if result.is_error or not result.content:
                return []

            return self._parse_notion_results(result.content, limit=limit)
        except Exception as exc:
            logger.warning("Error calling Notion tool '%s': %s", tool.namespaced_name, exc)
            return []

    async def gather_briefing_context(
        self,
        search_query: str = "AI tech news and breakthrough research",
        include_notion: bool = True,
    ) -> LighthouseBriefing:
        """Gather domain intelligence from configured MCP servers in parallel."""
        trends_task = self.fetch_tech_trends(query=search_query)
        notion_task = self.fetch_notion_updates() if include_notion else asyncio.sleep(0, result=[])

        trends_res, notion_res = await asyncio.gather(trends_task, notion_task, return_exceptions=True)

        trends: list[TechTrendItem] = trends_res if isinstance(trends_res, list) else []
        notion_items: list[NotionItem] = notion_res if isinstance(notion_res, list) else []

        citations: list[str] = []
        for trend in trends:
            if trend.url:
                citations.append(f"[{trend.title}]({trend.url})")
            elif trend.title:
                citations.append(trend.title)

        for n in notion_items:
            if n.url:
                citations.append(f"[Notion: {n.title}]({n.url})")
            elif n.title:
                citations.append(f"Notion: {n.title}")

        summary_parts = []
        if trends:
            summary_parts.append(f"Identified {len(trends)} recent tech/AI trend updates via MCP.")
        if notion_items:
            summary_parts.append(f"Found {len(notion_items)} recent Notion knowledge items.")

        summary = " ".join(summary_parts) if summary_parts else "No external MCP intelligence retrieved."
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        return LighthouseBriefing(
            date=today_str,
            trends=trends,
            notion_items=notion_items,
            summary=summary,
            citations=citations,
        )

    async def gather_context(self, **kwargs: Any) -> dict[str, Any]:
        """Gather domain-specific context conforming to GenieCoordinator protocol."""
        briefing = await self.gather_briefing_context(**kwargs)
        return {
            "summary": briefing.summary,
            "trends": [t.__dict__ for t in briefing.trends],
            "notion_items": [n.__dict__ for n in briefing.notion_items],
            "citations": briefing.citations,
        }

    def _parse_search_results(self, content: str, limit: int = 5) -> list[TechTrendItem]:
        """Parse raw tool output (JSON or markdown text) into structured TechTrendItems."""
        items: list[TechTrendItem] = []

        # 1. Try parsing JSON
        try:
            parsed = json.loads(content)
            raw_list = []
            if isinstance(parsed, list):
                raw_list = parsed
            elif isinstance(parsed, dict):
                # Common shapes: {"results": [...]}, {"organic": [...]}, {"items": [...]}
                for k in ("results", "organic", "items", "data"):
                    if k in parsed and isinstance(parsed[k], list):
                        raw_list = parsed[k]
                        break

            for entry in raw_list[:limit]:
                if isinstance(entry, dict):
                    title = entry.get("title") or entry.get("name") or "Tech Update"
                    url = entry.get("url") or entry.get("link") or entry.get("href") or ""
                    snippet = entry.get("snippet") or entry.get("body") or entry.get("description") or ""
                    items.append(
                        TechTrendItem(
                            title=str(title).strip(),
                            url=str(url).strip(),
                            snippet=str(snippet).strip(),
                        )
                    )
                elif isinstance(entry, str):
                    items.append(TechTrendItem(title=entry.strip()))

            if items:
                return items
        except (json.JSONDecodeError, TypeError):
            pass

        # 2. Fallback: Parse markdown links [Title](URL) or lines
        link_matches = re.findall(r"\[([^\]]+)\]\((https?://[^\)]+)\)", content)
        if link_matches:
            for title, url in link_matches[:limit]:
                items.append(TechTrendItem(title=title.strip(), url=url.strip()))
            return items

        # 3. Fallback: Plain text non-empty lines
        lines = [line.strip("- * \t\n") for line in content.splitlines() if line.strip()]
        for line in lines[:limit]:
            if line:
                items.append(TechTrendItem(title=line))

        return items

    def _parse_notion_results(self, content: str, limit: int = 5) -> list[NotionItem]:
        """Parse raw Notion tool output into structured NotionItems."""
        items: list[NotionItem] = []
        try:
            parsed = json.loads(content)
            raw_list = parsed if isinstance(parsed, list) else parsed.get("results", [])
            for entry in raw_list[:limit]:
                if isinstance(entry, dict):
                    title = "Untitled"
                    # Notion page title extraction
                    if "properties" in entry:
                        title_prop = entry["properties"].get("title") or entry["properties"].get("Name")
                        if title_prop and "title" in title_prop and title_prop["title"]:
                            title = title_prop["title"][0].get("plain_text", title)
                    title = entry.get("title", title)
                    url = entry.get("url", "")
                    item_type = entry.get("object", "page")
                    last_edited = entry.get("last_edited_time", "")
                    items.append(
                        NotionItem(
                            title=str(title),
                            url=str(url),
                            item_type=item_type,
                            last_edited=last_edited,
                        )
                    )
        except (json.JSONDecodeError, TypeError):
            # Text fallback
            lines = [line.strip("- * \t\n") for line in content.splitlines() if line.strip()]
            for line in lines[:limit]:
                items.append(NotionItem(title=line))

        return items
