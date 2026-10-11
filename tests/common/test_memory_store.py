import pytest

from common.memory.store import EpisodicStore, is_synthetic_context, should_index_turn


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


def test_vector_store_operations(tmp_path):
    db_file = tmp_path / "vec_memory.db"
    store = EpisodicStore(db_file, embedding_dim=4)

    t1 = store.log_turn("session-a", "user", "I love SQLite database engines.")
    t2 = store.log_turn("session-a", "assistant", "SQLite is an embedded database engine.")
    t3 = store.log_turn("session-b", "user", "Making vegetarian pasta for dinner.")

    # Check unindexed turns before embedding
    unindexed = store.get_unindexed_turns()
    assert len(unindexed) == 3

    # Add embeddings (4-dimensional test vectors)
    vec1 = [1.0, 0.0, 0.0, 0.0]
    vec2 = [0.9, 0.1, 0.0, 0.0]
    vec3 = [0.0, 0.0, 1.0, 0.0]

    store.add_embedding(t1, vec1, "session-a", "I love SQLite database engines.")
    store.add_embedding(t2, vec2, "session-a", "SQLite is an embedded database engine.")
    store.add_embedding(t3, vec3, "session-b", "Making vegetarian pasta for dinner.")

    assert store.has_embedding(t1) is True
    assert store.has_embedding(t2) is True
    assert store.has_embedding(t3) is True
    assert store.has_embedding(999) is False

    assert len(store.get_unindexed_turns()) == 0

    stats = store.get_stats()
    assert stats["embeddings"] == 3
    assert stats["embedding_dim"] == 4
    assert stats["vec_enabled"] is True

    # Search similar to vec1
    query_vec = [0.95, 0.05, 0.0, 0.0]
    matches = store.search_similar(query_vec, top_k=2, distance_threshold=0.5)
    assert len(matches) == 2
    assert matches[0].turn_id == t1
    assert matches[0].distance < 0.05
    assert matches[0].content == "I love SQLite database engines."
    assert matches[1].turn_id == t2

    # Search with session exclusion (exclude session-a)
    matches_filtered = store.search_similar(query_vec, top_k=5, distance_threshold=2.0, exclude_session_id="session-a")
    assert len(matches_filtered) == 1
    assert matches_filtered[0].turn_id == t3
    assert matches_filtered[0].session_id == "session-b"

    # Search with strict distance threshold
    strict_matches = store.search_similar(query_vec, top_k=5, distance_threshold=0.001)
    assert len(strict_matches) <= 1

    # Update existing embedding (re-embed t1)
    new_vec1 = [0.8, 0.2, 0.0, 0.0]
    store.add_embedding(t1, new_vec1, "session-a", "updated text")
    assert store.get_stats()["embeddings"] == 3

    # Delete single embedding
    assert store.delete_embedding(t2) is True
    assert store.has_embedding(t2) is False
    assert store.get_stats()["embeddings"] == 2
    # But turn itself still exists
    assert store.get_turn(t2) is not None

    # Delete turn cascades to remove embedding
    assert store.delete_turn(t1) is True
    assert store.has_embedding(t1) is False
    assert store.get_stats()["embeddings"] == 1


def test_vector_dimension_mismatch(tmp_path):
    db_file = tmp_path / "vec_dim.db"
    store = EpisodicStore(db_file, embedding_dim=4)
    t1 = store.log_turn("sess", "user", "Hello")

    with pytest.raises(ValueError, match="Vector dimension 3 does not match store dimension 4"):
        store.add_embedding(t1, [1.0, 2.0, 3.0], "sess")

    with pytest.raises(ValueError, match="Query vector dimension 2 does not match store dimension 4"):
        store.search_similar([1.0, 2.0])


def test_list_turns_and_sessions(tmp_path):
    db_file = tmp_path / "list_test.db"
    store = EpisodicStore(db_file)

    store.log_turn("sess-1", "user", "turn 1")
    store.log_turn("sess-1", "assistant", "turn 2")
    store.log_turn("sess-2", "user", "turn 3")

    turns = store.list_turns(limit=2)
    assert len(turns) == 2
    # Reverse chronological order
    assert turns[0].content == "turn 3"
    assert turns[1].content == "turn 2"

    sessions = store.list_sessions(limit=10)
    assert len(sessions) == 2
    sess_map = {s.session_id: s for s in sessions}
    assert sess_map["sess-1"].turn_count == 2
    assert sess_map["sess-2"].turn_count == 1


def test_sql_trigger_cascade(tmp_path):
    db_file = tmp_path / "trigger_test.db"
    store = EpisodicStore(db_file, embedding_dim=4)

    t1 = store.log_turn("session-x", "user", "important fact")
    store.add_embedding(t1, [1.0, 0.0, 0.0, 0.0], "session-x", "important fact")

    assert store.has_embedding(t1) is True

    # Delete turn directly via store.delete_turn
    assert store.delete_turn(t1) is True

    # Verify SQL trigger cascaded deletion to turn_embeddings and vec_turns
    assert store.has_embedding(t1) is False
    with store._get_connection() as conn:
        assert conn.execute("SELECT count(*) FROM turn_embeddings WHERE turn_id = ?;", (t1,)).fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM vec_turns WHERE turn_id = ?;", (t1,)).fetchone()[0] == 0


