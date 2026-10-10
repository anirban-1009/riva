import math

import httpx
import pytest

from common.llm.embeddings import (
    EmbeddingError,
    EmbeddingProvider,
    MockEmbeddingProvider,
    OllamaEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    cosine_distance,
    cosine_similarity,
    create_embedding_provider,
)


def test_cosine_similarity_and_distance() -> None:
    # Identical vectors
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    assert math.isclose(cosine_similarity(v1, v2), 1.0)
    assert math.isclose(cosine_distance(v1, v2), 0.0)

    # Orthogonal vectors
    v3 = [0.0, 1.0, 0.0]
    assert math.isclose(cosine_similarity(v1, v3), 0.0)
    assert math.isclose(cosine_distance(v1, v3), 1.0)

    # Opposite vectors
    v4 = [-1.0, 0.0, 0.0]
    assert math.isclose(cosine_similarity(v1, v4), -1.0)
    assert math.isclose(cosine_distance(v1, v4), 2.0)

    # Zero vector safety
    v_zero = [0.0, 0.0, 0.0]
    assert cosine_similarity(v1, v_zero) == 0.0

    # Dimension mismatch
    with pytest.raises(ValueError, match="Vector dimension mismatch"):
        cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])


@pytest.mark.asyncio
async def test_mock_embedding_provider() -> None:
    provider = MockEmbeddingProvider(dimension=128)
    assert isinstance(provider, EmbeddingProvider)
    assert provider.dimension == 128
    assert provider.model == "mock-embed"

    # Query embedding
    q_vec = await provider.embed_query("machine learning")
    assert len(q_vec) == 128
    norm = math.sqrt(sum(x * x for x in q_vec))
    assert math.isclose(norm, 1.0, rel_tol=1e-5)

    # Determinism: same text yields same vector
    q_vec_again = await provider.embed_query("machine learning")
    assert q_vec == q_vec_again

    # Different text yields different vector
    other_vec = await provider.embed_query("cooking recipes")
    assert q_vec != other_vec

    # Documents batch
    docs = ["doc one", "doc two", ""]
    doc_vecs = await provider.embed_documents(docs)
    assert len(doc_vecs) == 3
    assert len(doc_vecs[0]) == 128
    assert len(doc_vecs[1]) == 128
    assert doc_vecs[2] == [0.0] * 128

    await provider.close()


def test_create_embedding_provider_factory() -> None:
    mock_p = create_embedding_provider("mock", dimension=256)
    assert isinstance(mock_p, MockEmbeddingProvider)
    assert mock_p.dimension == 256

    ollama_p = create_embedding_provider("ollama", model="nomic-embed-text", base_url="http://custom:11434")
    assert isinstance(ollama_p, OllamaEmbeddingProvider)
    assert ollama_p.model == "nomic-embed-text"
    assert ollama_p.base_url == "http://custom:11434"

    openai_p = create_embedding_provider("openai", model="text-embed", api_key="secret-key")
    assert isinstance(openai_p, OpenAICompatibleEmbeddingProvider)
    assert openai_p.model == "text-embed"
    assert openai_p.api_key == "secret-key"

    with pytest.raises(ValueError, match="Unknown embedding provider"):
        create_embedding_provider("nonexistent")


