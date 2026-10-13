import hashlib
import math
import os
from typing import Any, ClassVar, Protocol, runtime_checkable

import httpx

try:
    import mlx.core as mx
    import mlx_lm
except ImportError:
    mlx_lm = None
    mx = None

_EMBED_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two float vectors.

    Returns a float in [-1.0, 1.0], or 0.0 if either vector has zero magnitude.
    """
    if len(vec1) != len(vec2):
        raise ValueError(f"Vector dimension mismatch: {len(vec1)} vs {len(vec2)}")

    dot = 0.0
    norm1_sq = 0.0
    norm2_sq = 0.0
    for a, b in zip(vec1, vec2):
        dot += a * b
        norm1_sq += a * a
        norm2_sq += b * b

    if norm1_sq <= 0.0 or norm2_sq <= 0.0:
        return 0.0

    return dot / (math.sqrt(norm1_sq) * math.sqrt(norm2_sq))


def cosine_distance(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine distance between two float vectors (1.0 - cosine_similarity).

    Returns a float typically in [0.0, 2.0].
    """
    return 1.0 - cosine_similarity(vec1, vec2)


class EmbeddingError(RuntimeError):
    """Raised when embedding generation fails."""


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for local vector embedding backends."""

    model: str
    dimension: int

    async def embed_query(self, text: str) -> list[float]:
        """Generate an embedding vector for a single query text."""
        ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for multiple document or memory texts."""
        ...

    async def close(self) -> None:
        """Close connection pools and release resources."""
        ...


