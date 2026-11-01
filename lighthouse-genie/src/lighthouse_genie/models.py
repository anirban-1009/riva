"""Data models for the Lighthouse Genie package."""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class TechTrendItem:
    """A technology news item, research breakthrough, or trending topic."""

    title: str
    url: str = ""
    snippet: str = ""
    source: str = "search"
    category: str = "AI / Tech"


@dataclass
class NotionItem:
    """A note, page, or task retrieved from the user's Notion knowledge base."""

    title: str
    url: str = ""
    item_type: str = "page"  # "page" | "database" | "block"
    last_edited: str = ""


@dataclass
class LighthouseBriefing:
    """Aggregated strategic intelligence gathered by Lighthouse Genie."""

    date: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    trends: list[TechTrendItem] = field(default_factory=list)
    notion_items: list[NotionItem] = field(default_factory=list)
    summary: str = ""
    citations: list[str] = field(default_factory=list)
