import json
from unittest.mock import MagicMock, patch

import pytest

from src.core.relevance_scorer import ScoringResult
from src.generator.sync_service import SyncService
from src.ingest.job_details_extractor import JobDetails


class TestSyncService:
    @pytest.fixture
    def mock_config(self):
        return {"obsidian": {"vault_path": "/tmp/vault", "folders": {"jobs": "Jobs", "companies": "Companies"}}}

    @pytest.fixture
    def sync_service(self, mock_config):
        with (
            patch("src.generator.sync_service.VaultManager"),
            patch("src.generator.sync_service.TemplateManager"),
            patch("src.generator.sync_service.DashboardGenerator"),
            patch("src.generator.sync_service.JobDetailsExtractor"),
        ):
            return SyncService(mock_config)

    def test_determine_specialization_ai_ml(self):
        job = JobDetails(
            id="1",
            title="Senior Machine Learning Engineer (AI/NLP)",
            company="A",
            location="B",
            description="C",
            posted_date="D",
            seniority_level="E",
            employment_type="F",
            job_function="G",
            industries="H",
            link="I",
        )
        assert job.determine_specialization() == "AI_ML"

        job.title = "LLM Researcher"
        assert job.determine_specialization() == "AI_ML"

    def test_determine_specialization_python(self):
        job = JobDetails(
            id="1",
            title="Django Backend Developer",
            company="A",
            location="B",
            description="C",
            posted_date="D",
            seniority_level="E",
            employment_type="F",
            job_function="G",
            industries="H",
            link="I",
        )
        assert job.determine_specialization() == "Python_Dev"

    def test_determine_specialization_backend(self):
        job = JobDetails(
            id="1",
            title="Platform Engineer (API)",
            company="A",
            location="B",
            description="C",
            posted_date="D",
            seniority_level="E",
            employment_type="F",
            job_function="G",
            industries="H",
            link="I",
        )
        assert job.determine_specialization() == "Backend"

    def test_determine_specialization_frontend(self):
        job = JobDetails(
            id="1",
            title="React Web Developer",
            company="A",
            location="B",
            description="C",
            posted_date="D",
            seniority_level="E",
            employment_type="F",
            job_function="G",
            industries="H",
            link="I",
        )
        assert job.determine_specialization() == "Frontend"

    def test_determine_specialization_devops(self):
        job = JobDetails(
            id="1",
            title="Kubernetes Infrastructure Specialist",
            company="A",
            location="B",
            description="C",
            posted_date="D",
            seniority_level="E",
            employment_type="F",
            job_function="G",
            industries="H",
            link="I",
        )
        assert job.determine_specialization() == "DevOps_Cloud"

    def test_determine_specialization_fullstack(self):
        job = JobDetails(
            id="1",
            title="Full Stack Engineer",
            company="A",
            location="B",
            description="C",
            posted_date="D",
            seniority_level="E",
            employment_type="F",
            job_function="G",
            industries="H",
            link="I",
        )
        assert job.determine_specialization() == "FullStack"

    def test_determine_specialization_general(self):
        job = JobDetails(
            id="1",
            title="Software Manager",
            company="A",
            location="B",
            description="C",
            posted_date="D",
            seniority_level="E",
            employment_type="F",
            job_function="G",
            industries="H",
            link="I",
        )
        assert job.determine_specialization() == "General"

    def test_load_analysis_success(self, sync_service):
        mock_job_data = {
            "id": "123",
            "analysis_data": json.dumps(
                {"score": 85, "reasoning": "Test", "matching_skills": ["Python"], "missing_skills": []}
            ),
        }
        result = sync_service._load_analysis(mock_job_data)
        assert result.score == 85
        assert result.matching_skills == ["Python"]

    def test_load_analysis_not_found(self, sync_service):
        mock_job_data = {"id": "123", "analysis_data": None}
        result = sync_service._load_analysis(mock_job_data)
        assert result.score == 0
        assert "not been scored" in result.reasoning

    def test_sync_success(self, sync_service):
        sync_service._sync_all = MagicMock()
        sync_service.sync()
        sync_service.vault_manager.ensure_folders_exist.assert_called_once()
        sync_service._sync_all.assert_called_once()
        sync_service.dashboard_generator.generate.assert_called_once_with(sync_service.extractor.db)

    def test_sync_pulls_obsidian_edits_before_regenerating_notes(self, sync_service):
        """A checkbox ticked in Obsidian must reach the DB before notes are regenerated,
        or the very same sync would immediately overwrite it back to the old DB value."""
        call_order = []
        sync_service.sync_from_obsidian = MagicMock(side_effect=lambda: call_order.append("sync_from_obsidian"))
        sync_service._sync_all = MagicMock(side_effect=lambda: call_order.append("_sync_all"))

        sync_service.sync()

        sync_service.sync_from_obsidian.assert_called_once()
        assert call_order == ["sync_from_obsidian", "_sync_all"]

    def test_sync_all(self, sync_service):
        # Mock database to return some job rows
        mock_db = MagicMock()
        sync_service.extractor.db = mock_db
        sync_service.extractor.db.get_all_jobs.return_value = [{"id": "123", "analysis_data": None}]

        # Mock extractor to return a job
        mock_job = MagicMock(spec=JobDetails)
        mock_job.id = "123"
        mock_job.title = "SDE"
        mock_job.company = "TestCo"
        mock_job.description = "Test Description"
        sync_service.extractor.get_cached_job.return_value = mock_job

        # Mock NetworkGraphBuilder
        with patch("src.generator.sync_service.NetworkGraphBuilder") as mock_builder_class:
            mock_builder = mock_builder_class.return_value
            mock_person = MagicMock()
            mock_person.full_name = "John Doe"
            mock_person.company = "TestCo"
            mock_person.position = "Manager"
            mock_builder.connections = [mock_person]

            # Mock template manager return values
            sync_service.template_manager.render_person.return_value = "person content"
            sync_service.template_manager.render_job.return_value = "job content"
            sync_service.template_manager.render_company.return_value = "company content"

            sync_service._sync_all()

        # Check if files were written
        from unittest.mock import ANY

        sync_service.vault_manager.write_file.assert_any_call("person content", "John Doe.md", "people")
        sync_service.vault_manager.write_file.assert_any_call("job content", "SDE - TestCo.md", "jobs", subfolder=ANY)
        sync_service.vault_manager.write_file.assert_any_call("company content", "TestCo.md", "companies")

    def test_sync_all_passes_applied_at_from_db(self, sync_service):
        """The DB's applied_at should flow through to the rendered job note."""
        mock_db = MagicMock()
        sync_service.extractor.db = mock_db
        sync_service.extractor.db.get_all_jobs.return_value = [
            {"id": "123", "status": "applied", "applied_at": "2026-08-22 10:00:00", "analysis_data": None}
        ]

        mock_job = MagicMock(spec=JobDetails)
        mock_job.id = "123"
        mock_job.title = "SDE"
        mock_job.company = "TestCo"
        mock_job.description = "Test Description"
        sync_service.extractor.get_cached_job.return_value = mock_job

        with patch("src.generator.sync_service.NetworkGraphBuilder") as mock_builder_class:
            mock_builder_class.return_value.connections = []
            sync_service.template_manager.render_job.return_value = "job content"
            sync_service._sync_all()

        _, kwargs = sync_service.template_manager.render_job.call_args
        assert kwargs["status"] == "Applied"
        assert kwargs["applied_at"] == "2026-08-22 10:00:00"

    def test_sync_all_removes_stale_score_bucket_duplicate(self, sync_service, tmp_path):
        """A job whose score bucket changed should not leave a duplicate in its old subfolder."""
        sync_service.vault_manager.vault_path = tmp_path
        sync_service.vault_manager.folders.get.return_value = "Jobs"
        jobs_folder = tmp_path / "Jobs"
        jobs_folder.mkdir()

        stale_folder = jobs_folder / "Score_0-9"
        stale_folder.mkdir()
        stale_path = stale_folder / "SDE - TestCo.md"
        stale_path.write_text('---\njob_id: "123"\nscore: 5\n---\n', encoding="utf-8")

        def fake_write_file(content, filename, folder_key, subfolder=""):
            folder_path = jobs_folder / subfolder if subfolder else jobs_folder
            folder_path.mkdir(parents=True, exist_ok=True)
            path = folder_path / filename
            path.write_text(content, encoding="utf-8")
            return path

        sync_service.vault_manager.write_file.side_effect = fake_write_file

        mock_db = MagicMock()
        sync_service.extractor.db = mock_db
        sync_service.extractor.db.get_all_jobs.return_value = [{"id": "123", "analysis_data": None}]

        mock_job = MagicMock(spec=JobDetails)
        mock_job.id = "123"
        mock_job.title = "SDE"
        mock_job.company = "TestCo"
        mock_job.description = "Test Description"
        sync_service.extractor.get_cached_job.return_value = mock_job
        sync_service._load_analysis = MagicMock(
            return_value=ScoringResult(score=95, matching_skills=[], missing_skills=[], reasoning="great")
        )

        sync_service.template_manager.render_job.return_value = "job content"
        sync_service.template_manager.render_company.return_value = "company content"

        with patch("src.generator.sync_service.NetworkGraphBuilder") as mock_builder_class:
            mock_builder_class.return_value.connections = []
            sync_service._sync_all()

        assert not stale_path.exists()
        assert (jobs_folder / "Score_90-99" / "SDE - TestCo.md").exists()

    def test_sync_all_preserves_poc(self, sync_service, tmp_path):
        """poc_name/poc_link authored in Obsidian must survive a full re-sync."""
        sync_service.vault_manager.vault_path = tmp_path
        sync_service.vault_manager.folders.get.return_value = "Jobs"
        jobs_folder = tmp_path / "Jobs"
        jobs_folder.mkdir()

        existing_note = jobs_folder / "SDE - TestCo.md"
        existing_note.write_text(
            '---\njob_id: "123"\npoc_name: "Jane Doe"\npoc_link: "https://linkedin.com/in/janedoe"\n---\n',
            encoding="utf-8",
        )

        mock_db = MagicMock()
        sync_service.extractor.db = mock_db
        sync_service.extractor.db.get_all_jobs.return_value = [{"id": "123", "analysis_data": None}]

        mock_job = MagicMock(spec=JobDetails)
        mock_job.id = "123"
        mock_job.title = "SDE"
        mock_job.company = "TestCo"
        mock_job.description = "Test Description"
        sync_service.extractor.get_cached_job.return_value = mock_job

        with patch("src.generator.sync_service.NetworkGraphBuilder") as mock_builder_class:
            mock_builder_class.return_value.connections = []
            sync_service.template_manager.render_job.return_value = "job content"
            sync_service._sync_all()

        _, kwargs = sync_service.template_manager.render_job.call_args
        assert kwargs["poc_name"] == "Jane Doe"
        assert kwargs["poc_link"] == "https://linkedin.com/in/janedoe"

    def test_sync_all_skips_discovered_jobs(self, sync_service):
        """Unscraped ('discovered') jobs should not be written to the vault."""
        mock_db = MagicMock()
        sync_service.extractor.db = mock_db
        sync_service.extractor.db.get_all_jobs.return_value = [
            {"id": "123", "status": "discovered", "analysis_data": None},
        ]

        with patch("src.generator.sync_service.NetworkGraphBuilder") as mock_builder_class:
            mock_builder_class.return_value.connections = []
            sync_service._sync_all()

        sync_service.extractor.get_cached_job.assert_not_called()
        sync_service.vault_manager.write_file.assert_not_called()

    def test_sync_all_skips_auto_rejected_zero_score_jobs(self, sync_service):
        """Jobs auto-rejected by the score-0 experience filter should not be written to the vault."""
        mock_db = MagicMock()
        sync_service.extractor.db = mock_db
        sync_service.extractor.db.get_all_jobs.return_value = [
            {"id": "123", "status": "rejected", "relevance_score": 0, "analysis_data": None},
        ]

        with patch("src.generator.sync_service.NetworkGraphBuilder") as mock_builder_class:
            mock_builder_class.return_value.connections = []
            sync_service._sync_all()

        sync_service.extractor.get_cached_job.assert_not_called()
        sync_service.vault_manager.write_file.assert_not_called()

    def test_sync_all_keeps_manually_rejected_jobs_with_a_real_score(self, sync_service):
        """A job rejected after actually being considered (non-zero score) should still sync."""
        mock_db = MagicMock()
        sync_service.extractor.db = mock_db
        sync_service.extractor.db.get_all_jobs.return_value = [
            {"id": "123", "status": "rejected", "relevance_score": 72, "analysis_data": None},
        ]

        mock_job = MagicMock(spec=JobDetails)
        mock_job.id = "123"
        mock_job.title = "SDE"
        mock_job.company = "TestCo"
        mock_job.description = "Test Description"
        sync_service.extractor.get_cached_job.return_value = mock_job

        with patch("src.generator.sync_service.NetworkGraphBuilder") as mock_builder_class:
            mock_builder_class.return_value.connections = []
            sync_service.template_manager.render_job.return_value = "job content"
            sync_service.template_manager.render_company.return_value = "company content"
            sync_service._sync_all()

        sync_service.extractor.get_cached_job.assert_called_once()

    def test_prune_vault_removes_auto_rejected_notes(self, sync_service, tmp_path):
        """Notes for jobs auto-rejected with a 0 score should be pruned from the vault."""
        sync_service.vault_manager.vault_path = tmp_path
        sync_service.vault_manager.folders.get.return_value = "Jobs"
        jobs_folder = tmp_path / "Jobs"
        jobs_folder.mkdir()

        job_file = jobs_folder / "Auto Rejected Job.md"
        job_file.write_text('---\njob_id: "123"\nstatus: "Rejected"\n---\n', encoding="utf-8")

        sync_service.extractor.db.get_all_jobs.return_value = [
            {"id": "123", "status": "rejected", "relevance_score": 0}
        ]

        sync_service.prune_vault()

        assert not job_file.exists()

    def test_prune_vault(self, sync_service, tmp_path):
        """Test removing orphaned files from vault."""
        sync_service.vault_manager.vault_path = tmp_path
        sync_service.vault_manager.folders.get.return_value = "Jobs"
        jobs_folder = tmp_path / "Jobs"
        jobs_folder.mkdir()

        # Create an orphaned job file
        job_file = jobs_folder / "Old Job.md"
        job_file.write_text('---\njob_id: "999"\nstatus: "ToApply"\n---\n', encoding="utf-8")

        # Mock DB to NOT contain ID 999
        sync_service.extractor.db.get_all_jobs.return_value = [{"id": "123"}]

        sync_service.prune_vault()

        assert not job_file.exists()

    def test_prune_vault_removes_unscraped_notes(self, sync_service, tmp_path):
        """Notes for jobs still in 'discovered' status should also be pruned."""
        sync_service.vault_manager.vault_path = tmp_path
        sync_service.vault_manager.folders.get.return_value = "Jobs"
        jobs_folder = tmp_path / "Jobs"
        jobs_folder.mkdir()

        # Job exists in DB but hasn't been scraped yet (external-style id)
        job_file = jobs_folder / "Unscraped Job.md"
        job_file.write_text('---\njob_id: "ext-999"\nstatus: "ToApply"\n---\n', encoding="utf-8")

        sync_service.extractor.db.get_all_jobs.return_value = [{"id": "ext-999", "status": "discovered"}]

        sync_service.prune_vault()

        assert not job_file.exists()

    def test_sync_from_obsidian(self, sync_service, tmp_path):
        """Test updating DB status from Obsidian notes."""
        sync_service.vault_manager.vault_path = tmp_path
        sync_service.vault_manager.folders.get.return_value = "Jobs"
        jobs_folder = tmp_path / "Jobs"
        jobs_folder.mkdir()

        # Create a job file with a status property
        job_file = jobs_folder / "Active Job.md"
        job_file.write_text('---\njob_id: "123"\nstatus: "Applied"\n---\n', encoding="utf-8")

        # Mock DB
        sync_service.extractor.db.job_exists.return_value = True

        sync_service.sync_from_obsidian()

        sync_service.extractor.db.update_job_status.assert_called_with("123", "applied")

    def test_sync_from_obsidian_applied_checkbox_marks_applied(self, sync_service, tmp_path):
        """Checking the `applied` checkbox on a ToApply job should bump it to Applied."""
        sync_service.vault_manager.vault_path = tmp_path
        sync_service.vault_manager.folders.get.return_value = "Jobs"
        jobs_folder = tmp_path / "Jobs"
        jobs_folder.mkdir()

        job_file = jobs_folder / "New Job.md"
        job_file.write_text('---\njob_id: "123"\nstatus: "ToApply"\napplied: true\n---\n', encoding="utf-8")

        sync_service.extractor.db.job_exists.return_value = True

        sync_service.sync_from_obsidian()

        sync_service.extractor.db.update_job_status.assert_called_with("123", "applied")

    def test_sync_from_obsidian_unchecking_applied_reverts_to_apply(self, sync_service, tmp_path):
        """Unchecking `applied` on a job still marked Applied should revert it to ToApply."""
        sync_service.vault_manager.vault_path = tmp_path
        sync_service.vault_manager.folders.get.return_value = "Jobs"
        jobs_folder = tmp_path / "Jobs"
        jobs_folder.mkdir()

        job_file = jobs_folder / "Reverted Job.md"
        job_file.write_text('---\njob_id: "123"\nstatus: "Applied"\napplied: false\n---\n', encoding="utf-8")

        sync_service.extractor.db.job_exists.return_value = True

        sync_service.sync_from_obsidian()

        sync_service.extractor.db.update_job_status.assert_called_with("123", "to_apply")

    def test_load_analysis_error(self, sync_service):
        """Test error handling in _load_analysis."""
        mock_job_data = {"id": "123", "analysis_data": "{invalid json}"}
        result = sync_service._load_analysis(mock_job_data)
        assert result.score == 0
        assert "not been scored" in result.reasoning
