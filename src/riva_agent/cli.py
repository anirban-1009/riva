import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime

import httpx
import yaml

from common import get_episodic_store, get_profile_store
from common.llm.embeddings import create_embedding_provider
from riva_agent import config


def _get_gateway_url() -> str:
    return os.environ.get("RIVA_GATEWAY_URL", "http://localhost:8085").rstrip("/")


def cmd_ask(args: argparse.Namespace) -> int:
    """Send a prompt to Riva gateway in assistant mode with streaming response."""
    gateway_url = _get_gateway_url()
    endpoint = f"{gateway_url}/v1/chat/completions"
    payload = {
        "model": "riva",
        "messages": [{"role": "user", "content": args.prompt}],
        "stream": True,
    }

    try:
        with httpx.stream("POST", endpoint, json=payload, timeout=60.0) as response:
            if response.status_code != 200:
                print(
                    f"Error from Riva Gateway ({response.status_code}): {response.read().decode('utf-8')}",
                    file=sys.stderr,
                )
                return 1

            for line in response.iter_lines():
                if not line or line.startswith(":"):
                    continue
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                sys.stdout.write(content)
                                sys.stdout.flush()
                    except json.JSONDecodeError:
                        continue

            sys.stdout.write("\n")
            sys.stdout.flush()
            return 0
    except httpx.ConnectError:
        print(
            f"Failed to connect to Riva Gateway at {endpoint}. Is the server running? "
            f"(Try: uv run python -m riva_agent)",
            file=sys.stderr,
        )
        return 1
    except Exception as e:
        print(f"Error querying Riva: {e}", file=sys.stderr)
        return 1


def cmd_profile_list(args: argparse.Namespace) -> int:
    """List all profile entries."""
    store = get_profile_store(config.DATA_DIR / "profile.db")
    entries = store.list_all(category=args.category)
    if not entries:
        print("No profile entries found.")
        return 0

    print(f"{'Category':<15} {'Key':<30} {'Value'}")
    print(f"{'-' * 14:<15} {'-' * 29:<30} {'-' * 30}")
    for e in entries:
        print(f"{e.category:<15} {e.key:<30} {e.value}")
    return 0


def cmd_profile_set(args: argparse.Namespace) -> int:
    """Set or update a profile entry."""
    store = get_profile_store(config.DATA_DIR / "profile.db")
    store.set(key=args.key, value=args.value, category=args.category)
    print(f"✔ Set profile [{args.category}] '{args.key}' = '{args.value}'")
    return 0


def cmd_profile_get(args: argparse.Namespace) -> int:
    """Get the value of a profile entry."""
    store = get_profile_store(config.DATA_DIR / "profile.db")
    val = store.get(args.key)
    if val is None:
        print(f"Key '{args.key}' not found in profile.", file=sys.stderr)
        return 1
    print(val)
    return 0


def cmd_profile_delete(args: argparse.Namespace) -> int:
    """Delete a profile entry."""
    store = get_profile_store(config.DATA_DIR / "profile.db")
    deleted = store.delete(args.key)
    if deleted:
        print(f"✔ Deleted profile entry '{args.key}'")
        return 0
    print(f"Key '{args.key}' not found.", file=sys.stderr)
    return 1


def cmd_profile_show(args: argparse.Namespace) -> int:
    """Show formatted user profile context."""
    store = get_profile_store(config.DATA_DIR / "profile.db")
    ctx = store.format_context(max_entries=100)
    if not ctx:
        print("No profile entries found.")
        return 0
    print(ctx)
    return 0


def cmd_profile_edit(args: argparse.Namespace) -> int:
    """Edit user profile in $EDITOR as YAML."""
    store = get_profile_store(config.DATA_DIR / "profile.db")
    entries = store.list_all()

    data = [{"category": e.category, "key": e.key, "value": e.value} for e in entries]

    with tempfile.NamedTemporaryFile("w+", suffix=".yaml", delete=False) as tf:
        yaml.safe_dump(data, tf, sort_keys=False, allow_unicode=True)
        temp_path = tf.name

    editor = os.environ.get("EDITOR") or ("nano" if shutil.which("nano") else "vi")
    try:
        ret = subprocess.call([editor, temp_path])
        if ret != 0:
            print("Editor exited with non-zero status. Profile edit aborted.", file=sys.stderr)
            return 1

        with open(temp_path, "r", encoding="utf-8") as tf:
            content = tf.read().strip()
            new_data = yaml.safe_load(content) if content else []

        if new_data is None:
            new_data = []

        if not isinstance(new_data, list):
            print("Invalid profile format. Expected a YAML list of entries.", file=sys.stderr)
            return 1

        existing_keys = {e.key for e in entries}
        new_keys = set()
        for item in new_data:
            if not isinstance(item, dict) or "key" not in item or "value" not in item:
                continue
            k = str(item["key"]).strip()
            v = str(item["value"]).strip()
            cat = str(item.get("category", "general")).strip()
            if k:
                store.set(key=k, value=v, category=cat)
                new_keys.add(k)

        for removed_key in existing_keys - new_keys:
            store.delete(removed_key)

        print(f"✔ Profile synchronized ({len(new_keys)} entries active).")
        return 0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def cmd_memory_list(args: argparse.Namespace) -> int:
    """List recent conversation turns or pending candidate memories."""
    store = get_episodic_store(config.DATA_DIR / "memory.db")
    if args.pending:
        pending = store.list_pending()
        if not pending:
            print("No pending memory candidates.")
            return 0
        print(f"{'ID':<6} {'Fact':<40} {'Source'}")
        print(f"{'-' * 5:<6} {'-' * 39:<40} {'-' * 30}")
        for p in pending:
            print(f"{p.id:<6} {p.fact:<40} {p.source_snippet}")
        return 0

    # Fetch recent turns across sessions
    turns = store.list_turns(limit=args.limit)

    if not turns:
        print("No conversation history recorded.")
        return 0

    print(f"{'ID':<6} {'Role':<10} {'Turn Snippet':<50} {'Created'}")
    print(f"{'-' * 5:<6} {'-' * 9:<10} {'-' * 49:<50} {'-' * 20}")
    for t in reversed(turns):
        snippet = t.content[:48].replace("\n", " ") + ("..." if len(t.content) > 48 else "")
        print(f"{t.id:<6} {t.role:<10} {snippet:<50} {t.created_at}")
    return 0


