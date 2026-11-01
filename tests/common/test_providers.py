from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from common.llm.providers import OllamaProvider


@pytest.mark.asyncio
async def test_ollama_provider_get_capabilities_list_and_dict():
    provider = OllamaProvider()
    provider.__class__._capabilities_cache = None

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "models": [
            {"name": "tev1:0.8b", "capabilities": ["decision", "tools", "thinking", "completion"]},
            {"name": "llama3:8b", "capabilities": {"completion": True, "tools": False}},
        ]
    }

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp

    with patch.object(provider, "_get_client", return_value=mock_client):
        caps1 = await provider.get_capabilities("tev1:0.8b")
        assert "thinking" in caps1
        assert "tools" in caps1

        caps2 = await provider.get_capabilities("llama3:8b")
        assert caps2 == ["completion"]


@pytest.mark.asyncio
async def test_openai_provider_chat_turn_async_with_tools():
    from common.llm.providers import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(base_url="http://localhost:8000/v1")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Searching now...",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "search__search",
                                "arguments": '{"query": "quantum computing"}',
                            },
                        }
                    ],
                }
            }
        ]
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp

    with patch.object(provider, "_get_client", return_value=mock_client):
        turn = await provider.chat_turn_async(
            [{"role": "user", "content": "Search quantum computing"}],
            tools=[{"type": "function", "function": {"name": "search__search"}}],
        )

        assert turn.has_tool_calls is True
        assert len(turn.tool_calls) == 1
        assert turn.tool_calls[0].id == "call_123"
        assert turn.tool_calls[0].name == "search__search"
        assert turn.tool_calls[0].arguments == {"query": "quantum computing"}
        assert turn.content == "Searching now..."

        # Verify chat_async calls chat_turn_async and returns string content
        content_str = await provider.chat_async([{"role": "user", "content": "Search quantum computing"}])
        assert content_str == "Searching now..."


@pytest.mark.asyncio
async def test_ollama_provider_chat_turn_async_with_tools():
    provider = OllamaProvider()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "notes__read",
                        "arguments": {"path": "/tmp/a.txt"},
                    }
                }
            ],
        }
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp

    with patch.object(provider, "_get_client", return_value=mock_client):
        turn = await provider.chat_turn_async(
            [{"role": "user", "content": "Read note"}],
            tools=[{"type": "function", "function": {"name": "notes__read"}}],
        )

        assert turn.has_tool_calls is True
        assert len(turn.tool_calls) == 1
        assert turn.tool_calls[0].name == "notes__read"
        assert turn.tool_calls[0].arguments == {"path": "/tmp/a.txt"}
        assert turn.content == ""
