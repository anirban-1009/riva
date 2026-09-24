from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from common.profile.store import ProfileStore
from common.memory.store import EpisodicStore
from riva_agent import config
from riva_agent.api.gateway import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / ".riva"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "MODEL", None)
    return data_dir


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
        # "riva" is auto-inserted as virtual model if not present
        assert len(data["data"]) == 3
        model_ids = [m["id"] for m in data["data"]]
        assert "riva" in model_ids
        assert "llama3" in model_ids


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
            "stream": False,
        }

        response = client.post("/v1/chat/completions", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["choices"][0]["message"]["content"] == "This is a mocked response"
        assert data["model"] == "test-model"


@pytest.mark.asyncio
async def test_chat_completions_assistant_mode(isolated_data_dir):
    # Set up user profile
    prof_store = ProfileStore(isolated_data_dir / "profile.db")
    prof_store.set("Location", "Munich", category="facts")
    prof_store.set("Job", "Software Engineer", category="facts")

    with patch("riva_agent.api.gateway.create_provider") as mock_create:
        mock_provider = AsyncMock()
        mock_provider.get_capabilities.return_value = []
        mock_provider.chat_async.return_value = "I know you live in Munich!"
        mock_create.return_value = mock_provider

        payload = {
            "model": "riva",
            "messages": [{"role": "user", "content": "Where do I live?"}],
            "stream": False,
        }

        response = client.post("/v1/chat/completions", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["model"] == "riva"
        assert data["choices"][0]["message"]["content"] == "I know you live in Munich!"

        # Verify profile context was injected into the prompt
        call_args = mock_provider.chat_async.call_args[0][0]
        assert call_args[0]["role"] == "system"
        assert "You are Riva, a private personal assistant" in call_args[0]["content"]
        assert "Location: Munich" in call_args[0]["content"]

        # Verify turn was logged in episodic store
        mem_store = EpisodicStore(isolated_data_dir / "memory.db")
        with mem_store._get_connection() as conn:
            turns = conn.execute("SELECT role, content FROM turns;").fetchall()
        assert len(turns) == 2
        assert turns[0]["role"] == "user"
        assert turns[0]["content"] == "Where do I live?"
        assert turns[1]["role"] == "assistant"
        assert turns[1]["content"] == "I know you live in Munich!"


@pytest.mark.asyncio
async def test_chat_completions_assistant_mode_explicit_directive(isolated_data_dir):
    with patch("riva_agent.api.gateway.create_provider") as mock_create:
        mock_provider = AsyncMock()
        mock_provider.get_capabilities.return_value = []
        mock_provider.chat_async.return_value = "Understood, I will remember that."
        mock_create.return_value = mock_provider

        payload = {
            "model": "riva",
            "messages": [{"role": "user", "content": "Remember that I am allergic to shellfish"}],
            "stream": False,
        }

        response = client.post("/v1/chat/completions", json=payload)
        assert response.status_code == 200

        # Verify fact was directly saved to profile store
        prof_store = ProfileStore(isolated_data_dir / "profile.db")
        entries = prof_store.list_all(category="facts")
        assert len(entries) >= 1
        assert any("allergic to shellfish" in e.value.lower() for e in entries)


@pytest.mark.asyncio
async def test_chat_completions_passthrough_mode(isolated_data_dir):
    # Pass-through mode should NOT inject profile or log memory
    prof_store = ProfileStore(isolated_data_dir / "profile.db")
    prof_store.set("Secret", "Classified", category="facts")

    with patch("riva_agent.api.gateway.create_provider") as mock_create:
        mock_provider = AsyncMock()
        mock_provider.get_capabilities.return_value = []
        mock_provider.chat_async.return_value = "Clean response"
        mock_create.return_value = mock_provider

        payload = {
            "model": "gemma4:12b",
            "messages": [{"role": "user", "content": "Format this code"}],
            "stream": False,
        }

        response = client.post("/v1/chat/completions", json=payload)
        assert response.status_code == 200

        # Verify messages sent to model were verbatim without system injection
        call_args = mock_provider.chat_async.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0]["role"] == "user"
        assert call_args[0]["content"] == "Format this code"

        # Verify NO turns logged in episodic memory
        mem_store = EpisodicStore(isolated_data_dir / "memory.db")
        with mem_store._get_connection() as conn:
            turns = conn.execute("SELECT * FROM turns;").fetchall()
        assert len(turns) == 0


@pytest.mark.asyncio
async def test_chat_completions_streaming():
    from httpx import ASGITransport, AsyncClient

    with patch("riva_agent.api.gateway.create_provider") as mock_create:
        mock_provider = AsyncMock()
        mock_provider.get_capabilities.return_value = ["thinking"]

        async def mock_chat_stream(*args, **kwargs):
            yield "token 1"
            yield "token 2"

        mock_provider.chat_stream = mock_chat_stream
        mock_create.return_value = mock_provider

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            payload = {
                "model": "test-model",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True,
            }
            async with ac.stream("POST", "/v1/chat/completions", json=payload) as response:
                assert response.status_code == 200
                lines = []
                async for line in response.aiter_lines():
                    if line:
                        lines.append(line)

                assert any("role" in l for l in lines)
                assert any("token 1" in l for l in lines)
                assert any("token 2" in l for l in lines)
                assert any("[DONE]" in l for l in lines)


@pytest.mark.asyncio
async def test_show_model_ollama():
    with patch("riva_agent.api.gateway.config") as mock_config, patch(
        "riva_agent.api.gateway.OllamaProvider"
    ) as mock_ollama:
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
