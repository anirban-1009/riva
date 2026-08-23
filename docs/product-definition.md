# Riva Product Definition

> Mirrors the [wiki](https://github.com/anirban-1009/riva/wiki/Product-Definition) — the wiki is the canonical source; update it first.

What Riva is, who it's for, what "done" means, and what we're deliberately not building. This page is the tiebreaker when a scope question comes up — if a proposed feature can't be traced back to something here, it doesn't get built.

**Status**: v1 defined, pre-implementation. Last reviewed 2026-08-23 — all open questions from §9 resolved; see §9 for the decisions log.

---

## 1. Product Statement

> Riva is a private personal assistant that knows me — a persistent memory and profile layer over a local LLM, reachable from the tools I already use.

The differentiator is not the gateway and not the Genies. It's that **Riva accumulates a model of one person that no hosted assistant is allowed to hold**, because the underlying data — finances, health, career anxieties — is too sensitive to send to someone else's server. Every hosted assistant starts each conversation as a stranger. Riva doesn't.

Everything else in this repo is a delivery mechanism for that one idea.

---

## 2. Who It's For

**User: me, one person, every day.** Not a portfolio piece, not an open-source product, not a multi-user service.

This is a liberating constraint, and it should be used aggressively:

- Single-user assumptions are **correct**, not technical debt. No auth, no tenancy, no user IDs, no onboarding, no migration story.
- Setup ergonomics for strangers are worth **zero**. A README that only I can follow is a fine README.
- Generality is a cost, not a virtue. Build for my actual workflows, not for the abstract user.
- Tests exist to stop me losing a morning to a silent regression — not to signal quality to a reader.

**The bar for every feature**: would I notice if it disappeared? If not, it shouldn't have been built.

---

## 3. Product Principles

Each of these rules something out. A principle that forbids nothing isn't a principle.

### 3.1 Local-only is a privacy guarantee, not a cost optimization

Personal financial, health, and career data never leaves the machine. This is the reason the project exists.

**What this forbids:**

- Hosted embedding APIs for the memory store. Embeddings of my journal are still my journal. Local embedding model or no semantic memory.
- Treating the `openai` provider as a production path. It exists for **evaluation and benchmarking only** — measuring how far behind local quality is. `config.yml.example` marks it dev/eval-only in the comment above `provider:`.
- Any cloud sync, telemetry, crash reporting, or hosted vector DB. Ever.

**Egress rule for outbound integrations** (Notion sync, RSS, arXiv): pulling public data *in* is unrestricted. Pushing data *out* is limited to content I explicitly authored and explicitly asked to publish. Profile fields and memory records are never egress-eligible, and no integration gets to decide this for itself.

### 3.2 Memory is the product; capabilities are readers of it

[Architecture](architecture.md) now leads with memory and profile as the load-bearing layer, ahead of the plugin protocol. A Genie is a thing that reads and writes memory in a domain-shaped way.

**What this forbids**: building the plugin protocol before the memory layer exists. See §6.

### 3.3 Invisible memory is untrustworthy memory

Memory systems fail on trust, not on recall. The failure mode that kills this product is not "Riva forgot" — it's "Riva confidently remembered something wrong, I couldn't see why, and I stopped believing it." Recovering that trust costs more than the feature was worth.

**What this requires**: inspection and deletion ship *with* memory in v1, not after it. I must always be able to answer "what does Riva think it knows about me, and where did that come from?"

### 3.4 Riva is not a coding assistant

I already have good coding tools. Riva's job is the personal domain — the one no hosted tool can serve. When Riva is proxying a coding client, it should stay out of the way entirely. See §5 for why this matters architecturally.

---

## 4. Explicit Non-Goals

Naming these is what makes the v1 scope real.

| Not building | Why |
|---|---|
| Multi-user, auth, accounts | One user. Permanently. |
| A web or desktop UI | The CLI plus existing OpenAI-compatible clients cover every surface I chose. A UI is a maintenance burden with no user. |
| All four Genies | Three of the four are currently aspirational README files. Building four shallow domains beats nothing; building one deep one beats four shallow ones. |
| The plugin protocol (in v1) | Deferred deliberately — see §6. |
| Training or fine-tuning models | Riva composes models, it doesn't make them. |
| Beating frontier models on general reasoning | Local models will lose. Riva wins on *knowing me*, not on raw capability. |

---

## 5. The Architectural Conflict, Resolved

**This was the most important open decision. It's resolved below.**

Today [`gateway.py`](../src/riva_agent/api/gateway.py) is a **stateless proxy**: `chat_completions` reads `request.messages` and forwards it verbatim. Riva owns no conversation state and assembles no prompt.

Memory requires the exact opposite. To use what it knows, Riva must own prompt assembly — inject profile and recalled facts, then write new facts back after the turn.

That collides with the OpenClaw surface. OpenClaw is a coding agent that manages its own history and system prompt, and sends large tool-augmented prompts. Injecting my fitness goals and budget into a coding request is **actively harmful**: it's noise that degrades the task and burns context on a machine already constrained to an 18GB memory budget (see [Local Model Memory](local-model-memory.md)).

So Riva needs two behaviours through one API:

1. **Pass-through mode** — clean proxy, no injection, no memory writes. Serves OpenClaw and any coding client. This is what exists today and it should stay exactly as it is.
2. **Assistant mode** — Riva assembles the prompt, injects profile and memory, persists what it learns. Serves the CLI and the proactive scheduler.

**Decision: route on the `model` field.** A virtual model id (`riva`) means assistant mode; any real model id (`gemma4:12b-mlx`) stays pass-through. This needs no new endpoints, works with every OpenAI-compatible client including model pickers, makes the mode explicit and visible at the call site, and leaves the coding path untouched. Rejected alternative: a separate `/riva/chat` endpoint — also viable, but it loses compatibility with existing clients, which was the whole point of the gateway.

This determines where memory read/write hooks live in M1: `chat_completions` checks `model == "riva"` before forwarding the request, gating whether prompt assembly and memory writes run at all. Everything else in `gateway.py` — SSE contract, heartbeats, config overrides — is unaffected.

---

## 6. v1 Scope: Memory and Profile That Persist

**v1 is done when Riva remembers me across sessions, and I trust what it remembers.**

Nothing else is in v1. Not the plugin protocol, not a Genie, not the router.

### Why the plugin protocol is deferred

[Architecture](architecture.md) §5 specifies a complete `Plugin` protocol — `can_handle`, `gather_context`, `tools`, `execute` — designed in full before a single Genie exists. That interface is currently a guess about the needs of four packages that are empty. Designing it now means committing to an abstraction with zero implementations to validate it against, and the confidence-score routing in particular (`can_handle` returning a float) assumes a routing model that has never been tested.

Build the memory layer first, then build **one** real Genie directly against it, then extract the protocol from what that Genie actually needed. The protocol will be smaller and righter.

### v1 Acceptance Criteria

Concrete and testable. v1 ships when all of these hold:

1. **Profile persists.** A structured profile (goals, constraints, preferences, key facts) survives restarts and is editable both by hand and through conversation.
2. **Episodic memory persists.** Conversations in assistant mode are recorded and survive restarts.
3. **Recall demonstrably works.** In a fresh session, Riva correctly uses a fact I established days earlier without me restating it.
4. **Assistant mode is scoped.** A request through the pass-through path produces byte-identical behaviour to today — no injection, no memory writes, no added latency. §5 is resolved and implemented.
5. **Memory is inspectable.** `riva memory list` shows what's stored; each record traces to the conversation that produced it.
6. **Memory is correctable.** `riva memory forget <id>` removes a record, and it stays gone.
7. **Nothing leaks.** Memory and profile live in local storage with local embeddings. Verified by inspecting outbound traffic during a full session, not by assuming.
8. **It survives me.** Regression tests cover the SSE stream contract and the memory read/write path — the two things whose silent breakage would cost me a morning.

### Deliberately not in v1

Semantic/vector recall (start with recency and explicit profile lookup — prove the loop before adding retrieval sophistication), memory consolidation or summarization, conflict resolution between contradictory facts, and any Genie.

### Memory Admission Policy

What earns a memory record. Two channels, both traceable to a source — because §3.3 requires I can always answer "where did that come from":

1. **Explicit save.** I say "remember X" (or invoke a dedicated tool call). Saved verbatim, tagged `explicit`, committed immediately — no review step, since I asked for it directly.
2. **Passive candidates.** After each assistant-mode turn, a lightweight local pass proposes 0–3 candidate facts against a fixed schema (preference / constraint / goal / dated fact), each carrying the source snippet it was drawn from. Candidates are **staged, not committed**: they surface in `riva memory list --pending` for a one-keystroke accept/reject next time I'm in the CLI, and auto-expire unreviewed after 7 days.

This keeps store growth bounded by a human decision on every committed record, rather than an LLM's silent judgment call — the exact failure mode §3.3 warns about.

---

## 7. Roadmap After v1

Sequenced by dependency, not ambition.

| Milestone | Outcome | Depends on |
|---|---|---|
| **M0 — Gateway hardening** | Contract tests on streaming; `openai` provider marked eval-only in config. Small, thin, do it alongside M1. | — |
| **M1 — Profile** | Structured profile store, hand- and conversation-editable. | §5 resolved |
| **M2 — Episodic memory** | Conversation persistence and recency-based recall. | M1 |
| **M3 — CLI** | `riva ask`, `riva memory list/forget`. The trust surface from §3.3. | M2 |
| **M4 — Semantic recall** | Local-embedding vector search over memory, once recency is proven insufficient. | M3 |
| **M5 — Proactive digests** | Scheduler process, first digest. A second entry point beyond the gateway. Delivered via a local macOS notification (`osascript`/`terminal-notifier`); the digest body is written to `~/riva/digests/` as the durable, inspectable record — nothing leaves the machine, satisfying §3.1. | M3 |
| **M6 — First Genie** | One domain, built directly on memory. Protocol extracted afterward, not before. | M4 |

**Genie priority when M6 arrives**: Lighthouse Genie first. Its data is the least sensitive (public news, papers, repos), which makes it the safest place to learn the integration patterns, and its output is naturally periodic — so it doubles as the first real consumer of the M5 scheduler. Money and Workout carry the sensitive data and should be built once the memory layer has earned trust.

---

## 8. Success Metrics

Usage metrics for a one-person product. Reviewed monthly, honestly.

1. **Retention** — I use Riva 5+ days a week without falling back to a hosted assistant for personal questions. *This is the only metric that really matters; the rest diagnose it.*
2. **Recall value** — at least once a day, Riva uses something it remembered that I didn't restate.
3. **No repetition** — a month passes without me having to re-tell Riva a core fact about myself.
4. **Trust** — zero incidents of confidently-wrong recall that I couldn't trace to a source.
5. **Reliability** — zero mornings lost to Riva being broken.

**The kill signal**: if after v1 I find myself opening a hosted assistant for personal questions out of habit, the memory layer didn't deliver, and the answer is to fix recall quality — not to add Genies.

---

## 9. Decisions Log

Formerly "Open Questions." Resolved 2026-08-23.

- **§5 routing** — decided: virtual model id (`riva`) on the `model` field. See §5.
- **Storage engine** — decided: SQLite for both profile and episodic memory. No server process, no network surface (§3.1), and a file I can open and inspect by hand with the `sqlite3` CLI (§3.3) — no tooling gap to justify anything heavier for a single-user store. If M4's semantic recall needs vector search, the `sqlite-vec` extension covers it without a storage-engine swap; revisit only if that turns out not to be true.
- **Memory admission policy** — decided: explicit save + staged/reviewed passive candidates. See §6, "Memory Admission Policy."
- **Notification channel for M5** — decided: local macOS notification + digest file under `~/riva/digests/`. See §7.
- **Doc drift** — fixed: [Architecture](architecture.md) now marks unimplemented modules (`common/memory/`, `common/profile/`, `common/interfaces/plugin.py`, `common/llm/router.py`) as planned and leads with memory/profile ahead of the plugin protocol.
