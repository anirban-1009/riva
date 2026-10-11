import hashlib
import logging
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

try:
    import sqlite_vec
except ImportError:
    sqlite_vec = None

logger = logging.getLogger(__name__)


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


@dataclass
class VectorMatch:
    turn_id: int
    session_id: str
    role: str
    content: str
    distance: float
    created_at: str


@dataclass
class SessionSummary:
    session_id: str
    turn_count: int
    last_turn: str


def is_synthetic_context(content: str) -> bool:
    """Check if message content is runtime/synthetic client metadata rather than user-authored text."""
    text = content.strip()
    return (
        "OPENCLAW_INTERNAL_CONTEXT" in text
        or "OpenClaw runtime context" in text
        or "runtime-generated, not user-authored" in text
        or text.startswith("<<<BEGIN_")
    )


def should_index_turn(content: str) -> bool:
    """Determine whether a turn has sufficient semantic signal to be vector indexed.

    Filters out:
    - Empty or very short turns (< 15 characters, e.g. "ok", "thanks", "yes", "hello").
    - Synthetic client / transport runtime context envelopes (e.g. OpenClaw metadata).
    - Common boilerplate conversational filler or confirmations.
    """
    text = content.strip()
    if len(text) < 15:
        return False

    if is_synthetic_context(text):
        return False

    normalized = text.lower().rstrip(".!?,")
    low_signal_filler = {
        "thank you very much",
        "thanks a lot",
        "thanks for the help",
        "ok sounds good",
        "sounds good to me",
        "good morning to you",
        "have a great day",
        "have a nice day",
        "i appreciate it",
        "no problem at all",
        "you are welcome",
        "you're welcome",
        "see you later",
        "bye for now",
    }
    if normalized in low_signal_filler:
        return False

    return True


def format_relevant_context(matches: list[VectorMatch]) -> str:
    """Format semantic vector matches into an XML context block for prompt injection."""
    if not matches:
        return ""
    lines = ["<relevant_past_context>", "Relevant discussions and facts recalled from past conversations:"]
    for m in matches:
        date_str = m.created_at.split()[0] if m.created_at else "past session"
        lines.append(f'- [{m.role.capitalize()} on {date_str}]: "{m.content.strip()}"')
    lines.append("</relevant_past_context>")
    return "\n".join(lines)


