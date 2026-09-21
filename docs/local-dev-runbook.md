# Local Dev Runbook: Starting, Checking, and Recovering the Stack

> Mirrors the [wiki](https://github.com/anirban-1009/riva/wiki/Local-Dev-Runbook) — the wiki is the canonical source; update it first.

Command reference for running `riva-agent` locally against the current
inference backend (`mlx_lm.server` + MLX, see `docs/local-model-memory.md`
and `docs/model-context-window.md` for how this setup was chosen). Kept
separate from the investigation docs since this one's meant to be looked up
quickly, not read start to end.

## Ports in play

| Port | What's on it | Managed by |
|---|---|---|
| `8085` | `riva-agent` gateway (`/v1/chat/completions`, etc.) | `uv run` — manual, not a service |
| `8081` | `mlx_lm.server` (current inference backend) | `nohup` — manual, not a service |
| `11434` | Ollama (only relevant if `config.yml`'s `provider` is switched back to `ollama`) | `Ollama.app` — auto-starts, a real macOS service |

`mlx_lm.server` doesn't survive a reboot or crash on its own — if the
machine restarts, it needs to be started manually again before the gateway
can serve requests. Ollama does survive reboots (`Ollama.app` relaunches
it), so no action needed there unless it's been quit manually.

## Bringing the stack up

Start in this order — the gateway doesn't hard-fail if the backend isn't up
yet, but requests will error until it is.

**1. Start `mlx_lm.server`** (skip if already running — check first with the
port-check command below):

```bash
mlx_lm.server --model mlx-community/gemma-4-E4B-it-qat-4bit --port 8081
```

To run it in the background instead of tying up a terminal:

```bash
nohup mlx_lm.server --model mlx-community/gemma-4-E4B-it-qat-4bit --port 8081 \
  > /tmp/mlx_server.log 2>&1 &
disown
```

**2. Start the `riva-agent` gateway**. `config.yml`'s `openai.base_url`
already points at it (see below), so no env var override is needed:

```bash
uv run --package riva-agent python -m riva_agent
```

Or backgrounded:

```bash
nohup uv run --package riva-agent python -m riva_agent \
  > /tmp/riva_dev.log 2>&1 &
disown
```

`config.yml`'s relevant section:

```yaml
provider: openai
model: mlx-community/gemma-4-E4B-it-qat-4bit

openai:
  base_url: http://localhost:8081/v1
```

(`OPENAI_BASE_URL` / `OPENAI_API_KEY` env vars still work as a fallback if
`openai.base_url` / `openai.api_key` aren't set in `config.yml` — see
`riva_agent/config.py`.)

## Health checks

```bash
# mlx_lm.server responding?
curl -s -o /dev/null -w "mlx_lm.server: %{http_code}\n" http://localhost:8081/v1/models

# gateway responding, and can it reach the backend?
curl -s -o /dev/null -w "gateway: %{http_code}\n" http://localhost:8085/v1/models

# end-to-end chat request
curl -s -X POST http://localhost:8085/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"whatever","messages":[{"role":"user","content":"reply with just the word OK"}]}'
```

A `200` from `/v1/models` on both ports means the chain is healthy. If the
gateway is up but the chat request errors, the backend (`mlx_lm.server`) is
the most likely place to look first — check its own health check above.

## Checking what's on a port

```bash
# see what's listening on (or connected to) a specific port
lsof -nP -iTCP:8085 -sTCP:LISTEN
lsof -nP -iTCP:8081 -sTCP:LISTEN
lsof -nP -iTCP:11434 -sTCP:LISTEN

# see ALL connections (not just listeners) to a port — useful for spotting
# a client mid-request, or confirming nothing unexpected is connected
lsof -nP -iTCP:8085
```

No output from the `-sTCP:LISTEN` form means nothing is bound to that port.

## Killing a stuck process on a port

```bash
# find the PID, then kill it directly
lsof -nP -iTCP:8085 -sTCP:LISTEN
kill <PID>

# one-liner: find and kill in one shot
lsof -nP -iTCP:8085 -sTCP:LISTEN | awk 'NR==2{print $2}' | xargs kill

# confirm the port is actually free afterward
lsof -nP -iTCP:8085 -sTCP:LISTEN || echo "port free"
```

If `kill` doesn't work (rare — usually only if the process is wedged),
escalate to `kill -9 <PID>`, but try a plain `kill` first so the process can
shut down cleanly (release the port, flush logs, etc.) rather than being cut
off mid-operation.

## Common recovery scenarios

**"Address already in use" when starting the gateway or `mlx_lm.server`:**
something's already bound to that port — almost always a previous instance
still running. Find and kill it (see above), confirm the port is free, then
retry the start command.

**Gateway requests hang or time out:** check whether `mlx_lm.server` is
still alive (`ps aux | grep mlx_lm.server`) — if the process died silently,
restart it (step 1 above), no need to restart the gateway.

**Switching back to Ollama** (e.g. to compare against `gemma4-q3-16k` or the
original `gemma4:12b-mlx` again): edit `config.yml` — the `openai:` section
is simply ignored when `provider` isn't `openai`, no need to remove it:

```yaml
provider: ollama
model: gemma4-q3-16k   # or gemma4:12b-mlx, or any other pulled Ollama tag
```

Then restart the gateway (Ollama's own default `http://localhost:11434`
applies automatically):

```bash
uv run --package riva-agent python -m riva_agent
```
