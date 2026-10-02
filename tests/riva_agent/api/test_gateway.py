from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from common.memory.store import EpisodicStore
from common.profile.store import ProfileStore
from riva_agent import config
from riva_agent.api.gateway import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / ".riva"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "MODEL", None)
    return data_dir


@pytest.mark.asyncio
async def test_list_models(client):
    with patch("riva_agent.api.gateway.create_provider") as mock_create:
        mock_provider = AsyncMock()
        mock_provider.list_models.return_value = ["llama3", "mistral"]
        mock_create.return_value = mock_provider

        response = await client.get("/v1/models")
        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "list"
        # "riva" is auto-inserted as virtual model if not present
        assert len(data["data"]) == 3
        model_ids = [m["id"] for m in data["data"]]
        assert "riva" in model_ids
        assert "llama3" in model_ids


@pytest.mark.asyncio
async def test_chat_completions_non_streaming(client):
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

        response = await client.post("/v1/chat/completions", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["choices"][0]["message"]["content"] == "This is a mocked response"
        assert data["model"] == "test-model"


@pytest.mark.asyncio
async def test_chat_completions_assistant_mode(client, isolated_data_dir):
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

        response = await client.post("/v1/chat/completions", json=payload)
        assert response.status_code == 200
        data = response.json()
        # In assistant mode, the response model should be the concrete backend model, not the virtual "riva" ID.
        assert data["model"] != "riva"
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
async def test_chat_completions_assistant_mode_explicit_directive(client, isolated_data_dir):
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

        response = await client.post("/v1/chat/completions", json=payload)
        assert response.status_code == 200

        # Verify fact was directly saved to profile store
        prof_store = ProfileStore(isolated_data_dir / "profile.db")
        entries = prof_store.list_all(category="facts")
        assert len(entries) >= 1
        assert any("allergic to shellfish" in e.value.lower() for e in entries)


@pytest.mark.asyncio
async def test_chat_completions_assistant_mode_passive_candidate(client, isolated_data_dir):
    with patch("riva_agent.api.gateway.create_provider") as mock_create:
        mock_provider = AsyncMock()
        mock_provider.get_capabilities.return_value = []
        mock_provider.chat_async.return_value = "Great company to work at!"
        mock_create.return_value = mock_provider

        payload = {
            "model": "riva",
            "messages": [{"role": "user", "content": "I work as a software engineer at Stripe"}],
            "stream": False,
        }

        response = await client.post("/v1/chat/completions", json=payload)
        assert response.status_code == 200

        # Verify fact was NOT committed directly to profile
        prof_store = ProfileStore(isolated_data_dir / "profile.db")
        assert len(prof_store.list_all(category="facts")) == 0

        # Verify candidate fact was staged in pending_memories
        mem_store = EpisodicStore(isolated_data_dir / "memory.db")
        pending = mem_store.list_pending()
        assert len(pending) == 1
        assert "software engineer" in pending[0].fact.lower()
        assert pending[0].source_snippet == "I work as a software engineer at Stripe"

        # Sending duplicate query should not create duplicate pending candidate
        await client.post("/v1/chat/completions", json=payload)
        assert len(mem_store.list_pending()) == 1


@pytest.mark.asyncio
async def test_chat_completions_assistant_mode_conversational_turn_replay(client, isolated_data_dir):
    with patch("riva_agent.api.gateway.create_provider") as mock_create:
        mock_provider = AsyncMock()
        mock_provider.get_capabilities.return_value = []
        mock_provider.chat_async.return_value = "I heard you like coffee!"
        mock_create.return_value = mock_provider

        # Turn 1
        p1 = {
            "model": "riva",
            "messages": [{"role": "user", "content": "I enjoy drinking black coffee in the morning"}],
            "stream": False,
        }
        res1 = await client.post("/v1/chat/completions", json=p1)
        assert res1.status_code == 200

        # Turn 2: single-turn query (e.g. from `riva ask`)
        mock_provider.chat_async.return_value = "You said you enjoy black coffee."
        p2 = {
            "model": "riva",
            "messages": [{"role": "user", "content": "What beverage did I mention?"}],
            "stream": False,
        }
        res2 = await client.post("/v1/chat/completions", json=p2)
        assert res2.status_code == 200

        # Inspect messages passed to provider on Turn 2
        call_args = mock_provider.chat_async.call_args[0][0]
        # Should contain: system prompt, Turn 1 user, Turn 1 assistant, Turn 2 user
        assert len(call_args) == 4
        assert call_args[0]["role"] == "system"
        assert call_args[1]["role"] == "user"
        assert "black coffee" in call_args[1]["content"]
        assert call_args[2]["role"] == "assistant"
        assert "like coffee" in call_args[2]["content"]
        assert call_args[3]["role"] == "user"
        assert call_args[3]["content"] == "What beverage did I mention?"


@pytest.mark.asyncio
async def test_chat_completions_assistant_mode_multi_turn_payload_no_duplication(client, isolated_data_dir):
    with patch("riva_agent.api.gateway.create_provider") as mock_create:
        mock_provider = AsyncMock()
        mock_provider.get_capabilities.return_value = []
        mock_provider.chat_async.return_value = "Understood."
        mock_create.return_value = mock_provider

        # Client manages its own history and sends multiple messages in payload
        payload = {
            "model": "riva",
            "messages": [
                {"role": "user", "content": "Client msg 1"},
                {"role": "assistant", "content": "Client msg 2"},
                {"role": "user", "content": "Client msg 3"},
            ],
            "stream": False,
        }
        res = await client.post("/v1/chat/completions", json=payload)
        assert res.status_code == 200

        call_args = mock_provider.chat_async.call_args[0][0]
        # Should be system prompt + 3 client messages, exactly 4 messages total
        assert len(call_args) == 4
        assert call_args[0]["role"] == "system"
        assert call_args[1]["content"] == "Client msg 1"
        assert call_args[2]["content"] == "Client msg 2"
        assert call_args[3]["content"] == "Client msg 3"


@pytest.mark.asyncio
async def test_chat_completions_passthrough_mode(client, isolated_data_dir):
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

        response = await client.post("/v1/chat/completions", json=payload)
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
async def test_chat_completions_streaming(client):
    with patch("riva_agent.api.gateway.create_provider") as mock_create:
        mock_provider = AsyncMock()
        mock_provider.get_capabilities.return_value = ["thinking"]

        async def mock_chat_stream(*args, **kwargs):
            yield "token 1"
            yield "token 2"

        mock_provider.chat_stream = mock_chat_stream
        mock_create.return_value = mock_provider

        payload = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": True,
        }
        async with client.stream("POST", "/v1/chat/completions", json=payload) as response:
            assert response.status_code == 200
            lines = []
            async for line in response.aiter_lines():
                if line:
                    lines.append(line)

            assert any("role" in line for line in lines)
            assert any("token 1" in line for line in lines)
            assert any("token 2" in line for line in lines)
            assert any("[DONE]" in line for line in lines)


