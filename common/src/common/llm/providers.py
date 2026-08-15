import json
import os
import time
from typing import Any, AsyncGenerator, ClassVar, Protocol, runtime_checkable

import httpx

# Local models can take minutes to generate, but should still fail fast if
# the backend is unreachable. Read gets the long budget; connect/write/pool don't.
_REQUEST_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)

# How long Ollama keeps a model resident in memory after the last request.
# Ollama's own default (5m) is short enough that a normal back-and-forth
# conversation can force a full model reload between turns.
_DEFAULT_KEEP_ALIVE = "30m"

# How long to trust a cached /api/tags capabilities lookup before refreshing.
_CAPABILITIES_TTL_S = 300.0


@runtime_checkable
class LLMProvider(Protocol):
    """Common interface every backend (Ollama, OpenAI-compatible, ...) implements.

    Params are the lowest common denominator across backends: `temperature`
    and `max_tokens` are translated into whatever shape the wire protocol
    expects, `think` is a no-op on backends without a reasoning toggle, and
    `extra` is an escape hatch for passing provider-native fields straight
    through without widening this interface.
    """

    model: str

    async def chat_async(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: bool | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str: ...

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: bool | None = None,
        extra: dict[str, Any] | None = None,
    ) -> AsyncGenerator[str, None]: ...

    async def get_capabilities(self, model: str) -> list[str]: ...

    async def list_models(self) -> list[str]: ...


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

    @staticmethod
    def _build_options(
        temperature: float | None,
        max_tokens: int | None,
        extra: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Translate the common param names into Ollama's `options` shape."""
        options = dict(extra) if extra else {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        return options

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

    async def list_models(self) -> list[str]:
        """Return the names of models installed in this Ollama instance."""
        client = self._get_client()
        response = await client.get(f"{self.base_url}/api/tags")
        response.raise_for_status()
        return [m["name"] for m in response.json().get("models", [])]

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: bool | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        """Send a chat prompt to Ollama synchronously and return the assistant response."""
        url = f"{self.base_url}/api/chat"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": _DEFAULT_KEEP_ALIVE,
        }
        options = self._build_options(temperature, max_tokens, extra)
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
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: bool | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        """Send a chat prompt to Ollama asynchronously and return the response."""
        client = self._get_client()
        url = f"{self.base_url}/api/chat"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": _DEFAULT_KEEP_ALIVE,
        }
        options = self._build_options(temperature, max_tokens, extra)
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
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: bool | None = None,
        extra: dict[str, Any] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream chat tokens from Ollama asynchronously."""
        client = self._get_client()
        url = f"{self.base_url}/api/chat"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "keep_alive": _DEFAULT_KEEP_ALIVE,
        }
        options = self._build_options(temperature, max_tokens, extra)
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


class OpenAICompatibleProvider:
    """Provider for any backend that speaks the OpenAI `/chat/completions` wire
    protocol: OpenAI itself, Groq, OpenRouter, Together, or a self-hosted
    vLLM/LM Studio/llama.cpp server.

    `base_url` defaults to OpenAI's API but is meant to be overridden (via
    the constructor or OPENAI_BASE_URL) to point at any compatible endpoint.
    """

    _shared_client: ClassVar[httpx.AsyncClient | None] = None

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
    ) -> None:
        """Initialize with base URL, API key, and model name, all overridable via env vars."""
        self.base_url = (
            base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        ).rstrip("/")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model

    def _get_client(self) -> httpx.AsyncClient:
        """Lazy-initialize and return the shared, connection-pooled AsyncClient.

        Auth isn't baked into the client's default headers because it's shared
        across every instance of this class; each request attaches its own
        instance's API key instead, so multiple instances with different keys
        can safely reuse the same connection pool.
        """
        cls = OpenAICompatibleProvider
        if cls._shared_client is None or cls._shared_client.is_closed:
            cls._shared_client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)
        return cls._shared_client

    @classmethod
    async def close(cls) -> None:
        """Close the shared HTTP client session."""
        if cls._shared_client and not cls._shared_client.is_closed:
            await cls._shared_client.aclose()
        cls._shared_client = None

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    @staticmethod
    def _build_payload(
        model: str,
        messages: list[dict[str, str]],
        stream: bool,
        temperature: float | None,
        max_tokens: int | None,
        extra: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": stream}
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if extra:
            payload.update(extra)
        return payload

    async def get_capabilities(self, model: str) -> list[str]:
        """OpenAI-compatible APIs don't expose a capabilities endpoint.

        Always returns []; callers should treat that as "no capability info
        available" rather than "this model supports nothing", and skip
        fields (like Ollama's `think`) that only some backends understand.
        """
        del model  # required by LLMProvider; this backend has no per-model lookup
        return []

    async def list_models(self) -> list[str]:
        """Return model ids available on this endpoint, via the standard GET /models."""
        client = self._get_client()
        response = await client.get(
            f"{self.base_url}/models", headers=self._auth_headers()
        )
        response.raise_for_status()
        return [m["id"] for m in response.json().get("data", [])]

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: bool | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        """Send a chat prompt synchronously and return the assistant response."""
        del think  # required by LLMProvider; no equivalent in the OpenAI wire format
        url = f"{self.base_url}/chat/completions"
        payload = self._build_payload(
            self.model, messages, False, temperature, max_tokens, extra
        )

        with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
            try:
                response = client.post(url, json=payload, headers=self._auth_headers())
                response.raise_for_status()
                resp_data = response.json()
                return str(resp_data["choices"][0]["message"]["content"])
            except httpx.HTTPError as e:
                raise RuntimeError(f"OpenAI-compatible request failed: {e}") from e

    async def chat_async(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: bool | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        """Send a chat prompt asynchronously and return the assistant response."""
        del think  # required by LLMProvider; no equivalent in the OpenAI wire format
        client = self._get_client()
        url = f"{self.base_url}/chat/completions"
        payload = self._build_payload(
            self.model, messages, False, temperature, max_tokens, extra
        )

        try:
            response = await client.post(url, json=payload, headers=self._auth_headers())
            response.raise_for_status()
            resp_data = response.json()
            return str(resp_data["choices"][0]["message"]["content"])
        except httpx.HTTPError as e:
            raise RuntimeError(f"OpenAI-compatible request failed: {e}") from e

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: bool | None = None,
        extra: dict[str, Any] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream chat tokens asynchronously, parsing the OpenAI SSE format."""
        del think  # required by LLMProvider; no equivalent in the OpenAI wire format
        client = self._get_client()
        url = f"{self.base_url}/chat/completions"
        payload = self._build_payload(
            self.model, messages, True, temperature, max_tokens, extra
        )

        try:
            async with client.stream(
                "POST", url, json=payload, headers=self._auth_headers()
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[len("data: ") :]
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    choices = chunk.get("choices") or [{}]
                    content = choices[0].get("delta", {}).get("content")
                    if content:
                        yield content
        except httpx.HTTPError as e:
            raise RuntimeError(f"OpenAI-compatible stream request failed: {e}") from e


_PROVIDERS: dict[str, type[LLMProvider]] = {
    "ollama": OllamaProvider,
    "openai": OpenAICompatibleProvider,
}


def create_provider(
    name: str,
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> LLMProvider:
    """Instantiate the named backend ("ollama" or "openai") with optional overrides.

    `api_key` is silently dropped for backends that don't accept one (e.g.
    Ollama) so callers can pass it unconditionally without checking which
    backend is active.
    """
    try:
        cls = _PROVIDERS[name.lower()]
    except KeyError:
        raise ValueError(
            f"Unknown LLM provider {name!r}; expected one of {sorted(_PROVIDERS)}"
        ) from None
    kwargs: dict[str, Any] = {}
    if model:
        kwargs["model"] = model
    if base_url:
        kwargs["base_url"] = base_url
    if api_key and cls is OpenAICompatibleProvider:
        kwargs["api_key"] = api_key
    return cls(**kwargs)  # type: ignore[return-value]
