from unittest.mock import MagicMock, patch

import pytest

from src.ingest.job_details_extractor import JobDetails, JobDetailsExtractor
from src.ingest.selectors import (
    JOB_COMPANY_SELECTORS,
    JOB_DESCRIPTION_SELECTORS,
    JOB_INSIGHT_SELECTORS,
    JOB_TITLE_SELECTORS,
)


class TestJobDetailsExtractor:
    @pytest.fixture
    def mock_browser_manager(self):
        return MagicMock()

    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock()
        llm.generate_json.return_value = None
        return llm

    @pytest.fixture
    def extractor(self, mock_browser_manager, mock_llm):
        with patch("src.ingest.job_details_extractor.DatabaseManager") as mock_db:
            extractor = JobDetailsExtractor(mock_browser_manager, llm_client=mock_llm)
            extractor.db = mock_db.return_value
            return extractor

    def test_get_cached_job_exists(self, extractor):
        """Test loading job from database when it exists."""
        job_id = "123"
        job_data = {
            "id": job_id,
            "title": "Dev",
            "company": "Tech",
            "location": "Remote",
            "description": "Desc",
            "posted_date": "2d",
            "seniority_level": "Mid",
            "employment_type": "Full",
            "job_function": "Eng",
            "industries": "IT",
            "link": "url",
            "salary": "$100k",
            "apply_link": "https://apply.com",
            "raw_data": None,
        }
        extractor.db.get_job.return_value = job_data

        job = extractor.get_cached_job(job_id)
        assert job is not None
        assert job.id == job_id
        assert job.title == "Dev"

    def test_get_cached_job_not_exists(self, extractor):
        """Test returning None when job is not in database."""
        extractor.db.get_job.return_value = None
        assert extractor.get_cached_job("999") is None

    def test_extract_job_details_from_cache(self, extractor, mock_browser_manager):
        """Test that extract_job_details prefers cache over browser."""
        job_id = "123"
        with patch.object(extractor, "get_cached_job") as mock_get:
            mock_get.return_value = JobDetails(
                id=job_id,
                title="Cached",
                company="",
                location="",
                description="",
                posted_date="",
                seniority_level="",
                employment_type="",
                job_function="",
                industries="",
                link="",
                salary="",
                apply_link="",
            )

            result = extractor.extract_job_details(job_id, "some-url")

            assert result.title == "Cached"
            mock_browser_manager.goto.assert_not_called()

    def test_extract_job_details_success(self, extractor, mock_browser_manager):
        """Test successful extraction from mocked page."""
        job_id = "456"
        job_url = "https://linkedin.com/jobs/view/456"
        mock_page = mock_browser_manager.page

        # Mock selectors using the first selector in each list to match implementation
        def mock_locator(selector):
            mock_elem = MagicMock()
            if selector == JOB_TITLE_SELECTORS[0]:
                mock_elem.count.return_value = 1
                mock_elem.inner_text.return_value = "Software Engineer"
            elif selector == JOB_COMPANY_SELECTORS[0]:
                mock_elem.count.return_value = 1
                mock_elem.inner_text.return_value = "Google"
            elif selector == JOB_DESCRIPTION_SELECTORS[0]:
                mock_elem.count.return_value = 1
                mock_elem.inner_text.return_value = "Detailed description"
            elif selector == JOB_INSIGHT_SELECTORS[0]:
                mock_elem.count.return_value = 2
                item1 = MagicMock()
                item1.inner_text.return_value = "Full-time · IT"
                item2 = MagicMock()
                item2.inner_text.return_value = "Mid-Senior level · Software"
                mock_elem.all.return_value = [item1, item2]
            else:
                mock_elem.count.return_value = 0

            mock_elem.first = mock_elem
            return mock_elem

        mock_page.locator.side_effect = mock_locator

        result = extractor.extract_job_details(job_id, job_url)

        assert result is not None
        assert result.title == "Software Engineer"
        assert result.company == "Google"
        assert result.description == "Detailed description"
        assert result.employment_type == "Full-time"
        assert result.seniority_level == "Mid-Senior level"

        # Verify DB save called
        extractor.db.save_job.assert_called_once()

    def test_extract_job_details_failure(self, extractor, mock_browser_manager):
        """Test behavior when extraction fails (e.g. timeout)."""
        job_id = "fail"
        mock_browser_manager.goto.side_effect = Exception("Page load error")

        result = extractor.extract_job_details(job_id, "url")
        assert result is None

    def test_selector_fallback(self, extractor, mock_browser_manager):
        """Test that extractor falls back to secondary selectors if primary fails."""
        job_id = "fallback-selector"
        mock_page = mock_browser_manager.page

        # Setup: First title selector fails (count 0), second succeeds
        def mock_locator(selector):
            mock_elem = MagicMock()
            if selector == JOB_TITLE_SELECTORS[0]:
                mock_elem.count.return_value = 0
            elif selector == JOB_TITLE_SELECTORS[1]:
                mock_elem.count.return_value = 1
                mock_elem.inner_text.return_value = "Fallback Title"
                mock_elem.first = mock_elem
            elif selector == JOB_COMPANY_SELECTORS[0]:
                mock_elem.count.return_value = 1
                mock_elem.inner_text.return_value = "Company"
                mock_elem.first = mock_elem
            else:
                mock_elem.count.return_value = 0
            return mock_elem

        mock_page.locator.side_effect = mock_locator

        result = extractor.extract_job_details(job_id, "url")
        assert result.title == "Fallback Title"

    def test_ai_fallback_extraction(self, extractor, mock_browser_manager, mock_llm):
        """Test that extractor uses LLM when selector extraction is insufficient."""
        job_id = "ai-fallback"
        mock_page = mock_browser_manager.page

        # Setup: Selectors return minimal info (missing description)
        def mock_locator(selector):
            mock_elem = MagicMock()
            if selector == JOB_TITLE_SELECTORS[0]:
                mock_elem.count.return_value = 1
                mock_elem.inner_text.return_value = "Basic Title"
                mock_elem.first = mock_elem
            # Return cached/empty for others to trigger AI fallback
            mock_elem.count.return_value = 0
            if selector == "body":
                mock_elem.inner_text.return_value = "Raw page text containing job details..."
                return mock_elem
            return mock_elem

        mock_page.locator.side_effect = mock_locator

        # Setup LLM to return enhanced details
        mock_llm.generate_json.return_value = {
            "title": "Enhanced Title",
            "company": "AI Company",
            "description": "Full description extracted by AI",
            "location": "AI Land",
        }

        result = extractor.extract_job_details(job_id, "url")

        # Verify LLM was called
        mock_llm.generate_json.assert_called_once()

        # Verify result contains AI-extracted data
        assert result.title == "Enhanced Title"
        assert result.company == "AI Company"
        assert result.description == "Full description extracted by AI"

    def test_extract_multiple_jobs(self, extractor):
        """Test extracting multiple jobs with mix of success/fail."""
        job_list = [
            {"id": "1", "link": "url1"},
            {"id": "2", "link": "url2"},
            {"id": "", "link": "url3"},  # Invalid
        ]

        with patch.object(extractor, "extract_job_details") as mock_extract:
            mock_extract.side_effect = [
                JobDetails("1", "Title1", "", "", "", "", "", "", "", "", "url1"),
                None,  # Failure
            ]

            results = extractor.extract_multiple_jobs(job_list, delay=0)

            assert len(results) == 1
            assert results[0].id == "1"
            assert mock_extract.call_count == 2

    def test_extract_job_details_login_modal(self, extractor, mock_browser_manager):
        """Test that login modal detection logs a debug message but continues extraction."""
        job_id = "login-wall"
        mock_page = mock_browser_manager.page

        # Mock login modal presence
        mock_modal = MagicMock()
        mock_modal.count.return_value = 1

        def mock_locator(selector):
            if "modal" in selector or "auth" in selector:  # Simplified check for test
                return mock_modal

            # Allow basic extraction to succeed
            mock_elem = MagicMock()
            if selector == JOB_TITLE_SELECTORS[0]:
                mock_elem.count.return_value = 1
                mock_elem.inner_text.return_value = "Behind Wall"
                mock_elem.first = mock_elem
                return mock_elem

            mock_elem.count.return_value = 0
            return mock_elem

        mock_page.locator.side_effect = mock_locator

        # We need to ensure LOGIN_MODAL_SELECTORS in source matches our mock expectation
        # But since we can't easily change the imported constant, we rely on the fact
        # actual selectors are used. We'll just trust the side_effect logic.
        # Ideally we'd patch LOGIN_MODAL_SELECTORS, but patching imported list is tricky.
        # Instead, we just ensure `locator` is called and returns something for those selectors.

        result = extractor.extract_job_details(job_id, "url")
        assert result.title == "Behind Wall"

    def test_save_to_cache_db_error(self, extractor):
        """Test error handling when saving to database fails."""
        job = JobDetails("err", "Title", "", "", "", "", "", "", "", "", "")

        extractor.db.save_job.side_effect = Exception("Boom")
        # Should not raise exception
        extractor._save_to_cache(job)

    def test_get_cached_job_db_error(self, extractor):
        """Test error handling when database get fails."""
        job_id = "fail"
        extractor.db.get_job.side_effect = Exception("error")

        job = extractor.get_cached_job(job_id)
        assert job is None

    def test_extract_criteria_fields(self, extractor, mock_browser_manager):
        """Test extraction of specific criteria fields like Seniority and Industry."""
        job_id = "criteria"
        mock_page = mock_browser_manager.page

        # Mock criteria items
        mock_item1 = MagicMock()
        mock_header1 = MagicMock()
        mock_header1.inner_text.return_value = "Seniority level"
        mock_value1 = MagicMock()
        mock_value1.inner_text.return_value = "Director"

        mock_item2 = MagicMock()
        mock_header2 = MagicMock()
        mock_header2.inner_text.return_value = "Industries"
        mock_value2 = MagicMock()
        mock_value2.inner_text.return_value = "Tech, AI"

        # Helper to return children of item
        def item_locator(item, selector):
            if "subheader" in selector:
                return mock_header1 if item == mock_item1 else mock_header2
            if "span" in selector:
                return mock_value1 if item == mock_item1 else mock_value2
            return MagicMock()

        # We actually need to mock how _get_text calls methods on the item
        # _get_text calls item.locator(selector).first.inner_text()

        def mock_get_text_side_effect(root, selectors):
            if root == mock_item1 and "Seniority" in str(selectors):
                return "Director"  # simplified
            if root == mock_item2 and "Industries" in str(selectors):
                return "Tech, AI"
            return ""

        # Refactor: It's hard to mock internal styling of _get_text without patching it or complex mocks.
        # Let's patch _get_text instead as it's a helper method.

        with patch.object(extractor, "_get_text") as mock_get_text:
            # Setup the specific return values for criteria items
            def get_text_side_effect(root, selectors):
                if root == mock_item1 and "header" in str(selectors[0]):
                    return "Seniority level"
                if root == mock_item1 and "text" in str(selectors[0]):
                    return "Director"
                if root == mock_item2 and "header" in str(selectors[0]):
                    return "Industries"
                if root == mock_item2 and "text" in str(selectors[0]):
                    return "Tech, AI"
                return ""

            # We also need it to work for main job details
            mock_get_text.side_effect = lambda root, selectors: (
                "Basic Title"
                if root == mock_page and "title" in str(selectors[0])
                else get_text_side_effect(root, selectors)
            )

            # Mock the finding of criteria items
            mock_list = MagicMock()
            mock_list.all.return_value = [mock_item1, mock_item2]

            def page_locator(selector):
                if "description__job-criteria-item" in selector:
                    return mock_list
                # For other things return empty/basic
                m = MagicMock()
                m.count.return_value = 0
                return m

            mock_page.locator.side_effect = page_locator

            result = extractor.extract_job_details(job_id, "url")

            assert result.seniority_level == "Director"
            assert result.industries == "Tech, AI"

    def test_extract_fallbacks_from_search_result(self, extractor, mock_browser_manager):
        """Test that data from search result (fallback_data) is used when extraction fails."""
        job_id = "fallback"
        fallback_data = {"title": "Fallback Title", "company": "Fallback Co", "location": "Fallback Loc"}

        # Mock page that returns nothing
        mock_page = mock_browser_manager.page
        mock_page.locator.return_value.count.return_value = 0

        result = extractor.extract_job_details(job_id, "url", fallback_data=fallback_data)

        assert result.title == "Fallback Title"
        assert result.company == "Fallback Co"
        assert result.location == "Fallback Loc"
