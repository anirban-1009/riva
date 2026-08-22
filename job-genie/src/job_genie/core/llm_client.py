"""
Backward compatibility module for LLM clients.
New code should import from job_genie.core.ai instead.
"""

from job_genie.core.ai import FallbackClient, GeminiClient, LLMClient, OllamaClient, get_llm_client

__all__ = ["FallbackClient", "GeminiClient", "LLMClient", "OllamaClient", "get_llm_client"]
