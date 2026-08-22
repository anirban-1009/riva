import subprocess
import sys
from unittest.mock import MagicMock

import pytest

from src.ingest.external_searcher import ExternalSiteSearcher


class TestExternalSiteSearcher:
    @pytest.fixture
    def mock_browser_manager(self):
        return MagicMock()

    @pytest.fixture
    def mock_llm(self):
        return MagicMock()

    @pytest.fixture
    def searcher(self, mock_browser_manager, mock_llm):
        return ExternalSiteSearcher(mock_browser_manager, mock_llm)

    def test_search_site_job_id_is_stable_across_runs(self, searcher, mock_browser_manager, mock_llm):
        """job_id must be deterministic across process runs so caching/dedup by id
        works. Regression test for using Python's randomized hash() instead of a
        stable hash, which produced a different id for the same URL every run."""
        job_url = "https://boards.greenhouse.io/example/jobs/12345"
        mock_browser_manager.page.evaluate.side_effect = [
            None,
            None,
            None,
            [{"text": "Software Engineer", "href": job_url}],
        ]
        mock_llm.generate_json.return_value = [{"title": "Software Engineer", "url": job_url}]

        results = searcher.search_site("https://example.com/careers", company_name="Example Co")

        assert len(results) == 1
        job_id = results[0].id
        assert job_id.startswith("ext-")

        # Recompute in a fresh subprocess (fresh PYTHONHASHSEED) to prove the id
        # doesn't depend on the randomized hash() of the current process.
        script = "import hashlib; " f"print('ext-' + hashlib.sha256({job_url!r}.encode()).hexdigest()[:16])"
        other_process_id = subprocess.check_output([sys.executable, "-c", script]).decode().strip()

        assert job_id == other_process_id

    def test_search_site_no_links_found(self, searcher, mock_browser_manager):
        mock_browser_manager.page.evaluate.return_value = []

        results = searcher.search_site("https://example.com/careers")

        assert results == []

    def test_search_site_navigation_failure(self, searcher, mock_browser_manager):
        mock_browser_manager.goto.side_effect = Exception("Navigation failed")

        results = searcher.search_site("https://example.com/careers")

        assert results == []
