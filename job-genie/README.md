# job-genie

## Purpose

`job-genie` transforms your job search into a visual, interactive mind map inside Obsidian. It finds jobs, scores them against your resume, surfaces who you know at each company from your LinkedIn network, and can generate a tailored resume PDF per job.

## Responsibilities

- **Job Search & Scraping**: Querying job listings (LinkedIn and external career sites) and extracting relevant details from job descriptions.
- **Relevance Scoring & Gap Analysis**: Scoring jobs against your resume and surfacing skill/experience gaps.
- **Network Graph**: Matching your LinkedIn connections to target companies.
- **Resume Tailoring**: Generating a tailored resume PDF for a specific job.
- **Obsidian Sync**: Writing jobs/companies/people as an interactive vault (Markdown + Canvas).
- **Email Digests**: Daily email summaries of top job matches.

## Dependencies

- `common`

## Package Structure

```text
src/job_genie/
├── __init__.py
├── __main__.py
├── main.py          # click CLI group (search, scrape, score, network, notify, sync, tailor, login, check)
├── core/             # orchestrator, database, resume/relevance/gap-analysis services
│   └── ai/            # LLM clients: Ollama, Gemini, fallback chain
├── ingest/            # LinkedIn/job-site scraping, resume parsing
├── generator/          # Obsidian vault generation, resume tailoring, templates
├── notification/        # email digest + providers
└── utils/               # logging, exceptions

tests/    # mirrors src/job_genie/ structure
docs/     # ARCHITECTURE, CLI_REFERENCE, DATA_PROCESSING, DEPLOYMENT, DEVELOPMENT_PLAN,
          # FIRST_RUN, MIND_MAP_STRUCTURE, REQUIREMENTS, VAULT_SEARCH, CODE_OF_CONDUCT
scripts/  # standalone verification/maintenance scripts
```

## Quick Start

1. **Set up**: follow [`docs/FIRST_RUN.md`](docs/FIRST_RUN.md) — copy `config.sample.yaml` to `config.yaml`, fill in your paths, and set API keys in `.env`.
2. `uv run --package job-genie job-genie login` — logs you into LinkedIn.
3. `uv run --package job-genie job-genie search` — finds new jobs.
4. `uv run --package job-genie job-genie scrape` — fetches details.
5. `uv run --package job-genie job-genie score --all` — ranks jobs with AI.
6. `uv run --package job-genie job-genie sync` — writes to your Obsidian vault.

See [`docs/CLI_REFERENCE.md`](docs/CLI_REFERENCE.md) for the full command list, and [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for running it on a schedule.

## Running

```bash
uv run --package job-genie job-genie <command>
# or
uv run --package job-genie python -m job_genie <command>
```

## Relationship to the riva-agent AI Gateway

`riva-agent` runs an OpenAI-compatible AI Gateway ([`src/riva_agent/api/gateway.py`](../src/riva_agent/api/gateway.py)) exposing `/v1/chat/completions`, `/v1/models`, and `/v1/embeddings` over local (Ollama) and hosted (Gemini, OpenAI-eval-only) providers. Today it's a stateless proxy — no memory, no prompt injection, no notion of a Genie calling it.

`job-genie`'s `core/ai/` clients (Ollama, Gemini, fallback chain) call those providers **directly**, bypassing the gateway entirely. That's intentional, not a shortcut to fix later opportunistically:

- Per [`docs/product-definition.md`](../docs/product-definition.md), memory is the load-bearing layer and Genies are readers of it (§3.2) — routing a Genie through the gateway before that layer exists means integrating against an API that's still going to change shape.
- The gateway's two-mode split (pass-through for coding clients vs. assistant mode with memory injection, §5) has to be resolved and implemented first, since that decision determines what a Genie's request even looks like.
- In the post-v1 roadmap (§7, M6), **Lighthouse Genie** is first in line for gateway integration — its data is the least sensitive and it doubles as the first consumer of the proactive-digest scheduler. `job-genie` (résumés, salary signals, job-search anxiety) is exactly the kind of sensitive data §3.1 says should wait until the memory layer has earned trust.

When job-genie's turn comes, the shape of the change is: swap the direct Ollama/Gemini calls in `core/ai/` for HTTP calls to the gateway's `/v1/chat/completions` (and possibly `/v1/embeddings`, if relevance scoring moves to semantic matching), addressed in assistant mode so scoring and gap-analysis can draw on profile/memory instead of only the resume passed in per call.

## Notes

This package should remain independent of other Genie packages. Any shared functionality should be moved into `common`.
