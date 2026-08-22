from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from typing import Any, Dict


class EmailProvider(ABC):
    """Abstract base class for email providers."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize the provider with configuration.

        Args:
            config: The provider-specific configuration.
        """
        self.config = config

    @abstractmethod
    def send(self, msg: MIMEMultipart) -> bool:
        """
        Send an email message.

        Args:
            msg: The MIMEMultipart message to send.

        Returns:
            bool: True if successful, False otherwise.
        """
        pass
