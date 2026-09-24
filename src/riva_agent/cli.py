import argparse
import json
import os
import sys
from pathlib import Path

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
                print(f"Error from Riva Gateway ({response.status_code}): {response.read().decode('utf-8')}", file=sys.stderr)
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
        print(f"Failed to connect to Riva Gateway at {endpoint}. Is the server running? (Try: uv run python -m riva_agent)", file=sys.stderr)
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
    print(f"{'-'*14:<15} {'-'*29:<30} {'-'*30}")
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
        print(f"{'-'*5:<6} {'-'*39:<40} {'-'*30}")
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
    print(f"{'-'*5:<6} {'-'*9:<10} {'-'*49:<50} {'-'*20}")
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
    prof_set.add_argument("--category", "-c", type=str, default="general", help="Category (e.g. goals, facts, preferences)")
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

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    exit_code = args.func(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
