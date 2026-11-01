# lighthouse-genie

## Purpose

The `lighthouse-genie` package acts as the user's strategic advisor, personal guide, and learning coordinator. It coordinates technology news, AI research publications, and Notion knowledge by orchestrating configured Model Context Protocol (MCP) servers.

## Responsibilities

- **Tech Trends & AI News Monitoring**: Queries configured MCP search tools (e.g. Brave, DuckDuckGo) for breakthrough research and technology updates.
- **Notion Integration & Sync**: Connects to MCP Notion tools for personal knowledge retrieval and tracking.
- **Proactive Briefings**: Feeds aggregated strategic intelligence and source citations into morning digests via `gather_briefing_context()`.
- **Genie Coordinator**: Implements the `GenieCoordinator` protocol from `common.interfaces.plugin`.

## Dependencies

- `common`

## Package Structure

```text
src/
└── lighthouse_genie/
    ├── __init__.py       # Exports LighthouseCoordinator, models, and CLI diagnostics
    ├── coordinator.py    # MCP tool discovery, search/notion parsing, and briefing assembly
    └── models.py         # TechTrendItem, NotionItem, LighthouseBriefing
```

## Running

```bash
uv run --package lighthouse-genie python -m lighthouse_genie
```

## Notes

This package should remain independent of other Genie packages. Any shared functionality should be moved into `common`.
