import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List

from jinja2 import Environment, FileSystemLoader

from src.notification.providers import get_provider
from src.utils.logger import get_logger

logger = get_logger(__name__)


class EmailService:
    """Service to handle sending email notifications."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize the email service with configuration.

        Args:
            config: The full project configuration dictionary.
        """
        self.config = config
        self.email_config = config.get("notifications", {}).get("email", {})
        self.user_config = config.get("user", {})

        self.enabled = self.email_config.get("enabled", False)
        self.provider_type = self.email_config.get("provider", "smtp")

        # Resolve all secrets in the email config before passing to provider
        resolved_config = self.email_config.copy()
        for key, value in resolved_config.items():
            if isinstance(value, str):
                resolved_config[key] = self._resolve_secret(value)

        self.provider = get_provider(self.provider_type, resolved_config)

        self.recipient_email = self.user_config.get("email")
        self.user_name = self.user_config.get("full_name", "User")
        self.from_email = resolved_config.get("smtp_user")

        # Setup Jinja2 environment
        template_dir = Path(__file__).parent / "templates"
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def _resolve_secret(self, value: str) -> str:
        """
        Resolves secrets from environment variables if in ${VAR} format.

        Args:
            value: The string to resolve.

        Returns:
            str: The resolved secret or the original value.
        """
        if value and isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            env_var = value[2:-1]
            return os.getenv(env_var, "")
        return value

    def send_job_digest(self, scored_jobs: List[Dict[str, Any]]) -> bool:
        """
        Generates and sends an HTML email digest of scored jobs.

        Args:
            scored_jobs: List of dictionaries containing 'job' (JobDetails) and 'score' (ScoringResult).

        Returns:
            bool: True if sent successfully (or disabled), False otherwise.
        """
        if not self.enabled:
            logger.info("Email notifications are disabled.")
            return True

        if not scored_jobs:
            logger.info("No jobs to include in the digest.")
            return True

        if not self.recipient_email:
            logger.error("No recipient email found in configuration.")
            return False

        try:
            # Prepare message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"Job Digest: {len(scored_jobs)} New Matches Found"
            msg["From"] = self.from_email
            msg["To"] = self.recipient_email

            # Render HTML
            template = self.jinja_env.get_template("job_digest.html.j2")
            html_content = template.render(user_name=self.user_name, jobs=scored_jobs)

            # Add body parts
            text_fallback = f"Hi {self.user_name},\n\nYou have {len(scored_jobs)} new job matches."
            msg.attach(MIMEText(text_fallback, "plain"))
            msg.attach(MIMEText(html_content, "html"))

            # Send via Provider
            logger.info(f"Sending email digest via {self.provider_type} to {self.recipient_email}...")
            return self.provider.send(msg)

        except Exception as e:
            logger.error(f"Failed to send email digest: {e}")
            return False