def cmd_memory_forget(args: argparse.Namespace) -> int:
    """Delete an episodic turn record and cascaded vector embedding by ID."""
    store = get_episodic_store(config.DATA_DIR / "memory.db", embedding_dim=config.EMBEDDING_DIMENSION)
    deleted = store.delete_turn(args.id)
    if deleted:
        print(f"✔ Removed turn ID {args.id} and associated vector embeddings from episodic memory.")
        return 0
    print(f"Turn ID {args.id} not found.", file=sys.stderr)
    return 1


def cmd_memory_search(args: argparse.Namespace) -> int:
    """Semantically search conversation turns using vector embeddings."""
    import asyncio

    store = get_episodic_store(config.DATA_DIR / "memory.db", embedding_dim=config.EMBEDDING_DIMENSION)
    if not store._vec_enabled:
        print("Error: sqlite-vec is not enabled or available in SQLite.", file=sys.stderr)
        return 1

    query = args.query.strip()
    if not query:
        print("Error: Search query cannot be empty.", file=sys.stderr)
        return 1

    async def _search_async() -> list:
        provider = create_embedding_provider(
            config.EMBEDDING_PROVIDER,
            model=config.EMBEDDING_MODEL,
            base_url=config.EMBEDDING_BASE_URL,
            dimension=config.EMBEDDING_DIMENSION,
        )
        try:
            vec = await provider.embed_query(query)
            if not vec:
                return []
            return store.search_similar(
                vec,
                top_k=args.limit,
                distance_threshold=args.threshold,
                session_id=getattr(args, "session", None),
            )
        finally:
            await provider.close()

    try:
        matches = asyncio.run(_search_async())
    except Exception as e:
        print(f"Error during semantic search: {e}", file=sys.stderr)
        return 1

    if not matches:
        print(f"No semantic matches found for '{query}' (threshold: {args.threshold}).")
        return 0

    print(f"{'ID':<6} {'Score':<8} {'Role':<10} {'Created':<20} {'Matched Text'}")
    print(f"{'-' * 5:<6} {'-' * 7:<8} {'-' * 9:<10} {'-' * 19:<20} {'-' * 35}")
    for m in matches:
        score = max(0.0, 1.0 - m.distance)
        snippet = m.content[:60].replace("\n", " ") + ("..." if len(m.content) > 60 else "")
        print(f"{m.turn_id:<6} {score:<8.3f} {m.role:<10} {m.created_at[:19]:<20} {snippet}")

    return 0


def cmd_memory_accept(args: argparse.Namespace) -> int:
    """Accept a pending candidate memory and save to profile."""
    mem_store = get_episodic_store(config.DATA_DIR / "memory.db")
    profile_store = get_profile_store(config.DATA_DIR / "profile.db")

    pending_list = mem_store.list_pending()
    target = next((p for p in pending_list if p.id == args.id), None)
    if not target:
        print(f"Pending memory ID {args.id} not found.", file=sys.stderr)
        return 1

    profile_store.set(key=target.fact[:50], value=target.fact, category="facts")
    mem_store.resolve_pending(args.id, "accepted")
    print(f"✔ Accepted memory ID {args.id} into profile: '{target.fact}'")
    return 0


def cmd_memory_reject(args: argparse.Namespace) -> int:
    """Reject a pending candidate memory."""
    mem_store = get_episodic_store(config.DATA_DIR / "memory.db")
    success = mem_store.resolve_pending(args.id, "rejected")
    if success:
        print(f"✔ Rejected pending memory ID {args.id}.")
        return 0
    print(f"Pending memory ID {args.id} not found.", file=sys.stderr)
    return 1


def cmd_memory_reindex(args: argparse.Namespace) -> int:
    """Backfill or recompute vector embeddings for conversation turns."""
    import asyncio

    store = get_episodic_store(config.DATA_DIR / "memory.db", embedding_dim=config.EMBEDDING_DIMENSION)
    if not store._vec_enabled:
        print("Error: sqlite-vec is not enabled or available in SQLite.", file=sys.stderr)
        return 1

    if getattr(args, "force", False):
        cleared = store.clear_embeddings()
        print(f"Purged {cleared} existing vector embeddings for full reindex.")

    unindexed = store.get_unindexed_turns(limit=args.limit)
    if not unindexed:
        print("All conversation turns are already indexed.")
        return 0

    print(f"Found {len(unindexed)} unindexed turns. Connecting to embedding provider '{config.EMBEDDING_PROVIDER}'...")

    async def _reindex_async() -> int:
        provider = create_embedding_provider(
            config.EMBEDDING_PROVIDER,
            model=config.EMBEDDING_MODEL,
            base_url=config.EMBEDDING_BASE_URL,
            dimension=config.EMBEDDING_DIMENSION,
        )
        indexed_count = 0

        batch_size = max(1, args.batch_size)
        try:
            for i in range(0, len(unindexed), batch_size):
                batch = unindexed[i : i + batch_size]
                texts = [t.content for t in batch]
                vectors = await provider.embed_documents(texts)
                for t, vec in zip(batch, vectors):
                    store.add_embedding(t.id, vec, session_id=t.session_id, content=t.content)
                    indexed_count += 1
        finally:
            await provider.close()

        return indexed_count

    try:
        indexed = asyncio.run(_reindex_async())
        print(f"✔ Successfully indexed {indexed} turns into vector store.")
        return 0
    except Exception as e:
        print(f"Error during vector reindexing: {e}", file=sys.stderr)
        return 1


