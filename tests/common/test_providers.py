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
