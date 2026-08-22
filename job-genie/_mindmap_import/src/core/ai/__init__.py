import os
from typing import Any, Dict

from src.core.ai.base import LLMClient
from src.core.ai.fallback import FallbackClient
from src.core.ai.gemini import GeminiClient
from src.core.ai.ollama import OllamaClient
from src.utils.logger import get_logger

logger = get_logger(__name__)


def get_llm_client(config: Dict[str, Any]) -> LLMClient:
    """
    Factory function to create an LLM client based on configuration.
    Supports a 'fallback' provider which tries Gemini then Ollama.

    Args:
        config: The 'ai' section of the config dictionary.

    Returns:
        LLMClient: An instance of either GeminiClient, OllamaClient, or FallbackClient.
    """
    provider = config.get("provider", "gemini").lower()

    def create_gemini():
        gemini_cfg = config.get("gemini", {})
        api_key = config.get("gemini_api_key") or gemini_cfg.get("api_key")
        if api_key and isinstance(api_key, str) and api_key.startswith("${") and api_key.endswith("}"):
            env_var = api_key[2:-1]
            api_key = os.getenv(env_var)

        model_name = config.get("model_name") or gemini_cfg.get("model_name", "gemini-2.0-flash-exp")
        embedding_model = gemini_cfg.get("embedding_model", "text-embedding-004")
        if not api_key:
            raise ValueError("Gemini API Key is missing.")
        return GeminiClient(api_key=api_key, model_name=model_name, embedding_model=embedding_model)

    def create_ollama():
        ollama_config = config.get("ollama", {})
        model_name = ollama_config.get("model_name", "llama3.2:latest")
        base_url = ollama_config.get("base_url", "http://localhost:11434")
        embedding_model = ollama_config.get("embedding_model", "nomic-embed-text")
        return OllamaClient(model_name=model_name, base_url=base_url, embedding_model=embedding_model)

    if provider == "gemini":
        try:
            return create_gemini()
        except ValueError as e:
            logger.warning(f"Failed to initialize Gemini: {e}")
            raise

    if provider == "ollama":
        return create_ollama()

    if provider == "auto" or provider == "fallback":
        clients = []
        # Try to add Gemini
        try:
            clients.append(create_gemini())
        except Exception as e:
            logger.info(f"Skipping Gemini in fallback mode: {e}")

        # Always add Ollama as backup if available
        clients.append(create_ollama())

        if not clients:
            raise ValueError("No LLM providers could be initialized.")

        return FallbackClient(clients) if len(clients) > 1 else clients[0]

    if provider == "mock":
        from unittest.mock import MagicMock

        return MagicMock(spec=LLMClient)

    raise ValueError(f"Unsupported LLM provider: {provider}")


# Re-export key classes for convenience
__all__ = ["LLMClient", "GeminiClient", "OllamaClient", "FallbackClient", "get_llm_client"]
