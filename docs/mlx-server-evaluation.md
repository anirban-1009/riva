# MLX-Native Serving: Approach and Metrics

> Mirrors the [wiki](https://github.com/anirban-1009/riva/wiki/MLX-Server-Evaluation) — the wiki is the canonical source; update it first.

Third round of the local-model evaluation that started in
`docs/local-model-memory.md`. That doc solved the memory problem (Ollama +
GGUF quant) but introduced a real speed regression that only showed up once
`docs/model-context-window.md`'s context-window bug was fixed and steady-state
throughput could actually be measured cleanly. This document covers what was
tried next, why, and the numbers behind the model currently live in
`config.yml`.

## The problem this round started from

Once `gemma4-q3-16k` (the Unsloth GGUF quant from the previous round) was
actually generating tokens cleanly, its throughput was measured properly for
the first time — and it was meaningfully slower than the original model, not
just a wash:

| Model | Generation speed |
|---|---|
| `gemma4:12b-mlx` (original) | 26.2 tok/s |
| `gemma4-q3-16k` (GGUF quant) | 14.2 tok/s |

About 1.8x slower, confirmed on a clean warm request (not cold-load noise).
Full GPU/Metal offload was confirmed active (`49/49 layers` in Ollama's own
log), so the gap isn't a missing-acceleration bug — it's that llama.cpp's
Metal backend for GGUF K-quants generally isn't as optimized on Apple Silicon
as MLX's native execution path. The memory win was real, but it came at a
real throughput cost.

## Why not "just quantize the MLX model further"

Checked before assuming this was possible:

- Ollama's own library has no smaller MLX tag for `gemma4` than `12b-mlx`
  (already `NVFP4`, roughly 4-bit — verified via `ollama show`).
- `mlx-community`'s own further-quantized 12B builds aren't meaningfully
  smaller: `gemma-4-12B-it-OptiQ-4bit` (8.35GB) and `gemma-4-12B-mxfp4`
  (10.13GB) are the same 4-bit class already in use, not a real reduction.
  4-bit is roughly the practical floor for MLX quantization — there's no MLX
  equivalent of GGUF's more aggressive K-quant scheme.
- Ollama's `hf.co/...` pull mechanism **only accepts GGUF** — a direct test
  pulling an MLX repo failed outright:
  `Error: pull model manifest: 400: {"error":"Repository is not GGUF or is
  not compatible with llama.cpp"}`. There's no way to get an arbitrary MLX
  build into Ollama.

So "smaller + still MLX-fast" wasn't available as a quantization of the same
12B weights through Ollama at all.

## The approach: a different serving stack, the same model family

Gemma 4 ships its own architecturally smaller "effective parameter"
sub-models (E2B, E4B — not quantizations, genuinely smaller networks), and
`mlx-community` publishes MLX-native builds of them. Getting to one requires
bypassing Ollama for this model:

- **`mlx_lm.server`** — Apple's own MLX serving tool, run as a plain local
  process (`mlx_lm.server --model <repo> --port 8081`). It speaks the
  OpenAI-compatible `/v1/chat/completions` API natively.
- Because `riva-agent` already had `OpenAICompatibleProvider` (built earlier
  specifically to make the backend swappable), pointing the gateway at it
  required **zero new provider code** — just config.

Chose `mlx-community/gemma-4-E4B-it-qat-4bit`: instruction-tuned, and
quantization-*aware*-trained (calibrated for 4-bit during training, not
quantized after the fact like the GGUF candidate), which should hold quality
better than a post-training quant at the same bit depth.

## Metrics

All three measured with the same fixed prompt on the same hardware
(Apple M3 Pro, 18GB unified memory), warm (not cold-load) generation speed:

| Model | Backend | Disk size | Resident RAM | Generation speed |
|---|---|---|---|---|
| `gemma4:12b-mlx` (original) | Ollama + MLX | 7.7GB | ~10GB | 26.2 tok/s |
| `gemma4-q3-16k` | Ollama + llama.cpp | 6.2GB | 6.45GB | 14.2 tok/s |
| **`gemma-4-E4B-it-qat-4bit`** | `mlx_lm.server` + MLX | 6.33GB | **5.96GB** | **25.0 tok/s** |

Resident RAM measured system-wide (`top`'s process MEM column), not `ps`
RSS — `ps` undercounts MLX's Metal-offloaded memory, a lesson learned the
hard way during the first benchmark round (see `docs/local-model-memory.md`,
footnote 1).

Generation speed: first request after a cold load measured 20.6 tok/s
(includes warm-up compilation overhead MLX pays once); the number in the
table is the second, clean request — 275 completion tokens in 11.02s wall
time.

### Quality spot check

Same test prompt used in the original evaluation ("Write a 200 word
paragraph about tidal energy"), for direct comparability:

> "Tidal energy harnesses the predictable, powerful movement of ocean tides
> to generate electricity, offering a reliable and sustainable source of
> renewable power... The technology primarily utilizes tidal barrages—large
> dams built across estuaries—or underwater turbines that capture the
> kinetic energy of the incoming and outgoing tidal flows..."

354 completion tokens, coherent, covers the same core points as both earlier
candidates (predictability vs. solar/wind, barrage vs. turbine methods,
cost/ecological tradeoffs). No degradation visible on this test.

## Caveats

- **Different model, not a quant of the same weights.** E4B is Gemma 4's own
  smaller sub-model, architecturally distinct from the 12B model — not the
  same weights at lower precision like the GGUF comparison was. "Quality
  holds up" here is a one-prompt spot check, same limitation as every other
  candidate evaluated so far, but the delta being measured is different in
  kind (a smaller model, not just a smaller encoding of the same model).
- **Operational cost:** `mlx_lm.server` is a second long-lived process
  outside Ollama's management — no `keep_alive`, no automatic reboot
  survival, no shared model registry with Ollama's other tags. See
  `docs/local-dev-runbook.md` for start/stop/recovery commands.
- **Not hardened for exposure beyond localhost.** Checked its source
  directly: it's built on Python's stdlib `http.server`
  (`ThreadingHTTPServer` + `BaseHTTPRequestHandler`), not a real ASGI server
  like the `uvicorn`/FastAPI stack `riva-agent`'s own gateway runs on. No
  TLS, minimal auth, no rate limiting. Fine for a single trusted local
  client; the tool's own startup warning says as much.
- MLX (and therefore `mlx_lm.server`) **cannot run inside Docker** on this
  machine — Docker Desktop's Linux VM has no Metal GPU passthrough, so this
  has to run as a native macOS process regardless of how `riva-agent` itself
  is deployed.

## Current status

This is what's actually live in `config.yml` as of this writing:

```yaml
provider: openai
model: mlx-community/gemma-4-E4B-it-qat-4bit

openai:
  base_url: http://localhost:8081/v1
```

Verified end-to-end through the real gateway (not just direct calls to
`mlx_lm.server`): non-streaming, streaming, and `/v1/models` all confirmed
working, with no environment variable overrides needed — `config.yml`'s
`openai.base_url` is read directly (see `riva_agent/config.py`).
