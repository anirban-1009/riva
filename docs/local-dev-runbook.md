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

### Automated startup (Recommended)

Use the dev stack orchestration script, which starts `mlx_lm.server` (reading the model from `config.yml`), launches the Riva AI Gateway, verifies health on both ports, and checks OpenClaw:

```bash
# Start the full stack (background)
./scripts/start_stack.sh start

# Start in Dev mode (foreground gateway with auto-reload on src/ & common/)
./scripts/start_stack.sh dev

# Other commands available
./scripts/start_stack.sh status   # Check ports 8081, 8085 and service health
./scripts/start_stack.sh logs     # Follow combined logs (~/.riva/logs/)
./scripts/start_stack.sh chat     # Start stack and launch OpenClaw TUI
./scripts/start_stack.sh stop     # Stop MLX and Gateway background processes
./scripts/start_stack.sh restart  # Restart the full stack
```

### Manual startup (Step-by-Step)

If you prefer starting services manually or need to isolate an issue, start in this order — the gateway doesn't hard-fail if the backend isn't up yet, but requests will error until it is.

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
uv run --package riva-agent uvicorn riva_agent.api.gateway:app --host 0.0.0.0 --port 8085
```

Or backgrounded:

```bash
nohup uv run --package riva-agent uvicorn riva_agent.api.gateway:app \
  --host 0.0.0.0 --port 8085 > /tmp/riva_dev.log 2>&1 &
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

## Riva CLI: Trust Surface & Storage Operations

The `riva` CLI (`riva_agent/cli.py`) serves as the core user trust surface and local hygiene tool. It allows direct inspection, correction, compaction, and disaster recovery of all local stores without writing custom scripts or raw SQL.

Commands default to operating on databases and logs located in `~/.riva/` (or the directory specified by `RIVA_DATA_DIR`).

### 1. Direct Assistant Querying (`riva ask`)

Stream an end-to-end conversation turn through the assistant pipeline with profile context injection and episodic turn persistence:

```bash
uv run riva ask "What are my main goals for this quarter?"
```

### 2. User Profile Management (`riva profile`)

Inspect, update, or prune persistent profile entries stored in `profile.db`:

```bash
# List all profile entries
uv run riva profile list

# Filter entries by category (e.g., facts, constraints, goals, preferences)
uv run riva profile list --category facts
uv run riva profile list --category constraints

# Retrieve a single key
uv run riva profile get location

# Set or update a key
uv run riva profile set location "Munich" --category facts
uv run riva profile set diet "No peanuts" --category constraints

# Delete a key
uv run riva profile delete location
```

### 3. Episodic Memory & Human-in-the-Loop Review (`riva memory`)

Inspect recorded conversation history, review staged candidate facts extracted from past conversations, and permanently purge turns:

```bash
# List recent conversation turns across sessions
uv run riva memory list
uv run riva memory list --limit 20

# View staged candidate memories awaiting human review
uv run riva memory list --pending

# Accept a staged candidate memory into the durable user profile
uv run riva memory accept <id>

# Reject an unwanted candidate memory
uv run riva memory reject <id>

# Permanently delete a sensitive or erroneous conversation turn
uv run riva memory forget <id>
```

### 4. Storage Telemetry, Compaction & Hygiene (`riva storage`)

Keep database files compact, reclaim deleted SQLite pages, enforce log bounds, and snapshot databases.

#### Check Storage Telemetry (`status`)
Aggregates file size on disk, active WAL/SHM file overhead, table row counts, and total log footprint in `~/.riva/logs/`:

```bash
uv run riva storage status
```

#### Reclaim Disk Space (`vacuum`)
Executes `VACUUM` and `PRAGMA wal_checkpoint(TRUNCATE)` on both `memory.db` and `profile.db` to release free pages to the filesystem and truncate WAL logs to zero bytes:

```bash
uv run riva storage vacuum
```

#### Retention Pruning & Log Rotation (`prune`)
Prunes raw conversation turns older than the retention threshold (default: 30 days) and unreviewed candidate memories older than the review threshold (default: 7 days). It also checks `~/.riva/logs/` (`gateway.log`, `mlx_server.log`, `riva_gateway.log`), rotating any log over 50MB using a copytruncate strategy (retaining up to 3 rotations):

```bash
# Preview deleted rows and log rotation candidates without altering files (dry run)
uv run riva storage prune --dry-run

# Execute pruning with default thresholds (30 days turns, 7 days pending)
uv run riva storage prune

# Customize retention windows
uv run riva storage prune --turns-days 60 --pending-days 14
# or using the --turns-older-than alias:
uv run riva storage prune --turns-older-than 45
```

#### Online Point-in-Time Snapshots (`backup`)
Uses SQLite `VACUUM INTO` to create non-blocking, consistent point-in-time database snapshots in `~/.riva/backups/`:

```bash
uv run riva storage backup
# Outputs created backup paths:
#   ~/.riva/backups/memory_YYYYMMDD_HHMMSS.db
#   ~/.riva/backups/profile_YYYYMMDD_HHMMSS.db
```

#### Disaster Recovery / Restore Procedure
To restore state from a backup:
1. Stop running stack services (`./scripts/start_stack.sh stop`).
2. Copy the backup file over the active store:
   ```bash
   cp ~/.riva/backups/memory_20260927_204127.db ~/.riva/memory.db
   cp ~/.riva/backups/profile_20260927_204127.db ~/.riva/profile.db
   ```
3. Remove stale WAL/SHM files:
   ```bash
   rm -f ~/.riva/*.db-wal ~/.riva/*.db-shm
   ```
4. Restart the stack (`./scripts/start_stack.sh start`).
