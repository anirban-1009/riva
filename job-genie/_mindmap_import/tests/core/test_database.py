import pytest

from src.core.database import DatabaseManager


class TestDatabaseManager:
    @pytest.fixture
    def db(self, tmp_path):
        # Use a temporary file for testing
        db_file = tmp_path / "test_jobs.db"
        return DatabaseManager(db_path=str(db_file))

    def test_init_db(self, db):
        """Verify fallback tables are created."""
        with db._get_connection() as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            assert "jobs" in tables
            assert "requests" in tables

    def test_save_and_get_job(self, db):
        """Test saving and retrieving a job."""
        job_data = {
            "id": "job123",
            "title": "AI Engineer",
            "company": "DeepMind",
            "location": "London",
            "description": "Building AGi",
            "status": "new",
        }
        db.save_job(job_data)

        retrieved = db.get_job("job123")
        assert retrieved is not None
        assert retrieved["title"] == "AI Engineer"
        assert retrieved["company"] == "DeepMind"

    def test_job_exists(self, db):
        """Test job_exists method."""
        job_data = {"id": "exists123", "title": "Test"}
        db.save_job(job_data)

        assert db.job_exists("exists123") is True
        assert db.job_exists("missing123") is False

    def test_get_all_jobs(self, db):
        """Test retrieving multiple jobs."""
        db.save_job({"id": "j1", "title": "Job 1"})
        db.save_job({"id": "j2", "title": "Job 2"})

        jobs = db.get_all_jobs()
        assert len(jobs) == 2
        ids = [j["id"] for j in jobs]
        assert "j1" in ids
        assert "j2" in ids

    def test_save_and_get_request(self, db):
        """Test referral request storage."""
        db.save_job({"id": "ref123", "title": "Referral Job"})
        db.save_request(
            job_id="ref123",
            connection_name="John Doe",
            profile_url="http://linkedin/john",
            message="Hi John, can you refer me?",
        )

        requests = db.get_requests_for_job("ref123")
        assert len(requests) == 1
        assert requests[0]["connection_name"] == "John Doe"
        assert requests[0]["message_content"] == "Hi John, can you refer me?"

    def test_get_jobs_by_status(self, db):
        """Test filtering jobs by status."""
        db.save_job({"id": "s1", "title": "Job 1", "status": "new"})
        db.save_job({"id": "s2", "title": "Job 2", "status": "applied"})

        new_jobs = db.get_jobs_by_status("new")
        assert len(new_jobs) == 1
        assert new_jobs[0]["id"] == "s1"

        applied_jobs = db.get_jobs_by_status("applied")
        assert len(applied_jobs) == 1
        assert applied_jobs[0]["id"] == "s2"

    def test_get_all_requests(self, db):
        """Test retrieving all referral requests."""
        db.save_job({"id": "r1", "title": "Job 1"})
        db.save_job({"id": "r2", "title": "Job 2"})
        db.save_request("r1", "Alice", "url1", "msg1")
        db.save_request("r2", "Bob", "url2", "msg2")

        all_reqs = db.get_all_requests()
        assert len(all_reqs) == 2

    def test_save_analysis(self, db):
        """Test updating job with analysis results."""
        db.save_job({"id": "a1", "title": "Job 1"})
        db.save_analysis("a1", 85, '{"reason": "good"}')

        job = db.get_job("a1")
        assert job["relevance_score"] == 85
        assert job["analysis_data"] == '{"reason": "good"}'

    def test_update_job_status(self, db):
        """Test updating job status."""
        db.save_job({"id": "status1", "title": "Job 1", "status": "new"})
        db.update_job_status("status1", "interviewing")

        job = db.get_job("status1")
        assert job["status"] == "interviewing"

    def test_update_job_status_stamps_applied_at(self, db):
        """Marking a job applied should record when, and reverting should clear it."""
        db.save_job({"id": "applied1", "title": "Job 1", "status": "new"})
        assert db.get_job("applied1")["applied_at"] is None

        db.update_job_status("applied1", "applied")
        job = db.get_job("applied1")
        assert job["status"] == "applied"
        assert job["applied_at"] is not None

        db.update_job_status("applied1", "to_apply")
        assert db.get_job("applied1")["applied_at"] is None

    def test_get_all_analyses(self, db):
        """Test retrieving jobs with analysis data."""
        db.save_job({"id": "an1", "title": "Job 1"})
        db.save_job({"id": "an2", "title": "Job 2"})
        db.save_analysis("an1", 90, '{"data": 1}')

        analyses = db.get_all_analyses(min_score=80)
        assert len(analyses) == 1
        assert analyses[0]["id"] == "an1"

        none = db.get_all_analyses(min_score=95)
        assert len(none) == 0

    def test_delete_job(self, db):
        """Test deleting a job and its associated requests."""
        db.save_job({"id": "del1", "title": "Job 1"})
        db.save_request("del1", "Alice", "url", "msg")

        db.delete_job("del1")

        assert db.get_job("del1") is None
        assert len(db.get_requests_for_job("del1")) == 0

    def test_vault_index_status_empty_initially(self, db):
        """No status should be tracked before anything is indexed."""
        assert db.get_vault_index_status() == {}

    def test_upsert_and_search_vault_text(self, db):
        """Indexed documents should be findable via BM25 full-text search."""
        db.upsert_vault_document(
            path="Jobs/Acme.md",
            category="Jobs",
            title="Senior Backend Engineer - Acme",
            content="Looking for strong Kubernetes and distributed systems experience.",
            mtime=100.0,
        )

        results = db.search_vault_text("kubernetes")
        assert len(results) == 1
        assert results[0]["path"] == "Jobs/Acme.md"
        assert results[0]["category"] == "Jobs"
        assert "Kubernetes" in results[0]["snippet"]

        assert db.search_vault_text("nonexistentterm") == []

    def test_upsert_vault_document_updates_status(self, db):
        """Upserting should record the file's mtime for later change detection."""
        db.upsert_vault_document("Jobs/A.md", "Jobs", "A", "content", mtime=100.0)

        status = db.get_vault_index_status()
        assert status["Jobs/A.md"]["mtime"] == 100.0
        assert status["Jobs/A.md"]["embedded_mtime"] is None

    def test_upsert_vault_document_replaces_prior_text(self, db):
        """Re-upserting the same path should replace, not duplicate, the indexed content."""
        db.upsert_vault_document("Jobs/A.md", "Jobs", "A", "original kubernetes content", mtime=100.0)
        db.upsert_vault_document("Jobs/A.md", "Jobs", "A", "updated rust content", mtime=200.0)

        assert db.search_vault_text("kubernetes") == []
        results = db.search_vault_text("rust")
        assert len(results) == 1
        assert db.get_vault_index_status()["Jobs/A.md"]["mtime"] == 200.0

    def test_delete_vault_document(self, db):
        """Deleting a document should remove it from the text index and status tracking."""
        db.upsert_vault_document("Jobs/A.md", "Jobs", "A", "kubernetes content", mtime=100.0)
        db.delete_vault_document("Jobs/A.md")

        assert db.search_vault_text("kubernetes") == []
        assert db.get_vault_index_status() == {}

    def test_upsert_and_search_vault_semantic(self, db):
        """Documents indexed with an embedding should be retrievable via KNN search."""
        if not db.vector_search_enabled:
            pytest.skip("sqlite-vec extension not available")

        embedding_dim = db.embedding_dim
        doc_embedding = [1.0] + [0.0] * (embedding_dim - 1)
        db.upsert_vault_document("Jobs/A.md", "Jobs", "Job A", "content", mtime=100.0, embedding=doc_embedding)

        results = db.search_vault_semantic(doc_embedding, limit=5)
        assert len(results) == 1
        assert results[0]["path"] == "Jobs/A.md"
        assert results[0]["title"] == "Job A"
        assert results[0]["distance"] == pytest.approx(0.0)

        status = db.get_vault_index_status()
        assert status["Jobs/A.md"]["embedded_mtime"] == 100.0

    def test_text_only_reindex_preserves_embedded_mtime(self, db):
        """A text-only re-upsert (no embedding) must not erase a prior embedded_mtime.

        Otherwise a keyword-only reindex would make an already-embedded file look
        unembedded, forcing (and re-billing) an unnecessary re-embed later.
        """
        if not db.vector_search_enabled:
            pytest.skip("sqlite-vec extension not available")

        embedding_dim = db.embedding_dim
        doc_embedding = [1.0] + [0.0] * (embedding_dim - 1)
        db.upsert_vault_document("Jobs/A.md", "Jobs", "A", "content v1", mtime=100.0, embedding=doc_embedding)

        # Text changed (e.g. status tag edit) but re-indexed without an embedding.
        db.upsert_vault_document("Jobs/A.md", "Jobs", "A", "content v2", mtime=200.0, embedding=None)

        status = db.get_vault_index_status()
        assert status["Jobs/A.md"]["mtime"] == 200.0
        assert status["Jobs/A.md"]["embedded_mtime"] == 100.0

    def test_delete_vault_document_removes_embedding(self, db):
        """Deleting a document should also drop its vector entry, not just the text index."""
        if not db.vector_search_enabled:
            pytest.skip("sqlite-vec extension not available")

        embedding_dim = db.embedding_dim
        doc_embedding = [1.0] + [0.0] * (embedding_dim - 1)
        db.upsert_vault_document("Jobs/A.md", "Jobs", "A", "content", mtime=100.0, embedding=doc_embedding)
        db.delete_vault_document("Jobs/A.md")

        assert db.search_vault_semantic(doc_embedding, limit=5) == []
