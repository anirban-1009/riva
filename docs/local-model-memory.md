# Local Model Memory: Why the Dev Machine Was Thrashing, and What Fixed It

> Mirrors the [wiki](https://github.com/anirban-1009/riva/wiki/Local-Model-Memory) — the wiki is the canonical source; update it first.

This document records a memory investigation on the dev laptop (Apple
Silicon, 18GB unified memory) running `riva-agent`'s local Ollama backend,
and the benchmark that led to switching the default model. Kept as a
reference for the next time the machine feels sluggish while a local model
is loaded.

> **This was round one of three.** The fix here (`UD-Q3_K_XL`) solved the
> memory problem; `docs/model-context-window.md` covers a context-window bug
> it introduced for OpenClaw, and `docs/mlx-server-evaluation.md` covers a
> real speed regression found afterward that led to switching backends
> entirely. The model actually live in `config.yml` today is the one from
> that third round, not this one — see `docs/mlx-server-evaluation.md`'s
> "Current status" for what's actually running.

## What was actually happening

### 1. One process was eating over half the machine's memory

The gateway was slow (7–22s for short replies) and the system was swapping
heavily:

```
vm.swapusage: total ≈ 14.3 GB   used ≈ 13.3 GB   free ≈ 1.0 GB   (93% consumed)
```

Sorting processes by memory found one dominant consumer — `ollama` running
`gemma4:12b-mlx` — at **10.0 GB resident**, ahead of Docker's VM (1.8GB),
WindowServer (1.2GB), and every other desktop app combined. On an 18GB
machine, the model alone consumed over half the available memory before any
normal app was even running, so swap filled up and stayed pinned near its
ceiling.

Quitting Docker Desktop's window was tried first and barely moved the
needle (swap stayed ~13.1/14.3GB used) — confirming the model, not Docker,
was the actual bottleneck.

### 2. Nothing was actively using the model — it was just resident

A follow-up check found no active connections to the gateway and only one
idle pooled connection into Ollama's port. The 10GB wasn't a stuck request
or a leak — it was the model sitting loaded in memory, held there by the
gateway's `keep_alive: 30m` setting (`common/src/common/llm/providers.py:15`).
That's expected behavior, just expensive at this model size on this machine.

### 3. Same model class, better quantization beat a smaller model

The instinct was to drop to a smaller model (fewer parameters), but that
trades away quality. Unsloth publishes "Dynamic" (`UD-`) GGUF quantizations
that keep more bits on sensitive layers instead of uniformly downcasting the
whole model, so they hold quality much better than a generic quant at the
same file size — and Ollama can pull them directly:
`ollama pull hf.co/unsloth/gemma-4-12b-it-GGUF:<tag>`.

Benchmarked the current model against two Unsloth quants of the *same* 12B
model with one fixed prompt each (cold load → generate → measure resident
RSS + latency):

| Model | Disk size | Resident RAM | Cold latency | Quality |
|---|---|---|---|---|
| `gemma4:12b-mlx` (previous default) | 7.7GB | ~10GB¹ | 150s | Coherent |
| `UD-Q4_K_XL` | 7.5GB | 7.55GB | 175s² | Coherent |
| **`UD-Q3_K_XL`** | 6.2GB | **6.45GB** | **65s** | Coherent, no visible drop |

¹ From a separate system-wide check, not the benchmark's own sampler — `ps`
undercounts MLX's Metal-offloaded memory, so this number isn't collected the
same way as the other two.
² All three runs were cold loads, so latency is dominated by disk/page-fault
time rather than steady-state throughput; `UD-Q4_K_XL` coming out slower
than the previous default is most likely noise from that, not a real
regression.

A methodology snag caught mid-benchmark: the RSS sampler initially looked
for a process named `ollama runner` (correct for the MLX engine), but
GGUF-quantized models run under a completely different process,
`llama-server`. The first GGUF sample came back as a bogus `0GB` until this
was found and the sampler pattern was widened to match both.

**Fix**: switched the default local model to `UD-Q3_K_XL` — ~3.5GB less
resident than the previous default, meaningfully faster even accounting for
cold-load noise, and no visible quality loss on the test prompt. Confirmed
live against the running gateway: a request specifying a different model
still comes back tagged `UD-Q3_K_XL`, confirming the pin is in effect.

## The control surface used

`config.yml`'s `model` key (see `riva_agent/config.py`) pins the whole
platform to one model regardless of what any client requests — this is how
the new default is applied without touching gateway code:

```yaml
model: hf.co/unsloth/gemma-4-12b-it-GGUF:UD-Q3_K_XL
```

## Caveats

- Single prompt, single run per candidate — directional, not a rigorous
  benchmark. Worth re-running with real `riva-agent` prompts (code-heavy,
  multi-step, long-context) before treating this as fully validated.
- Latency numbers are cold-load dominated, not a clean measure of
  steady-state generation speed.
- The MLX baseline's memory figure wasn't captured by the same method as the
  two GGUF quants (see footnote 1) — a true apples-to-apples comparison would
  need something like `powermetrics` (requires `sudo`) to capture MLX's
  Metal-resident memory directly.

## End result

Switching to `UD-Q3_K_XL` cuts resident memory from ~10GB to ~6.45GB and
resolves the swap-thrashing this investigation started from — leaving real
headroom on an 18GB machine instead of consuming nearly all of it. Applied
in `config.yml` and confirmed live against the running gateway. Still worth
validating against real `riva-agent` workloads (see [Caveats](#caveats))
before fully trusting it beyond the test prompt. Unused pulled models
(`gemma3:4b`, `UD-Q4_K_XL`) can now be removed.
