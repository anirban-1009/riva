# Today's LLM Memory Investigation — Notes

A plain walkthrough of what we actually did today while chasing down why the
laptop was struggling to run the local model, in the order we did it. See
`docs/local-model-memory.md` for the formal write-up with full data; this is
the shorter "what happened and why" version.

## 1. Started because the laptop felt slow

Requests to the gateway were taking way longer than they should, and the
machine felt generally sluggish. First move was just to look at what the
system was actually doing while a request was in flight — CPU, memory, swap.

That's where it got interesting: the machine's swap was almost completely
full (13.3 out of 14.3 GB used). Something was eating memory hard.

## 2. First suspect: Docker

Docker Desktop was running, so it was the obvious first guess — quit the
Docker app to see if that freed anything up.

It barely made a difference. Swap usage stayed basically flat. So Docker
wasn't the real problem — just noise.

## 3. Actual suspect: Ollama itself

Sorted every process on the machine by memory usage, and one thing stood out
immediately: `ollama` running `gemma4:12b-mlx` was sitting at **10 GB**
resident — more than half the entire 18 GB machine, by itself, doing nothing
(no request was even in flight at the time — it was just the model sitting
loaded in memory).

That's the real answer: the model itself was just too big for this laptop
once anything else was running alongside it.

## 4. The instinct: just use a smaller model

The obvious fix is "use a smaller model." But that trades away quality —
fewer parameters, less capable answers. Before going down that path, the
better question was: **can we keep the same model, just make it smaller
without hurting quality?**

That's where quantization came in — instead of shrinking the model
(fewer parameters), shrink how precisely each parameter is stored (fewer
bits per weight). Same "brain," smaller footprint.

## 5. Why Unsloth specifically

Standard quantization (the generic Q4/Q3/etc. you'd get by default) loses
quality roughly proportional to how aggressively you compress. Unsloth
publishes "Dynamic" quants that are smarter about it — they keep more
precision on the layers that matter most and compress harder on the ones
that don't, so you lose a lot less quality per GB saved than a naive quant
would.

Checked Hugging Face directly (not guessing) and confirmed Unsloth has a
GGUF repo for the exact same model we were running (`gemma-4-12b-it`), with
several dynamic quant sizes available — from a mild trim (`UD-Q5_K_XL`,
8 GB) down to an aggressive one (`UD-Q2_K_XL`, 4.3 GB).

## 6. The ranking process — how we actually tested it

Rather than guess which quant level was "good enough," we ran a real
comparison:

1. Pulled two candidates that bracket the interesting range: `UD-Q4_K_XL`
   (same size as the original model, tests if the smarter quant alone helps)
   and `UD-Q3_K_XL` (meaningfully smaller, tests where quality starts to
   break).
2. For each one — including the original model as the baseline — unloaded
   everything, loaded that one model cold, sent it the exact same prompt,
   and measured: how much memory it actually used while running, how long
   it took, and whether the answer still made sense.
3. Hit a real bug partway through: the tool watching memory usage was
   looking for a process called `ollama runner`, which is right for the
   original MLX model — but the quantized GGUF models run under a
   completely different process (`llama-server`), so the first reading came
   back as a bogus zero. Caught it, fixed the tool, re-ran it properly.

That last part matters — the first version of the "ranking" would have been
wrong for two of the three models if that bug hadn't been caught.

## 7. What actually made a difference

| Model | Memory used | Speed | Answer quality |
|---|---|---|---|
| Original (`gemma4:12b-mlx`) | ~10 GB | slow | good |
| `UD-Q4_K_XL` (same size, smarter quant) | 7.55 GB | slow | good |
| **`UD-Q3_K_XL` (smaller, smarter quant)** | **6.45 GB** | **much faster** | **still good** |

The smaller Unsloth quant (`UD-Q3_K_XL`) won clearly: about a third less
memory than the model we started with, noticeably faster, and no visible
drop in answer quality on the prompt we tested. Going from 10 GB down to
6.45 GB resident is the difference between the model alone eating over half
the machine's memory versus leaving real room for everything else running
alongside it.

## Where this stands

`config.yml` now pins the platform to `UD-Q3_K_XL` — confirmed live against
the running gateway (a request asking for a different model still comes back
tagged `UD-Q3_K_XL`). This is still based on one test prompt, not a full
evaluation, so it's worth trying it on some actual day-to-day prompts to be
sure quality holds up outside the one thing we tested (see
`docs/local-model-memory.md` for the full caveats). The two models we no
longer need (`gemma3:4b`, `UD-Q4_K_XL`) can be removed from Ollama to free
up disk.
