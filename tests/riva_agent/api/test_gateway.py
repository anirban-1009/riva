import pytest
import httpx
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
from riva_agent.api.gateway import app

client = TestClient(app)

@pytest.mark.asyncio
async def test_list_models():
    with patch("riva_agent.api.gateway.create_provider") as mock_create:
        mock_provider = AsyncMock()
        mock_provider.list_models.return_value = ["llama3", "mistral"]
        mock_create.return_value = mock_provider

        response = client.get("/v1/models")
        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "list"
        assert len(data["data"]) == 2
        assert data["data"][0]["id"] == "llama3"

@pytest.mark.asyncio
async def test_chat_completions_non_streaming():
    with patch("riva_agent.api.gateway.create_provider") as mock_create:
        mock_provider = AsyncMock()
        mock_provider.get_capabilities.return_value = ["thinking"]
        mock_provider.chat_async.return_value = "This is a mocked response"
        mock_create.return_value = mock_provider

        payload = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": False
        }

        response = client.post("/v1/chat/completions", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["choices"][0]["message"]["content"] == "This is a mocked response"

@pytest.mark.asyncio
async def test_chat_completions_streaming():
    # For streaming, we use httpx.AsyncClient with ASGITransport to test the response generator
    from httpx import ASGITransport, AsyncClient

    with patch("riva_agent.api.gateway.create_provider") as mock_create:
        mock_provider = AsyncMock()
        mock_provider.get_capabilities.return_value = ["thinking"]

        # Mock the chat_stream generator
        async def mock_chat_stream(*args, **kwargs):
            yield "token 1"
            yield "token 2"

        mock_provider.chat_stream = mock_chat_stream
        mock_create.return_value = mock_provider

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            payload = {
                "model": "test-model",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True
            }
            async with ac.stream("POST", "/v1/chat/completions", json=payload) as response:
                assert response.status_code == 200
                lines = []
                async for line in response.aiter_lines():
                    if line:
                        lines.append(line)

                # Check for start, tokens, and done
                assert any("role" in l for l in lines)
                assert any("token 1" in l for l in lines)
                assert any("token 2" in l for l in lines)
                assert any("[DONE]" in l for l in lines)

@pytest.mark.asyncio
async def test_show_model_ollama():
    with patch("riva_agent.api.gateway.config") as mock_config, \
         patch("riva_agent.api.gateway.OllamaProvider") as mock_ollama:
        mock_config.PROVIDER = "ollama"
        mock_provider = MagicMock()
        mock_provider.base_url = "http://localhost:11434"

        mock_response = MagicMock()
        mock_response.json.return_value = {"model": "test"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        mock_provider._get_client.return_value = mock_client
        mock_ollama.return_value = mock_provider

        payload = {"name": "test-model"}
        response = client.post("/api/show", json=payload)
        assert response.status_code == 200
        assert response.json() == {"model": "test"}

@pytest.mark.asyncio
async def test_show_model_non_ollama():
    with patch("riva_agent.api.gateway.config") as mock_config:
        mock_config.PROVIDER = "openai"
        response = client.post("/api/show", json={"name": "test-model"})
        assert response.status_code == 501