class EpisodicStore:
    """Local SQLite-backed episodic store for conversation turns, staged candidate memories, and vector recall."""

    def __init__(self, db_path: Optional[str | Path] = None, embedding_dim: int = 768):
        if db_path is None:
            data_dir = Path(os.environ.get("RIVA_DATA_DIR", Path.home() / ".riva"))
            data_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(data_dir / "memory.db")
        else:
            self.db_path = str(db_path)
            if self.db_path != ":memory:":
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self.embedding_dim = int(os.environ.get("RIVA_EMBEDDING_DIMENSION", embedding_dim))
        self._vec_enabled = False
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.create_function("should_index_turn", 1, should_index_turn)
        if self.db_path != ":memory:":
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")

        if sqlite_vec is not None:
            try:
                conn.enable_load_extension(True)
                sqlite_vec.load(conn)
                conn.enable_load_extension(False)
                self._vec_enabled = True
            except Exception as e:
                logger.warning("Could not load sqlite-vec extension: %s", e)
                self._vec_enabled = False
        else:
            self._vec_enabled = False

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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, id);")
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS turn_embeddings (
                    turn_id INTEGER PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(turn_id) REFERENCES turns(id) ON DELETE CASCADE
                );
                """
            )

            if self._vec_enabled:
                conn.execute(
                    f"""
                    CREATE VIRTUAL TABLE IF NOT EXISTS vec_turns USING vec0(
                        turn_id INTEGER PRIMARY KEY,
                        embedding float[{self.embedding_dim}] distance_metric=cosine
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS trg_turns_delete_embeddings
                    AFTER DELETE ON turns
                    BEGIN
                        DELETE FROM turn_embeddings WHERE turn_id = OLD.id;
                        DELETE FROM vec_turns WHERE turn_id = OLD.id;
                    END;
                    """
                )

            conn.commit()

    def log_turn(self, session_id: str, role: str, content: str) -> int:
        """Log a conversation turn to episodic history. Returns the new turn ID."""
        clean_content = content.strip()
        if not clean_content or is_synthetic_context(clean_content):
            return 0
        with self._get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO turns (session_id, role, content) VALUES (?, ?, ?);",
                (session_id.strip(), role.strip(), clean_content),
            )
            conn.commit()
            return cur.lastrowid or 0

    def get_turn(self, turn_id: int) -> Optional[Turn]:
        """Fetch a single conversation turn by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, session_id, role, content, created_at FROM turns WHERE id = ?;",
                (turn_id,),
            ).fetchone()
            if not row:
                return None
            return Turn(
                id=row["id"],
                session_id=row["session_id"],
                role=row["role"],
                content=row["content"],
                created_at=str(row["created_at"]),
            )

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

    def list_turns(self, limit: int = 10) -> list[Turn]:
        """Fetch recent turns across all sessions in reverse chronological order."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, role, content, created_at
                FROM turns
                ORDER BY id DESC
                LIMIT ?;
                """,
                (limit,),
            ).fetchall()

            return [
                Turn(
                    id=r["id"],
                    session_id=r["session_id"],
                    role=r["role"],
                    content=r["content"],
                    created_at=str(r["created_at"]),
                )
                for r in rows
            ]

    def list_sessions(self, limit: int = 20) -> list[SessionSummary]:
        """List recent conversation sessions with turn counts and last activity timestamps."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT session_id, count(*) as turn_count, max(created_at) as last_turn
                FROM turns
                GROUP BY session_id
                ORDER BY last_turn DESC
                LIMIT ?;
                """,
                (limit,),
            ).fetchall()

            return [
                SessionSummary(
                    session_id=r["session_id"],
                    turn_count=r["turn_count"],
                    last_turn=str(r["last_turn"]),
                )
                for r in rows
            ]

    def delete_turn(self, turn_id: int) -> bool:
        """Delete an episodic turn record by ID. Vector embeddings are cascaded via SQL trigger."""
        with self._get_connection() as conn:
            cur = conn.execute("DELETE FROM turns WHERE id = ?;", (turn_id,))
            conn.commit()
            return cur.rowcount > 0

    def add_embedding(
        self,
        turn_id: int,
        vector: list[float],
        session_id: str,
        content: str = "",
    ) -> None:
        """Store or update vector embedding for a conversation turn."""
        if not self._vec_enabled or sqlite_vec is None:
            raise RuntimeError("sqlite-vec is not enabled or available")
        if content and is_synthetic_context(content):
            return
        if len(vector) != self.embedding_dim:
            raise ValueError(f"Vector dimension {len(vector)} does not match store dimension {self.embedding_dim}")

        serialized = sqlite_vec.serialize_float32(vector)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest() if content else ""

        with self._get_connection() as conn:
            # vec0 requires delete before insert on existing PK
            conn.execute("DELETE FROM vec_turns WHERE turn_id = ?;", (turn_id,))
            conn.execute(
                "INSERT INTO vec_turns(turn_id, embedding) VALUES (?, ?);",
                (turn_id, serialized),
            )
            conn.execute(
                """
                INSERT INTO turn_embeddings (turn_id, session_id, content_hash)
                VALUES (?, ?, ?)
                ON CONFLICT(turn_id) DO UPDATE SET
                    session_id = excluded.session_id,
                    content_hash = excluded.content_hash,
                    created_at = CURRENT_TIMESTAMP;
                """,
                (turn_id, session_id.strip(), content_hash),
            )
            conn.commit()

    def search_similar(
        self,
        query_vector: list[float],
        top_k: int = 5,
        distance_threshold: float = 0.5,
        exclude_session_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> list[VectorMatch]:
        """Search for conversation turns semantically similar to query_vector."""
        if not self._vec_enabled or sqlite_vec is None:
            return []
        if len(query_vector) != self.embedding_dim:
            raise ValueError(
                f"Query vector dimension {len(query_vector)} does not match store dimension {self.embedding_dim}"
            )

        serialized = sqlite_vec.serialize_float32(query_vector)
        with self._get_connection() as conn:
            query = """
                SELECT t.id, t.session_id, t.role, t.content, t.created_at, v.distance
                FROM vec_turns v
                JOIN turns t ON v.turn_id = t.id
                WHERE v.embedding MATCH ? AND v.k = ? AND v.distance <= ?
            """
            params: list[Any] = [serialized, max(1, top_k), distance_threshold]
            if exclude_session_id:
                query += " AND t.session_id != ?"
                params.append(exclude_session_id.strip())
            if session_id:
                query += " AND t.session_id = ?"
                params.append(session_id.strip())
            query += " ORDER BY v.distance ASC;"

            rows = conn.execute(query, tuple(params)).fetchall()
            return [
                VectorMatch(
                    turn_id=r["id"],
                    session_id=r["session_id"],
                    role=r["role"],
                    content=r["content"],
                    distance=float(r["distance"]),
                    created_at=str(r["created_at"]),
                )
                for r in rows
            ]

    def format_relevant_context(self, matches: list[VectorMatch]) -> str:
        """Format semantic vector matches into an XML context block for prompt injection."""
        return format_relevant_context(matches)

    def delete_embedding(self, turn_id: int) -> bool:
        """Permanently delete a vector embedding without deleting the turn itself."""
        with self._get_connection() as conn:
            if self._vec_enabled:
                try:
                    conn.execute("DELETE FROM vec_turns WHERE turn_id = ?;", (turn_id,))
                except Exception as e:
                    logger.debug("Failed deleting from vec_turns: %s", e)
            cur = conn.execute("DELETE FROM turn_embeddings WHERE turn_id = ?;", (turn_id,))
            conn.commit()
            return cur.rowcount > 0

    def clear_embeddings(self) -> int:
        """Purge all vector embeddings and metadata from the episodic store."""
        with self._get_connection() as conn:
            if self._vec_enabled:
                try:
                    conn.execute("DELETE FROM vec_turns;")
                except Exception as e:
                    logger.debug("Failed deleting all from vec_turns: %s", e)
            cur = conn.execute("DELETE FROM turn_embeddings;")
            conn.commit()
            return cur.rowcount

    def has_embedding(self, turn_id: int) -> bool:
        """Check if a turn currently has a vector embedding."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT 1 FROM turn_embeddings WHERE turn_id = ?;", (turn_id,)).fetchone()
            return row is not None

    def get_unindexed_turns(self, limit: int = 100) -> list[Turn]:
        """Fetch conversation turns that have not yet been vector embedded."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT t.id, t.session_id, t.role, t.content, t.created_at
                FROM turns t
                LEFT JOIN turn_embeddings e ON t.id = e.turn_id
                WHERE e.turn_id IS NULL AND should_index_turn(t.content)
                ORDER BY t.id ASC
                LIMIT ?;
                """,
                (limit,),
            ).fetchall()
            return [
                Turn(
                    id=r["id"],
                    session_id=r["session_id"],
                    role=r["role"],
                    content=r["content"],
                    created_at=str(r["created_at"]),
                )
                for r in rows
            ]

    def add_pending(self, fact: str, source_snippet: str) -> int:
        """Stage a proposed candidate memory fact for human review. Returns the pending record ID."""
        clean_fact = fact.strip()
        clean_source = source_snippet.strip()
        if not clean_fact or is_synthetic_context(clean_fact) or is_synthetic_context(clean_source):
            return 0
        with self._get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO pending_memories (fact, source_snippet, status) VALUES (?, ?, 'pending');",
                (clean_fact, clean_source),
            )
            conn.commit()
            return cur.lastrowid or 0

    def list_pending(self, status: str = "pending") -> list[PendingMemory]:
        """List candidate memories filtered by status (default: 'pending')."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT id, fact, source_snippet, status, created_at "
                "FROM pending_memories WHERE status = ? ORDER BY id ASC;",
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

    def get_stats(self) -> dict:
        """Return telemetry about the episodic store and vector index."""
        stats = {
            "file_size": 0,
            "wal_size": 0,
            "shm_size": 0,
            "turns": 0,
            "pending": 0,
            "embeddings": 0,
            "embedding_dim": self.embedding_dim,
            "vec_enabled": self._vec_enabled,
        }
        db_path = Path(self.db_path)
        if db_path.exists():
            stats["file_size"] = db_path.stat().st_size

        wal_path = Path(f"{self.db_path}-wal")
        shm_path = Path(f"{self.db_path}-shm")
        if wal_path.exists():
            stats["wal_size"] = wal_path.stat().st_size
        if shm_path.exists():
            stats["shm_size"] = shm_path.stat().st_size

        with self._get_connection() as conn:
            stats["turns"] = conn.execute("SELECT count(*) FROM turns;").fetchone()[0]
            stats["pending"] = conn.execute("SELECT count(*) FROM pending_memories;").fetchone()[0]
            stats["embeddings"] = conn.execute("SELECT count(*) FROM turn_embeddings;").fetchone()[0]

        stats["vector_count"] = stats["embeddings"]
        stats["vector_bytes"] = stats["embeddings"] * self.embedding_dim * 4

        return stats

    def vacuum(self) -> None:
        """Compact the database and truncate the WAL file."""
        with self._get_connection() as conn:
            conn.execute("VACUUM;")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")

    def backup(self, backup_path: Path | str) -> None:
        """Create an online snapshot using VACUUM INTO."""
        backup_path = Path(backup_path)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            conn.execute("VACUUM INTO ?;", (str(backup_path),))

    def prune(self, turns_days: int = 30, pending_days: int = 7, dry_run: bool = False) -> dict:
        """Prune old conversation turns, expired pending memories, and orphaned embeddings."""
        results = {"turns_deleted": 0, "pending_deleted": 0}

        with self._get_connection() as conn:
            # Turn pruning
            turns_query = "SELECT count(*) FROM turns WHERE created_at < datetime('now', ?);"
            turns_val = f"-{turns_days} days"
            results["turns_deleted"] = conn.execute(turns_query, (turns_val,)).fetchone()[0]

            # Pending pruning
            pending_query = "SELECT count(*) FROM pending_memories WHERE created_at < datetime('now', ?);"
            pending_val = f"-{pending_days} days"
            results["pending_deleted"] = conn.execute(pending_query, (pending_val,)).fetchone()[0]

            if not dry_run:
                # Associated vector embeddings and metadata are cascaded by SQL trigger
                conn.execute("DELETE FROM turns WHERE created_at < datetime('now', ?);", (turns_val,))
                conn.execute("DELETE FROM pending_memories WHERE created_at < datetime('now', ?);", (pending_val,))
                conn.commit()

        return results


_episodic_store: Optional[EpisodicStore] = None


def get_episodic_store(db_path: Optional[str | Path] = None, embedding_dim: int = 768) -> EpisodicStore:
    """Get or lazily instantiate singleton EpisodicStore instance."""
    global _episodic_store
    if _episodic_store is None or db_path is not None:
        store = EpisodicStore(db_path, embedding_dim=embedding_dim)
        if db_path is None:
            _episodic_store = store
        return store
    return _episodic_store
