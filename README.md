# Riva Agent

Riva Agent is an AI platform compatible with OpenClaw that manages and orchestrates various modular capabilities (Genie packages) within a `uv` workspace, while sharing common infrastructure through the `common` package.

## Documentation

The **[wiki](https://github.com/anirban-1009/riva/wiki)** is the primary, canonical source for documentation — write/update docs there first. The `docs/` folder mirrors select wiki pages for in-repo reading:
- **[Development Timeline](docs/development_timeline.md)**: Phased roadmap and milestone schedule from foundation through v1 and post-v1.
- **[Local Dev Runbook](docs/local-dev-runbook.md)**: Command reference for starting, health-checking, and recovering the local dev stack.
- **[Architecture](docs/architecture.md)**: System design philosophy, layers, and core interfaces.
- **[Inference Latency Investigation](docs/inference-latency.md)**: Root causes, benchmarks, and gateway configuration controls.

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

Sync all dependencies:

```bash
uv sync
```

View workspace dependency tree:

```bash
uv tree
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
