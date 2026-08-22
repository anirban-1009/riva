from unittest.mock import MagicMock, patch

import pytest

from src.ingest.job_searcher import JobSearcher


class TestJobSearcher:
    @pytest.fixture
    def mock_browser_manager(self):
        return MagicMock()

    @pytest.fixture
    def searcher(self, mock_browser_manager):
        return JobSearcher(mock_browser_manager)

    def test_construct_search_url_basic(self, searcher):
        """Test basic URL construction with keywords and location."""
        url = searcher.construct_search_url("Python", "New York")
        assert "keywords=Python" in url
        assert "location=New+York" in url
        assert "refresh=true" in url

    def test_construct_search_url_with_filters(self, searcher):
        """Test URL construction with experience level and job type filters."""
        filters = {"experience_level": ["Mid-Senior level", "Associate"], "job_type": ["Full-time", "Contract"]}
        url = searcher.construct_search_url("Python", "USA", filters=filters, location_type="Remote")

        assert "keywords=Python" in url
        assert "location=USA" in url
        assert "f_WT=2" in url  # Remote
        assert "f_E=4%2C3" in url or "f_E=3%2C4" in url  # Mid-Senior(4) and Associate(3)
        assert "f_JT=F%2CC" in url or "f_JT=C%2CF" in url  # Full-time(F) and Contract(C)

    def test_construct_search_url_unknown_values(self, searcher):
        """Test URL construction with unknown filter values which should be ignored."""
        filters = {"experience_level": ["Super Expert"], "job_type": ["Gig"]}
        url = searcher.construct_search_url("Python", "USA", filters=filters, location_type="Mars")

        assert "f_WT" not in url
        assert "f_E" not in url
        assert "f_JT" not in url

    def test_search_no_results(self, searcher, mock_browser_manager):
        """Test search when no results are found."""
        mock_page = mock_browser_manager.page
        mock_page.content.return_value = "No matching jobs found"
        mock_page.wait_for_selector.side_effect = Exception("Not found")

        results = searcher.search("NonExistentJob", "Nowhere")

        assert results == []
        mock_browser_manager.goto.assert_called_once()

    @patch("src.ingest.job_searcher.JobSearchResult")
    def test_search_with_results(self, mock_result_class, searcher, mock_browser_manager):
        """Test search with mocked results."""
        mock_page = mock_browser_manager.page

        # Mock locator for job cards
        mock_card = MagicMock()
        mock_title = MagicMock()
        mock_title.count.return_value = 1
        mock_title.first.inner_text.return_value = "Software Engineer"
        mock_title.first.get_attribute.return_value = "/jobs/view/12345"

        mock_company = MagicMock()
        mock_company.count.return_value = 1
        mock_company.first.inner_text.return_value = "Tech Co"

        mock_location = MagicMock()
        mock_location.count.return_value = 1
        mock_location.first.inner_text.return_value = "San Francisco"

        mock_card.locator.side_effect = lambda selector: {
            ".job-card-list__title": mock_title,
            ".job-card-container__primary-description": mock_company,
            ".job-card-container__metadata-item": mock_location,
        }[selector]

        mock_page.locator.return_value.locator.return_value.all.return_value = [mock_card]

        results = searcher.search("Python", "SF")

        assert len(results) == 1
        # JobSearchResult is called once
        mock_result_class.assert_called_once_with(
            id="12345",
            title="Software Engineer",
            company="Tech Co",
            link="https://www.linkedin.com/jobs/view/12345",
            location="San Francisco",
        )

    def test_search_navigation_error(self, searcher, mock_browser_manager):
        """Test search handles navigation errors gracefully."""
        # The search method calls self.browser.goto, so we need to mock that
        mock_browser_manager.goto.side_effect = Exception("Network Error")

        # We need to catch the exception because the implementation doesn't appear to catch navigation errors
        # inside search(). Wait, looking at the code in step 118...
        # The code: self.browser.goto(url) is NOT in a try/except block.
        # So it SHOULD raise an exception.

        with pytest.raises(Exception, match="Network Error"):
            searcher.search("Python", "SF")

    def test_search_parse_error(self, searcher, mock_browser_manager):
        """Test search handles errors while parsing individual job cards."""
        mock_page = mock_browser_manager.page

        # Mock finding the list container
        mock_page.wait_for_selector.return_value = True

        # Mock one job card that raises error when accessed
        mock_card = MagicMock()
        # The code calls card.locator(...), so we make that raise
        mock_card.locator.side_effect = Exception("Parsing Error")

        # We need to return a list of cards
        mock_list = MagicMock()
        mock_list.locator.return_value.all.return_value = [mock_card]

        mock_page.locator.return_value = mock_list

        results = searcher.search("Python", "SF")

        # Should return empty list because the single card failed to parse
        assert results == []

    def test_construct_search_url_all_filters(self, searcher):
        """Test construct_search_url with all possible supported filters."""
        filters = {
            "experience_level": ["Entry level"],
            "job_type": ["Internship"],
        }
        # location_type is a separate argument, not part of filters dict in implementation
        url = searcher.construct_search_url("Java", "Berlin", filters=filters, location_type="On-site")

        # Robust verification using urllib.parse
        import urllib.parse

        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)

        assert "f_TPR" not in params  # date_posted is not currently implemented in construct_search_url
        assert params["f_E"] == ["2"]
        assert params["f_JT"] == ["I"]
        assert params["f_WT"] == ["1"]
