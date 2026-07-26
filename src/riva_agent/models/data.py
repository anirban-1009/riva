from dataclasses import dataclass, field

from pydantic import BaseModel


@dataclass
class Delta:
    content: str | None = None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None


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
