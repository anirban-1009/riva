# Telemetry as the Bootstrap for an Eval Harness — Proposal

## The gap this addresses

Multiple job descriptions tailored against the resume converged on the same ask in different words: "built and run evals, not just prompts in a notebook" (posting #1), "build and defend the eval suite... every behaviour change ships behind a golden set and a regression gate... you bring up evaluation before we do" (Vahan.ai), "write unit and integration tests and participate in code reviews" (Teradata). Riva's existing evaluation work (`docs/inference-latency.md`, `docs/mlx-server-evaluation.md`, `docs/local-model-memory.md`) is genuinely rigorous *manual* benchmarking — controlled comparisons, caught measurement bugs, honestly-recorded caveats — but it's one-off, run by hand each time a question comes up. It is not a standing system.

**The core idea of this proposal**: don't build "an eval harness" as a separate green-field project. Instrument the gateway once, and let a real eval system grow out of the data that instrumentation produces. Telemetry and evaluation are the same pipeline at different maturity stages, not two separate efforts.

## What "telemetry" means here

Every request that passes through `riva_agent/api/gateway.py`'s `/v1/chat/completions` gets one structured record, captured at the point the response completes (success or failure). This is additive to the existing per-request logging already described in `docs/architecture.md` (`request_id`, `model`, `stream`, `think`) — it turns those log lines into queryable, structured rows instead of text to grep.

### Proposed schema (one row per request)

| Field | Why it's captured |
|---|---|
| `request_id`, `timestamp` | Join key; time-series analysis |
| `genie` | Which Genie initiated the request (or `passthrough` for OpenClaw) — lets you slice quality/latency by domain later |
| `provider`, `model`, `backend` | Ollama vs. MLX vs. OpenAI-compatible, and which model/quant — exactly the axis `mlx-server-evaluation.md` compared by hand |
| `prompt_tokens`, `completion_tokens` | Cost/throughput analysis |
| `ttft_ms` (time to first token) | The text equivalent of the "time-to-first-audio" latency metric that shows up in voice-agent JDs — the moment a stream starts mattering more than total latency |
| `total_latency_ms` | What `inference-latency.md` measured by hand each time |
| `thinking_used`, `streaming` | Already-decided per-request flags from `reasoning.py` and `config.yml` — free to capture, already computed |
| `error`, `error_type` | Failure-rate tracking without grepping logs |
| `prompt_text`, `response_text` | Stored **locally only** — see the privacy note below |

### Storage: local SQLite, no exceptions

A new `telemetry_events` table, alongside wherever the memory/profile SQLite store ends up living (per `product-definition.md`'s open question on storage engine — this can reuse that same database). No hosted telemetry backend (Honeycomb, Datadog, any SaaS APM) — that would violate the platform's own local-only, no-egress principle (`product-definition.md` §3.1). Storing full prompt/response text **locally** is consistent with that principle — the rule is about data leaving the machine, not about what's retained on it. This is worth stating explicitly in the design so it doesn't read as an oversight later.

## The bridge: five stages, each one a small addition to the last

This is the part that actually closes the gap — not "collect logs," but the specific path from logs to something an interviewer would recognize as an eval system.

### Stage 1 — Dashboard (closes "observability" on its own)

A local script or a small Streamlit/FastAPI+HTMX page reading straight from `telemetry_events`: p50/p95 latency, token throughput, thinking-mode frequency, error rate, all sliceable by model/provider/genie. This alone is a legitimate answer to Teradata's "identify and resolve system performance bottlenecks" and the general "observability" ask — and it's the cheapest stage to build.

### Stage 2 — Regression detection (the "regression gate," bootstrapped from data already being collected)

After any model, config, or prompt change: compare a window of telemetry from before the change to a window after. Did p95 latency move? Did the error rate move? Did token cost per request change? This is a real regression gate — not over model *output quality* yet, but over the operational characteristics that `inference-latency.md` and `mlx-server-evaluation.md` were manually re-checking every time. No separate golden-set infrastructure is needed for this stage; it's a query over Stage 1's data.

### Stage 3 — Sampling for quality labeling (where a golden set actually comes from)

Periodically (or on every Nth request), copy a request/response pair into a separate `review_queue` table. Review sampled pairs by hand on some cadence and label each `good` / `bad` / `needs_correction`. This is the realistic way a golden set gets built — organically, from real traffic, a little at a time — rather than the common failure mode of trying to write 200 test cases from scratch before doing anything else and never finishing.

### Stage 4 — Golden-set regression (the actual "eval suite" the job descriptions meant)

Once enough labeled `good` pairs accumulate, they become fixtures: re-run each one's prompt against any new model/config, and either diff the output against the recorded good answer with a cheap similarity check, or use a second, larger local model as an LLM-judge for a coarse pass/fail. Flag drift for human review rather than auto-blocking — a solo project doesn't need a hard CI gate, but the mechanism is identical to one that would.

### Stage 5 — Continuous, data-backed model choice

Every model/backend decision in `mlx-server-evaluation.md` and `local-model-memory.md` was made by hand, once, from a handful of test prompts. With Stages 1-2 running continuously, those same comparisons (latency, memory-adjacent proxies, throughput) update themselves from real traffic instead of needing a fresh manual benchmark every time a new model or quant shows up. This is a direct, literal match for the JD phrase "you have opinions about model choice grounded in latency and cost numbers — and you change them when shown better numbers": the numbers are just always current instead of needing to be re-measured.

## Tech choices, and why each one is worth naming on its own

- **OpenTelemetry** for the instrumentation layer, even though the "backend" here is local SQLite rather than a hosted OTel collector. Using the SDK/API surface correctly — spans, attributes, context propagation across the async request lifecycle — is the resume-relevant skill; where the data lands is a separate, swappable decision.
- **SQLite** for storage — reuses the same engine the platform's own open questions already point to for memory/profile, keeps everything local, and is trivial to query ad hoc (`sqlite3` CLI, a notebook, a script) without standing up infrastructure.
- **Streamlit** (or a minimal FastAPI+HTMX page) for Stage 1's dashboard — deliberately not Grafana+Prometheus, which would be its own multi-day side quest unless that specific stack is a separate goal worth naming.
- **Structured JSON-lines as the cheapest possible first step** — before even standing up the SQLite table, wrapping the gateway in something that appends one JSON object per request to a log file is Stage 0: zero schema migrations, immediately greppable, and a trivial `jq`/pandas job to backfill into SQLite once Stage 1 is worth building.

## Implementation order

1. **Stage 0**: JSON-lines telemetry log wrapping every `/v1/chat/completions` call (cheapest possible instrumentation; can ship same-day).
2. **Stage 1**: Move to a `telemetry_events` SQLite table once trend queries (not just tailing a log file) are worth having; build the dashboard.
3. **Stage 2**: Before/after regression queries, run manually first, then as a script triggered after any `config.yml` change.
4. **Stage 3**: `review_queue` sampling + a lightweight manual-labeling loop (even a CLI prompt is fine to start).
5. **Stage 4**: Golden-set replay + drift flagging once Stage 3 has produced enough labeled pairs to be worth automating.
6. **Stage 5** falls out of Stages 1-2 automatically — no separate build step, just leaving them running.

## What this closes, and what it still doesn't

**Closes**: "observability" (Teradata), "you bring up evaluation before we do" and "opinions on model choice grounded in latency/cost numbers, changed when shown better numbers" (Vahan.ai) — the last one almost word-for-word, once Stage 5 is running.

**Does not fully close on its own**: Vahan.ai's specific ask for a "golden set and regression gate" gating *every behaviour change* as a hard CI-style requirement — Stage 4 gets genuinely close to this in substance, but calling it that outright should wait until Stage 4 is actually built and has caught at least one real regression, not just designed. Precision here matters the same way the Kafka/Redpanda naming does in the companion `money-genie` proposal — describe what's actually running, not the aspiration.

## Open questions

- Same storage-engine question `product-definition.md` already has open (SQLite, presumably shared with memory/profile) — resolve once, use everywhere.
- Sampling rate for Stage 3 — every request is cheap to log but expensive to hand-label; needs a deliberate cadence (e.g. N per day) rather than "whenever."
- Whether Stage 4's judge is a second local model call (cost: more inference) or a cheaper string/embedding similarity check (cost: less discriminating) — likely worth prototyping both on a small labeled set before committing.
