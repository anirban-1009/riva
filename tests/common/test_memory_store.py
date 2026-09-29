import pytest

from common.memory.store import EpisodicStore


@pytest.fixture
def mem_store(tmp_path):
    db_file = tmp_path / "test_memory.db"
    return EpisodicStore(db_file)


def test_turn_logging_and_retrieval(mem_store):
    session_id = "test-session-1"

    t1 = mem_store.log_turn(session_id, "user", "Hello Riva")
    t2 = mem_store.log_turn(session_id, "assistant", "Hello! How can I help you today?")
    t3 = mem_store.log_turn(session_id, "user", "What's the weather?")

    assert t1 > 0
    assert t2 > t1
    assert t3 > t2

    turns = mem_store.get_recent_turns(session_id, limit=2)
    assert len(turns) == 2
    # Chronological order of the last 2 turns
    assert turns[0].role == "assistant"
    assert turns[1].role == "user"
    assert turns[1].content == "What's the weather?"

    # Delete turn
    assert mem_store.delete_turn(t1) is True
    remaining = mem_store.get_recent_turns(session_id, limit=10)
    assert len(remaining) == 2


def test_pending_memories(mem_store):
    p1 = mem_store.add_pending("User moved to Munich", "I recently relocated to Munich for Stripe")
    p2 = mem_store.add_pending("User prefers dark mode", "I always turn on dark mode")

    assert p1 > 0
    assert p2 > p1

    pending = mem_store.list_pending("pending")
    assert len(pending) == 2
    assert pending[0].fact == "User moved to Munich"

    # Resolve accept
    assert mem_store.resolve_pending(p1, "accepted") is True
    assert len(mem_store.list_pending("pending")) == 1
    assert len(mem_store.list_pending("accepted")) == 1

    # Delete
    assert mem_store.delete_pending(p2) is True
    assert len(mem_store.list_pending("pending")) == 0


def test_episodic_store_stats_vacuum_backup(mem_store, tmp_path):
    mem_store.log_turn("session-1", "user", "Hello")
    mem_store.add_pending("Fact 1", "snippet 1")

    stats = mem_store.get_stats()
    assert stats["turns"] == 1
    assert stats["pending"] == 1
    assert stats["file_size"] > 0
    assert isinstance(stats["wal_size"], int)
    assert isinstance(stats["shm_size"], int)

    # Vacuum
    mem_store.vacuum()

    # Backup
    backup_file = tmp_path / "backup_mem.db"
    mem_store.backup(backup_file)
    assert backup_file.exists()

    # Verify backup is a valid SQLite DB with the same data
    backup_store = EpisodicStore(backup_file)
    assert len(backup_store.get_recent_turns("session-1")) == 1
    assert len(backup_store.list_pending("pending")) == 1


def test_episodic_store_prune(mem_store):
    with mem_store._get_connection() as conn:
        conn.execute(
            "INSERT INTO turns (session_id, role, content, created_at) "
            "VALUES ('s1', 'user', 'old turn', datetime('now', '-35 days'));"
        )
        conn.execute(
            "INSERT INTO turns (session_id, role, content, created_at) "
            "VALUES ('s1', 'user', 'new turn', datetime('now', '-5 days'));"
        )
        conn.execute(
            "INSERT INTO pending_memories (fact, source_snippet, status, created_at) "
            "VALUES ('old fact', 'src', 'pending', datetime('now', '-10 days'));"
        )
        conn.execute(
            "INSERT INTO pending_memories (fact, source_snippet, status, created_at) "
            "VALUES ('new fact', 'src', 'pending', datetime('now', '-2 days'));"
        )
        conn.commit()

    # Dry-run test
    dry_results = mem_store.prune(turns_days=30, pending_days=7, dry_run=True)
    assert dry_results["turns_deleted"] == 1
    assert dry_results["pending_deleted"] == 1

    # Verify rows still exist after dry run
    stats = mem_store.get_stats()
    assert stats["turns"] == 2
    assert stats["pending"] == 2

    # Actual prune
    prune_results = mem_store.prune(turns_days=30, pending_days=7, dry_run=False)
    assert prune_results["turns_deleted"] == 1
    assert prune_results["pending_deleted"] == 1

    # Verify old rows removed, new rows preserved
    stats_after = mem_store.get_stats()
    assert stats_after["turns"] == 1
    assert stats_after["pending"] == 1
    turns = mem_store.get_recent_turns("s1", limit=10)
    assert turns[0].content == "new turn"
    pending = mem_store.list_pending("pending")
    assert pending[0].fact == "new fact"
