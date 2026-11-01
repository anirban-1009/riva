"""Lighthouse Genie: Strategic advisor, technology news, and learning coordinator."""

from lighthouse_genie.coordinator import LighthouseCoordinator
from lighthouse_genie.models import (
    LighthouseBriefing,
    NotionItem,
    TechTrendItem,
)

__all__ = [
    "LighthouseBriefing",
    "LighthouseCoordinator",
    "NotionItem",
    "TechTrendItem",
]


def main() -> None:
    """Entry point for running Lighthouse Genie diagnostic CLI."""
    print("💡 Lighthouse Genie - Autonomous Strategic Advisor")
    print("Orchestrates standard Model Context Protocol (MCP) tools for tech intelligence.")
