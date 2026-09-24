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
        think: Any = None,
        extra: dict[str, Any] | None = None,
    ) -> str: ...

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: Any = None,
        extra: dict[str, Any] | None = None,
    ) -> AsyncGenerator[Any, None]: ...

    async def get_capabilities(self, model: str) -> list[str]: ...

    async def list_models(self) -> list[str]: ...


def inject_concise_thinking_instruction(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Inject a concise reasoning instruction into the system turn."""
    concise_prompt = "Keep your thinking concise: maximum 2-3 brief sentences before answering."
    msgs = [dict(m) for m in messages]
    for msg in msgs:
        if msg.get("role") == "system":
            content = msg.get("content", "")
            if concise_prompt not in content:
                msg["content"] = f"{content}\n{concise_prompt}".strip()
            return msgs
    return [{"role": "system", "content": concise_prompt}] + msgs


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

    @classmethod
    def _get_client(cls) -> httpx.AsyncClient:
        """Return the process-wide shared client, instantiating it if necessary."""
        if cls._shared_client is None or cls._shared_client.is_closed:
            cls._shared_client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)
        return cls._shared_client

    @classmethod
    async def close(cls) -> None:
        """Close the shared client, releasing any pooled connections."""
        if cls._shared_client is not None and not cls._shared_client.is_closed:
            await cls._shared_client.aclose()
        cls._shared_client = None

    @staticmethod
    def _build_options(
        temperature: float | None,
        max_tokens: int | None,
        extra: dict[str, Any] | None,
    ) -> dict[str, Any]:
        options: dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        if extra:
            options.update(extra)
        return options

    @classmethod
    def _build_payload(
        cls,
        model: str,
        messages: list[dict[str, str]],
        stream: bool,
        options: dict[str, Any] | None,
        think: Any = None,
    ) -> dict[str, Any]:
        msgs = list(messages)
        payload: dict[str, Any] = {
            "model": model,
            "messages": msgs,
            "stream": stream,
            "keep_alive": _DEFAULT_KEEP_ALIVE,
        }
        if options:
            payload["options"] = options
        if think is not None:
            effort_val = think.value if hasattr(think, "value") else str(think).lower()
            if effort_val in ("none", "false"):
                payload["think"] = False
            elif effort_val == "low":
                payload["think"] = True
                payload["messages"] = inject_concise_thinking_instruction(msgs)
            else:
                payload["think"] = True
        return payload

    async def get_capabilities(self, model: str) -> list[str]:
        """Return Ollama's reported capabilities for `model` (e.g. ["completion", "tools", "thinking"])."""
        now = time.monotonic()
        cls = self.__class__
        if (
            cls._capabilities_cache is not None
            and (now - cls._capabilities_cache_at) < _CAPABILITIES_TTL_S
            and model in cls._capabilities_cache
        ):
            return cls._capabilities_cache[model]

        client = self._get_client()
        url = f"{self.base_url}/api/tags"
        try:
            response = await client.get(url)
            response.raise_for_status()
            cache: dict[str, list[str]] = {}
            for item in response.json().get("models", []):
                name = item.get("name")
                if not name:
                    continue
                caps: list[str] = [
                    k for k, v in item.get("capabilities", {}).items() if v
                ]
                cache[name] = caps
                if ":" in name:
                    cache[name.split(":")[0]] = caps
            cls._capabilities_cache = cache
            cls._capabilities_cache_at = now
            return cache.get(model, [])
        except httpx.HTTPError:
            if cls._capabilities_cache is not None and model in cls._capabilities_cache:
                return cls._capabilities_cache[model]
            return []

    async def list_models(self) -> list[str]:
        """Return model names available in Ollama, via GET /api/tags."""
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
        think: Any = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        """Send a chat prompt to Ollama synchronously and return the assistant response."""
        url = f"{self.base_url}/api/chat"
        options = self._build_options(temperature, max_tokens, extra)
        payload = self._build_payload(self.model, messages, False, options, think)

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
        think: Any = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        """Send a chat prompt to Ollama asynchronously and return the response."""
        client = self._get_client()
        url = f"{self.base_url}/api/chat"
        options = self._build_options(temperature, max_tokens, extra)
        payload = self._build_payload(self.model, messages, False, options, think)

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
        think: Any = None,
        extra: dict[str, Any] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream chat tokens from Ollama asynchronously."""
        client = self._get_client()
        url = f"{self.base_url}/api/chat"
        options = self._build_options(temperature, max_tokens, extra)
        payload = self._build_payload(self.model, messages, True, options, think)

        try:
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    msg = chunk.get("message", {})
                    thinking = msg.get("thinking")
                    content = msg.get("content")
                    if thinking:
                        yield ("reasoning", thinking)
                    if content:
                        yield ("content", content)
        except httpx.HTTPError as e:
            raise RuntimeError(f"Ollama stream request failed: {e}") from e


class OpenAICompatibleProvider:
    """Provider for any backend that speaks the OpenAI `/chat/completions` wire
    protocol: vLLM, LMDeploy, llama.cpp server, mlx-lm, or OpenAI itself.
    """

    _shared_client: ClassVar[httpx.AsyncClient | None] = None

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str = "default",
    ) -> None:
        self.base_url = (
            base_url
            or os.getenv("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        ).rstrip("/")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model

    @classmethod
    def _get_client(cls) -> httpx.AsyncClient:
        if cls._shared_client is None or cls._shared_client.is_closed:
            cls._shared_client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)
        return cls._shared_client

    @classmethod
    async def close(cls) -> None:
        if cls._shared_client is not None and not cls._shared_client.is_closed:
            await cls._shared_client.aclose()
        cls._shared_client = None

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    @classmethod
    def _build_payload(
        cls,
        model: str,
        messages: list[dict[str, str]],
        stream: bool,
        temperature: float | None,
        max_tokens: int | None,
        think: Any = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        msgs = list(messages)
        payload: dict[str, Any] = {"model": model, "messages": msgs, "stream": stream}
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        if think is not None:
            effort_val = think.value if hasattr(think, "value") else str(think).lower()
            if effort_val in ("none", "false"):
                payload["chat_template_kwargs"] = {"enable_thinking": False}
            elif effort_val == "low":
                payload["chat_template_kwargs"] = {"enable_thinking": True}
                payload["reasoning_effort"] = "low"
                payload["messages"] = inject_concise_thinking_instruction(msgs)
            elif effort_val in ("high", "true"):
                payload["chat_template_kwargs"] = {"enable_thinking": True}
                payload["reasoning_effort"] = "high"

        if extra:
            payload.update(extra)
        return payload

    async def get_capabilities(self, model: str) -> list[str]:
        """OpenAI-compatible APIs don't expose a capabilities endpoint.
        Returns ['thinking', 'completion'] so that thinking router decisions
        are forwarded for thinking-capable engines (like MLX server).
        """
        del model
        return ["thinking", "completion"]

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
        think: Any = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        """Send a chat prompt synchronously and return the assistant response."""
        url = f"{self.base_url}/chat/completions"
        payload = self._build_payload(
            self.model, messages, False, temperature, max_tokens, think, extra
        )

        with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
            try:
                response = client.post(url, json=payload, headers=self._auth_headers())
                response.raise_for_status()
                resp_data = response.json()
                msg = resp_data["choices"][0]["message"]
                return str(msg.get("content") or "")
            except httpx.HTTPError as e:
                raise RuntimeError(f"OpenAI-compatible request failed: {e}") from e

    async def chat_async(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: Any = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        """Send a chat prompt asynchronously and return the assistant response."""
        client = self._get_client()
        url = f"{self.base_url}/chat/completions"
        payload = self._build_payload(
            self.model, messages, False, temperature, max_tokens, think, extra
        )

        try:
            response = await client.post(url, json=payload, headers=self._auth_headers())
            response.raise_for_status()
            resp_data = response.json()
            msg = resp_data["choices"][0]["message"]
            return str(msg.get("content") or "")
        except httpx.HTTPError as e:
            raise RuntimeError(f"OpenAI-compatible request failed: {e}") from e

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: Any = None,
        extra: dict[str, Any] | None = None,
    ) -> AsyncGenerator[Any, None]:
        """Stream chat tokens asynchronously, parsing the OpenAI SSE format."""
        client = self._get_client()
        url = f"{self.base_url}/chat/completions"
        payload = self._build_payload(
            self.model, messages, True, temperature, max_tokens, think, extra
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
                    delta = choices[0].get("delta", {})
                    reasoning = delta.get("reasoning") or delta.get("reasoning_content")
                    content = delta.get("content")
                    if reasoning:
                        yield ("reasoning", reasoning)
                    if content:
                        yield ("content", content)
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
