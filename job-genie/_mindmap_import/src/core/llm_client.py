"""
Backward compatibility module for LLM clients.
New code should import from src.core.ai instead.
"""

from src.core.ai import FallbackClient, GeminiClient, LLMClient, OllamaClient, get_llm_client

__all__ = ["LLMClient", "GeminiClient", "OllamaClient", "FallbackClient", "get_llm_client"]
