import json
from abc import ABC, abstractmethod
from typing import Any

from job_genie.utils.logger import get_logger

logger = get_logger(__name__)


class LLMClient(ABC):
    """Abstract base class for LLM clients to ensure consistent interface."""

    @abstractmethod
    def generate(self, prompt: str, system_instruction: str | None = None, max_tokens: int | None = None) -> str:
        """
        Generates a text response from the LLM.

        Args:
            prompt: The user prompt.
            system_instruction: Optional system instruction or context.
            max_tokens: Optional cap on generated output tokens.

        Returns:
            str: The generated text response.
        """

    def embed(self, text: str) -> list[float]:
        """
        Generates an embedding vector for the given text.

        Returns an empty list if the provider doesn't support embeddings or the call fails,
        so callers can fall back to keyword-only search instead of crashing.
        """
        return []

    def generate_json(self, prompt: str, system_instruction: str | None = None) -> dict[str, Any] | list[Any]:
        """
        Generates a JSON response from the LLM.

        Args:
            prompt: The user prompt.
            system_instruction: Optional system instruction.

        Returns:
            The value parsed from the LLM's JSON output - a dict for a JSON object response,
            or a list for a JSON array response.
        """
        response_text = self.generate(prompt, system_instruction)
        if not response_text:
            return {}

        try:
            # Basic cleanup if LLM wraps in markdown code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            return json.loads(response_text, strict=False)
        except json.JSONDecodeError:
            # Fallback: extract the first top-level JSON object or array, whichever starts first.
            spans = []
            obj_start, obj_end = response_text.find("{"), response_text.rfind("}")
            if obj_start != -1 and obj_end != -1:
                spans.append((obj_start, obj_end))
            arr_start, arr_end = response_text.find("["), response_text.rfind("]")
            if arr_start != -1 and arr_end != -1:
                spans.append((arr_start, arr_end))
            spans.sort()

            for start, end in spans:
                try:
                    return json.loads(response_text[start : end + 1], strict=False)
                except json.JSONDecodeError:
                    continue

            logger.error("Failed to parse JSON from LLM: No JSON object or array found.")
            logger.debug(f"Raw response: {response_text}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error parsing LLM response: {e}")
            return {}
