# lighthouse-genie

## Purpose

The `lighthouse-genie` package is responsible for acting as the user's strategic advisor, personal guide, and learning coordinator. It tracks AI news, tech trends, research publications, GitHub projects, coordinates Notion integrations, maps learning roadmaps, schedules reminders, and tracks long-term goals.

## Responsibilities

- **Tech Trends & AI News Monitoring**: Aggregating updates from RSS, arXiv, GitHub, Hacker News, Twitter, and other research sources.
- **Learning & Roadmaps**: Advising on technical roadmaps, learning paths, and book recommendations.
- **Notion Integration & Sync**: Maintaining a personal knowledge base and syncing items like bookmarked papers, lists, and task notes to Notion.
- **Goal & Reminder Planning**: Coordinating reminders, weekly digests, and tracking progress toward long-term personal growth goals.
- **External API Integrations**: Connecting to knowledge storage interfaces, news scrapers, and task boards.

## Dependencies

- `common`

## Package Structure

```text
src/
└── lighthouse_genie/
    ├── __init__.py
    ├── models.py
    ├── services.py
    ├── tools.py
    ├── prompts.py
    └── plugin.py
```

## Running

```bash
uv run --package lighthouse-genie python -m lighthouse_genie
```

## Notes

This package should remain independent of other Genie packages. Any shared functionality should be moved into `common`.