def cmd_storage_status(args: argparse.Namespace) -> int:
    """Show storage telemetry for Riva databases and logs."""
    mem_store = get_episodic_store(config.DATA_DIR / "memory.db", embedding_dim=config.EMBEDDING_DIMENSION)
    prof_store = get_profile_store(config.DATA_DIR / "profile.db")

    m_stats = mem_store.get_stats()
    p_stats = prof_store.get_stats()

    # Log footprint
    log_dir = config.DATA_DIR / "logs"
    log_size = 0
    if log_dir.exists():
        for f in log_dir.rglob("*"):
            if f.is_file():
                log_size += f.stat().st_size

    print(f"{'Component':<20} {'Size':<14} {'Details'}")
    print(f"{'-' * 20:<20} {'-' * 14:<14} {'-' * 30}")

    mem_details = (
        f"(Turns: {m_stats['turns']}, Embeddings: {m_stats.get('embeddings', 0)}, Pending: {m_stats['pending']})"
    )
    mem_size_str = f"{m_stats['file_size'] / 1024:.2f} KB"
    print(f"{'Memory DB':<20} {mem_size_str:<14} {mem_details}")
    if m_stats["wal_size"] > 0:
        wal_size_str = f"{m_stats['wal_size'] / 1024:.2f} KB"
        print(f"{'  WAL':<20} {wal_size_str:<14}")

    vec_count = m_stats.get("vector_count", m_stats.get("embeddings", 0))
    emb_dim = m_stats.get("embedding_dim", config.EMBEDDING_DIMENSION)
    vec_bytes = m_stats.get("vector_bytes", vec_count * emb_dim * 4)
    backend_status = "sqlite-vec" if m_stats.get("vec_enabled") else "disabled"
    vec_details = f"(Vectors: {vec_count}, Dim: {emb_dim}, Backend: {backend_status})"
    vec_size_str = f"{vec_bytes / 1024:.2f} KB"
    print(f"{'  Vector Index':<20} {vec_size_str:<14} {vec_details}")

    prof_size_str = f"{p_stats['file_size'] / 1024:.2f} KB"
    print(f"{'Profile DB':<20} {prof_size_str:<14} (Rows: {p_stats['rows']})")
    if p_stats["wal_size"] > 0:
        prof_wal_str = f"{p_stats['wal_size'] / 1024:.2f} KB"
        print(f"{'  WAL':<20} {prof_wal_str:<14}")

    log_size_str = f"{log_size / 1024:.2f} KB"
    print(f"{'Logs':<20} {log_size_str:<14}")

    return 0


def cmd_storage_vacuum(args: argparse.Namespace) -> int:
    """Compact databases and reclaim space."""
    mem_store = get_episodic_store(config.DATA_DIR / "memory.db")
    prof_store = get_profile_store(config.DATA_DIR / "profile.db")

    mem_store.vacuum()
    prof_store.vacuum()

    print("✔ Databases vacuumed and WAL checkpoints truncated.")
    return 0


def cmd_storage_prune(args: argparse.Namespace) -> int:
    """Prune old conversation turns and pending memories, and rotate logs."""
    mem_store = get_episodic_store(config.DATA_DIR / "memory.db")

    # 1. DB Pruning
    results = mem_store.prune(
        turns_days=args.turns_days,
        pending_days=args.pending_days,
        dry_run=args.dry_run,
    )

    action = "Would delete" if args.dry_run else "Deleted"
    print(f"✔ {action} {results['turns_deleted']} old turns and {results['pending_deleted']} expired pending memories.")

    # 2. Log Rotation (copytruncate)
    log_dir = config.DATA_DIR / "logs"
    if log_dir.exists():
        log_names = ["gateway.log", "mlx_server.log", "riva_gateway.log"]
        for p in log_dir.glob("*.log"):
            if p.name not in log_names:
                log_names.append(p.name)
        if (log_dir / "log").exists() and "log" not in log_names:
            log_names.append("log")

        for log_name in log_names:
            log_path = log_dir / log_name
            if not log_path.is_file():
                continue
            try:
                size = log_path.stat().st_size
            except OSError:
                continue

            if size > 50 * 1024 * 1024:
                if args.dry_run:
                    print(f"ℹ {log_name} would be rotated (size: {size / 1024 / 1024:.2f} MB).")
                else:
                    # Rotate: .2 -> .3, .1 -> .2, current -> .1
                    for i in range(2, 0, -1):
                        for old, new in [
                            (log_path.parent / f"{log_path.name}.{i}", log_path.parent / f"{log_path.name}.{i + 1}"),
                            (log_path.with_suffix(f".{i}"), log_path.with_suffix(f".{i + 1}")),
                        ]:
                            if old.exists() and old != new:
                                try:
                                    old.rename(new)
                                except OSError:
                                    pass

                    # Copy current to .1
                    target_rotated = log_path.parent / f"{log_path.name}.1"
                    shutil.copyfile(log_path, target_rotated)
                    suffix_rotated = log_path.with_suffix(".1")
                    if suffix_rotated != target_rotated and not suffix_rotated.exists():
                        try:
                            shutil.copyfile(target_rotated, suffix_rotated)
                        except OSError:
                            pass

                    # Truncate original to 0 bytes
                    with open(log_path, "w") as f:
                        f.truncate(0)

                    print(f"✔ Rotated {log_name} (exceeded 50MB).")

    return 0


