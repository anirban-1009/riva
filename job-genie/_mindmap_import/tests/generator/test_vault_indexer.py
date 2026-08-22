from unittest.mock import MagicMock

import pytest

from src.core.database import DatabaseManager
from src.generator.vault_indexer import VaultIndexer


class TestVaultIndexer:
    @pytest.fixture
    def config(self, tmp_path):
        return {
            "obsidian": {
                "vault_path": str(tmp_path),
                "folders": {"jobs": "Jobs", "people": "People", "companies": "Companies"},
            }
        }

    @pytest.fixture
    def db(self, tmp_path):
        return DatabaseManager(db_path=str(tmp_path / "test_jobs.db"))

    def write_note(self, tmp_path, relative_path: str, content: str):
        file_path = tmp_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def test_reindex_all_indexes_every_file(self, config, db, tmp_path):
        self.write_note(tmp_path, "Jobs/acme.md", "# Backend Engineer - Acme\nKubernetes experience required.")
        self.write_note(tmp_path, "People/jane.md", "# Jane Doe\nWorks at Acme.")

        indexer = VaultIndexer(config, db)
        updated = indexer.reindex_all()

        assert updated == 2
        results = indexer.search_text("kubernetes")
        assert len(results) == 1
        assert results[0]["category"] == "Jobs"

    def test_title_extracted_from_first_heading(self, config, db, tmp_path):
        self.write_note(tmp_path, "Jobs/acme.md", "# Backend Engineer - Acme\nBody text.")
        indexer = VaultIndexer(config, db)
        indexer.reindex_all()

        results = indexer.search_text("body")
        assert results[0]["title"] == "Backend Engineer - Acme"

    def test_title_falls_back_to_filename_without_heading(self, config, db, tmp_path):
        self.write_note(tmp_path, "Jobs/no_heading.md", "Just some content, no heading.")
        indexer = VaultIndexer(config, db)
        indexer.reindex_all()

        results = indexer.search_text("content")
        assert results[0]["title"] == "no_heading"

    def test_category_falls_back_to_notes_for_unmapped_folder(self, config, db, tmp_path):
        self.write_note(tmp_path, "Clippings/article.md", "Some clipped article content.")
        indexer = VaultIndexer(config, db)
        indexer.reindex_all()

        results = indexer.search_text("clipped")
        assert results[0]["category"] == "Notes"

    def test_reindex_changed_skips_unchanged_files(self, config, db, tmp_path):
        self.write_note(tmp_path, "Jobs/acme.md", "# Acme\nContent.")
        indexer = VaultIndexer(config, db)
        indexer.reindex_all()

        # Nothing on disk changed, so a second pass should find no work to do.
        updated = indexer.reindex_changed()
        assert updated == 0

    def test_reindex_changed_reindexes_modified_files(self, config, db, tmp_path):
        path = self.write_note(tmp_path, "Jobs/acme.md", "# Acme\nOriginal content.")
        indexer = VaultIndexer(config, db)
        indexer.reindex_all()

        # Bump mtime so the file looks modified regardless of filesystem timestamp resolution.
        new_content = "# Acme\nUpdated content."
        path.write_text(new_content, encoding="utf-8")
        import os

        os.utime(path, (path.stat().st_atime, path.stat().st_mtime + 10))

        updated = indexer.reindex_changed()
        assert updated == 1
        assert indexer.search_text("updated") != []
        assert indexer.search_text("original") == []

    def test_reindex_removes_deleted_files(self, config, db, tmp_path):
        path = self.write_note(tmp_path, "Jobs/acme.md", "# Acme\nContent.")
        indexer = VaultIndexer(config, db)
        indexer.reindex_all()

        path.unlink()
        indexer.reindex_changed()

        assert indexer.search_text("content") == []
        assert db.get_vault_index_status() == {}

    def test_reindex_missing_vault_path_returns_zero(self, db, tmp_path):
        config = {"obsidian": {"vault_path": str(tmp_path / "does_not_exist"), "folders": {}}}
        indexer = VaultIndexer(config, db)
        assert indexer.reindex_all() == 0

    def test_reindex_without_llm_client_does_not_embed(self, config, db, tmp_path):
        self.write_note(tmp_path, "Jobs/acme.md", "# Acme\nContent.")
        indexer = VaultIndexer(config, db, llm_client=None)
        indexer.reindex_all()

        status = db.get_vault_index_status()
        assert status["Jobs/acme.md"]["embedded_mtime"] is None

    def test_reindex_with_llm_client_embeds_documents(self, config, db, tmp_path):
        if not db.vector_search_enabled:
            pytest.skip("sqlite-vec extension not available")

        self.write_note(tmp_path, "Jobs/acme.md", "# Acme\nContent.")
        mock_llm = MagicMock()
        mock_llm.embed.return_value = [1.0] + [0.0] * (db.embedding_dim - 1)

        indexer = VaultIndexer(config, db, llm_client=mock_llm)
        indexer.reindex_all()

        mock_llm.embed.assert_called_once()
        status = db.get_vault_index_status()
        assert status["Jobs/acme.md"]["embedded_mtime"] is not None

    def test_search_semantic_without_llm_client_returns_empty(self, config, db):
        indexer = VaultIndexer(config, db, llm_client=None)
        assert indexer.search_semantic("query") == []

    def test_search_semantic_embeds_query_and_delegates_to_db(self, config, db):
        mock_llm = MagicMock()
        query_embedding = [0.1, 0.2]
        mock_llm.embed.return_value = query_embedding

        indexer = VaultIndexer(config, db, llm_client=mock_llm)
        db.search_vault_semantic = MagicMock(return_value=[{"path": "Jobs/a.md"}])

        results = indexer.search_semantic("kubernetes roles", limit=5)

        mock_llm.embed.assert_called_once_with("kubernetes roles")
        db.search_vault_semantic.assert_called_once_with(query_embedding, limit=5)
        assert results == [{"path": "Jobs/a.md"}]

    def test_search_semantic_handles_failed_embedding(self, config, db):
        mock_llm = MagicMock()
        mock_llm.embed.return_value = []

        indexer = VaultIndexer(config, db, llm_client=mock_llm)
        assert indexer.search_semantic("query") == []
