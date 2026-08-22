from typing import Any, Dict
from unittest.mock import MagicMock, patch

from src.notification.providers.smtp import GmailProvider, OutlookProvider, SMTPProvider


class TestSMTPProvider:
    """Tests for the generic SMTPProvider."""

    def test_smtp_provider_init(self) -> None:
        """Verify SMTPProvider correctly initializes with configuration."""
        config: Dict[str, Any] = {
            "smtp_server": "smtp.example.com",
            "smtp_port": 587,
            "smtp_user": "user@example.com",
            "smtp_password": "password",
        }
        provider = SMTPProvider(config)
        assert provider.server == "smtp.example.com"
        assert provider.port == 587
        assert provider.user == "user@example.com"
        assert provider.password == "password"

    @patch("smtplib.SMTP")
    def test_smtp_provider_send(self, mock_smtp_class: MagicMock) -> None:
        """Verify SMTPProvider calls smtplib with correct parameters."""
        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp

        config: Dict[str, Any] = {
            "smtp_server": "smtp.example.com",
            "smtp_user": "user@example.com",
            "smtp_password": "password",
        }
        provider = SMTPProvider(config)
        msg = MagicMock()

        assert provider.send(msg) is True
        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with("user@example.com", "password")
        mock_smtp.send_message.assert_called_once_with(msg)


class TestGmailProvider:
    """Tests for the GmailProvider."""

    def test_gmail_provider_defaults(self) -> None:
        """Verify GmailProvider uses correct default SMTP settings."""
        config: Dict[str, Any] = {"smtp_user": "user@gmail.com", "smtp_password": "app_password"}
        provider = GmailProvider(config)
        assert provider.server == "smtp.gmail.com"
        assert provider.port == 587


class TestOutlookProvider:
    """Tests for the OutlookProvider."""

    def test_outlook_provider_defaults(self) -> None:
        """Verify OutlookProvider uses correct default SMTP settings."""
        config: Dict[str, Any] = {"smtp_user": "user@outlook.com", "smtp_password": "password"}
        provider = OutlookProvider(config)
        assert provider.server == "smtp.office365.com"
        assert provider.port == 587
