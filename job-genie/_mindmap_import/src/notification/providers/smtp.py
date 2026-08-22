import smtplib
from email.mime.multipart import MIMEMultipart
from typing import Any, Dict

from src.utils.logger import get_logger

from .base import EmailProvider

logger = get_logger(__name__)


class SMTPProvider(EmailProvider):
    """Generic SMTP email provider."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize the SMTP provider.

        Args:
            config: Dictionary containing 'smtp_server', 'smtp_port', 'smtp_user', and 'smtp_password'.
        """
        super().__init__(config)
        self.server = config.get("smtp_server")
        self.port = config.get("smtp_port", 587)
        self.user = config.get("smtp_user")
        self.password = config.get("smtp_password")

    def send(self, msg: MIMEMultipart) -> bool:
        """
        Send an email message via SMTP.

        Args:
            msg: The MIMEMultipart message to send.

        Returns:
            bool: True if sent successfully, False otherwise.
        """
        if not all([self.server, self.user, self.password]):
            logger.error("SMTP configuration incomplete.")
            return False

        try:
            with smtplib.SMTP(self.server, self.port) as server:
                server.starttls()
                server.login(self.user, self.password)
                server.send_message(msg)
            return True
        except Exception as e:
            logger.error(f"SMTP error: {e}")
            return False


class GmailProvider(SMTPProvider):
    """Gmail-specific provider using pre-set SMTP settings."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize the Gmail provider with default Gmail SMTP settings.

        Args:
            config: Configuration dictionary for SMTP user and password.
        """
        # Force Gmail SMTP settings if not provided
        config.setdefault("smtp_server", "smtp.gmail.com")
        config.setdefault("smtp_port", 587)
        super().__init__(config)


class OutlookProvider(SMTPProvider):
    """Outlook/Office365-specific provider using pre-set SMTP settings."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize the Outlook provider with default Outlook SMTP settings.

        Args:
            config: Configuration dictionary for SMTP user and password.
        """
        # Force Outlook SMTP settings if not provided
        config.setdefault("smtp_server", "smtp.office365.com")
        config.setdefault("smtp_port", 587)
        super().__init__(config)
