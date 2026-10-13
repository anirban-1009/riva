# Riva Documentation Index

This directory contains technical specifications, architecture guides, empirical investigations, and operational runbooks for the Riva platform.

The canonical wiki documentation mirrors the files in these categorized directories.

---

## Directory Structure

```text
docs/
├── architecture/         # System design, virtual model routing, and agent capabilities
│   ├── architecture.md
│   └── assistant-capabilities.md
├── memory/               # Episodic store, semantic recall, and profile routing
│   ├── semantic-memory-architecture.md
│   ├── nlp-memory-routing.md
│   └── memory-store-evaluation.md
├── product/              # Product requirements, core tenets, and milestone schedule
│   ├── product-definition.md
│   └── development-timeline.md
├── inference/            # Local model evaluations, memory footprints, and latency benchmarks
│   ├── inference-latency.md
│   ├── laya-mlx-and-compute-bottlenecks.md
│   ├── mlx-server-evaluation.md
│   ├── local-model-memory.md
│   ├── model-context-window.md
│   └── llm-investigation-notes.md
└── runbooks/             # Operational runbooks and service recovery procedures
    └── local-dev-runbook.md
```

---

## 1. Architecture & Capabilities

| Document | Description |
|---|---|
| [System Architecture](architecture/architecture.md) | Three-layer platform design, virtual model routing, API gateway, and plugin protocol. |
| [Assistant Capabilities](architecture/assistant-capabilities.md) | Assistant runtime modes, capability matrix, extended-thinking heuristics, and tooling specs. |

---

## 2. Memory & State Management

| Document | Description |
|---|---|
| [Semantic Memory Architecture](memory/semantic-memory-architecture.md) | On-device embeddings, `sqlite-vec` integration, hybrid context assembly, and pollution defense. |
| [NLP Memory Routing](memory/nlp-memory-routing.md) | Why dependency parsing outperforms embedding classification for first-person memory gating. |
| [Memory Store Evaluation](memory/memory-store-evaluation.md) | Empirical benchmarks comparing SQLite, local Mem0, and hybrid routing latency. |

---

## 3. Product & Roadmap

| Document | Description |
|---|---|
| [Product Definition](product/product-definition.md) | Core tenets, v1 acceptance criteria, memory admission policy, and genie capability order. |
| [Development Timeline](product/development-timeline.md) | Milestone schedule from Foundation (M0) through Trust CLI (M3) and Semantic Recall (M4). |

---

## 4. Local Model & Inference Benchmarks

| Document | Description |
|---|---|
| [Inference Latency Investigation](inference/inference-latency.md) | Root causes of local model latency, thinking heuristics, and MLX benchmarks. |
| [Laya-MLX & Compute Bottlenecks](inference/laya-mlx-and-compute-bottlenecks.md) | Apple Silicon unified memory profiling, compute bottlenecks, and engine trade-offs. |
| [MLX Server Evaluation](inference/mlx-server-evaluation.md) | Comparative evaluation between `mlx_lm.server` and Ollama on Apple Silicon. |
| [Local Model Memory](inference/local-model-memory.md) | Quantization trade-offs, resident memory footprints, and multi-model coexistence. |
| [Model Context Window](inference/model-context-window.md) | Context window sizing, token allocation, and truncation bug investigations. |
| [LLM Investigation Notes](inference/llm-investigation-notes.md) | Raw benchmark data, speed measurements, and preliminary exploration logs. |

---

## 5. Operations & Runbooks

| Document | Description |
|---|---|
| [Local Dev Runbook](runbooks/local-dev-runbook.md) | Local development setup, port mappings, service controls, and disaster recovery procedures. |
