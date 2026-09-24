import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Turn:
    id: int
    session_id: str
    role: str
    content: str
    created_at: str


@dataclass
class PendingMemory:
    id: int
    fact: str
    source_snippet: str
    status: str
    created_at: str


class EpisodicStore:
    """Local SQLite-backed episodic store for conversation turns and staged candidate memories."""

    def __init__(self, db_path: Optional[str | Path] = None):
        if db_path is None:
            data_dir = Path(os.environ.get("RIVA_DATA_DIR", Path.home() / ".riva"))
            data_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(data_dir / "memory.db")
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
                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, id);"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fact TEXT NOT NULL,
                    source_snippet TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.commit()

    def log_turn(self, session_id: str, role: str, content: str) -> int:
        """Log a conversation turn to episodic history. Returns the new turn ID."""
        with self._get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO turns (session_id, role, content) VALUES (?, ?, ?);",
                (session_id.strip(), role.strip(), content.strip()),
            )
            conn.commit()
            return cur.lastrowid or 0

    def get_recent_turns(self, session_id: str, limit: int = 10) -> list[Turn]:
        """Fetch the most recent turns for a session in chronological order."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, role, content, created_at
                FROM turns
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?;
                """,
                (session_id.strip(), limit),
            ).fetchall()

            # Reverse to return in chronological order (oldest to newest of the recent slice)
            turns = [
                Turn(
                    id=r["id"],
                    session_id=r["session_id"],
                    role=r["role"],
                    content=r["content"],
                    created_at=str(r["created_at"]),
                )
                for r in reversed(rows)
            ]
            return turns

    def delete_turn(self, turn_id: int) -> bool:
        """Delete an episodic turn record by ID."""
        with self._get_connection() as conn:
            cur = conn.execute("DELETE FROM turns WHERE id = ?;", (turn_id,))
            conn.commit()
            return cur.rowcount > 0

    def add_pending(self, fact: str, source_snippet: str) -> int:
        """Stage a proposed candidate memory fact for human review. Returns the pending record ID."""
        with self._get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO pending_memories (fact, source_snippet, status) VALUES (?, ?, 'pending');",
                (fact.strip(), source_snippet.strip()),
            )
            conn.commit()
            return cur.lastrowid or 0

    def list_pending(self, status: str = "pending") -> list[PendingMemory]:
        """List candidate memories filtered by status (default: 'pending')."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT id, fact, source_snippet, status, created_at FROM pending_memories WHERE status = ? ORDER BY id ASC;",
                (status.strip().lower(),),
            ).fetchall()

            return [
                PendingMemory(
                    id=r["id"],
                    fact=r["fact"],
                    source_snippet=r["source_snippet"],
                    status=r["status"],
                    created_at=str(r["created_at"]),
                )
                for r in rows
            ]

    def resolve_pending(self, memory_id: int, status: str) -> bool:
        """Update the review status of a pending memory ('accepted', 'rejected')."""
        with self._get_connection() as conn:
            cur = conn.execute(
                "UPDATE pending_memories SET status = ? WHERE id = ?;",
                (status.strip().lower(), memory_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def delete_pending(self, memory_id: int) -> bool:
        """Permanently delete a pending memory proposal."""
        with self._get_connection() as conn:
            cur = conn.execute("DELETE FROM pending_memories WHERE id = ?;", (memory_id,))
            conn.commit()
            return cur.rowcount > 0


_episodic_store: Optional[EpisodicStore] = None


def get_episodic_store(db_path: Optional[str | Path] = None) -> EpisodicStore:
    """Get or lazily instantiate singleton EpisodicStore instance."""
    global _episodic_store
    if _episodic_store is None or db_path is not None:
        store = EpisodicStore(db_path)
        if db_path is None:
            _episodic_store = store
        return store
    return _episodic_store
