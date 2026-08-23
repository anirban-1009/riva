# Money Genie — ML & Event-Streaming Architecture Guideline

> Package-local design doc, not yet mirrored to the wiki. If this plan is adopted, fold the decisions into the wiki per the repo's normal convention (wiki is canonical; `docs/` mirrors it).

## Why this document exists

This is a deliberate architecture plan for `money-genie` written to close two specific, named skill gaps — PyTorch and Kafka — that showed up repeatedly across job descriptions tailored against the resume (Teradata: Java/Go/Python + Kafka preferred; Honeywell and Experity: PyTorch/TensorFlow as a named must-have). The intent is explicit: build real, defensible experience with both, inside a genie whose *stated* purpose already has natural room for them, rather than bolting them onto something that doesn't need them.

Both technologies are scoped below against `money-genie`'s own README responsibilities (expense categorization, cash-flow forecasting) so the resulting bullets are honest engineering, not resume padding wearing a project as a costume.

## Read this first: a real tension with `product-definition.md`

Riva's product definition lists as an explicit non-goal: *"Training or fine-tuning models — Riva composes models, it doesn't make them."* A PyTorch-based transaction categorizer or forecaster is, literally, training a model. That non-goal was almost certainly written with a different thing in mind — not competing with frontier LLMs — but as written, this plan conflicts with it.

Don't silently build around your own stated architecture doc. Pick one before writing code:

1. **Amend `product-definition.md`** to scope that non-goal precisely — e.g. "Riva does not train or fine-tune general-purpose language models; small, task-specific classical/deep-learning models within a Genie's own domain are in scope." This is probably the more honest fix, since the spirit of the original line was about not reinventing an LLM, not about banning all model training anywhere in the platform.
2. **Keep the non-goal as-is** and record this plan as a consciously-decided, logged exception in `product-definition.md`'s Open Questions section, with the reasoning written down (skill-building intent, not product necessity) so future-you doesn't wonder why money-genie contradicts the product doc.

Either way, this should be a recorded decision, not a quiet inconsistency — that's the same discipline `product-definition.md` already asks of everything else in this repo.

---

## Part 1 — PyTorch: two tasks that are already in scope

`money-genie`'s README already lists **"Expense Tracking & Categorization"** and **"Cash Flow Forecasting"** as core responsibilities. Both are genuine, bounded supervised-learning problems — good news, because it means PyTorch here is solving a real product need, not manufacturing one.

### 1a. Transaction categorization (classification)

**Problem**: an incoming transaction (merchant string, amount, date, account) needs a category label (groceries, rent, subscriptions, etc.).

**Why this has to be a real trained model, not an LLM prompt**: routing every transaction through the local LLM for categorization would "work," but it wouldn't close the PyTorch gap — it would just be more LLM usage. The point of this task is a small, purpose-built classifier trained on your own data.

