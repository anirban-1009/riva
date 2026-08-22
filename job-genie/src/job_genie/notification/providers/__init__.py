from typing import Any

from .base import EmailProvider
from .smtp import GmailProvider, OutlookProvider, SMTPProvider


def get_provider(provider_type: str, config: dict[str, Any]) -> EmailProvider:
    """
    Factory function to get an email provider.

    Args:
        provider_type: Type of provider ('gmail', 'outlook', 'smtp').
        config: Configuration dictionary for the provider.

    Returns:
        EmailProvider instance.
    """
    providers: dict[str, type[EmailProvider]] = {
        "gmail": GmailProvider,
        "outlook": OutlookProvider,
        "smtp": SMTPProvider,
    }

    provider_class = providers.get(provider_type.lower(), SMTPProvider)
    return provider_class(config)


__all__ = ["EmailProvider", "GmailProvider", "OutlookProvider", "SMTPProvider", "get_provider"]
