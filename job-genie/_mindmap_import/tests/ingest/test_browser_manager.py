from unittest.mock import MagicMock, patch

import pytest

from src.ingest.browser_manager import BrowserManager
from src.utils.exceptions import ScraperError


class TestBrowserManager:
    @patch("src.ingest.browser_manager.sync_playwright")
    def test_start_creates_browser_context(self, mock_playwright_sync):
        """Test that start() initializes playwright, browser, context, and page."""
        # Setup mocks
        mock_playwright_instance = MagicMock()
        mock_playwright_sync.return_value.start.return_value = mock_playwright_instance

        mock_browser = MagicMock()
        mock_playwright_instance.chromium.launch.return_value = mock_browser

        mock_context = MagicMock()
        mock_browser.new_context.return_value = mock_context

        # Test
        manager = BrowserManager(headless=True)
        manager.start()

        # Verify
        mock_playwright_sync.return_value.start.assert_called_once()
        mock_playwright_instance.chromium.launch.assert_called_with(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
            ignore_default_args=["--enable-automation"],
        )
        mock_browser.new_context.assert_called_once()
        # Verify context options like user_agent
        call_args = mock_browser.new_context.call_args[1]
        assert "user_agent" in call_args
        assert call_args["viewport"] == {"width": 1280, "height": 720}

        mock_context.new_page.assert_called_once()
        assert manager.page is not None

    @patch("src.ingest.browser_manager.sync_playwright")
    def test_start_loads_session(self, mock_playwright_sync, tmp_path):
        """Test that start() loads storage state if session path exists."""
        # Setup mocks
        mock_playwright_instance = MagicMock()
        mock_playwright_sync.return_value.start.return_value = mock_playwright_instance
        mock_browser = MagicMock()
        mock_playwright_instance.chromium.launch.return_value = mock_browser

        # Create a dummy session file
        session_file = tmp_path / "session.json"
        session_file.touch()

        manager = BrowserManager(session_path=session_file)
        manager.start()

        # Verify storage_state is passed
        call_args = mock_browser.new_context.call_args[1]
        assert call_args["storage_state"] == str(session_file)

    @patch("src.ingest.browser_manager.sync_playwright")
    def test_stop_saves_session(self, mock_playwright_sync, tmp_path):
        """Test that stop() saves storage state."""
        # Setup mocks
        mock_playwright_instance = MagicMock()
        mock_playwright_sync.return_value.start.return_value = mock_playwright_instance
        mock_browser = MagicMock()
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_context = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_page.url = "https://www.linkedin.com/feed/"  # Non-login URL

        session_file = tmp_path / "session.json"

        manager = BrowserManager(session_path=session_file)
        manager.start()
        manager.stop()

        mock_context.storage_state.assert_called_with(path=str(session_file))
        mock_context.close.assert_called()
        mock_browser.close.assert_called()

    def test_goto_raises_if_not_started(self):
        """Test goto raises error if browser not started."""
        manager = BrowserManager()
        with pytest.raises(ScraperError, match="Browser not started"):
            manager.goto("http://example.com")

    @patch("src.ingest.browser_manager.sync_playwright")
    def test_start_exception(self, mock_playwright_sync):
        """Test that start() raises ScraperError on failure."""
        mock_playwright_sync.side_effect = Exception("Playwright Error")
        manager = BrowserManager()

        with pytest.raises(ScraperError, match="Failed to start browser"):
            manager.start()

    def test_goto_exception(self):
        """Test that goto() raises ScraperError on navigation failure."""
        manager = BrowserManager()
        # Mock attributes directly since we don't start it
        manager.page = MagicMock()
        manager.page.goto.side_effect = Exception("Nav Error")

        with pytest.raises(ScraperError, match="Failed to navigate"):
            manager.goto("http://example.com")

    def test_context_manager(self):
        """Test that BrowserManager works as a context manager."""
        with patch.object(BrowserManager, "start") as mock_start, patch.object(BrowserManager, "stop") as mock_stop:
            with BrowserManager():
                pass

            mock_start.assert_called_once()
            mock_stop.assert_called_once()

    @patch("src.ingest.browser_manager.sync_playwright")
    def test_login_manual_already_logged_in(self, mock_playwright, tmp_path):
        """Test login_manual exits early if already logged in."""
        manager = BrowserManager(session_path=tmp_path / "session.json")

        # Setup mocks
        mock_page = MagicMock()
        # Mock success selector found
        mock_page.locator.return_value.count.return_value = 1

        with patch.object(manager, "start"), patch.object(manager, "goto"), patch.object(manager, "page", mock_page):
            manager.login_manual()

            # verify we checked for login
            mock_page.locator.assert_called_with(".global-nav")

    @patch("src.ingest.browser_manager.sync_playwright")
    def test_login_manual_wait_for_login(self, mock_playwright, tmp_path):
        """Test login_manual waits for user to login."""
        manager = BrowserManager(session_path=tmp_path / "session.json")

        # Setup mocks
        mock_page = MagicMock()
        mock_context = MagicMock()
        manager.context = mock_context

        # Mock success selector NOT found initially
        mock_page.locator.return_value.count.return_value = 0

        with patch.object(manager, "start"), patch.object(manager, "goto"), patch.object(manager, "page", mock_page):
            manager.login_manual()

            # verify we waited for login
            mock_page.wait_for_selector.assert_called_with(".global-nav", timeout=300000)
            # verify we saved state
            mock_context.storage_state.assert_called()

    @patch("src.ingest.browser_manager.sync_playwright")
    def test_login_manual_timeout(self, mock_playwright):
        """Test login_manual raises error on timeout."""
        manager = BrowserManager()

        # Setup mocks
        mock_page = MagicMock()
        mock_page.locator.return_value.count.return_value = 0
        mock_page.wait_for_selector.side_effect = Exception("Timeout")

        with patch.object(manager, "start"), patch.object(manager, "goto"), patch.object(manager, "page", mock_page):
            with pytest.raises(ScraperError, match="Login timeout"):
                manager.login_manual()

    @patch("src.ingest.browser_manager.sync_playwright")
    def test_stop_skips_save_on_login_page(self, mock_playwright_sync, tmp_path):
        """Test that stop() skips saving state if on a login page."""
        # Setup mocks
        mock_playwright_instance = MagicMock()
        mock_playwright_sync.return_value.start.return_value = mock_playwright_instance
        mock_browser = MagicMock()
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_context = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page

        # Mock being on a login page
        mock_page.url = "https://www.linkedin.com/login"

        session_file = tmp_path / "session.json"

        manager = BrowserManager(session_path=session_file)
        manager.start()
        manager.stop()

        # storage_state should NOT have been called
        mock_context.storage_state.assert_not_called()
        mock_context.close.assert_called()
        mock_browser.close.assert_called()

    def test_stop_no_errors(self):
        """Test stop handles component teardown safely."""
        manager = BrowserManager()
        # No components initialized
        manager.stop()  # Should not raise

        # Partially initialized
        manager.context = MagicMock()
        manager.context.close.side_effect = Exception("Close error")  # Should be caught/logged

        manager.stop()  # Should not raise