**Design**:
- **Data source**: a local SQLite table of transactions plus user-corrected labels. Every correction is a training example — this mirrors Riva's own memory philosophy (`product-definition.md` §3.3: invisible/uncorrectable state is untrustworthy) applied to a model instead of a memory record.
- **Baseline first**: ship a rules/heuristic categorizer (merchant string contains "netflix" → subscriptions) before any model exists, so there's an honest number to beat and the feature works on day one.
- **Model v1**: a small `torch.nn.Module` — an embedding layer over character n-grams or a bag-of-words/TF-IDF vector feeding a couple of linear layers, trained with a real `DataLoader`/optimizer loop. Deliberately not a wrapper around a pretrained model at first; the point is to have written an actual training loop.
- **Model v2 (optional, once v1 works)**: fine-tune a small pretrained text encoder (e.g. a distilled BERT-class model) if the bag-of-words baseline plateaus — this is the point where "fine-tuning" becomes literally true and citable.
- **Serving**: model loads once at genie startup, runs locally (consistent with the local-only principle — no cloud training/inference service), and is versioned (a plain version file, mirroring the platform's existing commitizen/semver discipline).
- **Evaluation**: precision/recall per category and a confusion matrix against a held-out slice of your own labeled history. Surface the model's confidence alongside the predicted category — low-confidence predictions get flagged for the user to correct rather than silently trusted, which both improves the product and keeps generating training data.

### 1b. Cash-flow forecasting (sequence modeling)

**Problem**: project the next N days/weeks of income and expense from historical transaction patterns.

**Design**:
- **Baseline**: a moving-average or seasonal-naive forecast, documented with its own error numbers, before any neural model exists.
- **Model**: a small recurrent or temporal-convolutional PyTorch model trained on your own transaction history, aiming to beat the baseline.
- **Evaluation — backtesting**: train on months 1..N, predict month N+1, compare to what actually happened, roll the window forward and repeat. This backtest loop is itself a legitimate, citable evaluation practice (walk-forward validation), and it's a natural companion to the telemetry/eval work described in the separate `experiments/` proposal — the same discipline, applied to a forecasting model instead of an LLM.

### Build order for Part 1

1. Local SQLite transaction store + a correction-capture UI/CLI path (the training-data source for everything after this).
2. Rules-based categorization baseline — ships something correct immediately.
3. PyTorch categorization model v1, evaluated against the baseline on held-out data.
4. Cash-flow baseline (moving average), then the PyTorch forecasting model, backtested against it.

---

## Part 2 — Kafka: an event-driven transaction pipeline

### Say the quiet part out loud first

Riva is explicitly single-user and local-only. A multi-broker Kafka cluster for one person's transaction stream is not what a pragmatic engineer would reach for on the product merits alone — a local queue (Redis Streams, or even a plain SQLite-backed queue) would serve `money-genie` just as well with a fraction of the operational weight. Be honest with yourself about which goal is driving this: "best architecture for this product" or "real Kafka experience for a resume that keeps hitting this gap." Choosing the latter deliberately is fine — plenty of legitimate skill-building happens on side projects that are slightly over-engineered on purpose — but know that's what's happening, and be ready to say so in an interview if asked "why Kafka here?" (the honest answer — "I wanted hands-on experience with it, and I designed a use case where the reasoning below is genuinely defensible even if a queue would also work" — is a fine answer).

### A realistic single-broker architecture

- **Broker**: a single local Kafka broker (KRaft mode, no separate Zookeeper) or **Redpanda** (Kafka-API-compatible, single binary, much lighter to run on a laptop) via `docker-compose`, consistent with the project's existing Docker usage.
- **Topics**:
  - `transactions.raw` — producer: the import path (bank CSV, manual entry, or a future webhook source).
  - `transactions.categorized` — consumer: the PyTorch categorization service publishes results here after reading `transactions.raw`.
  - `budget.alerts` — consumer: a budget-threshold checker watches `transactions.categorized` and publishes alerts for the memory/profile layer to pick up.
- **Consumer groups**: categorization, forecasting, and budget-alerting as three independent consumer groups reading the same topic(s) — this is the part worth understanding and being able to explain, since "one producer, one consumer" doesn't demonstrate anything Kafka-specific over a plain queue.

### The honest reasons to reach for this (have these ready for an interview)

- **Decoupling** ingestion from potentially-slow ML inference (categorization/forecasting) so imports don't block on model latency.
- **Replayability** — reprocess historical transactions through a new model version by replaying `transactions.raw` from offset zero, without re-importing anything.
- **Multiple independent consumers** acting on the same event stream without coordinating with each other — the actual reason teams reach for a log-based broker instead of a queue.

### If precision matters later (it will, on a resume)

If the actual broker running is Redpanda, describe it that way — *"built a Kafka-API-compatible event-streaming pipeline (Redpanda)"* — rather than claiming Kafka itself, unless real Kafka is what's actually deployed. This kind of precision is exactly the sort of thing an interviewer who knows the space will probe, and getting caught overstating it costs more credibility than the precise version would have.

### Build order for Part 2

1. Redpanda (or Kafka/KRaft) via `docker-compose`, one topic (`transactions.raw`), one producer (the import path), one consumer (the categorization service from Part 1) — introduce this only once categorization already exists as something worth decoupling.
2. `transactions.categorized` topic + the forecasting service as a second independent consumer.
3. `budget.alerts` topic + a consumer that writes into the memory/profile layer once that layer exists (per the main product roadmap's M1/M2).

---

## Open questions to resolve before starting

- **Product-definition tension** (above) — amend the non-goal, or log a deliberate exception? Don't skip this.
- **Where does training happen?** Given the local-only principle, on-device (this laptop) or a periodic offline job on the same machine — no cloud training service is consistent with the rest of the platform.
- **Kafka or Redpanda?** Redpanda is almost certainly the more sensible choice for a laptop-run single-user app while still being an honest, describable "Kafka-API-compatible" claim.
- **Sequencing against the main roadmap**: `product-definition.md` currently defers *all* Genie work until after the memory layer (M1-M4) is built, with Lighthouse Genie first (§7, "Genie priority when M6 arrives"). This plan effectively proposes Money Genie work ahead of that sequencing. Worth deciding explicitly whether that's an accepted deviation (for the skill-building reasons above) or whether this plan waits its turn — either is defensible, but it's a second place this document knowingly diverges from the stated roadmap and should be a conscious call, not an accident.
