import argparse
import json
import os
import shutil
import sys
import uuid
from datetime import datetime

import httpx

from common import get_episodic_store, get_profile_store
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
    with store._get_connection() as conn:
        rows = conn.execute(
            "SELECT id, session_id, role, content, created_at FROM turns ORDER BY id DESC LIMIT ?;",
            (args.limit,),
        ).fetchall()

    if not rows:
        print("No conversation history recorded.")
        return 0

    print(f"{'ID':<6} {'Role':<10} {'Turn Snippet':<50} {'Created'}")
    print(f"{'-' * 5:<6} {'-' * 9:<10} {'-' * 49:<50} {'-' * 20}")
    for r in reversed(rows):
        snippet = r["content"][:48].replace("\n", " ") + ("..." if len(r["content"]) > 48 else "")
        print(f"{r['id']:<6} {r['role']:<10} {snippet:<50} {r['created_at']}")
    return 0


def cmd_memory_forget(args: argparse.Namespace) -> int:
    """Delete an episodic turn record by ID."""
    store = get_episodic_store(config.DATA_DIR / "memory.db")
    deleted = store.delete_turn(args.id)
    if deleted:
        print(f"✔ Removed turn ID {args.id} from episodic memory.")
        return 0
    print(f"Turn ID {args.id} not found.", file=sys.stderr)
    return 1


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


def cmd_storage_status(args: argparse.Namespace) -> int:
    """Show storage telemetry for Riva databases and logs."""
    mem_store = get_episodic_store(config.DATA_DIR / "memory.db")
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

    print(f"{'Component':<20} {'Size':<12} {'Details'}")
    print(f"{'-' * 20:<20} {'-' * 11:<12} {'-' * 30}")

    mem_details = f"(Turns: {m_stats['turns']}, Pending: {m_stats['pending']})"
    print(f"{'Memory DB':<20} {m_stats['file_size'] / 1024:<11.2f} KB {mem_details}")
    if m_stats["wal_size"] > 0:
        print(f"{'  WAL':<20} {m_stats['wal_size'] / 1024:<11.2f} KB")

    print(f"{'Profile DB':<20} {p_stats['file_size'] / 1024:<11.2f} KB (Rows: {p_stats['rows']})")
    if p_stats["wal_size"] > 0:
        print(f"{'  WAL':<20} {p_stats['wal_size'] / 1024:<11.2f} KB")

    print(f"{'Logs':<20} {log_size / 1024:<11.2f} KB")

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
    with mem_store._get_connection() as conn:
        rows = conn.execute(
            """
            SELECT session_id, count(*) as turn_count, max(created_at) as last_turn
            FROM turns
            GROUP BY session_id
            ORDER BY last_turn DESC
            LIMIT ?;
            """,
            (args.limit,),
        ).fetchall()

    if not rows:
        print("No recorded chat sessions found.")
        return 0

    print(f"{'Session ID':<38} {'Turns':<8} {'Last Turn'}")
    print(f"{'-' * 38:<38} {'-' * 7:<8} {'-' * 20}")
    for r in rows:
        print(f"{r['session_id']:<38} {r['turn_count']:<8} {r['last_turn']}")
    return 0


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

    # riva memory ...
    memory_parser = subparsers.add_parser("memory", help="Inspect and manage episodic and candidate memories")
    memory_sub = memory_parser.add_subparsers(dest="memory_action", required=True)

    mem_list = memory_sub.add_parser("list", help="List episodic turns or pending memories")
    mem_list.add_argument("--pending", action="store_true", help="List pending candidate facts")
    mem_list.add_argument("--limit", "-n", type=int, default=15, help="Number of turns to show")
    mem_list.set_defaults(func=cmd_memory_list)

    mem_forget = memory_sub.add_parser("forget", help="Delete an episodic turn record")
    mem_forget.add_argument("id", type=int, help="Turn ID to delete")
    mem_forget.set_defaults(func=cmd_memory_forget)

    mem_accept = memory_sub.add_parser("accept", help="Accept a pending candidate memory")
    mem_accept.add_argument("id", type=int, help="Pending memory ID to accept")
    mem_accept.set_defaults(func=cmd_memory_accept)

    mem_reject = memory_sub.add_parser("reject", help="Reject a pending candidate memory")
    mem_reject.add_argument("id", type=int, help="Pending memory ID to reject")
    mem_reject.set_defaults(func=cmd_memory_reject)

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

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    exit_code = args.func(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
