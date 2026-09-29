import pytest

from common.profile.store import ProfileStore


@pytest.fixture
def store(tmp_path):
    db_file = tmp_path / "test_profile.db"
    return ProfileStore(db_file)


def test_profile_set_get_delete(store):
    assert store.get("location") is None

    store.set("location", "Munich", category="facts")
    assert store.get("location") == "Munich"

    entry = store.get_entry("location")
    assert entry is not None
    assert entry.key == "location"
    assert entry.value == "Munich"
    assert entry.category == "facts"

    # Overwrite / upsert
    store.set("location", "Berlin", category="facts")
    assert store.get("location") == "Berlin"

    # Delete
    assert store.delete("location") is True
    assert store.get("location") is None
    assert store.delete("location") is False


def test_profile_list_all_and_category(store):
    store.set("job", "Software Engineer", category="facts")
    store.set("diet", "No peanuts", category="constraints")
    store.set("theme", "Dark mode", category="preferences")

    all_entries = store.list_all()
    assert len(all_entries) == 3

    facts = store.list_all(category="facts")
    assert len(facts) == 1
    assert facts[0].key == "job"

    constraints = store.list_all(category="constraints")
    assert len(constraints) == 1
    assert constraints[0].key == "diet"


def test_format_context(store):
    assert store.format_context() == ""

    store.set("Location", "Munich", category="facts")
    store.set("Diet", "Peanut allergy", category="constraints")

    ctx = store.format_context()
    assert "[User Profile & Durable Facts]" in ctx
    assert "- Location: Munich [facts]" in ctx
    assert "- Diet: Peanut allergy [constraints]" in ctx


def test_profile_store_stats_vacuum_backup(store, tmp_path):
    store.set("key1", "val1", category="facts")
    store.set("key2", "val2", category="goals")

    stats = store.get_stats()
    assert stats["rows"] == 2
    assert stats["file_size"] > 0
    assert isinstance(stats["wal_size"], int)
    assert isinstance(stats["shm_size"], int)

    # Vacuum
    store.vacuum()

    # Backup
    backup_file = tmp_path / "backup_prof.db"
    store.backup(backup_file)
    assert backup_file.exists()

    # Verify backup DB content
    backup_store = ProfileStore(backup_file)
    assert backup_store.get("key1") == "val1"
    assert backup_store.get("key2") == "val2"
    assert len(backup_store.list_all()) == 2
