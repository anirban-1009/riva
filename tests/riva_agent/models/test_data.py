import pytest
from riva_agent.models.data import (
    AssistantMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    Chunk,
    Delta,
    Model,
    ModelList,
    StreamChoice,
)

def test_chat_message_flattening():
    # Test plain string content
    msg1 = ChatMessage(role="user", content="Hello")
    assert msg1.content == "Hello"

    # Test multimodal content array (OpenAI style)
    multimodal_content = [
        {"type": "text", "text": "Hello "},
        {"type": "image_url", "image_url": {"url": "..."}},
        {"type": "text", "text": "world"},
    ]
    msg2 = ChatMessage(role="user", content=multimodal_content)
    assert msg2.content == "Hello world"

    # Test array with no text parts
    no_text_content = [
        {"type": "image_url", "image_url": {"url": "..."}},
    ]
    msg3 = ChatMessage(role="user", content=no_text_content)
    assert msg3.content == ""

def test_chat_completion_request():
    messages = [ChatMessage(role="user", content="Hi")]
    req = ChatCompletionRequest(
        model="gpt-4",
        messages=messages,
        stream=True,
        temperature=0.7,
        max_tokens=100
    )
    assert req.model == "gpt-4"
    assert len(req.messages) == 1
    assert req.stream is True
    assert req.temperature == 0.7
    assert req.max_tokens == 100

def test_dataclass_integrity():
    # Test Delta
    delta = Delta(content="foo", reasoning="bar")
    assert delta.content == "foo"
    assert delta.reasoning == "bar"
    assert delta.role is None

    # Test AssistantMessage
    msg = AssistantMessage(content="Hello", reasoning_content="I think...")
    assert msg.content == "Hello"
    assert msg.reasoning_content == "I think..."
    assert msg.role == "assistant"

    # Test StreamChoice
    sc = StreamChoice(delta=delta, index=0, finish_reason=None)
    assert sc.delta.content == "foo"
    assert sc.index == 0
    assert sc.finish_reason is None

    # Test Chunk
    chunk = Chunk(id="chunk-1", created=123456, model="test-model", choices=[sc])
    assert chunk.id == "chunk-1"
    assert chunk.object == "chat.completion.chunk"
    assert len(chunk.choices) == 1

    # Test Choice & ChatCompletionResponse
    choice = Choice(message=msg, index=0, finish_reason="stop")
    resp = ChatCompletionResponse(
        id="resp-1", created=123456, model="test-model", choices=[choice]
    )
    assert resp.id == "resp-1"
    assert resp.object == "chat.completion"
    assert len(resp.choices) == 1

    # Test Model & ModelList
    model = Model(id="gemma-2b", created=123456)
    assert model.id == "gemma-2b"
    assert model.object == "model"
    model_list = ModelList(data=[model])
    assert len(model_list.data) == 1
    assert model_list.object == "list"

