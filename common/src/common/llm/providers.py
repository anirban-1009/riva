import asyncio
import json
from typing import Any, AsyncGenerator
import httpx

class OllamaProvider:
    """Provider for communicating with a local Ollama instance."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "gemma") -> None:
        """Initialize the Ollama provider with base URL and model name."""
        self.base_url = base_url
        self.model = model
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Lazy-initialize and return the connection-pooled AsyncClient."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client session."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def chat(self, messages: list[dict[str, str]], options: dict[str, Any] | None = None) -> str:
        """Send a chat prompt to Ollama synchronously and return the assistant response."""
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False
        }
        if options:
            payload["options"] = options

        with httpx.Client(timeout=60.0) as client:
            try:
                response = client.post(url, json=payload)
                response.raise_for_status()
                resp_data = response.json()
                return str(resp_data["message"]["content"])
            except httpx.HTTPError as e:
                raise RuntimeError(f"Ollama request failed: {e}") from e

    async def chat_async(self, messages: list[dict[str, str]], options: dict[str, Any] | None = None) -> str:
        """Send a chat prompt to Ollama asynchronously and return the response."""
        client = self._get_client()
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False
        }
        if options:
            payload["options"] = options

        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            resp_data = response.json()
            return str(resp_data["message"]["content"])
        except httpx.HTTPError as e:
            raise RuntimeError(f"Ollama request failed: {e}") from e

    async def chat_stream(self, messages: list[dict[str, str]], options: dict[str, Any] | None = None) -> AsyncGenerator[str, None]:
        """Stream chat tokens from Ollama asynchronously."""
        client = self._get_client()
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True
        }
        if options:
            payload["options"] = options

        try:
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content
        except httpx.HTTPError as e:
            raise RuntimeError(f"Ollama stream request failed: {e}") from e