@pytest.mark.asyncio
async def test_ollama_embedding_provider_mocked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        import json

        data = json.loads(request.content)
        inputs = data.get("input", [])
        # Return 4-dimensional vectors for each input
        embeddings = [[float(idx + 1)] * 4 for idx in range(len(inputs))]
        return httpx.Response(200, json={"model": "nomic-embed-text", "embeddings": embeddings}, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    provider = OllamaEmbeddingProvider(
        base_url="http://mock-ollama:11434",
        model="nomic-embed-text",
        dimension=4,
        batch_size=2,
        client=client,
    )

    # Single query
    query_vec = await provider.embed_query("What is SQLite?")
    assert len(query_vec) == 4
    assert query_vec == [1.0, 1.0, 1.0, 1.0]

    # Documents with batch chunking (3 items with batch_size=2 requires 2 chunk calls)
    docs = ["fact A", "fact B", "fact C"]
    doc_vecs = await provider.embed_documents(docs)
    assert len(doc_vecs) == 3
    assert doc_vecs[0] == [1.0, 1.0, 1.0, 1.0]
    assert doc_vecs[1] == [2.0, 2.0, 2.0, 2.0]
    assert doc_vecs[2] == [1.0, 1.0, 1.0, 1.0]

    # Empty text
    empty_vec = await provider.embed_query("   ")
    assert empty_vec == [0.0] * 4

    empty_docs = await provider.embed_documents([])
    assert empty_docs == []


@pytest.mark.asyncio
async def test_ollama_fallback_to_v1_embeddings() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        import json

        url_str = str(request.url)
        if url_str.endswith("/api/embed"):
            return httpx.Response(404, json={"error": "not found"}, request=request)
        if url_str.endswith("/v1/embeddings"):
            data = json.loads(request.content)
            inputs = data.get("input", [])
            items = [{"index": i, "embedding": [0.5] * 4} for i in range(len(inputs))]
            return httpx.Response(200, json={"data": items}, request=request)
        return httpx.Response(500, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    provider = OllamaEmbeddingProvider(
        base_url="http://mock-ollama:11434",
        dimension=4,
        client=client,
    )

    res = await provider.embed_query("test query")
    assert res == [0.5, 0.5, 0.5, 0.5]


@pytest.mark.asyncio
async def test_ollama_error_handling() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    provider = OllamaEmbeddingProvider(
        base_url="http://mock-ollama:11434",
        client=client,
    )

    with pytest.raises(EmbeddingError, match="Failed to generate embeddings"):
        await provider.embed_query("hello")


@pytest.mark.asyncio
async def test_openai_compatible_embedding_provider_mocked() -> None:
    captured_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured_headers.update(dict(request.headers))
        data = json.loads(request.content)
        inputs = data.get("input", [])
        items = [{"index": i, "embedding": [0.25 * (i + 1)] * 4} for i in range(len(inputs))]
        return httpx.Response(200, json={"data": items}, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    provider = OpenAICompatibleEmbeddingProvider(
        base_url="http://mock-openai:8000/v1",
        model="custom-embed",
        dimension=4,
        api_key="test-token",
        batch_size=2,
        client=client,
    )

    vecs = await provider.embed_documents(["item 1", "item 2"])
    assert len(vecs) == 2
    assert vecs[0] == [0.25, 0.25, 0.25, 0.25]
    assert captured_headers.get("authorization") == "Bearer test-token"


@pytest.mark.asyncio
async def test_live_ollama_nomic_embed_integration() -> None:
    """Test against live Ollama instance if available on default port."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            if resp.status_code != 200:
                pytest.skip("Local Ollama not reachable")
            data = resp.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            if not any("nomic-embed-text" in m for m in models):
                pytest.skip("nomic-embed-text not installed locally")
    except Exception:
        pytest.skip("Local Ollama not running")

    provider = OllamaEmbeddingProvider(model="nomic-embed-text")
    query_vec = await provider.embed_query("Database indexing and WAL mode")
    assert len(query_vec) == 768

    doc_vecs = await provider.embed_documents(
        [
            "SQLite WAL mode provides concurrency for reads and writes.",
            "Vegetarian meal prep recipes with broccoli and lentils.",
        ]
    )
    assert len(doc_vecs) == 2
    assert len(doc_vecs[0]) == 768
    assert len(doc_vecs[1]) == 768

    # Semantic relevance check: database query should be closer to database doc than vegetarian doc
    sim_db = cosine_similarity(query_vec, doc_vecs[0])
    sim_food = cosine_similarity(query_vec, doc_vecs[1])
    assert sim_db > sim_food
