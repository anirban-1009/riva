from unittest.mock import MagicMock, patch

import pytest

from common.memory.store import EpisodicStore
from common.profile.store import ProfileStore
from riva_agent import cli, config


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / ".riva"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    return data_dir


def test_cli_profile_lifecycle(capsys):
    parser = cli.build_parser()

    # 1. Profile Set
    args = parser.parse_args(["profile", "set", "location", "Munich", "-c", "facts"])
    ret = args.func(args)
    assert ret == 0
    captured = capsys.readouterr().out
    assert "Set profile [facts] 'location' = 'Munich'" in captured

    # 2. Profile Get
    args = parser.parse_args(["profile", "get", "location"])
    ret = args.func(args)
    assert ret == 0
    captured = capsys.readouterr().out
    assert captured.strip() == "Munich"

    # 3. Profile List
    args = parser.parse_args(["profile", "list"])
    ret = args.func(args)
    assert ret == 0
    captured = capsys.readouterr().out
    assert "location" in captured
    assert "Munich" in captured

    # 4. Profile Delete
    args = parser.parse_args(["profile", "delete", "location"])
    ret = args.func(args)
    assert ret == 0
    captured = capsys.readouterr().out
    assert "Deleted profile entry 'location'" in captured

    # Delete non-existent
    args = parser.parse_args(["profile", "delete", "location"])
    ret = args.func(args)
    assert ret == 1


def test_cli_memory_lifecycle(capsys):
    parser = cli.build_parser()

    # Populate episodic store
    mem_store = EpisodicStore(config.DATA_DIR / "memory.db")
    turn_id = mem_store.log_turn("session-1", "user", "Remember that I run at 7 AM")
    pending_id = mem_store.add_pending("User runs at 7 AM", "I run at 7 AM")

    # 1. Memory List (turns)
    args = parser.parse_args(["memory", "list"])
    ret = args.func(args)
    assert ret == 0
    captured = capsys.readouterr().out
    assert "Remember that I run at 7 AM" in captured

    # 2. Memory List (--pending)
    args = parser.parse_args(["memory", "list", "--pending"])
    ret = args.func(args)
    assert ret == 0
    captured = capsys.readouterr().out
    assert "User runs at 7 AM" in captured

    # 3. Memory Accept
    args = parser.parse_args(["memory", "accept", str(pending_id)])
    ret = args.func(args)
    assert ret == 0
    captured = capsys.readouterr().out
    assert f"Accepted memory ID {pending_id}" in captured

    # Verify fact added to profile
    prof_store = ProfileStore(config.DATA_DIR / "profile.db")
    assert prof_store.get("User runs at 7 AM") == "User runs at 7 AM"

    # 4. Memory Forget
    args = parser.parse_args(["memory", "forget", str(turn_id)])
    ret = args.func(args)
    assert ret == 0
    captured = capsys.readouterr().out
    assert f"Removed turn ID {turn_id}" in captured


def test_cli_ask_success(capsys):
    parser = cli.build_parser()
    args = parser.parse_args(["ask", "What is my job?"])

    # Mock streaming response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.iter_lines.return_value = [
        'data: {"choices": [{"delta": {"content": "You work "}}]}',
        'data: {"choices": [{"delta": {"content": "at Stripe."}}]}',
        "data: [DONE]",
    ]

    with patch("httpx.stream") as mock_stream:
        mock_stream.return_value.__enter__.return_value = mock_response
        ret = args.func(args)

    assert ret == 0
    captured = capsys.readouterr().out
    assert "You work at Stripe." in captured


def test_cli_storage_status(capsys):
    parser = cli.build_parser()

    # Pre-populate data
    mem_store = EpisodicStore(config.DATA_DIR / "memory.db")
    mem_store.log_turn("s1", "user", "Hi")
    prof_store = ProfileStore(config.DATA_DIR / "profile.db")
    prof_store.set("k1", "v1")

    log_dir = config.DATA_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "gateway.log").write_text("sample log line\n")

    args = parser.parse_args(["storage", "status"])
    ret = args.func(args)
    assert ret == 0

    captured = capsys.readouterr().out
    assert "Memory DB" in captured
    assert "Profile DB" in captured
    assert "Logs" in captured
    assert "Turns: 1" in captured
    assert "Rows: 1" in captured


def test_cli_storage_vacuum(capsys):
    parser = cli.build_parser()
    args = parser.parse_args(["storage", "vacuum"])
    ret = args.func(args)
    assert ret == 0

    captured = capsys.readouterr().out
    assert "Databases vacuumed and WAL checkpoints truncated." in captured


