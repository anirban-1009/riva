from unittest.mock import MagicMock, patch

import pytest

from src.core.orchestrator import MindMapApp


class TestMindMapApp:
    @pytest.fixture
    def mock_config(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("user: {resume_path: 'resume.pdf'}\nsearch: {keywords: ['AI'], location: 'India'}")
        return config_path

    @pytest.fixture
    def app(self, mock_config):
        with (
            patch("src.core.orchestrator.get_llm_client"),
            patch("src.core.orchestrator.ResumeService"),
            patch("src.core.orchestrator.AnalysisService"),
            patch("src.core.orchestrator.ReferralService"),
        ):
            return MindMapApp(str(mock_config))

    def test_map_all_networks(self, app):
        with patch("src.core.orchestrator.JobDetailsExtractor") as mock_extractor_cls:
            mock_extractor = mock_extractor_cls.return_value
            mock_extractor.db.get_all_jobs.return_value = [{"id": "123", "title": "AI"}]

            mock_job = MagicMock()
            mock_job.id = "123"
            mock_extractor.get_cached_job.return_value = mock_job

            app.referral_service.find_potential_connections.return_value = [MagicMock()]

            app.map_all_networks()
            app.referral_service.find_potential_connections.assert_called_once()

    def test_refresh_existing_jobs(self, app):
        with (
            patch("src.core.orchestrator.JobDetailsExtractor") as mock_extractor_cls,
            patch("src.core.orchestrator.BrowserManager"),
        ):
            mock_extractor = mock_extractor_cls.return_value
            mock_extractor.db.get_all_jobs.return_value = [{"id": "123", "title": "AI"}]

            mock_job = MagicMock()
            mock_extractor.extract_multiple_jobs.return_value = [mock_job]

            app.refresh_existing_jobs(headless=True, limit=None)
            mock_extractor.extract_multiple_jobs.assert_called_once()

    def test_find_network(self, app):
        with patch("src.core.orchestrator.JobDetailsExtractor") as mock_extractor_cls:
            mock_extractor = mock_extractor_cls.return_value
            mock_job = MagicMock()
            mock_job.company = "Google"
            mock_extractor.get_cached_job.return_value = mock_job

            app.find_network("123")
            app.referral_service.find_potential_connections.assert_called_once_with(mock_job)

    def test_scrape_with_id(self, app):
        with (
            patch("src.core.orchestrator.JobDetailsExtractor") as mock_extractor_cls,
            patch("src.core.orchestrator.BrowserManager"),
        ):
            mock_extractor = mock_extractor_cls.return_value
            app.scrape(headless=True, limit=None, force=False, job_id="123")
            mock_extractor.extract_multiple_jobs.assert_called_once()

    def test_scrape_no_jobs(self, app):
        with (
            patch("src.core.orchestrator.JobSearcher") as mock_searcher_cls,
            patch("src.core.orchestrator.JobDetailsExtractor") as mock_extractor_cls,
            patch("src.core.orchestrator.BrowserManager"),
        ):
            mock_searcher = mock_searcher_cls.return_value
            mock_searcher.search.return_value = []
            mock_extractor = mock_extractor_cls.return_value
            mock_extractor.db.get_jobs_by_status.return_value = []

            app.scrape(headless=True, limit=None, force=False)
            mock_searcher.search.assert_called()

    def test_search(self, app):
        with (
            patch("src.core.orchestrator.JobSearcher") as mock_searcher_cls,
            patch("src.core.orchestrator.JobDetailsExtractor"),
            patch("src.core.orchestrator.BrowserManager"),
        ):
            mock_searcher = mock_searcher_cls.return_value
            app.search(headless=True)
            mock_searcher.search.assert_called()

    def test_sync(self, app):
        with patch("src.core.orchestrator.SyncService") as mock_sync_cls:
            mock_sync = mock_sync_cls.return_value
            app.sync()
            mock_sync.sync.assert_called_once()

    def test_referral_job_not_found(self, app):
        with patch("src.core.orchestrator.JobDetailsExtractor") as mock_extractor_cls:
            mock_extractor = mock_extractor_cls.return_value
            mock_extractor.get_cached_job.return_value = None
            res = app.referral("999", "Alice")
            assert res is None

    def test_tailor_resume(self, app):
        with patch("src.core.orchestrator.JobDetailsExtractor") as mock_extractor_cls:
            mock_extractor = mock_extractor_cls.return_value
            mock_extractor.get_cached_job.return_value = MagicMock()
            app.resume_service.get_resume_data.return_value = {"skills": []}

            with patch("src.core.orchestrator.ResumeTailorer") as mock_tailorer_cls:
                mock_tailorer = mock_tailorer_cls.return_value
                mock_tailorer.tailor_resume.return_value = {}
                mock_tailorer.generate_latex.return_value = "latex"
                mock_tailorer.compile_pdf.return_value = None

                res = app.tailor_resume("123")
                assert res is not None
                assert "Resume_" in str(res)
