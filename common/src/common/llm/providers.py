import json
import os
import time
from typing import Any, AsyncGenerator, ClassVar

import httpx

# Local models can take minutes to generate, but should still fail fast if
# Ollama is unreachable. Read gets the long budget; connect/write/pool don't.
_REQUEST_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)

# How long Ollama keeps a model resident in memory after the last request.
# Ollama's own default (5m) is short enough that a normal back-and-forth
# conversation can force a full model reload between turns.
_DEFAULT_KEEP_ALIVE = "30m"

# How long to trust a cached /api/tags capabilities lookup before refreshing.
_CAPABILITIES_TTL_S = 300.0


class OllamaProvider:
    """Provider for communicating with a local Ollama instance."""

    # Shared across instances so every request reuses the same pooled
    # connections instead of paying TCP setup cost per request.
    _shared_client: ClassVar[httpx.AsyncClient | None] = None

    # Cache of model name -> Ollama-reported capabilities (e.g. ["completion",
    # "tools", "thinking"]), refreshed at most every _CAPABILITIES_TTL_S.
    _capabilities_cache: ClassVar[dict[str, list[str]] | None] = None
    _capabilities_cache_at: ClassVar[float] = 0.0

    def __init__(self, base_url: str | None = None, model: str = "gemma") -> None:
        """Initialize the Ollama provider with base URL and model name."""
        self.base_url = base_url or os.getenv(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        )
        self.model = model

    def _get_client(self) -> httpx.AsyncClient:
        """Lazy-initialize and return the shared, connection-pooled AsyncClient."""
        cls = OllamaProvider
        if cls._shared_client is None or cls._shared_client.is_closed:
            cls._shared_client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)
        return cls._shared_client

    @classmethod
    async def close(cls) -> None:
        """Close the shared HTTP client session."""
        if cls._shared_client and not cls._shared_client.is_closed:
            await cls._shared_client.aclose()
        cls._shared_client = None

    async def get_capabilities(self, model: str) -> list[str]:
        """Return Ollama's reported capabilities for `model` (e.g. ["completion", "tools", "thinking"]).

        Queried from /api/tags instead of guessed from the model name, so
        newly pulled or renamed models are handled correctly without a code
        change. Cached across all models for _CAPABILITIES_TTL_S since the
        installed model list rarely changes mid-session.
        """
        cls = OllamaProvider
        now = time.monotonic()
        if (
            cls._capabilities_cache is None
            or now - cls._capabilities_cache_at > _CAPABILITIES_TTL_S
        ):
            client = self._get_client()
            response = await client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            models = response.json().get("models", [])
            cls._capabilities_cache = {
                m["name"]: m.get("capabilities", []) for m in models
            }
            cls._capabilities_cache_at = now
        return cls._capabilities_cache.get(model, [])

    def chat(
        self,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
        think: bool | None = None,
    ) -> str:
        """Send a chat prompt to Ollama synchronously and return the assistant response."""
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": _DEFAULT_KEEP_ALIVE,
        }
        if options:
            payload["options"] = options
        if think is not None:
            payload["think"] = think

        with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
            try:
                response = client.post(url, json=payload)
                response.raise_for_status()
                resp_data = response.json()
                return str(resp_data["message"]["content"])
            except httpx.HTTPError as e:
                raise RuntimeError(f"Ollama request failed: {e}") from e

    async def chat_async(
        self,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
        think: bool | None = None,
    ) -> str:
        """Send a chat prompt to Ollama asynchronously and return the response."""
        client = self._get_client()
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": _DEFAULT_KEEP_ALIVE,
        }
        if options:
            payload["options"] = options
        if think is not None:
            payload["think"] = think

        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            resp_data = response.json()
            return str(resp_data["message"]["content"])
        except httpx.HTTPError as e:
            raise RuntimeError(f"Ollama request failed: {e}") from e

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
        think: bool | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream chat tokens from Ollama asynchronously."""
        client = self._get_client()
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "keep_alive": _DEFAULT_KEEP_ALIVE,
        }
        if options:
            payload["options"] = options
        if think is not None:
            payload["think"] = think

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
