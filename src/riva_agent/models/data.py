from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, field_validator


@dataclass
class Delta:
    role: str | None = None
    content: str | None = None


class ChatMessage(BaseModel):
    role: str
    content: str

    @field_validator("content", mode="before")
    @classmethod
    def _flatten_content_parts(cls, value: Any) -> Any:
        """Accept OpenAI's multimodal content-parts array (used by clients like
        the Vercel AI SDK even for plain text) and flatten it to a string.

        Only text parts are kept since no configured provider handles
        image/audio inputs yet; other part types are silently dropped rather
        than rejecting the whole request.
        """
        if isinstance(value, list):
            return "".join(
                part.get("text", "")
                for part in value
                if isinstance(part, dict) and part.get("type") == "text"
            )
        return value


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None


class EmbeddingRequest(BaseModel):
    model: str
    input: str | list[str]


@dataclass
class StreamChoice:
    delta: Delta = field(default_factory=Delta)
    index: int = 0
    finish_reason: str | None = None


@dataclass
class Chunk:
    id: str
    created: int
    model: str
    choices: list[StreamChoice]
    object: str = "chat.completion.chunk"


@dataclass
class AssistantMessage:
    content: str
    role: str = "assistant"


@dataclass
class Choice:
    message: AssistantMessage
    index: int = 0
    finish_reason: str | None = "stop"


@dataclass
class ChatCompletionResponse:
    id: str
    created: int
    model: str
    choices: list[Choice]
    object: str = "chat.completion"
    usage: dict[str, int] | None = None


@dataclass
class Model:
    id: str
    created: int
    object: str = "model"
    owned_by: str = "ollama"


@dataclass
class ModelList:
    data: list[Model]
    object: str = "list"


@dataclass
class EmbeddingData:
    embedding: list[float]
    index: int = 0
    object: str = "embedding"


@dataclass
class EmbeddingResponse:
    data: list[EmbeddingData]
    model: str
    object: str = "list"
