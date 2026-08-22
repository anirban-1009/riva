from unittest.mock import MagicMock, patch

import pytest

from src.core.llm_client import FallbackClient, GeminiClient, LLMClient, OllamaClient, get_llm_client


class TestLLMClient:
    """Test suite for LLMClient and its implementations."""

    @patch("src.core.ai.gemini.genai.Client")
    def test_gemini_client_generate(self, mock_client_class):
        """Test Gemini client text generation."""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value.text = "Gemini Response"
        mock_client_class.return_value = mock_client

        client = GeminiClient(api_key="test_key")
        result = client.generate("Hello")

        assert result == "Gemini Response"
        mock_client_class.assert_called_with(api_key="test_key")
        mock_client.models.generate_content.assert_called_once()

    @patch("requests.post")
    def test_ollama_client_generate(self, mock_post):
        """Test Ollama client text generation."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "Ollama Response"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        client = OllamaClient(model_name="llama3")
        result = client.generate("Hello")

        assert result == "Ollama Response"
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["model"] == "llama3"

    def test_llm_client_generate_json(self):
        """Test JSON parsing logic in base LLMClient."""

        class MockClient(LLMClient):
            def generate(self, prompt, system_instruction=None):
                return '```json\n{"status": "ok", "value": 42}\n```'

        client = MockClient()
        result = client.generate_json("test")
        assert result == {"status": "ok", "value": 42}

    def test_llm_client_generate_json_alternate_block(self):
        """Test JSON parsing with alternate markdown blocks."""

        class MockClient(LLMClient):
            def generate(self, prompt, system_instruction=None):
                return '```\n{"status": "ok"}\n```'

        client = MockClient()
        result = client.generate_json("test")
        assert result == {"status": "ok"}

    def test_llm_client_generate_json_failure(self):
        """Test JSON parsing failure returns empty dict."""

        class MockClient(LLMClient):
            def generate(self, prompt, system_instruction=None):
                return "Not a JSON"

        client = MockClient()
        result = client.generate_json("test")
        assert result == {}

    def test_llm_client_generate_json_empty_response(self):
        """Test that an empty response from LLM returns an empty dictionary."""

        class MockClient(LLMClient):
            def generate(self, prompt, system_instruction=None):
                return ""

        client = MockClient()
        result = client.generate_json("test")
        assert result == {}

    def test_llm_client_generate_json_recovery(self):
        """Test recovery from malformed JSON by finding the boundaries of the JSON object."""

        class MockClient(LLMClient):
            def generate(self, prompt, system_instruction=None):
                return 'Some text before {"key": "value"} some text after'

        client = MockClient()
        result = client.generate_json("test")
        assert result == {"key": "value"}

    def test_llm_client_generate_json_unrecoverable(self):
        """Test that malformed JSON with no boundaries returns an empty dictionary."""

        class MockClient(LLMClient):
            def generate(self, prompt, system_instruction=None):
                return "No json here { not even a valid one"

        client = MockClient()
        result = client.generate_json("test")
        assert result == {}

    def test_llm_client_generate_json_unexpected_exception(self):
        """Test that unexpected exceptions during parsing are handled and return an empty dictionary."""

        class MockClient(LLMClient):
            def generate(self, prompt, system_instruction=None):
                return '{"valid": "json"}'

        client = MockClient()
        # Mock json.loads to raise a non-JSON exception
        with patch("json.loads", side_effect=RuntimeError("Unexpected error")):
            result = client.generate_json("test")
            assert result == {}

    def test_factory_gemini(self):
        """Test factory function for Gemini provider."""
        config = {"provider": "gemini", "gemini_api_key": "abc"}
        with patch("src.core.ai.gemini.genai.Client"):
            client = get_llm_client(config)
            assert isinstance(client, GeminiClient)
            assert client.api_key == "abc"

    def test_factory_ollama(self):
        """Test factory function for Ollama provider."""
        config = {"provider": "ollama", "ollama": {"model_name": "phi3", "base_url": "http://local:11434"}}
        client = get_llm_client(config)
        assert isinstance(client, OllamaClient)
        assert client.model_name == "phi3"
        assert client.base_url == "http://local:11434"

    @patch("src.core.ai.gemini.genai.Client")
    def test_factory_fallback_both_available(self, mock_client):
        """Test factory in fallback mode when both are configured."""
        config = {"provider": "fallback", "gemini": {"api_key": "abc"}, "ollama": {"model_name": "phi3"}}
        client = get_llm_client(config)
        assert isinstance(client, FallbackClient)
        assert len(client.clients) == 2

    def test_factory_fallback_gemini_missing(self):
        """Test factory in fallback mode when Gemini is missing (returns Ollama)."""
        config = {
            "provider": "fallback",
            "gemini": {"api_key": ""},  # Missing key
            "ollama": {"model_name": "phi3"},
        }
        client = get_llm_client(config)
        assert isinstance(client, OllamaClient)
        assert client.model_name == "phi3"

    def test_fallback_client_success_first(self):
        """Test FallbackClient returns first success."""
        c1 = MagicMock(spec=LLMClient)
        c1.generate.return_value = "Success 1"
        c2 = MagicMock(spec=LLMClient)

        fallback = FallbackClient([c1, c2])
        assert fallback.generate("test") == "Success 1"
        c1.generate.assert_called_once()
        c2.generate.assert_not_called()

    def test_fallback_client_success_second(self):
        """Test FallbackClient falls back on error or empty response."""
        c1 = MagicMock(spec=LLMClient)
        c1.generate.side_effect = Exception("error")
        c2 = MagicMock(spec=LLMClient)
        c2.generate.return_value = "Success 2"

        fallback = FallbackClient([c1, c2])
        assert fallback.generate("test") == "Success 2"
        c2.generate.assert_called_once()

    def test_fallback_client_all_fail(self):
        """Test FallbackClient returns empty string if all fail."""
        c1 = MagicMock(spec=LLMClient)
        c1.generate.return_value = ""
        c2 = MagicMock(spec=LLMClient)
        c2.generate.side_effect = Exception("error")

        fallback = FallbackClient([c1, c2])
        assert fallback.generate("test") == ""

    def test_factory_invalid_provider(self):
        """Test factory function raises error for unknown provider."""
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            get_llm_client({"provider": "openai"})