def test_cli_storage_prune(capsys):
    parser = cli.build_parser()

    mem_store = EpisodicStore(config.DATA_DIR / "memory.db")
    with mem_store._get_connection() as conn:
        conn.execute(
            "INSERT INTO turns (session_id, role, content, created_at) "
            "VALUES ('s1', 'user', 'old', datetime('now', '-40 days'));"
        )
        conn.execute(
            "INSERT INTO turns (session_id, role, content, created_at) "
            "VALUES ('s1', 'user', 'new', datetime('now', '-2 days'));"
        )
        conn.execute(
            "INSERT INTO pending_memories (fact, source_snippet, status, created_at) "
            "VALUES ('old fact', 'src', 'pending', datetime('now', '-10 days'));"
        )
        conn.execute(
            "INSERT INTO pending_memories (fact, source_snippet, status, created_at) "
            "VALUES ('new fact', 'src', 'pending', datetime('now', '-1 days'));"
        )
        conn.commit()

    # 1. Dry run
    args = parser.parse_args(["storage", "prune", "--dry-run", "--turns-days", "30", "--pending-days", "7"])
    ret = args.func(args)
    assert ret == 0
    captured = capsys.readouterr().out
    assert "Would delete 1 old turns and 1 expired pending memories." in captured

    # Verify rows still exist
    stats = mem_store.get_stats()
    assert stats["turns"] == 2
    assert stats["pending"] == 2

    # 2. Actual prune (using --turns-older-than alias)
    args = parser.parse_args(["storage", "prune", "--turns-older-than", "30", "--pending-days", "7"])
    ret = args.func(args)
    assert ret == 0
    captured = capsys.readouterr().out
    assert "Deleted 1 old turns and 1 expired pending memories." in captured

    stats = mem_store.get_stats()
    assert stats["turns"] == 1
    assert stats["pending"] == 1


def test_cli_storage_log_rotation(capsys):
    parser = cli.build_parser()
    log_dir = config.DATA_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    gateway_log = log_dir / "gateway.log"

    # Create dummy file > 50MB using seek (sparse file)
    with open(gateway_log, "wb") as f:
        f.seek(51 * 1024 * 1024)
        f.write(b"end")

    assert gateway_log.stat().st_size > 50 * 1024 * 1024

    # Dry-run
    args = parser.parse_args(["storage", "prune", "--dry-run"])
    ret = args.func(args)
    assert ret == 0
    captured = capsys.readouterr().out
    assert "gateway.log would be rotated" in captured
    assert gateway_log.stat().st_size > 50 * 1024 * 1024

    # Execution rotation 1: gateway.log -> gateway.log.1
    args = parser.parse_args(["storage", "prune"])
    ret = args.func(args)
    assert ret == 0
    captured = capsys.readouterr().out
    assert "Rotated gateway.log" in captured

    assert gateway_log.stat().st_size == 0
    rotated_1 = log_dir / "gateway.log.1"
    assert rotated_1.exists()
    assert rotated_1.stat().st_size > 50 * 1024 * 1024

    # Grow gateway.log again and rotate again: 1 -> 2
    with open(gateway_log, "wb") as f:
        f.seek(51 * 1024 * 1024)
        f.write(b"end2")

    args = parser.parse_args(["storage", "prune"])
    ret = args.func(args)
    assert ret == 0

    assert gateway_log.stat().st_size == 0
    rotated_2 = log_dir / "gateway.log.2"
    assert rotated_2.exists()


def test_cli_storage_backup(capsys):
    parser = cli.build_parser()

    mem_store = EpisodicStore(config.DATA_DIR / "memory.db")
    mem_store.log_turn("s1", "user", "turn to backup")
    prof_store = ProfileStore(config.DATA_DIR / "profile.db")
    prof_store.set("backup_key", "backup_val")

    args = parser.parse_args(["storage", "backup"])
    ret = args.func(args)
    assert ret == 0

    captured = capsys.readouterr().out
    assert "Backups created in" in captured

    backup_dir = config.DATA_DIR / "backups"
    assert backup_dir.exists()
    mem_backups = list(backup_dir.glob("memory_*.db"))
    prof_backups = list(backup_dir.glob("profile_*.db"))
    assert len(mem_backups) >= 1
    assert len(prof_backups) >= 1

    # Verify backups are readable
    b_mem = EpisodicStore(mem_backups[0])
    assert len(b_mem.get_recent_turns("s1")) == 1
    b_prof = ProfileStore(prof_backups[0])
    assert b_prof.get("backup_key") == "backup_val"


def test_cli_session_commands(capsys):
    parser = cli.build_parser()

    # 1. No session exists yet
    session_file = config.DATA_DIR / "session.id"
    if session_file.exists():
        session_file.unlink()

    args = parser.parse_args(["session", "id"])
    ret = args.func(args)
    assert ret == 1
    err = capsys.readouterr().err
    assert "No active session ID found." in err

    # 2. session list with no sessions in memory
    args = parser.parse_args(["session", "list"])
    ret = args.func(args)
    assert ret == 0
    out = capsys.readouterr().out
    assert "No recorded chat sessions found." in out

    # 3. session new
    args = parser.parse_args(["session", "new"])
    ret = args.func(args)
    assert ret == 0
    out = capsys.readouterr().out
    assert "Started new chat session:" in out
    assert session_file.exists()
    sid1 = session_file.read_text().strip()
    assert sid1 in out

    # 4. session id prints the active session
    args = parser.parse_args(["session", "id"])
    ret = args.func(args)
    assert ret == 0
    out = capsys.readouterr().out
    assert out.strip() == sid1

    # 5. Populate episodic memory with some turns across sessions
    mem_store = EpisodicStore(config.DATA_DIR / "memory.db")
    mem_store.log_turn(sid1, "user", "Hello in session 1")
    mem_store.log_turn(sid1, "assistant", "Hi there!")
    mem_store.log_turn("sid-2", "user", "Question in session 2")

    # 6. session list displays sessions
    args = parser.parse_args(["session", "list", "--limit", "10"])
    ret = args.func(args)
    assert ret == 0
    out = capsys.readouterr().out
    assert "Session ID" in out
    assert sid1 in out
    assert "sid-2" in out
    assert "2" in out  # turn count for sid1
