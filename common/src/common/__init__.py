from common.llm.providers import (
    LLMProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    create_provider,
)
from common.llm.manager import LLMManager

__all__ = [
    "LLMProvider",
    "OllamaProvider",
    "OpenAICompatibleProvider",
    "create_provider",
    "LLMManager",
]

def main() -> None:
    """Print a greeting from the common package."""
    print("Hello from common!")
