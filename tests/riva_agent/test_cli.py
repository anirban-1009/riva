from unittest.mock import MagicMock, patch

import pytest
import yaml

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


def test_cli_profile_show_and_edit(capsys):
    parser = cli.build_parser()
    prof_store = ProfileStore(config.DATA_DIR / "profile.db")

    # 1. Show empty
    args = parser.parse_args(["profile", "show"])
    ret = args.func(args)
    assert ret == 0
    assert "No profile entries found." in capsys.readouterr().out

    # 2. Show populated
    prof_store.set("role", "Engineer", category="career")
    args = parser.parse_args(["profile", "show"])
    ret = args.func(args)
    assert ret == 0
    captured = capsys.readouterr().out
    assert "[User Profile & Durable Facts]" in captured
    assert "role: Engineer [career]" in captured

    # 3. Edit profile via mocked editor
    def fake_editor_success(cmd):
        temp_file = cmd[1]
        with open(temp_file, "r") as f:
            data = yaml.safe_load(f)
        data[0]["value"] = "Principal Engineer"
        data.append({"category": "hobby", "key": "sports", "value": "Running"})
        with open(temp_file, "w") as f:
            yaml.safe_dump(data, f)
        return 0

    with patch("subprocess.call", side_effect=fake_editor_success):
        args = parser.parse_args(["profile", "edit"])
        ret = args.func(args)
        assert ret == 0
        assert "Profile synchronized (2 entries active)." in capsys.readouterr().out

    assert prof_store.get("role") == "Principal Engineer"
    assert prof_store.get("sports") == "Running"

    # 4. Edit with failure status
    with patch("subprocess.call", return_value=1):
        args = parser.parse_args(["profile", "edit"])
        ret = args.func(args)
        assert ret == 1
        assert "Profile edit aborted" in capsys.readouterr().err


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
    assert "Vector Index" in captured
    assert "Vectors: 0" in captured


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


def test_cli_memory_reindex(capsys, monkeypatch):
    parser = cli.build_parser()
    monkeypatch.setattr(config, "EMBEDDING_PROVIDER", "mock")
    monkeypatch.setattr(config, "EMBEDDING_DIMENSION", 768)

    mem_store = EpisodicStore(config.DATA_DIR / "memory.db", embedding_dim=768)
    mem_store.log_turn("s1", "user", "My MacBook Pro has 36GB unified memory.")
    mem_store.log_turn("s1", "assistant", "Bavarian breakfast with Weisswurst.")
    mem_store.log_turn("s1", "user", "ok")

    assert mem_store.get_stats()["embeddings"] == 0
    # SQL function should_index_turn filters out 'ok', returning only 2 substantive turns
    assert len(mem_store.get_unindexed_turns()) == 2

    # 1. Normal reindex
    args = parser.parse_args(["memory", "reindex"])
    ret = args.func(args)
    assert ret == 0
    out = capsys.readouterr().out
    assert "Successfully indexed 2 turns into vector store." in out
    assert mem_store.get_stats()["embeddings"] == 2

    # 2. Reindex when already up to date
    ret = args.func(args)
    assert ret == 0
    out = capsys.readouterr().out
    assert "All conversation turns are already indexed." in out

    # 3. Force reindex
    args_force = parser.parse_args(["memory", "reindex", "--force"])
    ret = args_force.func(args_force)
    assert ret == 0
    out = capsys.readouterr().out
    assert "Purged 2 existing vector embeddings for full reindex." in out
    assert "Successfully indexed 2 turns into vector store" in out
    assert mem_store.get_stats()["embeddings"] == 2


