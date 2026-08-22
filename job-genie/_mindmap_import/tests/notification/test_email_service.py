from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from src.notification.email_service import EmailService


@pytest.fixture
def mock_config() -> Dict[str, Any]:
    """Fixture for project configuration."""
    return {
        "notifications": {
            "email": {
                "enabled": True,
                "smtp_server": "smtp.test.com",
                "smtp_port": 587,
                "smtp_user": "test@user.com",
                "smtp_password": "password",
            }
        },
        "user": {"email": "recipient@target.com", "full_name": "Test Recipient"},
    }


@pytest.fixture
def sample_scored_jobs() -> List[Dict[str, Any]]:
    """Fixture for scored job data."""
    return [
        {
            "job": MagicMock(title="Software Engineer", company="Tech Co", location="Remote", link="http://job.com/1"),
            "score": MagicMock(score=85, key_matches=["Python", "Unit Testing"], reasoning="Great fit!"),
        }
    ]


class TestEmailService:
    """Tests for the EmailService class."""

    @patch("smtplib.SMTP")
    def test_send_job_digest_success(
        self, mock_smtp_class: MagicMock, mock_config: Dict[str, Any], sample_scored_jobs: List[Dict[str, Any]]
    ) -> None:
        """Verify successful generation and sending of a job digest email."""
        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp

        service = EmailService(mock_config)
        result = service.send_job_digest(sample_scored_jobs)

        assert result is True
        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with("test@user.com", "password")
        mock_smtp.send_message.assert_called_once()

        # Check if recipient is correct in the sent message
        args, _ = mock_smtp.send_message.call_args
        sent_msg = args[0]
        assert sent_msg["To"] == "recipient@target.com"
        assert "Job Digest" in sent_msg["Subject"]

    def test_disabled_service(self, mock_config: Dict[str, Any]) -> None:
        """Verify EmailService returns early if disabled in configuration."""
        mock_config["notifications"]["email"]["enabled"] = False
        service = EmailService(mock_config)

        result = service.send_job_digest([{"dummy": "data"}])
        assert result is True  # Should return True as it 'succeeded' in doing nothing

    @patch("smtplib.SMTP")
    def test_missing_recipient(
        self, mock_smtp_class: MagicMock, mock_config: Dict[str, Any], sample_scored_jobs: List[Dict[str, Any]]
    ) -> None:
        """Verify EmailService handles missing recipient email gracefully."""
        mock_config["user"]["email"] = None
        service = EmailService(mock_config)

        result = service.send_job_digest(sample_scored_jobs)
        assert result is False
        mock_smtp_class.assert_not_called()

    @patch("smtplib.SMTP")
    def test_smtp_error(
        self, mock_smtp_class: MagicMock, mock_config: Dict[str, Any], sample_scored_jobs: List[Dict[str, Any]]
    ) -> None:
        """Verify EmailService handles SMTP errors gracefully."""
        mock_smtp = MagicMock()
        mock_smtp.login.side_effect = Exception("SMTP Auth Failed")
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp

        service = EmailService(mock_config)
        result = service.send_job_digest(sample_scored_jobs)

        assert result is False
