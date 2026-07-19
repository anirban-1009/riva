# experiments

## Purpose

The `experiments` package is responsible for research, prototypes, benchmarks, and proof-of-concept implementations within the platform.

## Responsibilities

- **Prototyping**: Developing and sandboxing new ideas, models, and workflows.
- **Benchmarking**: Evaluating performance, accuracy, and costs of different prompts, LLMs, and utilities.
- **Proof of Concept**: Verifying the feasibility of major library/package upgrades or new tool integrations before production.

## Dependencies

- `common`

## Package Structure

```text
src/
└── experiments/
    ├── __init__.py
    ├── models.py
    ├── services.py
    ├── tools.py
    ├── prompts.py
    └── plugin.py
```

## Running

```bash
uv run --package experiments python -m experiments
```

## Notes

This package should remain independent of other Genie packages. Any shared functionality should be moved into `common`.