def test_should_index_turn():
    # Short / empty
    assert should_index_turn("") is False
    assert should_index_turn("ok") is False
    assert should_index_turn("thanks") is False
    assert should_index_turn("hello world!") is False  # 12 chars

    # Boilerplate filler
    assert should_index_turn("thank you very much") is False
    assert should_index_turn("Thanks a lot!") is False
    assert should_index_turn("ok sounds good.") is False
    assert should_index_turn("have a great day!") is False

    # Substantive turns
    assert should_index_turn("My MacBook Pro has an M3 Max chip with 36GB RAM.") is True
    assert should_index_turn("In Bavaria, breakfast often includes pretzels and Weisswurst.") is True
    assert should_index_turn("Please remember that my flight is at 7pm tomorrow.") is True

    # Synthetic client runtime context envelopes (OpenClaw)
    openclaw_env = (
        "OpenClaw runtime context for the immediately preceding user message.\n"
        "This context is runtime-generated, not user-authored. Keep internal details private.\n"
        "<<<BEGIN_OPENCLAW_INTERNAL_CONTEXT>>>\n"
        '{"chat_id": "+918919557783", "inbound_event_kind": "user_request"}\n'
        "<<<END_OPENCLAW_INTERNAL_CONTEXT>>>"
    )
    assert is_synthetic_context(openclaw_env) is True
    assert should_index_turn(openclaw_env) is False
    assert is_synthetic_context("Normal user message without wrappers") is False


def test_clear_embeddings(tmp_path):
    db_file = tmp_path / "clear_emb.db"
    store = EpisodicStore(db_file, embedding_dim=4)

    t1 = store.log_turn("s1", "user", "turn 1 with substantive length")
    t2 = store.log_turn("s1", "assistant", "turn 2 with substantive response")

    store.add_embedding(t1, [1.0, 0.0, 0.0, 0.0], "s1", "turn 1 with substantive length")
    store.add_embedding(t2, [0.0, 1.0, 0.0, 0.0], "s1", "turn 2 with substantive response")

    assert store.get_stats()["embeddings"] == 2
    cleared = store.clear_embeddings()
    assert cleared == 2
    assert store.get_stats()["embeddings"] == 0
    assert store.get_stats()["turns"] == 2
    assert len(store.get_unindexed_turns()) == 2


def test_vacuum_and_backup_with_vectors(tmp_path):
    db_file = tmp_path / "vec_vac_test.db"
    store = EpisodicStore(db_file, embedding_dim=4)

    t1 = store.log_turn("s1", "user", "Apple M3 hardware specifications")
    store.add_embedding(t1, [1.0, 0.0, 0.0, 0.0], "s1", "Apple M3 hardware specifications")

    # Vacuum
    store.vacuum()

    # Backup
    backup_file = tmp_path / "backup_vec.db"
    store.backup(backup_file)
    assert backup_file.exists()

    # Verify backup store retains vector index and can execute similarity search
    backup_store = EpisodicStore(backup_file, embedding_dim=4)
    assert backup_store.get_stats()["embeddings"] == 1
    matches = backup_store.search_similar([1.0, 0.0, 0.0, 0.0], top_k=1)
    assert len(matches) == 1
    assert matches[0].turn_id == t1
    assert matches[0].distance == pytest.approx(0.0, abs=1e-5)


def test_store_guards_against_synthetic_context(tmp_path):
    db_file = tmp_path / "synth_guard.db"
    store = EpisodicStore(db_file, embedding_dim=4)

    openclaw_env = (
        "OpenClaw runtime context for the immediately preceding user message.\n"
        "<<<BEGIN_OPENCLAW_INTERNAL_CONTEXT>>>\n"
        '{"chat_id": "123"}\n'
        "<<<END_OPENCLAW_INTERNAL_CONTEXT>>>"
    )

    # 1. log_turn rejects synthetic context
    turn_id = store.log_turn("s1", "user", openclaw_env)
    assert turn_id == 0
    assert len(store.list_turns()) == 0

    # 2. add_pending rejects synthetic context
    pend_id = store.add_pending(openclaw_env, "source")
    assert pend_id == 0
    pend_id2 = store.add_pending("valid fact", openclaw_env)
    assert pend_id2 == 0
    assert len(store.list_pending()) == 0

    # 3. add_embedding rejects synthetic content
    valid_turn = store.log_turn("s1", "user", "A substantive conversation turn about architecture")
    assert valid_turn > 0
    store.add_embedding(valid_turn, [1.0, 0.0, 0.0, 0.0], "s1", content=openclaw_env)
    assert store.get_stats()["embeddings"] == 0


def test_format_relevant_context(tmp_path):
    from common.memory.store import EpisodicStore, VectorMatch, format_relevant_context

    # Empty list
    assert format_relevant_context([]) == ""

    store = EpisodicStore(tmp_path / "fmt.db", embedding_dim=4)
    assert store.format_relevant_context([]) == ""

    matches = [
        VectorMatch(
            turn_id=1,
            session_id="sess-1",
            role="user",
            content="My favorite language is Python.",
            distance=0.12,
            created_at="2026-10-10 14:00:00",
        ),
        VectorMatch(
            turn_id=2,
            session_id="sess-1",
            role="assistant",
            content="Python is great for AI development.",
            distance=0.25,
            created_at="2026-10-10 14:00:05",
        ),
    ]

    formatted = format_relevant_context(matches)
    assert "<relevant_past_context>" in formatted
    assert "</relevant_past_context>" in formatted
    assert '[User on 2026-10-10]: "My favorite language is Python."' in formatted
    assert '[Assistant on 2026-10-10]: "Python is great for AI development."' in formatted
    assert store.format_relevant_context(matches) == formatted
