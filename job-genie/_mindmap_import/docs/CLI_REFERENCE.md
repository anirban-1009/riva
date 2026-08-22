# CLI Reference

The **Job Hunt Mindmap** tool is controlled entirely via the command line using `uv run mindmap`. Each command is designed to be part of a larger workflow, from discovering jobs to synchronizing them with your Obsidian vault.

## General Usage

```bash
uv run mindmap [OPTIONS] COMMAND [ARGS]...
```

Use `--help` with any command to see its specific options:
```bash
uv run mindmap <command> --help
```

---

## Core Commands

### `check`
Validates your `config.yaml` and environment variables. Run this first to ensure everything is set up correctly.

```bash
uv run mindmap check
```

### `login`
Launches a browser window for manual LinkedIn authentication. This saves your session cookies so that subsequent `search` and `scrape` commands can run headlessly.

```bash
uv run mindmap login
```

### `search`
Discovers new job postings based on the keywords and locations defined in your `config.yaml`. This only finds the basic listing information (IDs and links).

```bash
uv run mindmap search [--headless]
```

### `scrape`
Fetches the full job description and details for jobs found during the `search` phase.

```bash
uv run mindmap scrape [JOB_ID] [OPTIONS]
```
**Options:**
- `--headless`: Run without a browser window.
- `--limit <int>`: Limit the number of jobs to process.
- `--force`: Ignore the database cache and re-scrape details.
- `--min-fast-score <int>`: Only scrape jobs that pass a basic keyword matching threshold (0-100).
- `--score`: Automatically run the AI scoring immediately after scraping.

### `score`
Ranks jobs against your resume using either your local (Ollama) or cloud (Gemini) LLM provider.

```bash
uv run mindmap score [JOB_ID] [--all]
```
**Options:**
- `--all`: Score all jobs in the database that haven't been scored yet.
- `JOB_ID`: Score a specific job by its ID.

### `sync`
The "Mind Map Generator." This command exports your database (Jobs, Companies, Analysis) to your Obsidian vault. It automatically creates links between companies, connections, and jobs.

```bash
uv run mindmap sync
```

### `sync-back`
Synchronizes changes made in Obsidian (like `#Status` tag updates) back to the local database. This allows you to manage your application pipeline directly from Obsidian.

```bash
uv run mindmap sync-back
```

---

## Networking & Referrals

### `network`
Finds professional connections from your LinkedIn export who work at a specific job's company.

```bash
uv run mindmap network <JOB_ID>
```

### `network-all`
Scans all jobs in your database and identifies matching connections for every company.

```bash
uv run mindmap network-all
```

### `refer`
Generates a personalized, concise LinkedIn referral request message using AI. It incorporates your skills and the specific job title.

```bash
uv run mindmap refer <JOB_ID> [OPTIONS]
```
**Options:**
- `--name <text>`: Manually specify a person's name if not found in your network.
- `--max-chars <int>`: Set a character limit for the message (default: 200).
- *Output Example:* The tool shows the character count, e.g., `(158/190 chars)`.

---

## Utilities & Analysis

### `analyze-gaps`
Identifies common missing skills across high-scoring jobs. Helps you understand what to learn next or add to your resume. It also generates a detailed Markdown report with a gap table in your Obsidian vault's `Analysis/` folder.

```bash
uv run mindmap analyze-gaps [--min-score <int>] [--tag <text>]
```
**Options:**
- `--min-score <int>`: Minimum relevance score to include in analysis (default: 0).
- `--tag <text>`: Filter analysis by a specific job specialization (e.g., `AI_ML`, `Backend`, `Python_Dev`).

*Output Example:* A table summarizing gaps for each job and an AI-generated improvement plan is saved as `Analysis/Gap Analysis - <Tag>.md`.

### `tailor`
Generates a job-optimized LaTeX resume PDF based on your master resume and the specific job description.

```bash
uv run mindmap tailor <JOB_ID>
```

### `notify`
Sends an email digest of the top-ranked jobs found since the last notification.

```bash
uv run mindmap notify [--min-score <int>]
```

### `test-ai`
Verifies your connection to the configured AI provider (Ollama or Gemini).

```bash
uv run mindmap test-ai [--prompt <text>]
```

### `prune`
Cleans up your Obsidian vault by removing Markdown files for jobs that are no longer present in your local database.

```bash
uv run mindmap prune
```
