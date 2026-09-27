# Riva Agent

Riva Agent is an AI platform compatible with OpenClaw that manages and orchestrates various modular capabilities (Genie packages) within a `uv` workspace, while sharing common infrastructure through the `common` package.

## Documentation

The **[wiki](https://github.com/anirban-1009/riva/wiki)** is the primary, canonical source for documentation — write/update docs there first. The `docs/` folder mirrors select wiki pages for in-repo reading:
- **[Product Definition](docs/product-definition.md)**: Product statement, v1 scope, principles, and non-goals.
- **[Development Timeline](docs/development-timeline.md)**: Phased roadmap and milestone schedule from foundation through v1 and post-v1.
- **[Local Dev Runbook](docs/local-dev-runbook.md)**: Command reference for starting, health-checking, and recovering the local dev stack.
- **[Architecture](docs/architecture.md)**: System design philosophy, layers, and core interfaces.
- **[Inference Latency Investigation](docs/inference-latency.md)**: Root causes, benchmarks, and gateway configuration controls.
- **[MLX Server Evaluation](docs/mlx-server-evaluation.md)**: Local model memory benchmarks and MLX serving evaluation.

## Repository Structure

```text
riva-agent/
├── common/
├── job-genie/
├── money-genie/
├── workout-genie/
├── lighthouse-genie/
├── experiments/
└── riva-agent/
```

### Packages

| Package | Purpose |
|---------|---------|
| `riva-agent` | Main application responsible for orchestration and execution. |
| `common` | Shared models, utilities, configuration, interfaces, and reusable components. |
| `job-genie` | Career and job-search related capabilities. |
| `money-genie` | Personal finance and budgeting capabilities. |
| `workout-genie` | Health and workout related capabilities. |
| `lighthouse-genie` | Planning, productivity, and guidance capabilities. |
| `experiments` | Research, prototypes, benchmarks, and proof-of-concept implementations. |

---

## Workspace

This repository uses **uv Workspaces**.

Each package is independently versioned and manages its own dependencies while sharing a single workspace lockfile.

Example dependency graph:

```text
                riva-agent
              /    |    |    \
             /     |    |     \
        job   money lighthouse workout
            \    |      |      /
             \   |      |     /
                common
```

---

## Development

### Sync Dependencies

Install core platform dependencies (recommended, excludes heavy `experiments` notebooks and libraries):

```bash
# Sync core riva-agent, common, and genie packages (lean install)
uv sync
```

Install all workspace dependencies (including `experiments` with Jupyter, PyTorch, Mem0, etc.):

```bash
# Full workspace sync including prototyping notebooks
uv sync --all-packages
```

### View Dependency Tree

```bash
# Core platform dependency tree (excluding experiments)
uv tree --package riva-agent

# Full workspace dependency tree
uv tree --all-packages
```

### Local Dev Stack Automation

Run the full local stack (MLX inference backend + Riva AI Gateway + OpenClaw check):

```bash
# Start all services (background)
./scripts/start_stack.sh start

# Start in Dev mode (foreground gateway with auto-reload on src/ & common/)
./scripts/start_stack.sh dev

# Check status of ports (8081, 8085) and services
./scripts/start_stack.sh status

# Follow logs (~/.riva/logs/)
./scripts/start_stack.sh logs

# Start stack and launch OpenClaw terminal chat
./scripts/start_stack.sh chat

# Stop the stack
./scripts/start_stack.sh stop
```

Run the main application manually:

```bash
uv run --package riva-agent uvicorn riva_agent.api.gateway:app --host 0.0.0.0 --port 8085
```

Run an individual package:

```bash
uv run --package job-genie python -m job_genie
```

---

## CLI Usage Reference (`riva`)

The `riva` CLI is the primary trust and control surface for interacting with Riva in assistant mode, inspecting/steering persistent profiles and memory, and managing local storage lifecycle.

You can invoke commands via `uv run riva <subcommand>` or directly via `riva <subcommand>` when the environment is activated.

### 1. Terminal Assistant (`riva ask`)

Query Riva directly in Assistant Mode with streaming responses:

```bash
# Query the assistant (requires the stack or gateway to be running on port 8085)
uv run riva ask "What do you remember about my current location and dietary constraints?"
```

### 2. Profile Management (`riva profile`)

Inspect and modify durable user facts, preferences, constraints, and goals stored in `~/.riva/profile.db`:

```bash
# List all profile entries (or filter by category: facts, goals, constraints, preferences)
uv run riva profile list
uv run riva profile list --category facts

# Set or update a profile entry
uv run riva profile set location "Munich" --category facts
uv run riva profile set diet "Peanut allergy" --category constraints

# Retrieve a specific profile key
uv run riva profile get location

# Delete a profile key
uv run riva profile delete location
```

### 3. Memory & Provenance (`riva memory`)

Review recorded episodic conversation history, inspect staged candidate facts, and control memory retention in `~/.riva/memory.db`:

```bash
# List recent conversation turns across sessions
uv run riva memory list
uv run riva memory list --limit 25

# Inspect staged candidate memories pending human review
uv run riva memory list --pending

# Accept a pending memory fact into the persistent profile
uv run riva memory accept <id>

# Reject a pending candidate memory
uv run riva memory reject <id>

# Permanently forget an episodic conversation turn
uv run riva memory forget <id>
```

### 4. Storage Lifecycle & Hygiene (`riva storage`)

Maintain local disk efficiency, inspect table footprints, compact SQLite databases, prune old history, and manage backups:

```bash
# Show storage telemetry for databases, WAL overhead, row counts, and logs footprint
uv run riva storage status

# Compact databases and truncate active WAL checkpoints
uv run riva storage vacuum

# Preview turns and unreviewed pending memory deletions (dry run)
uv run riva storage prune --dry-run

# Prune old conversation turns (default: 30 days) and expired pending candidates (default: 7 days),
# and automatically rotate logs exceeding 50MB (copytruncate, retaining 3 rotations)
uv run riva storage prune
uv run riva storage prune --turns-days 60 --pending-days 14

# Create an online point-in-time snapshot backup of all databases in ~/.riva/backups/
uv run riva storage backup
```

### 5. Chat Session Management (`riva session` & Signal)

Riva isolates conversation turns by session ID. You can start a new session, inspect the current active session, or list past sessions from the CLI or directly via chat (e.g. over Signal).

#### Via Signal / OpenClaw Chat:
Send any of the following commands in your Signal chat with Riva:
- `/clear` or `/new_session` or `/start` or `new session`: Starts a brand new session, rotates the active session ID, and clears context without querying the LLM.
- `/new <your question>`: Starts a fresh session, clears previous turns, and answers your new question immediately.
- `POST /v1/session/new`: REST endpoint on Riva Gateway (`http://localhost:8085/v1/session/new`) to programmatically start a new session.

*(Note: OpenClaw internally consumes bare `/new` and `/reset`; using `/clear`, `/new_session`, or `/new <prompt>` delivers an explicit confirmation message back to Signal).*

#### Via CLI:
```bash
# Start a fresh chat session and persist the new session ID
uv run riva session new

# Print the active session ID
uv run riva session id

# List past chat sessions and their turn counts
uv run riva session list
uv run riva session list --limit 10
```

---

## Design Principles

- Modular architecture
- Shared code lives only in `common`
- Domain logic stays inside individual packages
- Independent dependency management
- Simple package boundaries
- Easy to extend with additional Genie packages

---

## Future Direction

The long-term goal is for each Genie package to act as a plugin that can be dynamically discovered and loaded by the main `riva-agent` application, enabling new capabilities to be added with minimal changes to the orchestrator.
