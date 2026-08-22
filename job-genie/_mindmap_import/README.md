# Job Hunt Mind Mapper
![Coverage](coverage.svg)

**Job Hunt Mind Mapper** is a Python-based tool designed to transform your job search into a visual, interactive mind map within Obsidian. It leverages your professional experience and LinkedIn network to surface and prioritize relevant opportunities.

## What is it?
Instead of tracking applications in endless spreadsheets, this tool generates a dynamic **knowledge graph** of your job hunt.
- **Find Jobs**: Automates the search for roles that match your skills and experience.
- **Visualize Connections**: See who you know at target companies directly alongside job listings.
- **Email Alerts**: Receive daily digests of top job matches directly to your inbox.
- **Manage Workflow**: Use Obsidian's Kanban or Canvas features to track applications from "To Apply" to "Offer".

## Documentation
*   [Features & Requirements](docs/REQUIREMENTS.md) - What the tool does.
*   [CLI Reference](docs/CLI_REFERENCE.md) - Detailed guide for all command-line tools.
*   [Mind Map Structure](docs/MIND_MAP_STRUCTURE.md) - How the Obsidian vault is organized to visualize your search.
*   [Architecture](docs/ARCHITECTURE.md) - How the system is built.
*   [Data Processing](docs/DATA_PROCESSING.md) - The logic behind job matching and scoring.
*   [Vault Search](docs/VAULT_SEARCH.md) - Full-text search over the Obsidian vault via SQLite FTS5.
*   [Development Plan](docs/DEVELOPMENT_PLAN.md) - Phased implementation guide with task lists.
*   [Deployment Strategy](docs/DEPLOYMENT.md) - How to run and schedule the tool locally.
*   [Code of Conduct](docs/CODE_OF_CONDUCT.md) - Design patterns (SOLID, OOP) and engineering standards.

## Quick Start 🚀

1.  **Set up**: [Follow the First Run Guide](docs/FIRST_RUN.md) to install dependencies and configure API keys.
2.  **Login**: `uv run mindmap login` (logs you into LinkedIn).
3.  **Search**: `uv run mindmap search` (finds new jobs).
4.  **Scrape**: `uv run mindmap scrape` (fetches details).
5.  **Score**: `uv run mindmap score --all` (ranks jobs with AI).
6.  **Visualize**: Open your vault in Obsidian!

## How to Run

The tool is designed to be run via a CLI. After installation, you can use the following commands:

-   `uv run mindmap check`: Validate config and environment.
-   `uv run mindmap login`: Manual LinkedIn login to save session.
-   `uv run mindmap search`: Discovery phase - finds job IDs.
-   `uv run mindmap scrape`: Extraction phase - gets job descriptions.
-   `uv run mindmap score`: AI phase - calculates relevance.
-   `uv run mindmap network`: Network phase - finds connections for a job.
-   `uv run mindmap notify`: Alert phase - sends email digest.
-   `uv run mindmap sync`: Sync job data to Obsidian vault.
-   `uv run mindmap tailor <JOB_ID>`: Generate a tailored resume PDF for a specific job.

For advanced usage and automation, see the [Deployment Strategy](docs/DEPLOYMENT.md).

## Tech Stack
-   **Core**: Python 3.13+
-   **Visualization**: Obsidian (Markdown + Canvas)
-   **Data Sources**: LinkedIn (via automation/export)
-   **Matching**: NLP/LLM for resume analysis


## Checkout

- https://x.com/AIPandaX/status/2025907777986867656