def test_cli_memory_forget_turn(capsys):
    parser = cli.build_parser()
    mem_store = EpisodicStore(config.DATA_DIR / "memory.db", embedding_dim=768)

    turn_id = mem_store.log_turn("s1", "user", "I run half-marathons.")
    mem_store.add_embedding(turn_id, [0.1] * 768, "s1", "I run half-marathons.")

    assert mem_store.get_turn(turn_id) is not None
    assert mem_store.has_embedding(turn_id) is True

    # 1. Forget via forget-turn
    args = parser.parse_args(["memory", "forget-turn", str(turn_id)])
    ret = args.func(args)
    assert ret == 0
    captured = capsys.readouterr().out
    assert f"Removed turn ID {turn_id} and associated vector embeddings from episodic memory." in captured

    # Verify cascaded deletion
    assert mem_store.get_turn(turn_id) is None
    assert mem_store.has_embedding(turn_id) is False

    # 2. Forget non-existent turn
    args_missing = parser.parse_args(["memory", "forget-turn", "9999"])
    ret_missing = args_missing.func(args_missing)
    assert ret_missing == 1
    err = capsys.readouterr().err
    assert "Turn ID 9999 not found." in err


def test_cli_memory_search(capsys, monkeypatch):
    from unittest.mock import AsyncMock

    parser = cli.build_parser()
    monkeypatch.setattr(config, "EMBEDDING_PROVIDER", "mock")
    monkeypatch.setattr(config, "EMBEDDING_DIMENSION", 768)

    mem_store = EpisodicStore(config.DATA_DIR / "memory.db", embedding_dim=768)
    t1 = mem_store.log_turn("session-1", "user", "I live in Berlin and run marathons.")
    t2 = mem_store.log_turn("session-2", "assistant", "Berlin has great running tracks.")
    assert t1 > 0 and t2 > 0

    fake_vec1 = [1.0] + [0.0] * 767
    fake_vec2 = [0.0, 1.0] + [0.0] * 766
    orthogonal_vec = [0.0, 0.0, 1.0] + [0.0] * 765

    mock_prov = AsyncMock()
    mock_prov.embed_documents.return_value = [fake_vec1, fake_vec2]
    mock_prov.embed_query.return_value = fake_vec1
    mock_prov.close = AsyncMock()

    with patch("riva_agent.cli.create_embedding_provider", return_value=mock_prov):
        # Reindex to create vectors
        args_reindex = parser.parse_args(["memory", "reindex"])
        assert args_reindex.func(args_reindex) == 0
        capsys.readouterr()  # flush output

        # 1. Search with match
        args_search = parser.parse_args(["memory", "search", "marathons", "--limit", "5"])
        ret = args_search.func(args_search)
        assert ret == 0
        captured = capsys.readouterr().out
        assert "Score" in captured
        assert "Role" in captured
        assert "Matched Text" in captured
        assert "Berlin and run marathons" in captured

        # 2. Search with session filter
        mock_prov.embed_query.return_value = fake_vec2
        args_sess = parser.parse_args(["memory", "search", "running", "--session", "session-2"])
        ret = args_sess.func(args_sess)
        assert ret == 0
        captured_sess = capsys.readouterr().out
        assert "Berlin has great running tracks" in captured_sess
        assert "Berlin and run marathons" not in captured_sess

        # 3. Search with impossible threshold
        mock_prov.embed_query.return_value = orthogonal_vec
        args_none = parser.parse_args(["memory", "search", "marathons", "--threshold", "0.38"])
        ret = args_none.func(args_none)
        assert ret == 0
        captured_none = capsys.readouterr().out
        assert "No semantic matches found for 'marathons'" in captured_none

        # 4. Search with empty query
        args_empty = parser.parse_args(["memory", "search", "   "])
        ret = args_empty.func(args_empty)
        assert ret == 1
        err = capsys.readouterr().err
        assert "Search query cannot be empty." in err

    # 5. Search when vector extension is disabled
    with patch.object(mem_store, "_vec_enabled", False):
        with patch("riva_agent.cli.get_episodic_store", return_value=mem_store):
            args_dis = parser.parse_args(["memory", "search", "test"])
            ret = args_dis.func(args_dis)
            assert ret == 1
            assert "sqlite-vec is not enabled" in capsys.readouterr().err

    # 6. Search when embedding provider fails
    with patch("riva_agent.cli.create_embedding_provider") as mock_err_prov:
        prov_err = AsyncMock()
        prov_err.embed_query.side_effect = RuntimeError("Embedding service down")
        mock_err_prov.return_value = prov_err
        args_err = parser.parse_args(["memory", "search", "test"])
        ret = args_err.func(args_err)
        assert ret == 1
        assert "Error during semantic search" in capsys.readouterr().err