@pytest.mark.asyncio
async def test_show_model_ollama(client):
    with (
        patch("riva_agent.api.gateway.config") as mock_config,
        patch("riva_agent.api.gateway.OllamaProvider") as mock_ollama,
    ):
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
        response = await client.post("/api/show", json=payload)
        assert response.status_code == 200
        assert response.json() == {"model": "test"}


@pytest.mark.asyncio
async def test_show_model_non_ollama(client):
    with patch("riva_agent.api.gateway.config") as mock_config:
        mock_config.PROVIDER = "openai"
        response = await client.post("/api/show", json={"name": "test-model"})
        assert response.status_code == 501


@pytest.mark.asyncio
async def test_session_id_management(client, isolated_data_dir):
    from riva_agent.api.gateway import get_current_session_id, reset_session_id

    sid1 = get_current_session_id()
    assert sid1
    assert (isolated_data_dir / "session.id").read_text().strip() == sid1

    # Calling again returns same
    assert get_current_session_id() == sid1

    # Reset gives new
    sid2 = reset_session_id()
    assert sid2 != sid1
    assert get_current_session_id() == sid2

    # GET /v1/session
    res_get = await client.get("/v1/session")
    assert res_get.status_code == 200
    assert res_get.json()["session_id"] == sid2

    # POST /v1/session/new
    res_post = await client.post("/v1/session/new")
    assert res_post.status_code == 200
    data = res_post.json()
    assert data["status"] == "ok"
    assert data["session_id"] != sid2
    assert get_current_session_id() == data["session_id"]


