import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ProfileEntry:
    key: str
    value: str
    category: str = "general"
    updated_at: str = ""


class ProfileStore:
    """Local SQLite-backed persistent store for user profile, goals, constraints, and facts."""

    def __init__(self, db_path: Optional[str | Path] = None):
        if db_path is None:
            data_dir = Path(os.environ.get("RIVA_DATA_DIR", Path.home() / ".riva"))
            data_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(data_dir / "profile.db")
        else:
            self.db_path = str(db_path)
            if self.db_path != ":memory:":
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        if self.db_path != ":memory:":
            conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS profile (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.commit()

    def set(self, key: str, value: str, category: str = "general") -> None:
        """Insert or update a profile entry."""
        clean_key = key.strip()
        clean_val = value.strip()
        clean_cat = category.strip().lower()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO profile (key, value, category, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    category = excluded.category,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                (clean_key, clean_val, clean_cat),
            )
            conn.commit()

    def get(self, key: str) -> Optional[str]:
        """Get the value of a profile key, or None if not found."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT value FROM profile WHERE key = ?;", (key.strip(),)
            ).fetchone()
            return row["value"] if row else None

    def get_entry(self, key: str) -> Optional[ProfileEntry]:
        """Get the full ProfileEntry for a key, or None if not found."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT key, value, category, updated_at FROM profile WHERE key = ?;",
                (key.strip(),),
            ).fetchone()
            if row:
                return ProfileEntry(
                    key=row["key"],
                    value=row["value"],
                    category=row["category"],
                    updated_at=str(row["updated_at"]),
                )
            return None

    def list_all(self, category: Optional[str] = None) -> list[ProfileEntry]:
        """List all profile entries, optionally filtered by category."""
        with self._get_connection() as conn:
            if category:
                rows = conn.execute(
                    "SELECT key, value, category, updated_at FROM profile WHERE category = ? ORDER BY key ASC;",
                    (category.strip().lower(),),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT key, value, category, updated_at FROM profile ORDER BY category ASC, key ASC;"
                ).fetchall()

            return [
                ProfileEntry(
                    key=r["key"],
                    value=r["value"],
                    category=r["category"],
                    updated_at=str(r["updated_at"]),
                )
                for r in rows
            ]

    def delete(self, key: str) -> bool:
        """Delete a profile entry. Returns True if a row was deleted, False otherwise."""
        with self._get_connection() as conn:
            cur = conn.execute("DELETE FROM profile WHERE key = ?;", (key.strip(),))
            conn.commit()
            return cur.rowcount > 0

    def format_context(self, max_entries: int = 50) -> str:
        """Format stored profile into a clean markdown snippet for system prompt injection."""
        entries = self.list_all()
        if not entries:
            return ""

        lines = ["[User Profile & Durable Facts]"]
        for entry in entries[:max_entries]:
            # Format nicely: - key: value (category)
            cat_suffix = f" [{entry.category}]" if entry.category != "general" else ""
            lines.append(f"- {entry.key}: {entry.value}{cat_suffix}")

        return "\n".join(lines)


_profile_store: Optional[ProfileStore] = None


def get_profile_store(db_path: Optional[str | Path] = None) -> ProfileStore:
    """Get or lazily instantiate singleton ProfileStore instance."""
    global _profile_store
    if _profile_store is None or db_path is not None:
        store = ProfileStore(db_path)
        if db_path is None:
            _profile_store = store
        return store
    return _profile_store
