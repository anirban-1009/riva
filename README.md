# Riva Agent

Riva Agent is an AI platform compatible with OpenClaw that manages and orchestrates various modular capabilities (Genie packages) within a `uv` workspace, while sharing common infrastructure through the `common` package.

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

Run the main application:

```bash
uv run --package riva-agent python -m riva_agent
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