def cmd_storage_backup(args: argparse.Namespace) -> int:
    """Create an online snapshot of databases."""
    backup_dir = config.DATA_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    mem_store = get_episodic_store(config.DATA_DIR / "memory.db")
    prof_store = get_profile_store(config.DATA_DIR / "profile.db")

    mem_backup_path = backup_dir / f"memory_{timestamp}.db"
    prof_backup_path = backup_dir / f"profile_{timestamp}.db"

    mem_store.backup(mem_backup_path)
    prof_store.backup(prof_backup_path)

    print(f"✔ Backups created in {backup_dir}:")
    print(f"  - {mem_backup_path.name}")
    print(f"  - {prof_backup_path.name}")
    return 0


def cmd_session_new(args: argparse.Namespace) -> int:
    """Start a new chat session."""
    sid = str(uuid.uuid4())
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    session_file = config.DATA_DIR / "session.id"
    session_file.write_text(sid)
    print(f"✔ Started new chat session: {sid}")
    return 0


def cmd_session_id(args: argparse.Namespace) -> int:
    """Print the active chat session ID."""
    session_file = config.DATA_DIR / "session.id"
    if session_file.exists():
        sid = session_file.read_text().strip()
        if sid:
            print(sid)
            return 0
    print("No active session ID found.", file=sys.stderr)
    return 1


def cmd_session_list(args: argparse.Namespace) -> int:
    """List recent conversation sessions from episodic memory."""
    mem_store = get_episodic_store(config.DATA_DIR / "memory.db")
    sessions = mem_store.list_sessions(limit=args.limit)

    if not sessions:
        print("No recorded chat sessions found.")
        return 0

    print(f"{'Session ID':<38} {'Turns':<8} {'Last Turn'}")
    print(f"{'-' * 38:<38} {'-' * 7:<8} {'-' * 20}")
    for s in sessions:
        print(f"{s.session_id:<38} {s.turn_count:<8} {s.last_turn}")
    return 0


def cmd_digest_generate(args: argparse.Namespace) -> int:
    """Generate a personal daily digest and optionally dispatch notifications."""
    from riva_agent.digest.dispatcher import dispatch_digest_notifications
    from riva_agent.digest.generator import collect_digest_context, generate_digest
    from riva_agent.digest.models import DigestConfig

    cfg = DigestConfig.from_env_or_config()
    target_date = args.date or datetime.now().strftime("%Y-%m-%d")

    print(f"Generating Riva digest for {target_date}...")
    try:
        ctx = collect_digest_context(date_str=target_date)
        record = generate_digest(
            context=ctx,
            config_obj=cfg,
            dry_run=args.dry_run,
        )
        print(f"✔ Digest created: {record.title}")
        if record.filepath:
            print(f"  Archive: {record.filepath}")

        if args.dry_run:
            print("\n--- Preview ---\n")
            print(record.content_markdown)
            print("\n---------------\n")

        if not args.no_notify:
            results = dispatch_digest_notifications(
                record,
                config_obj=cfg,
                dry_run=args.dry_run,
                force_channel=args.channel,
            )
            for res in results:
                status_icon = "✔" if res.success else "✖"
                print(f"  {status_icon} [{res.channel.upper()}] {res.message}")

        return 0
    except Exception as e:
        print(f"Failed to generate digest: {e}", file=sys.stderr)
        return 1


def cmd_digest_list(args: argparse.Namespace) -> int:
    """List archived markdown digests."""
    from riva_agent.digest.generator import list_digests

    digests = list_digests(limit=args.limit)
    if not digests:
        print(f"No archived digests found in {config.DIGEST_OUTPUT_DIR}.")
        return 0

    print(f"{'Date':<12} {'ID':<25} {'Title':<30} {'Filepath'}")
    print(f"{'-' * 11:<12} {'-' * 24:<25} {'-' * 29:<30} {'-' * 35}")
    for d in digests:
        path_str = str(d.filepath) if d.filepath else "-"
        print(f"{d.date:<12} {d.id:<25} {d.title[:28]:<30} {path_str}")
    return 0


def cmd_digest_show(args: argparse.Namespace) -> int:
    """Show content of an archived digest."""
    from riva_agent.digest.generator import read_digest

    record = read_digest(args.identifier)
    if not record:
        print(f"Digest '{args.identifier}' not found in {config.DIGEST_OUTPUT_DIR}.", file=sys.stderr)
        return 1

    print(f"# {record.title} (ID: {record.id}, Date: {record.date})")
    if record.filepath:
        print(f"Source: {record.filepath}\n")
    print(record.content_markdown)
    return 0


def cmd_digest_test_notify(args: argparse.Namespace) -> int:
    """Test notification dispatch to Signal or native macOS banner."""
    from riva_agent.digest.dispatcher import send_macos_notification, send_signal_message

    channel = args.channel or ("signal" if config.DIGEST_SIGNAL_ENABLED and config.DIGEST_SIGNAL_RECIPIENT else "macos")
    recipient = args.recipient or config.DIGEST_SIGNAL_RECIPIENT

    test_msg = (
        f"🌅 Riva test notification ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}): "
        f"Proactive dispatch bridge is operational."
    )

    if channel == "signal":
        if not recipient:
            print(
                "Error: No recipient specified. Use --recipient or configure digest.signal.recipient.",
                file=sys.stderr,
            )
            return 1
        print(f"Testing Signal dispatch to {recipient}...")
        res = send_signal_message(recipient, test_msg, dry_run=args.dry_run)
        icon = "✔" if res.success else "✖"
        print(f"{icon} [SIGNAL] {res.message}")
        return 0 if res.success else 1
    elif channel == "macos":
        print("Testing native macOS banner notification...")
        res = send_macos_notification("Riva Test Notification", test_msg, dry_run=args.dry_run)
        icon = "✔" if res.success else "✖"
        print(f"{icon} [MACOS] {res.message}")
        return 0 if res.success else 1
    else:
        print(f"Unknown channel '{channel}'. Supported: 'signal', 'macos'.", file=sys.stderr)
        return 1


