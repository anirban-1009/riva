import pathlib
from typing import Any

import yaml

from job_genie.core.ai.base import LLMClient
from job_genie.core.database import DatabaseManager
from job_genie.utils.logger import get_logger

logger = get_logger(__name__)

MAX_EMBED_CHARS = 8000


class VaultIndexer:
    """Keeps the vault_index / vault_vectors search tables in sync with the Obsidian vault's .md files."""

    def __init__(self, config: dict[str, Any], db: DatabaseManager, llm_client: LLMClient | None = None):
        obsidian_cfg = config.get("obsidian", {})
        self.vault_path = pathlib.Path(obsidian_cfg.get("vault_path", "./output"))
        self.db = db
        self.llm_client = llm_client

        # Map each configured subfolder name back to its category key, e.g. "Jobs" -> "jobs".
        self._folder_categories = {name: key for key, name in obsidian_cfg.get("folders", {}).items()}

    def reindex_all(self) -> int:
        """Re-indexes (and, if an LLM client is set, re-embeds) every file in the vault."""
        return self._reindex(force=True)

    def reindex_changed(self) -> int:
        """
        Indexes files that are new or changed since the last text index, and separately
        embeds any file whose content has changed since it was last embedded. These are
        tracked independently: a sync can refresh text search without paying for embedding
        calls, and a later semantic search will still pick up embeddings for those files.
        """
        return self._reindex(force=False)

    def _reindex(self, force: bool) -> int:
        if not self.vault_path.exists():
            logger.warning(f"Vault path not found: {self.vault_path}")
            return 0

        want_embeddings = self.llm_client is not None
        status = self.db.get_vault_index_status()
        seen_paths = set()
        updated = 0

        for file_path in self.vault_path.rglob("*.md"):
            path_str = str(file_path.relative_to(self.vault_path))
            seen_paths.add(path_str)
            mtime = file_path.stat().st_mtime
            prior = status.get(path_str)

            text_stale = force or prior is None or prior["mtime"] != mtime
            embed_stale = want_embeddings and (force or prior is None or prior["embedded_mtime"] != mtime)

            if not text_stale and not embed_stale:
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Could not read {file_path} for indexing: {e}")
                continue

            title = self._extract_title(content, file_path)
            category = self._category_for(file_path)
            embedding = self._embed(content) if embed_stale else None

            self.db.upsert_vault_document(path_str, category, title, content, mtime, embedding=embedding)
            updated += 1

        stale = set(status.keys()) - seen_paths
        for path_str in stale:
            self.db.delete_vault_document(path_str)

        if updated or stale:
            logger.info(f"Vault index: {updated} updated, {len(stale)} removed.")
        return updated

    def _embed(self, content: str) -> list[float] | None:
        if not self.llm_client:
            return None
        try:
            embedding = self.llm_client.embed(content[:MAX_EMBED_CHARS])
            return embedding or None
        except Exception as e:
            logger.warning(f"Failed to embed vault document: {e}")
            return None

    def _extract_title(self, content: str, file_path: pathlib.Path) -> str:
        if content.startswith("---"):
            end = content.find("\n---", 3)
            if end != -1:
                try:
                    frontmatter = yaml.safe_load(content[3:end])
                except yaml.YAMLError:
                    frontmatter = None
                if isinstance(frontmatter, dict) and frontmatter.get("title"):
                    return str(frontmatter["title"])

        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
        return file_path.stem

    def _category_for(self, file_path: pathlib.Path) -> str:
        relative_parts = file_path.relative_to(self.vault_path).parts
        if relative_parts and relative_parts[0] in self._folder_categories:
            return self._folder_categories[relative_parts[0]].capitalize()
        return "Notes"

    def search_text(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Keyword/full-text search over the vault, ranked by BM25."""
        return self.db.search_vault_text(query, limit=limit)

    def search_semantic(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Embedding-based similarity search over the vault."""
        if not self.llm_client:
            logger.warning("Semantic search requires an LLM client for embeddings.")
            return []
        embedding = self.llm_client.embed(query)
        if not embedding:
            logger.warning("Failed to embed query; semantic search unavailable.")
            return []
        return self.db.search_vault_semantic(embedding, limit=limit)
