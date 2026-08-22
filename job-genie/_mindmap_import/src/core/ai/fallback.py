from typing import List, Optional

from src.core.ai.base import LLMClient
from src.utils.logger import get_logger

logger = get_logger(__name__)


class FallbackClient(LLMClient):
    """Client that tries multiple providers in order if one fails."""

    def __init__(self, clients: List[LLMClient]):
        """
        Initialize with a list of clients.

        Args:
            clients: Ordered list of LLMClient instances.
        """
        self.clients = clients

    def generate(self, prompt: str, system_instruction: Optional[str] = None, max_tokens: Optional[int] = None) -> str:
        """
        Tries each client in order until one succeeds.
        """
        for client in self.clients:
            try:
                response = client.generate(prompt, system_instruction, max_tokens=max_tokens)
                if response:
                    return response
            except Exception as e:
                logger.warning(f"Provider {client.__class__.__name__} failed: {e}")
                continue

        logger.error("All LLM providers failed.")
        return ""

    def embed(self, text: str) -> List[float]:
        """
        Tries each client in order until one returns a non-empty embedding.
        """
        for client in self.clients:
            try:
                embedding = client.embed(text)
                if embedding:
                    return embedding
            except Exception as e:
                logger.warning(f"Provider {client.__class__.__name__} failed to embed: {e}")
                continue

        logger.error("All LLM providers failed to produce an embedding.")
        return []
