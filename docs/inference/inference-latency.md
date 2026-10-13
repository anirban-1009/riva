# Inference Latency: What We Learned and How We Fixed It

> Mirrors the [wiki](https://github.com/anirban-1009/riva/wiki/Inference-Latency) — the wiki is the canonical source; update it first.

This document records a real latency investigation against the gateway,
including root causes that were specific to this stack (Ollama + a locally
loaded model + OpenClaw as a client) and easy to miss without live testing.
Kept as a reference for the next time responses feel slow or inconsistent.

## What was actually slow, and why

### 1. A hidden "thinking" tax on every reply

`gemma4:12b-mlx` supports Ollama's `think` field, but **defaults to thinking
on** when that field is simply omitted from the request. The gateway never
sent it at all, so every reply — even "hi" — silently paid for an internal
reasoning pass before answering. Confirmed directly: the same prompt sent to
Ollama took **6.3s** with `think` omitted vs **0.6s** with `think: false` set
explicitly.

**Fix**: `riva_agent/reasoning.py` decides per-request whether to enable
thinking. A live `/api/tags` capability check gates whether the model even
supports it (replacing an earlier hardcoded model-name list, which is
exactly what missed `gemma4` in the first place and would miss the next new
model the same way), then a prompt-complexity heuristic decides `true`/
`false` for models that do support it.

### 2. The gateway's own heartbeat was killing slow requests

The SSE keep-alive used `asyncio.wait_for(..., timeout=15)`. `wait_for`
doesn't just time out — it **cancels** the coroutine it's wrapping. So the
moment a prompt's prefill took longer than 15 seconds (routine for large,
tool-augmented coding-agent prompts), it tore down the in-flight Ollama
request mid-generation, and the client received an empty "successful"
response instead of an error or a slow-but-complete one. This produced
exactly the "Agent couldn't generate a response" failures seen in testing.

**Fix**: switched to `asyncio.wait`, which polls the same task without
cancelling it, so a long prefill just gets more heartbeats instead of
getting killed.

### 3. Two large models fighting for the same memory

The biggest discovery: something entirely outside the gateway — OpenClaw's
web-search feature — was calling Ollama's `/api/generate` directly,
invisible to the gateway's own logs, taking 11–70+ seconds per call. That,
plus `gpt-oss` (12.9GB, `num_ctx: 131072`) and `gemma4` (9-10GB) both getting
loaded, meant Ollama was constantly evicting and reloading multi-gigabyte
models from disk — and generation throughput itself dropped (~32 tok/s to
~13-15 tok/s) under the resulting memory pressure. This is what made latency
so wildly inconsistent: anywhere from 0.4s to 3m27s for similar-looking
requests.

**Fix**: disabled OpenClaw's web-search feature and cut `gpt-oss`'s context
window from 131072 to 8192. Confirmed clean afterward: only one model
resident at a time, no more stray `/api/generate` calls.

## The control surface added

Rather than hardcoding these decisions, a project-root `config.yml` now
holds three overrides that apply regardless of what any client requests —
see `riva_agent/config.py`:

- `model` — pin the whole platform to one model.
- `thinking` — hard kill-switch, bypasses the heuristic entirely.
- `streaming` — force non-streaming responses globally.

## End result

Once the model-thrashing was resolved, a simple prompt through the full
gateway went from the 6–70+ second range down to **~1.5 seconds** — verified
directly against the running gateway, not estimated.
