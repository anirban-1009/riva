# Context Window: Why OpenClaw Got 400s After the Quant Switch

> Mirrors the [wiki](https://github.com/anirban-1009/riva/wiki/Model-Context-Window) — the wiki is the canonical source; update it first.

This document records a `400 Bad Request` investigation that surfaced right
after switching the default local model to `UD-Q3_K_XL` (see
`docs/local-model-memory.md`), including a wrong first guess that's worth
keeping on record so it doesn't get re-chased next time. Kept as a reference
for the next context-window-shaped error.

> **Round two of three.** `gemma4-q3-16k` (the fix below) was later replaced
> by a different backend entirely after a real speed regression turned up —
> see `docs/mlx-server-evaluation.md` for what's actually live in
> `config.yml` today. The context-window lesson here still applies to
> whatever model runs next, which is why this page is worth keeping.

## The symptom

After pinning `config.yml` to the Unsloth quant, OpenClaw started failing
requests through the gateway with:

```
RuntimeError: Ollama stream request failed: Client error '400 Bad Request'
for url 'http://localhost:11434/api/chat'
```

## First guess — wrong, but worth recording why

The initial theory was a "thinking" capability mismatch: `UD-Q3_K_XL`'s
`/api/tags` capabilities list `['completion', 'vision']` — no `thinking` —
yet a plain request with no `think` field streamed reasoning tokens by
default anyway. Explicitly sending `think: true` does 400 with `"does not
support thinking"`, which was reproducible in isolation.

This turned out to be a real quirk but **not the actual bug**: the gateway's
own capability gate (`gateway.py`, `chat_completions`) already prevents this
— it only sets `think` when `"thinking"` is in the model's live capabilities,
so it never sends `true` for this model. A direct test through the running
gateway confirmed a clean `200` with no `think` field involved. Chasing this
further would have been a dead end.

## The actual root cause

Found by reading Ollama's own request log directly (`~/.ollama/logs/server.log`)
instead of guessing further:

```
srv send_error: task id = 243, error: request (8042 tokens) exceeds the
available context size (4096 tokens), try increasing it
[GIN] ... | 400 | POST "/api/chat"
```

`UD-Q3_K_XL` is trained for a 262144-token context (confirmed via
`ollama show`), but Ollama's runtime loaded it with only **4096 tokens** —
its own conservative default, since nothing in the pulled model's Modelfile
set `num_ctx` explicitly. OpenClaw, as an agentic coding client, sends large
prompts (system prompt + tool definitions + conversation history); the
failing request was 8042 tokens — double what was available.
`--context-shift` was enabled on the runner but can't help when the
*initial* prompt alone already overflows the window.

## The fix — and the tradeoff behind the number chosen

Context window size drives KV-cache memory directly, which is exactly the
resource `docs/local-model-memory.md` spent effort shrinking (10GB → 6.45GB
resident). Jumping straight to OpenClaw's configured expectation
(`contextWindow: 128000`) would have clawed back a meaningful chunk of that
saving. Went with **16384** instead — 2x headroom over the 8042-token prompt
that actually failed, without ballooning memory back up.

Applied via a custom Ollama tag rather than a per-request parameter, so it's
guaranteed to stick regardless of what any client sends:

```bash
ollama show "hf.co/unsloth/gemma-4-12b-it-GGUF:UD-Q3_K_XL" --modelfile > Modelfile
echo "PARAMETER num_ctx 16384" >> Modelfile
ollama create gemma4-q3-16k -f Modelfile
```

This builds `gemma4-q3-16k` from the same underlying weights (no extra disk
used — blobs are reused by reference) with `num_ctx` baked in. `config.yml`
now points at this tag:

```yaml
model: gemma4-q3-16k
```

## Verification

- `ollama show gemma4-q3-16k --parameters` confirms `num_ctx 16384` is set.
- Direct Ollama request with the ~8042-token class of prompt that failed
  before: `200`, no error.
- Same prompt sent through the actual running gateway (`:8085`, not just raw
  Ollama): `200`, response correctly tagged `model: gemma4-q3-16k`.

## End result

OpenClaw's 400s are resolved — the exact prompt shape that triggered the
original error now completes successfully through the full gateway path.
The lesson for next time: when a model gets swapped, check its actual
loaded context window (`ollama show <tag>`) against what real clients send,
not just what fits in a quick manual test — the failure only showed up under
OpenClaw's real prompt sizes, not the short test prompts used during the
memory benchmark in `docs/local-model-memory.md`.
