import json
import time
import uuid
from typing import Any, AsyncGenerator
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from common.llm.providers import OllamaProvider
from common.llm.manager import LLMManager

app = FastAPI(title="Riva Agent AI Gateway", version="0.1.0")

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None

async def stream_generator(
    provider: OllamaProvider,
    messages: list[dict[str, str]],
    model: str,
    request_id: str,
    created_time: int,
    options: dict[str, Any]
) -> AsyncGenerator[str, None]:
    """Generate server-sent events for chat completion chunks."""
    try:
        async for token in provider.chat_stream(messages, options=options):
            chunk = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": created_time,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "content": token
                        },
                        "finish_reason": None
                    }
                ]
            }
            yield f"data: {json.dumps(chunk)}\n\n"

        done_chunk = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": created_time,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop"
                }
            ]
        }
        yield f"data: {json.dumps(done_chunk)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        error_chunk = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": created_time,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "content": f"\n[Stream Error: {e}]"
                    },
                    "finish_reason": "error"
                }
            ]
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"
        yield "data: [DONE]\n\n"

@app.get("/v1/models")
async def list_models() -> dict[str, Any]:
    """List available local Ollama models in OpenAI-compatible format."""
    provider = OllamaProvider()
    try:
        client = provider._get_client()
        response = await client.get(f"{provider.base_url}/api/tags")
        response.raise_for_status()
        ollama_models = response.json().get("models", [])

        models_list = []
        for model in ollama_models:
            models_list.append({
                "id": model["name"],
                "object": "model",
                "created": int(time.time()),
                "owned_by": "ollama"
            })
        return {"object": "list", "data": models_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch models: {e}")

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest) -> Any:
    """Handle chat completion requests, supporting streaming and non-streaming modes."""
    provider = OllamaProvider(model=request.model)

    messages_payload = [{"role": msg.role, "content": msg.content} for msg in request.messages]

    options = {}
    if request.temperature is not None:
        options["temperature"] = request.temperature
    if request.max_tokens is not None:
        options["num_predict"] = request.max_tokens

    request_id = f"chatcmpl-{uuid.uuid4()}"
    created_time = int(time.time())

    if request.stream:
        return StreamingResponse(
            stream_generator(provider, messages_payload, request.model, request_id, created_time, options),
            media_type="text/event-stream"
        )

    try:
        content = await provider.chat_async(messages_payload, options=options)
        return {
            "id": request_id,
            "object": "chat.completion",
            "created": created_time,
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
