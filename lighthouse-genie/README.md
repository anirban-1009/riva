# lighthouse-genie

## Purpose

The `lighthouse-genie` package is responsible for monitoring, aggregating, and summarizing updates about new technologies and trends in the AI industry, using Twitter (X) as its primary data source.

## Responsibilities

- **Twitter Feed Monitoring**: Tracking key AI researchers, developers, organizations, and trending hashtags on Twitter/X.
- **News Aggregation & Filtering**: Collecting tweets, threads, and referenced links, then filtering out noise to focus on high-signal AI developments.
- **AI Trend Summarization**: Condensing complex threads, research announcements, and product launches into clear, concise summaries.
- **Insight Delivery**: Organizing updates by category (e.g., LLMs, tooling, robotics, research papers) and delivering scheduled or on-demand digests.
- **Twitter API/Scraper Integration**: Managing authentication, rate limits, and data ingestion from Twitter/X.

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
