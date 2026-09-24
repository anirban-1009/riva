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
