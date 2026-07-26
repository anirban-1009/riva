import asyncio
import json
import time
import uuid
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from typing import Any, AsyncGenerator

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from common.llm.providers import OllamaProvider
from riva_agent.models.data import (
    AssistantMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    Chunk,
    Delta,
    Model,
    ModelList,
    StreamChoice,
)

try:
    __version__ = version("riva-agent")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

app = FastAPI(title="Riva Agent AI Gateway", version=__version__)


# How often to emit an SSE comment while waiting for the next token, so
# proxies/clients don't treat a slow cold model load as a dead connection.
_HEARTBEAT_INTERVAL_S = 15.0


async def stream_generator(
    provider: OllamaProvider,
    messages: list[dict[str, str]],
    model: str,
    request_id: str,
    created_time: int,
    options: dict[str, Any],
) -> AsyncGenerator[str, None]:
    """Generate server-sent events for chat completion chunks."""
    token_iter = provider.chat_stream(messages, options=options).__aiter__()
    try:
        while True:
            try:
                token = await asyncio.wait_for(
                    token_iter.__anext__(), timeout=_HEARTBEAT_INTERVAL_S
                )
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            except StopAsyncIteration:
                break

            chunk = Chunk(
                id=request_id,
                created=created_time,
                model=model,
                choices=[StreamChoice(delta=Delta(content=token))],
            )

            yield f"data: {json.dumps(asdict(chunk))}\n\n"

        done_chunk = Chunk(
            id=request_id,
            created=created_time,
            model=model,
            choices=[StreamChoice(index=0, finish_reason="stop")],
        )

        yield f"data: {json.dumps(asdict(done_chunk))}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        error_chunk = Chunk(
            id=request_id,
            created=created_time,
            model=model,
            choices=[
                StreamChoice(
                    delta=Delta(content=f"\n[Stream Error: {e}]"),
                    finish_reason="error",
                )
            ],
        )
        yield f"data: {json.dumps(asdict(error_chunk))}\n\n"
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

        models = [
            Model(id=model["name"], created=int(time.time())) for model in ollama_models
        ]
        return asdict(ModelList(data=models))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch models: {e}")


@app.post("/api/show")
async def show_model(request: dict[str, Any]) -> Any:
    """Proxy Ollama's native /api/show so Ollama-aware clients can query model metadata."""
    provider = OllamaProvider()
    client = provider._get_client()
    try:
        response = await client.post(f"{provider.base_url}/api/show", json=request)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Failed to reach Ollama: {e}")


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest) -> Any:
    """Handle chat completion requests, supporting streaming and non-streaming modes."""
    provider = OllamaProvider(model=request.model)

    messages_payload = [
        {"role": msg.role, "content": msg.content} for msg in request.messages
    ]

    options = {}
    if request.temperature is not None:
        options["temperature"] = request.temperature
    if request.max_tokens is not None:
        options["num_predict"] = request.max_tokens

    request_id = f"chatcmpl-{uuid.uuid4()}"
    created_time = int(time.time())

    if request.stream:
        return StreamingResponse(
            stream_generator(
                provider,
                messages_payload,
                request.model,
                request_id,
                created_time,
                options,
            ),
            media_type="text/event-stream",
        )

    try:
        content = await provider.chat_async(messages_payload, options=options)
        response = ChatCompletionResponse(
            id=request_id,
            created=created_time,
            model=request.model,
            choices=[Choice(message=AssistantMessage(content=content))],
        )
        return asdict(response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
