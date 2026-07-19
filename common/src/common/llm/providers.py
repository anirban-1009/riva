import asyncio
import json
import urllib.request
import urllib.error
from typing import Any

class OllamaProvider:
    """Provider for communicating with a local Ollama instance."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "gemma") -> None:
        """Initialize the Ollama provider with base URL and model name."""
        self.base_url = base_url
        self.model = model

    def chat(self, messages: list[dict[str, str]], options: dict[str, Any] | None = None) -> str:
        """Send a chat prompt to Ollama and return the assistant response."""
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False
        }
        if options:
            payload["options"] = options

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req) as response:
                resp_data = json.loads(response.read().decode("utf-8"))
                return str(resp_data["message"]["content"])
        except urllib.error.URLError as e:
            raise RuntimeError(f"Failed to connect to Ollama at {self.base_url}: {e}") from e

    async def chat_async(self, messages: list[dict[str, str]], options: dict[str, Any] | None = None) -> str:
        """Send an asynchronous chat prompt to Ollama."""
        return await asyncio.to_thread(self.chat, messages, options)