def cmd_digest_schedule_install(args: argparse.Namespace) -> int:
    """Install macOS launchd agent for scheduled daily digest execution."""
    from riva_agent.digest.scheduler import install_launchd_schedule

    time_val = args.time or config.DIGEST_SCHEDULE_TIME
    success, msg = install_launchd_schedule(schedule_time=time_val, dry_run=args.dry_run)
    icon = "✔" if success else "✖"
    print(f"{icon} {msg}")
    return 0 if success else 1


def cmd_digest_schedule_status(args: argparse.Namespace) -> int:
    """Show status of macOS launchd digest agent."""
    from riva_agent.digest.scheduler import get_launchd_schedule_status

    status = get_launchd_schedule_status()
    print("Riva Proactive Digest Schedule Status:")
    print(f"  Installed:       {'Yes' if status['installed'] else 'No'}")
    print(f"  Loaded:          {'Yes' if status['loaded'] else 'No'}")
    print(f"  Scheduled Time:  {status.get('schedule_time') or 'Not configured'}")
    print(f"  Plist Path:      {status.get('plist_path')}")
    print(f"  Details:         {status.get('detail')}")
    return 0


def cmd_digest_schedule_uninstall(args: argparse.Namespace) -> int:
    """Uninstall macOS launchd agent for daily digest."""
    from riva_agent.digest.scheduler import uninstall_launchd_schedule

    success, msg = uninstall_launchd_schedule(dry_run=args.dry_run)
    icon = "✔" if success else "✖"
    print(f"{icon} {msg}")
    return 0 if success else 1


def cmd_mcp_add(args: argparse.Namespace) -> int:
    """Add a new MCP server to config.yml."""
    from riva_agent.mcp.config import add_mcp_server

    env_dict = {}
    if args.env:
        for item in args.env:
            if "=" in item:
                k, v = item.split("=", 1)
                env_dict[k.strip()] = v.strip()
            else:
                env_dict[item.strip()] = os.environ.get(item.strip(), "")

    cmd = args.command
    cmd_args = list(args.server_args or [])

    if getattr(args, "cmd_and_args", None):
        if not cmd:
            cmd = args.cmd_and_args[0]
            if len(args.cmd_and_args) > 1 and not cmd_args:
                cmd_args = list(args.cmd_and_args[1:])
        elif not cmd_args:
            cmd_args = list(args.cmd_and_args)

    try:
        server = add_mcp_server(
            name=args.name,
            transport=args.transport,
            command=cmd,
            args=cmd_args,
            env=env_dict,
            url=args.url,
            readonly=args.readonly,
            enabled=not args.disabled,
            timeout=args.timeout,
        )
        print(f"✔ Added MCP server '{server.name}' to configuration.")
        print(f"  Transport: {server.transport}")
        target = server.command if server.transport == "stdio" else server.url
        print(f"  Target:    {target}")
        if server.args:
            print(f"  Args:      {' '.join(server.args)}")
        print(f"  Read-Only: {server.readonly}")
        print(f"  Enabled:   {server.enabled}")
        return 0
    except Exception as e:
        print(f"Error adding MCP server: {e}", file=sys.stderr)
        return 1


def cmd_mcp_remove(args: argparse.Namespace) -> int:
    """Remove an MCP server from config.yml."""
    from riva_agent.mcp.config import remove_mcp_server

    removed = remove_mcp_server(args.name)
    if removed:
        print(f"✔ Removed MCP server '{args.name}' from configuration.")
        return 0
    print(f"MCP server '{args.name}' not found in configuration.", file=sys.stderr)
    return 1


def cmd_mcp_list(args: argparse.Namespace) -> int:
    """List configured MCP servers."""
    from riva_agent.mcp.config import get_mcp_servers

    servers = get_mcp_servers()
    if not servers:
        print("No MCP servers configured.")
        print("Add one with: riva mcp add <name> --transport <stdio|sse> ...")
        return 0

    print(f"{'Server':<20} {'Transport':<12} {'Target':<32} {'Read-Only':<10} {'Enabled'}")
    print(f"{'-' * 19:<20} {'-' * 11:<12} {'-' * 31:<32} {'-' * 9:<10} {'-' * 7}")
    for s in servers:
        target = s.command if s.transport == "stdio" else (s.url or "")
        ro_str = "Yes" if s.readonly else "No"
        en_str = "Yes" if s.enabled else "No"
        print(f"{s.name:<20} {s.transport:<12} {target:<32} {ro_str:<10} {en_str}")
    return 0


def cmd_mcp_test(args: argparse.Namespace) -> int:
    """Test connectivity to configured MCP servers."""
    from common.mcp.client import MCPClient
    from riva_agent.mcp.config import get_mcp_servers

    servers = get_mcp_servers()
    if args.server:
        servers = [s for s in servers if s.name == args.server]
        if not servers:
            print(f"Server '{args.server}' not found in configuration.", file=sys.stderr)
            return 1

    if not servers:
        print("No MCP servers configured.")
        return 0

    async def _test_all():
        has_failure = False
        print("Testing MCP server connectivity...")
        for s in servers:
            if not s.enabled:
                print(f"○ {s.name} ({s.transport}): Disabled")
                continue
            client = MCPClient(s)
            try:
                connected = await client.connect()
                if connected:
                    tool_count = len(client.tools)
                    sfx = "s" if tool_count != 1 else ""
                    print(f"✔ {s.name} ({s.transport}): Connected ({tool_count} tool{sfx} available)")
                else:
                    has_failure = True
                    print(f"✖ {s.name} ({s.transport}): Connection failed ({client.status.error or 'unknown error'})")
            finally:
                await client.close()
        return 1 if has_failure else 0

    return asyncio.run(_test_all())


