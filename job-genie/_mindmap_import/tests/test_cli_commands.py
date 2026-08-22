import json
import pathlib
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from src.core.relevance_scorer import ScoringResult
from src.main import cli


@pytest.fixture(autouse=True)
def clean_data_env(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Give each test an isolated cwd with a fresh 'data' directory.

    This used to operate on the cwd-relative "data" directory directly and
    delete everything inside it (except a couple of filenames) before and
    after every test. Running pytest from the repo root - the normal case -
    made that resolve to the project's real data/ directory and silently wipe
    data/jobs.db. Chdir-ing into a per-test tmp_path keeps every relative
    "data/..." path the tests use fully isolated from the real project data,
    regardless of the invocation cwd.
    """
    monkeypatch.chdir(tmp_path)
    pathlib.Path("data").mkdir(parents=True, exist_ok=True)
    yield


@pytest.fixture
def runner() -> CliRunner:
    """Provides a Click CLI runner for testing."""
    return CliRunner()


@pytest.fixture
def mock_config(tmp_path: pathlib.Path) -> pathlib.Path:
    """Creates a temporary configuration file with standard mock values."""
    config_data = {
        "search": {"keywords": ["Python"], "location": "Remote", "location_type": "Remote", "filters": {}},
        "ai": {"provider": "ollama", "ollama": {"model_name": "llama3"}},
        "user": {
            "resume_path": "data/resume.pdf",
            "email": "user@example.com",
            "linkedin_connections_path": "data/Connections.csv",
        },
        "notifications": {"email": {"enabled": True}},
        "obsidian": {
            "vault_path": str(tmp_path / "vault"),
            "folders": {"jobs": "Jobs", "companies": "Companies", "people": "People", "analysis": "Analysis"},
        },
    }
    config_file = tmp_path / "test_config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_data, f)
    return config_file


class TestCLIValidation:
    """Validation tests for configuration and connectivity commands."""

    def test_check_valid_config(self, runner: CliRunner, mock_config: pathlib.Path) -> None:
        """Verify the 'check' command validates a correct configuration file."""
        result = runner.invoke(cli, ["check", "--config", str(mock_config)])
        assert result.exit_code == 0
        assert "Config file valid" in result.output

    @patch("src.core.orchestrator.get_llm_client")
    def test_test_ai_command_success(
        self, mock_get_client: MagicMock, runner: CliRunner, mock_config: pathlib.Path
    ) -> None:
        """Verify the 'test-ai' command displays successful AI responses."""
        mock_client = MagicMock()
        mock_client.generate.return_value = "AI Response"
        mock_get_client.return_value = mock_client

        result = runner.invoke(cli, ["test-ai", "--config", str(mock_config)])
        assert result.exit_code == 0
        assert "AI Response (ollama):" in result.output
        assert "AI Response" in result.output

    @patch("src.core.orchestrator.get_llm_client")
    def test_test_ai_command_empty_response(
        self, mock_get_client: MagicMock, runner: CliRunner, mock_config: pathlib.Path
    ) -> None:
        """Verify the 'test-ai' command handles empty AI responses gracefully."""
        mock_client = MagicMock()
        mock_client.generate.return_value = ""
        mock_get_client.return_value = mock_client

        result = runner.invoke(cli, ["test-ai", "--config", str(mock_config)])
        assert result.exit_code == 0
        assert "AI returned empty response" in result.output


class TestCLIJobIngestion:
    """Tests for job discovery, scraping, and session management."""

    @patch("src.core.orchestrator.JobDetailsExtractor")
    @patch("src.core.orchestrator.BrowserManager")
    @patch("src.core.orchestrator.JobSearcher")
    def test_search_command(
        self,
        mock_searcher_class: MagicMock,
        mock_browser_manager_class: MagicMock,
        mock_extractor_class: MagicMock,
        runner: CliRunner,
        mock_config: pathlib.Path,
    ) -> None:
        """Verify the 'search' command initiates job discovery via browser."""
        mock_searcher = mock_searcher_class.return_value
        mock_searcher.search.return_value = [MagicMock(id="1", title="Job 1", company="Co 1", location="Loc 1")]
        mock_browser_manager_class.return_value.__enter__.return_value = MagicMock()
        mock_extractor = mock_extractor_class.return_value
        mock_extractor.db.job_exists.return_value = False

        result = runner.invoke(cli, ["search", "--config", str(mock_config), "--headless"])
        assert result.exit_code == 0
        assert "Total unique jobs found: 1" in result.output
        assert "Job 1" in result.output

    @patch("src.core.orchestrator.BrowserManager")
    @patch("src.core.orchestrator.JobSearcher")
    @patch("src.core.orchestrator.JobDetailsExtractor")
    @patch("src.core.orchestrator.get_llm_client")
    def test_scrape_command(
        self,
        mock_get_llm: MagicMock,
        mock_extractor_class: MagicMock,
        mock_searcher_class: MagicMock,
        mock_browser_manager_class: MagicMock,
        runner: CliRunner,
        mock_config: pathlib.Path,
    ) -> None:
        """Verify the 'scrape' command handles multi-step job extraction logic."""
        mock_searcher = mock_searcher_class.return_value
        mock_searcher.search.return_value = [MagicMock(id="1", title="Job 1", company="Co 1")]
        mock_extractor = mock_extractor_class.return_value
        mock_extractor.extract_multiple_jobs.return_value = [MagicMock(title="Job 1", company="Co 1", link="url")]
        mock_extractor.db.job_exists.return_value = False
        mock_extractor.db.get_jobs_by_status.return_value = []
        mock_browser_manager_class.return_value.__enter__.return_value = MagicMock()

        result = runner.invoke(cli, ["scrape", "--config", str(mock_config), "--limit", "1"])
        assert result.exit_code == 0
        assert "Scraped 1 / 1 jobs" in result.output

    @patch("src.core.orchestrator.BrowserManager")
    def test_login_command(
        self, mock_browser_manager_class: MagicMock, runner: CliRunner, mock_config: pathlib.Path
    ) -> None:
        """Verify the 'login' command initiates a manual browser session for cookie retrieval."""
        mock_browser = MagicMock()
        mock_browser_manager_class.return_value.__enter__.return_value = mock_browser

        result = runner.invoke(cli, ["login", "--config", str(mock_config)])
        assert result.exit_code == 0
        assert "Starting browser for manual login" in result.output
        mock_browser.login_manual.assert_called_once()


class TestCLIJobAnalysis:
    """Tests for scoring, networking, and gap analysis commands."""

    @patch("src.core.orchestrator.JobDetailsExtractor")
    @patch("src.core.orchestrator.ReferralService")
    def test_network_command(
        self,
        mock_referral_service_class: MagicMock,
        mock_extractor_class: MagicMock,
        runner: CliRunner,
        mock_config: pathlib.Path,
    ) -> None:
        """Verify the 'network' command identifies connections for a cached job."""
        mock_extractor = mock_extractor_class.return_value
        mock_job = MagicMock(id="1", company="TestCo")
        mock_extractor.get_cached_job.return_value = mock_job
        mock_referral_service = mock_referral_service_class.return_value
        mock_referral_service.find_potential_connections.return_value = [
            MagicMock(full_name="Alice", position="Engineer")
        ]

        pathlib.Path("data/sample_connections.csv").touch()

        result = runner.invoke(cli, ["network", "1", "--config", str(mock_config)])
        assert result.exit_code == 0
        assert "Found 1 connections at TestCo:" in result.output
        assert "Alice" in result.output

    @patch("src.core.orchestrator.JobDetailsExtractor")
    @patch("src.core.orchestrator.get_llm_client")
    @patch("src.core.orchestrator.PDFResumeParser")
    @patch("src.core.orchestrator.AnalysisService")
    def test_score_command(
        self,
        mock_analysis_service_class: MagicMock,
        mock_parser_class: MagicMock,
        mock_get_llm: MagicMock,
        mock_extractor_class: MagicMock,
        runner: CliRunner,
        mock_config: pathlib.Path,
    ) -> None:
        """Verify the 'score' command evaluates job relevance scores."""
        mock_parser = mock_parser_class.return_value
        mock_parser.extract_text.return_value = "Resume Text"
        mock_extractor = mock_extractor_class.return_value
        mock_extractor.get_cached_job.return_value = MagicMock(id="1")
        mock_analysis_service = mock_analysis_service_class.return_value
        mock_analysis_service.score_job.return_value = ScoringResult(
            score=85, matching_skills=["A"], missing_skills=["B"], reasoning="Great fit"
        )
        pathlib.Path("data/sample_resume.pdf").touch()

        result = runner.invoke(cli, ["score", "1", "--config", str(mock_config)])
        assert result.exit_code == 0
        assert "Score 85" in result.output

    @patch("src.core.orchestrator.AnalysisService")
    @patch("src.core.orchestrator.get_llm_client")
    def test_analyze_gaps_command(
        self,
        mock_get_llm: MagicMock,
        mock_analysis_service_class: MagicMock,
        runner: CliRunner,
        mock_config: pathlib.Path,
    ) -> None:
        """Verify the 'analyze-gaps' command identifies missing skills across all scored jobs."""
        mock_analysis_service = mock_analysis_service_class.return_value
        mock_analysis_service.run_gap_analysis.return_value = MagicMock(
            skill_frequency={"Python": 2}, improvement_plan="Learn Python"
        )

        result = runner.invoke(cli, ["analyze-gaps", "--config", str(mock_config)])
        assert result.exit_code == 0
        assert "Analyzing gaps across jobs scored >= 0" in result.output
        assert "Python: 2 jobs" in result.output

    @patch("src.core.orchestrator.JobDetailsExtractor")
    @patch("src.core.orchestrator.EmailService")
    def test_notify_command(
        self,
        mock_service_class: MagicMock,
        mock_extractor_class: MagicMock,
        runner: CliRunner,
        mock_config: pathlib.Path,
    ) -> None:
        """Verify the 'notify' command sends digests for high-scoring jobs."""
        mock_extractor = mock_extractor_class.return_value
        mock_db = MagicMock()
        mock_extractor.db = mock_db

        mock_analysis_row = {
            "id": "notify_test",
            "analysis_data": json.dumps(
                {"score": 80, "matching_skills": ["A"], "missing_skills": ["B"], "reasoning": "R"}
            ),
        }
        mock_db.get_all_analyses.return_value = [mock_analysis_row]
        mock_extractor.get_cached_job.return_value = MagicMock(id="notify_test")

        mock_service = mock_service_class.return_value
        mock_service.send_job_digest.return_value = True

        result = runner.invoke(cli, ["notify", "--config", str(mock_config), "--min-score", "70"])
        assert result.exit_code == 0
        assert "Notifications sent." in result.output
