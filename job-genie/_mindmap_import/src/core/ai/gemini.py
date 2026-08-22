from typing import List, Optional

from google import genai
from google.genai import types

from src.core.ai.base import LLMClient
from src.utils.logger import get_logger

logger = get_logger(__name__)


class GeminiClient(LLMClient):
    """Client for Google Gemini API."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.0-flash",
        embedding_model: str = "text-embedding-004",
    ):
        """
        Initialize Gemini client with API key and model.

        Args:
            api_key: Google AI Studio API Key.
            model_name: Gemini model name (default: gemini-2.0-flash).
            embedding_model: Gemini embedding model name (default: text-embedding-004).
        """
        self.api_key = api_key
        self.model_name = model_name
        self.embedding_model = embedding_model
        try:
            self.client = genai.Client(api_key=api_key)
        except Exception as e:
            logger.error(f"Failed to initialize Gemini Client: {e}")
            self.client = None

    def generate(self, prompt: str, system_instruction: Optional[str] = None, max_tokens: Optional[int] = None) -> str:
        """
        Generates content using Gemini.

        Args:
            prompt: User prompt for generation.
            system_instruction: Optional system message.
            max_tokens: Optional cap on generated output tokens.

        Returns:
            str: Generated text content.
        """
        if not self.client:
            return ""

        try:
            config = None
            if system_instruction or max_tokens:
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction, max_output_tokens=max_tokens
                )

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )
            return response.text
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return ""

    def embed(self, text: str) -> List[float]:
        """
        Generates an embedding vector for the given text using Gemini's embedding model.

        Returns:
            List[float]: The embedding vector, or an empty list on failure.
        """
        if not self.client:
            return []

        try:
            response = self.client.models.embed_content(model=self.embedding_model, contents=text)
            return list(response.embeddings[0].values)
        except Exception as e:
            logger.error(f"Gemini embedding error: {e}")
            return []
