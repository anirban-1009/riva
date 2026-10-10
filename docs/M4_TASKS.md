# Milestone 4 (M4) — Semantic Recall: Task List

**Project Status**: 🟢 In Progress (Phase 2 Completed; Proceeding to Phase 3)
- [x] Local embedding provider implemented (`common/llm/embeddings.py`)
- [x] Basic embedding tests created (`tests/common/test_embeddings.py`)
- [x] Vector store integration (`sqlite-vec` in `common/memory/store.py`)

## Core Objectives
Enable cross-session semantic search to retrieve past facts and discussions relevant to the current prompt using strictly on-device embeddings and embedded vector search.

### Hard Constraints
- **Privacy**: Strictly on-device embeddings (Zero hosted APIs).
- **Zero Daemons**: Embedded vector search via `sqlite-vec` inside SQLite.
- **Inspectability**: Every retrieved vector must trace to a `turn_id` or `fact_id`.
- **Performance**: Ingestion must be asynchronous and non-blocking to the chat stream.

---

## Task Breakdown

### Phase 1: Local Embedding Engine (`common/llm/embeddings.py`)
- [x] **1.1 Model Selection & Runtime**
    - Implement local Ollama embeddings (`nomic-embed-text`) or in-process FastEmbed/ONNX (`bge-small-en-v1.5`).
    - Set up pooled `httpx.AsyncClient` for fast cold-starts.
- [x] **1.2 Embedding Client Protocol**
    - Implement `BaseEmbeddingProvider` with `embed_query` and `embed_documents`.
- [x] **1.3 Unit Tests**
    - Verify cosine similarity bounds and error resilience.

### Phase 2: Vector Store Integration (`sqlite-vec` in `common/memory/`)
- [x] **2.1 `sqlite-vec` Extension Loader**
    - Add `sqlite-vec` to `pyproject.toml`.
    - Configure `sqlite3.connect` to load extension dynamically.
- [x] **2.2 Schema Migration (`vec0` Virtual Table)**
    - Create `vec_turns` virtual table for embeddings.
    - Create `turn_embeddings` metadata join table.
- [x] **2.3 Vector Operations in `EpisodicStore`**
    - Implement `add_embedding`, `search_similar`, and `delete_embedding`.

### Phase 3: Asynchronous Ingestion & Lifecycle Management
- [ ] **3.1 Asynchronous Post-Turn Ingestion Worker**
    - Implement `asyncio.create_task` in `gateway.py` to embed turns after streaming ends.
    - Add filters for boilerplate/short turns.
- [ ] **3.2 Cascading Deletions & Storage Lifecycle**
    - Update `riva memory forget` and `prune()` to remove associated vectors.
    - Ensure `vacuum` and `backup` handle `sqlite-vec` tables.
- [ ] **3.3 Historical Backfill Tooling**
    - Create `riva memory reindex` CLI command.

### Phase 4: Hybrid Context Assembly in Gateway
- [ ] **4.1 Hybrid Retrieval Logic**
    - Concurrent fetch: Profile facts $\rightarrow$ Recent session turns $\rightarrow$ Semantic matches from past sessions.
- [ ] **4.2 Deduplication & Thresholding**
    - Exclude turns already in the active recency window.
    - Implement cosine distance threshold $\tau$ (e.g., $> 0.38$) to prevent hallucinations.
- [ ] **4.3 Prompt Injector Formatting**
    - Implement `<relevant_past_context>` block in the system prompt.

### Phase 5: Trust Surface & CLI Tooling (`riva memory`)
- [ ] **5.1 Semantic Search Command**
    - Implement `riva memory search` showing score, timestamp, and matched text.
- [ ] **5.2 Storage Telemetry Updates**
    - Update `riva storage status` to report vector count and disk footprint.
- [ ] **5.3 Selective Deletion**
    - Implement `riva memory forget-turn <turn_id>`.

### Phase 6: Evaluation & Benchmarking Suite
- [ ] **6.1 Latency Benchmark**
    - Verify retrieval phase executes in $< 40\text{ms}$ locally.
- [ ] **6.2 Semantic Recall Test Suite**
    - Create pytest cases for conceptual queries with zero token overlap.
- [ ] **6.3 Memory & VRAM Profiling**
    - Confirm embedding execution fits within 18GB unified memory budget.

---

## Execution Sequence
1. **Infrastructure**: `sqlite-vec` loading $\rightarrow$ Vector schema.
2. **Core Engine**: `embeddings.py` $\rightarrow$ `store.py` operations.
3. **Pipeline**: Background indexing in `gateway.py` $\rightarrow$ `riva memory search` CLI.
4. **Integration**: Hybrid prompt injection $\rightarrow$ End-to-end tests.
