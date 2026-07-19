from typing import Any, AsyncGenerator
from common.llm.providers import OllamaProvider

class LLMManager:
    """Manages LLM queries and interfaces across the platform."""

    def __init__(self, provider: OllamaProvider) -> None:
        """Initialize the manager with a given model provider."""
        self.provider = provider

    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        """Generate a response for a single user prompt, optionally using a system prompt."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return await self.provider.chat_async(messages)

    async def generate_stream(self, prompt: str, system_prompt: str | None = None) -> AsyncGenerator[str, None]:
        """Stream a response for a single user prompt, optionally using a system prompt."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        async for token in self.provider.chat_stream(messages):
            yield token