class OllamaEmbeddingProvider:
    """Embedding provider connecting to a local Ollama instance (default: nomic-embed-text)."""

    _shared_client: ClassVar[httpx.AsyncClient | None] = None

    def __init__(
        self,
        base_url: str | None = None,
        model: str = "nomic-embed-text",
        dimension: int = 768,
        query_prefix: str | None = "search_query: ",
        doc_prefix: str | None = "search_document: ",
        batch_size: int = 32,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        raw_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.base_url = raw_url.rstrip("/")
        self.model = model
        self.dimension = dimension
        # Nomic-embed-text recommends asymmetric prefixes for queries vs documents
        self.query_prefix = query_prefix if query_prefix and "nomic" in model.lower() else (query_prefix or "")
        self.doc_prefix = doc_prefix if doc_prefix and "nomic" in model.lower() else (doc_prefix or "")
        self.batch_size = max(1, batch_size)
        self._client = client

    @classmethod
    def _get_client(cls) -> httpx.AsyncClient:
        if cls._shared_client is None or cls._shared_client.is_closed:
            cls._shared_client = httpx.AsyncClient(timeout=_EMBED_TIMEOUT)
        return cls._shared_client

    def _client_instance(self) -> httpx.AsyncClient:
        return self._client or self._get_client()

    @classmethod
    async def close(cls) -> None:
        if cls._shared_client is not None and not cls._shared_client.is_closed:
            await cls._shared_client.aclose()

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query, prepending query_prefix if configured."""
        clean_text = text.strip()
        if not clean_text:
            return [0.0] * self.dimension

        prefixed = f"{self.query_prefix}{clean_text}" if self.query_prefix else clean_text
        embeddings = await self._embed_batch([prefixed])
        return embeddings[0]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of document strings, prepending doc_prefix if configured."""
        if not texts:
            return []

        prefixed_texts = [
            f"{self.doc_prefix}{t.strip()}" if self.doc_prefix and t.strip() else t.strip() for t in texts
        ]

        results: list[list[float]] = []
        for i in range(0, len(prefixed_texts), self.batch_size):
            chunk = prefixed_texts[i : i + self.batch_size]
            chunk_embeddings = await self._embed_batch(chunk)
            results.extend(chunk_embeddings)

        return results

    async def _embed_batch(self, inputs: list[str]) -> list[list[float]]:
        # Handle all-empty inputs fast
        valid_indices = [idx for idx, text in enumerate(inputs) if text]
        if not valid_indices:
            return [[0.0] * self.dimension for _ in inputs]

        client = self._client_instance()
        url = f"{self.base_url}/api/embed"
        payload = {"model": self.model, "input": inputs}

        try:
            resp = await client.post(url, json=payload)
            if resp.status_code == 404:
                # Fall back to legacy endpoint /api/embeddings or /v1/embeddings
                return await self._fallback_embed(inputs)
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings", [])
            if not embeddings:
                raise EmbeddingError(f"Ollama returned empty embeddings response for model {self.model!r}")

            # Validate dimensions and pad empty inputs if necessary
            output: list[list[float]] = []
            for emb in embeddings:
                if len(emb) != self.dimension:
                    self.dimension = len(emb)  # Dynamic dimension alignment
                output.append(emb)
            return output

        except httpx.HTTPError as e:
            raise EmbeddingError(f"Failed to generate embeddings from Ollama at {url}: {e}") from e

    async def _fallback_embed(self, inputs: list[str]) -> list[list[float]]:
        """Fallback to OpenAI-compatible /v1/embeddings endpoint on Ollama."""
        client = self._client_instance()
        url = f"{self.base_url}/v1/embeddings"
        payload = {"model": self.model, "input": inputs}
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            items = sorted(data.get("data", []), key=lambda x: x.get("index", 0))
            embeddings = [item["embedding"] for item in items]
            if embeddings:
                self.dimension = len(embeddings[0])
            return embeddings
        except httpx.HTTPError as e:
            raise EmbeddingError(f"Ollama fallback embeddings failed at {url}: {e}") from e


class OpenAICompatibleEmbeddingProvider:
    """Embedding provider connecting to any local OpenAI-compatible embedding endpoint."""

    _shared_client: ClassVar[httpx.AsyncClient | None] = None

    def __init__(
        self,
        base_url: str | None = None,
        model: str = "text-embedding-nomic",
        dimension: int = 768,
        api_key: str | None = None,
        batch_size: int = 32,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        raw_url = base_url or os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
        self.base_url = raw_url.rstrip("/")
        self.model = model
        self.dimension = dimension
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.batch_size = max(1, batch_size)
        self._client = client

    @classmethod
    def _get_client(cls) -> httpx.AsyncClient:
        if cls._shared_client is None or cls._shared_client.is_closed:
            cls._shared_client = httpx.AsyncClient(timeout=_EMBED_TIMEOUT)
        return cls._shared_client

    def _client_instance(self) -> httpx.AsyncClient:
        return self._client or self._get_client()

    @classmethod
    async def close(cls) -> None:
        if cls._shared_client is not None and not cls._shared_client.is_closed:
            await cls._shared_client.aclose()

    async def embed_query(self, text: str) -> list[float]:
        clean = text.strip()
        if not clean:
            return [0.0] * self.dimension
        embeddings = await self.embed_documents([clean])
        return embeddings[0]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        client = self._client_instance()
        endpoint = f"{self.base_url}/embeddings"
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        results: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            chunk = [t.strip() for t in texts[i : i + self.batch_size]]
            payload = {"model": self.model, "input": chunk}
            try:
                resp = await client.post(endpoint, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                items = sorted(data.get("data", []), key=lambda x: x.get("index", 0))
                chunk_embeddings = [item["embedding"] for item in items]
                if chunk_embeddings and self.dimension != len(chunk_embeddings[0]):
                    self.dimension = len(chunk_embeddings[0])
                results.extend(chunk_embeddings)
            except httpx.HTTPError as e:
                raise EmbeddingError(f"OpenAI-compatible embedding request failed at {endpoint}: {e}") from e

        return results


class MLXEmbeddingProvider:
    """Embedding provider using mlx-lm for local Apple Silicon acceleration."""

    def __init__(
        self,
        model_path: str = "mlx-community/snowflake-arctic-embed-m-v1.5",
        dimension: int = 768,
    ) -> None:
        if mlx_lm is None:
            raise ImportError("mlx-lm and mlx are required for MLXEmbeddingProvider")

        self.model, self.tokenizer = mlx_lm.load(model_path)
        self.model = self.model  # Ensure it's loaded
        self.dimension = dimension

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query. MLX is sync, so we run in a thread if needed, but simple call here."""
        clean = text.strip()
        if not clean:
            return [0.0] * self.dimension

        # MLX models typically provide embeddings via the model's forward pass or a utility
        # For embedding models, we typically take the mean of the last hidden state or use the [CLS] token
        # Note: mlx-lm's high-level API is geared towards generation;
        # for pure embeddings, we often interact with the model and tokenizer directly.
        tokens = self.tokenizer.encode(clean)
        output = self.model(tokens)
        # Simplified: return the mean of the embedding sequence
        emb = mx.mean(output, axis=1).tolist()[0]
        return emb

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple documents."""
        if not texts:
            return []

        results = []
        for t in texts:
            emb = await self.embed_query(t)
            results.append(emb)
        return results

    async def close(self) -> None:
        pass


class MockEmbeddingProvider:
    """Deterministic, local in-memory embedding provider for unit tests and offline benchmarking."""

    def __init__(self, model: str = "mock-embed", dimension: int = 768) -> None:
        self.model = model
        self.dimension = dimension

    async def embed_query(self, text: str) -> list[float]:
        clean = text.strip()
        if not clean:
            return [0.0] * self.dimension
        return self._generate_vector(f"query:{clean}")

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for t in texts:
            clean = t.strip()
            if not clean:
                results.append([0.0] * self.dimension)
            else:
                results.append(self._generate_vector(f"doc:{clean}"))
        return results

    async def close(self) -> None:
        pass

    def _generate_vector(self, text: str) -> list[float]:
        if not text:
            return [0.0] * self.dimension

        # Deterministic pseudo-vector generation from text hash
        raw_hash = hashlib.sha256(text.encode("utf-8")).digest()
        vec: list[float] = []
        for i in range(self.dimension):
            byte_val = raw_hash[i % len(raw_hash)]
            # Map byte [0, 255] to float in [-1.0, 1.0]
            val = (byte_val / 127.5) - 1.0
            vec.append(val)

        # Normalize to unit vector
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


_EMBEDDING_PROVIDERS: dict[str, type[EmbeddingProvider]] = {
    "ollama": OllamaEmbeddingProvider,
    "openai": OpenAICompatibleEmbeddingProvider,
    "mlx": MLXEmbeddingProvider,
    "mock": MockEmbeddingProvider,
}


def create_embedding_provider(
    name: str = "ollama",
    *,
    model: str | None = None,
    base_url: str | None = None,
    dimension: int | None = None,
    api_key: str | None = None,
    **kwargs: Any,
) -> EmbeddingProvider:
    """Instantiate an embedding provider ('ollama', 'openai', or 'mock')."""
    try:
        cls = _EMBEDDING_PROVIDERS[name.lower()]
    except KeyError:
        raise ValueError(
            f"Unknown embedding provider {name!r}; expected one of {sorted(_EMBEDDING_PROVIDERS)}"
        ) from None

    init_kwargs: dict[str, Any] = {**kwargs}
    if model:
        init_kwargs["model"] = model
    if base_url:
        init_kwargs["base_url"] = base_url
    if dimension is not None:
        init_kwargs["dimension"] = dimension
    if api_key and cls is OpenAICompatibleEmbeddingProvider:
        init_kwargs["api_key"] = api_key

    return cls(**init_kwargs)