def cmd_mcp_tools(args: argparse.Namespace) -> int:
    """List tools exposed by configured MCP servers."""
    from common.mcp.client import MCPClient
    from riva_agent.mcp.config import get_mcp_servers

    servers = get_mcp_servers()
    if args.server:
        servers = [s for s in servers if s.name == args.server]
        if not servers:
            print(f"Server '{args.server}' not found in configuration.", file=sys.stderr)
            return 1

    if not servers:
        print("No MCP servers configured.")
        return 0

    async def _list_tools():
        total_tools = 0
        for s in servers:
            if not s.enabled:
                continue
            client = MCPClient(s)
            try:
                connected = await client.connect()
                if not connected:
                    print(f"Server '{s.name}': Unable to connect ({client.status.error or 'error'}).")
                    continue
                tools = list(client.tools.values())
                total_tools += len(tools)
                print(f"\n📦 Server: {s.name} ({s.transport}, {len(tools)} tools)")
                if not tools:
                    print("  (No tools exposed)")
                    continue
                for t in tools:
                    print(f"  • Tool:        {t.namespaced_name} (original: {t.name})")
                    if t.description:
                        print(f"    Description: {t.description}")
                    if t.parameters and t.parameters.get("properties"):
                        prop_keys = list(t.parameters["properties"].keys())
                        print(f"    Parameters:  {', '.join(prop_keys)}")
            finally:
                await client.close()

        if total_tools == 0:
            print("No tools found on configured servers.")
        return 0

    return asyncio.run(_list_tools())


def cmd_mcp_call(args: argparse.Namespace) -> int:
    """Execute an MCP tool directly for debugging and inspection."""
    from common.mcp.client import MCPClient
    from riva_agent.mcp.config import get_mcp_servers

    servers = [s for s in get_mcp_servers() if s.name == args.server]
    if not servers:
        print(f"MCP server '{args.server}' not found in configuration.", file=sys.stderr)
        return 1

    server_cfg = servers[0]
    raw_args = {}
    args_json_str = args.args if args.args is not None else getattr(args, "raw_args", "{}")
    if args_json_str and args_json_str != "{}":
        try:
            raw_args = json.loads(args_json_str)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON arguments: {e}", file=sys.stderr)
            return 1

    async def _call():
        client = MCPClient(server_cfg)
        try:
            connected = await client.connect()
            if not connected:
                print(f"Failed to connect to '{server_cfg.name}': {client.status.error}", file=sys.stderr)
                return 1

            result = await client.call_tool(args.tool, raw_args)
            if result.is_error:
                print(f"Tool execution error:\n{result.content}", file=sys.stderr)
                return 1
            print(result.content)
            return 0
        finally:
            await client.close()

    return asyncio.run(_call())