@pytest.mark.asyncio
async def test_chat_completions_reset_command_bare(client, isolated_data_dir):
    from riva_agent.api.gateway import get_current_session_id

    initial_sid = get_current_session_id()

    with patch("riva_agent.api.gateway.create_provider") as mock_create:
        mock_provider = AsyncMock()
        mock_create.return_value = mock_provider

        # Bare /clear command
        payload = {
            "model": "riva",
            "messages": [{"role": "user", "content": "/clear"}],
            "stream": False,
        }
        response = await client.post("/v1/chat/completions", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "✨ New chat session started" in data["choices"][0]["message"]["content"]

        # Provider should NOT be called for bare reset
        mock_provider.chat_async.assert_not_called()

        # Session ID must be rotated
        new_sid = get_current_session_id()
        assert new_sid != initial_sid


@pytest.mark.asyncio
async def test_chat_completions_reset_command_bare_streaming(client, isolated_data_dir):
    from riva_agent.api.gateway import get_current_session_id

    initial_sid = get_current_session_id()

    with patch("riva_agent.api.gateway.create_provider") as mock_create:
        mock_provider = AsyncMock()
        mock_create.return_value = mock_provider

        payload = {
            "model": "riva",
            "messages": [{"role": "user", "content": "/new_session"}],
            "stream": True,
        }
        async with client.stream("POST", "/v1/chat/completions", json=payload) as response:
            assert response.status_code == 200
            lines = [line async for line in response.aiter_lines() if line]

            assert any("New chat session started" in line for line in lines)
            assert any("[DONE]" in line for line in lines)

        mock_provider.chat_stream.assert_not_called()
        assert get_current_session_id() != initial_sid


@pytest.mark.asyncio
async def test_chat_completions_reset_command_with_query(client, isolated_data_dir):
    from riva_agent.api.gateway import get_current_session_id

    initial_sid = get_current_session_id()

    with patch("riva_agent.api.gateway.create_provider") as mock_create:
        mock_provider = AsyncMock()
        mock_provider.get_capabilities.return_value = []
        mock_provider.chat_async.return_value = "The capital of France is Paris."
        mock_create.return_value = mock_provider

        payload = {
            "model": "riva",
            "messages": [
                {"role": "user", "content": "Old question from past session"},
                {"role": "assistant", "content": "Old answer"},
                {"role": "user", "content": "/new What is the capital of France?"},
            ],
            "stream": False,
        }

        response = await client.post("/v1/chat/completions", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["choices"][0]["message"]["content"] == "The capital of France is Paris."

        # Verify new session ID
        new_sid = get_current_session_id()
        assert new_sid != initial_sid

        # Verify old turns were purged from provider call payload
        call_args = mock_provider.chat_async.call_args[0][0]
        assert len(call_args) == 2
        assert call_args[0]["role"] == "system"
        assert call_args[1]["role"] == "user"
        assert call_args[1]["content"] == "What is the capital of France?"

        # Verify episodic memory logged turn under the new session ID
        mem_store = EpisodicStore(isolated_data_dir / "memory.db")
        turns = mem_store.get_recent_turns(new_sid)
        assert len(turns) == 2
        assert turns[0].role == "user"
        assert turns[0].content == "What is the capital of France?"
        assert turns[1].role == "assistant"