def cmd_mcp_serve(args: argparse.Namespace) -> int:
    """Start Riva as an MCP Server exposing memory and profile to external clients."""
    from riva_agent.mcp.server import create_mcp_server, get_mcp_api_key, run_mcp_sse_server

    api_key = get_mcp_api_key()
    server = create_mcp_server(api_key=api_key)

    if args.transport == "sse":
        auth_status = " [Auth: X-Riva-API-Key required]" if api_key else " [Auth: disabled]"
        print(
            f"Starting Riva MCP Server over SSE on http://{args.host}:{args.port}/sse{auth_status}...",
            file=sys.stderr,
        )
        try:
            asyncio.run(run_mcp_sse_server(server, host=args.host, port=args.port, api_key=api_key))
            return 0
        except KeyboardInterrupt:
            print("\nShutting down Riva MCP Server.", file=sys.stderr)
            return 0
        except Exception as e:
            print(f"Error running Riva MCP Server (SSE): {e}", file=sys.stderr)
            return 1
    else:
        # stdio transport: informational messages MUST go to stderr so stdin/stdout JSON-RPC stream is not corrupted
        print("Starting Riva MCP Server over stdio...", file=sys.stderr)
        try:
            asyncio.run(server.run_stdio_async())
            return 0
        except KeyboardInterrupt:
            return 0
        except Exception as e:
            print(f"Error running Riva MCP Server (stdio): {e}", file=sys.stderr)
            return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="riva",
        description="Riva: Private, persistent personal assistant",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # riva ask "<prompt>"
    ask_parser = subparsers.add_parser("ask", help="Ask Riva a question in assistant mode")
    ask_parser.add_argument("prompt", type=str, help="Question or prompt to send to Riva")
    ask_parser.set_defaults(func=cmd_ask)

    # riva profile ...
    profile_parser = subparsers.add_parser("profile", help="Manage persistent user profile")
    profile_sub = profile_parser.add_subparsers(dest="profile_action", required=True)

    prof_list = profile_sub.add_parser("list", help="List profile entries")
    prof_list.add_argument("--category", "-c", type=str, default=None, help="Filter by category")
    prof_list.set_defaults(func=cmd_profile_list)

    prof_set = profile_sub.add_parser("set", help="Set a profile entry")
    prof_set.add_argument("key", type=str, help="Profile key")
    prof_set.add_argument("value", type=str, help="Profile value")
    prof_set.add_argument(
        "--category",
        "-c",
        type=str,
        default="general",
        help="Category (e.g. goals, facts, preferences)",
    )
    prof_set.set_defaults(func=cmd_profile_set)

    prof_get = profile_sub.add_parser("get", help="Get a profile entry value")
    prof_get.add_argument("key", type=str, help="Profile key")
    prof_get.set_defaults(func=cmd_profile_get)

    prof_del = profile_sub.add_parser("delete", help="Delete a profile entry")
    prof_del.add_argument("key", type=str, help="Profile key")
    prof_del.set_defaults(func=cmd_profile_delete)

    prof_show = profile_sub.add_parser("show", help="Show formatted profile context")
    prof_show.set_defaults(func=cmd_profile_show)

    prof_edit = profile_sub.add_parser("edit", help="Edit profile in $EDITOR as YAML")
    prof_edit.set_defaults(func=cmd_profile_edit)

    # riva memory ...
    memory_parser = subparsers.add_parser("memory", help="Inspect and manage episodic and candidate memories")
    memory_sub = memory_parser.add_subparsers(dest="memory_action", required=True)

    mem_list = memory_sub.add_parser("list", help="List episodic turns or pending memories")
    mem_list.add_argument("--pending", action="store_true", help="List pending candidate facts")
    mem_list.add_argument("--limit", "-n", type=int, default=15, help="Number of turns to show")
    mem_list.set_defaults(func=cmd_memory_list)

    mem_search = memory_sub.add_parser("search", help="Semantically search conversation history")
    mem_search.add_argument("query", type=str, help="Search query text")
    mem_search.add_argument("--limit", "-n", type=int, default=5, help="Maximum results to return")
    mem_search.add_argument(
        "--threshold",
        "-t",
        type=float,
        default=config.SEMANTIC_DISTANCE_THRESHOLD,
        help=f"Cosine distance threshold (default: {config.SEMANTIC_DISTANCE_THRESHOLD})",
    )
    mem_search.add_argument(
        "--session",
        "-s",
        type=str,
        default=None,
        help="Filter to a specific session ID",
    )
    mem_search.set_defaults(func=cmd_memory_search)

    mem_forget = memory_sub.add_parser("forget", help="Delete an episodic turn record")
    mem_forget.add_argument("id", type=int, help="Turn ID to delete")
    mem_forget.set_defaults(func=cmd_memory_forget)

    mem_forget_turn = memory_sub.add_parser("forget-turn", help="Delete an episodic turn and cascaded vector embedding")
    mem_forget_turn.add_argument("id", type=int, help="Turn ID to delete")
    mem_forget_turn.set_defaults(func=cmd_memory_forget)

    mem_accept = memory_sub.add_parser("accept", help="Accept a pending candidate memory")
    mem_accept.add_argument("id", type=int, help="Pending memory ID to accept")
    mem_accept.set_defaults(func=cmd_memory_accept)

    mem_reject = memory_sub.add_parser("reject", help="Reject a pending candidate memory")
    mem_reject.add_argument("id", type=int, help="Pending memory ID to reject")
    mem_reject.set_defaults(func=cmd_memory_reject)

    mem_reindex = memory_sub.add_parser("reindex", help="Backfill vector embeddings for unindexed conversation turns")
    mem_reindex.add_argument("--limit", "-n", type=int, default=500, help="Maximum turns to process")
    mem_reindex.add_argument("--batch-size", type=int, default=32, help="Batch size for embedding calls")
    mem_reindex.add_argument("--force", action="store_true", help="Clear existing embeddings and reindex all turns")
    mem_reindex.set_defaults(func=cmd_memory_reindex)

    # riva storage ...
    storage_parser = subparsers.add_parser("storage", help="Manage storage lifecycle, compaction, and backups")
    storage_sub = storage_parser.add_subparsers(dest="storage_action", required=True)

    storage_status = storage_sub.add_parser("status", help="Show storage telemetry for Riva databases and logs")
    storage_status.set_defaults(func=cmd_storage_status)

    storage_vacuum = storage_sub.add_parser("vacuum", help="Compact databases and reclaim space")
    storage_vacuum.set_defaults(func=cmd_storage_vacuum)

    storage_prune = storage_sub.add_parser("prune", help="Prune old conversation turns and pending memories")
    storage_prune.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview deletions without modifying databases or rotating logs",
    )
    storage_prune.add_argument(
        "--turns-days",
        "--turns-older-than",
        dest="turns_days",
        type=int,
        default=30,
        help="Retention period for conversation turns in days (default: 30)",
    )
    storage_prune.add_argument(
        "--pending-days",
        type=int,
        default=7,
        help="Retention period for unreviewed pending memories in days (default: 7)",
    )
    storage_prune.set_defaults(func=cmd_storage_prune)

    storage_backup = storage_sub.add_parser("backup", help="Create an online snapshot of databases")
    storage_backup.set_defaults(func=cmd_storage_backup)

    # riva session ...
    session_parser = subparsers.add_parser("session", help="Manage assistant chat sessions")
    session_sub = session_parser.add_subparsers(dest="session_action", required=True)

    sess_new = session_sub.add_parser("new", help="Start a new chat session")
    sess_new.set_defaults(func=cmd_session_new)

    sess_id = session_sub.add_parser("id", help="Show active chat session ID")
    sess_id.set_defaults(func=cmd_session_id)

    sess_list = session_sub.add_parser("list", help="List recent chat sessions")
    sess_list.add_argument("--limit", "-n", type=int, default=15, help="Number of sessions to show")
    sess_list.set_defaults(func=cmd_session_list)

    # riva digest ...
    digest_parser = subparsers.add_parser("digest", help="Generate and manage proactive daily digests")
    digest_sub = digest_parser.add_subparsers(dest="digest_action", required=True)

    # riva digest generate
    dig_gen = digest_sub.add_parser("generate", help="Generate a personal digest now")
    dig_gen.add_argument("--date", type=str, default=None, help="Date for the digest (YYYY-MM-DD)")
    dig_gen.add_argument(
        "--channel",
        type=str,
        choices=["signal", "macos"],
        default=None,
        help="Force specific notification channel",
    )
    dig_gen.add_argument(
        "--no-notify", action="store_true", help="Generate and save digest without sending notifications"
    )
    dig_gen.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview digest without writing file or sending live notification",
    )
    dig_gen.set_defaults(func=cmd_digest_generate)

    # riva digest list
    dig_list = digest_sub.add_parser("list", help="List archived digests")
    dig_list.add_argument("--limit", "-n", type=int, default=15, help="Number of digests to show")
    dig_list.set_defaults(func=cmd_digest_list)

    # riva digest show <id>
    dig_show = digest_sub.add_parser("show", help="Show content of a specific digest")
    dig_show.add_argument("identifier", type=str, help="Digest date, filename, or ID")
    dig_show.set_defaults(func=cmd_digest_show)

    # riva digest test-notify
    dig_test = digest_sub.add_parser("test-notify", help="Test notification dispatch (Signal or macOS)")
    dig_test.add_argument("--channel", type=str, choices=["signal", "macos"], default=None, help="Channel to test")
    dig_test.add_argument("--recipient", type=str, default=None, help="Signal recipient (e.g. +1234567890)")
    dig_test.add_argument("--dry-run", action="store_true", help="Simulate without actually sending")
    dig_test.set_defaults(func=cmd_digest_test_notify)

    # riva digest schedule ...
    dig_sched = digest_sub.add_parser("schedule", help="Manage macOS launchd background schedule")
    sched_sub = dig_sched.add_subparsers(dest="schedule_action", required=True)

    sched_install = sched_sub.add_parser("install", help="Install launchd agent for daily scheduled run")
    sched_install.add_argument(
        "--time", "-t", type=str, default=None, help="Daily time in HH:MM format (default: 08:00)"
    )
    sched_install.add_argument("--dry-run", action="store_true", help="Preview plist without writing")
    sched_install.set_defaults(func=cmd_digest_schedule_install)

    sched_status = sched_sub.add_parser("status", help="Check launchd agent status")
    sched_status.set_defaults(func=cmd_digest_schedule_status)

    sched_uninstall = sched_sub.add_parser("uninstall", help="Uninstall launchd agent")
    sched_uninstall.add_argument("--dry-run", action="store_true", help="Simulate without deleting plist")
    sched_uninstall.set_defaults(func=cmd_digest_schedule_uninstall)

    # riva mcp ...
    mcp_parser = subparsers.add_parser("mcp", help="Manage and inspect Model Context Protocol (MCP) integrations")
    mcp_sub = mcp_parser.add_subparsers(dest="mcp_action", required=True)

    # riva mcp add <name>
    mcp_add = mcp_sub.add_parser("add", help="Add or update an MCP server configuration")
    mcp_add.add_argument("name", type=str, help="Unique identifier name for the MCP server")
    mcp_add.add_argument(
        "cmd_and_args",
        nargs="*",
        default=[],
        help="Command and optional arguments for stdio transport (e.g. 'uvx duckduckgo-mcp-server')",
    )
    mcp_add.add_argument(
        "--transport",
        "-t",
        type=str,
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport type ('stdio' or 'sse')",
    )
    mcp_add.add_argument("--command", "-c", type=str, default=None, help="Command executable for stdio transport")
    mcp_add.add_argument(
        "--args",
        dest="server_args",
        nargs="+",
        default=[],
        help="Arguments to pass to the stdio command (e.g. --args -y @mcp/server)",
    )
    mcp_add.add_argument(
        "--env",
        "-e",
        action="append",
        default=[],
        help="Environment variables in KEY=VALUE format (can be specified multiple times)",
    )
    mcp_add.add_argument("--url", "-u", type=str, default=None, help="Endpoint URL for sse transport")
    mcp_add.add_argument("--readonly", action="store_true", help="Enforce read-only tool execution")
    mcp_add.add_argument("--disabled", action="store_true", help="Register server as disabled")
    mcp_add.add_argument("--timeout", type=float, default=30.0, help="Execution timeout in seconds (default: 30)")
    mcp_add.set_defaults(func=cmd_mcp_add)

    # riva mcp remove <name>
    mcp_remove = mcp_sub.add_parser("remove", help="Remove an MCP server from configuration")
    mcp_remove.add_argument("name", type=str, help="Name of the MCP server to remove")
    mcp_remove.set_defaults(func=cmd_mcp_remove)

    # riva mcp list
    mcp_list = mcp_sub.add_parser("list", help="List all configured MCP servers")
    mcp_list.set_defaults(func=cmd_mcp_list)

    # riva mcp tools [server]
    mcp_tools = mcp_sub.add_parser("tools", help="List tools exposed by configured MCP servers")
    mcp_tools.add_argument("server", type=str, nargs="?", default=None, help="Optional server name to filter tools")
    mcp_tools.set_defaults(func=cmd_mcp_tools)

    # riva mcp test [server]
    mcp_test = mcp_sub.add_parser("test", help="Test connectivity to configured MCP servers")
    mcp_test.add_argument("server", type=str, nargs="?", default=None, help="Optional server name to test")
    mcp_test.set_defaults(func=cmd_mcp_test)

    # riva mcp call <server> <tool> [json_args] [--args '{"key": "val"}']
    mcp_call = mcp_sub.add_parser("call", help="Manually execute an MCP tool for debugging")
    mcp_call.add_argument("server", type=str, help="Name of the target MCP server")
    mcp_call.add_argument("tool", type=str, help="Tool name to execute")
    mcp_call.add_argument(
        "raw_args",
        type=str,
        nargs="?",
        default="{}",
        help='Optional JSON-encoded argument object string (e.g. \'{"query": "foo"}\')',
    )
    mcp_call.add_argument("--args", "-a", type=str, default=None, help="JSON-encoded argument object string")
    mcp_call.set_defaults(func=cmd_mcp_call)

    # riva mcp serve [--transport stdio|sse] [--host 127.0.0.1] [--port 8086]
    mcp_serve = mcp_sub.add_parser("serve", help="Start Riva as an MCP Server for external clients")
    mcp_serve.add_argument(
        "--transport",
        "-t",
        type=str,
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport to serve on ('stdio' or 'sse', default: stdio)",
    )
    mcp_serve.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host interface for sse transport (default: 127.0.0.1)",
    )
    mcp_serve.add_argument(
        "--port",
        "-p",
        type=int,
        default=8086,
        help="Port for sse transport (default: 8086)",
    )
    mcp_serve.set_defaults(func=cmd_mcp_serve)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    exit_code = args.func(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
