import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from typing import Any, AsyncGenerator

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from common.llm.providers import LLMProvider, OllamaProvider, create_provider
from riva_agent import config
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
from riva_agent.intelligence.reasoning import (
    HybridDecision,
    ReasoningEffort,
    decide_reasoning_effort,
    get_thinking_router,
)

try:
    __version__ = version("riva-agent")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-warm ThinkingRouter at startup so initial requests don't pay model load latency."""
    if config.THINKING_ENABLED:
        try:
            logger.info("Pre-warming ThinkingRouter (spaCy + Laya MLX)...")
            await asyncio.to_thread(get_thinking_router)
            logger.info("ThinkingRouter pre-warmed successfully.")
        except Exception as e:
            logger.warning("Failed to pre-warm ThinkingRouter: %s", e)
    yield


app = FastAPI(title="Riva Agent AI Gateway", version=__version__, lifespan=lifespan)


# How often to emit an SSE comment while waiting for the next token, so
# proxies/clients don't treat a slow cold model load as a dead connection.
_HEARTBEAT_INTERVAL_S = 15.0


async def stream_generator(
    provider: LLMProvider,
    messages: list[dict[str, str]],
    model: str,
    request_id: str,
    created_time: int,
    temperature: float | None,
    max_tokens: int | None,
    think: Any = None,
) -> AsyncGenerator[str, None]:
    """Generate server-sent events for chat completion chunks."""
    token_iter = provider.chat_stream(
        messages, temperature=temperature, max_tokens=max_tokens, think=think
    ).__aiter__()
    pending: asyncio.Task[Any] | None = None
    try:
        role_chunk = Chunk(
            id=request_id,
            created=created_time,
            model=model,
            choices=[StreamChoice(delta=Delta(role="assistant"))],
        )
        role_dict = asdict(role_chunk)
        role_dict["choices"][0]["delta"] = {
            k: v for k, v in role_dict["choices"][0]["delta"].items() if v is not None
        }
        yield f"data: {json.dumps(role_dict)}\n\n"

        while True:
            if pending is None:
                pending = asyncio.ensure_future(token_iter.__anext__())

            # Wait, not wait_for: wait_for cancels the awaited coroutine on
            # timeout, which would tear down the in-flight Ollama request
            # every time prefill on a large prompt outlasts the heartbeat
            # interval. wait leaves it running so we can keep polling it.
            done, _ = await asyncio.wait({pending}, timeout=_HEARTBEAT_INTERVAL_S)
            if pending not in done:
                yield ": keep-alive\n\n"
                continue

            task, pending = pending, None
            try:
                token_item = task.result()
            except StopAsyncIteration:
                break

            if isinstance(token_item, tuple):
                kind, token_text = token_item
            else:
                kind, token_text = "content", token_item

            if kind == "reasoning":
                delta = Delta(reasoning_content=token_text, reasoning=token_text)
            else:
                delta = Delta(content=token_text)

            chunk = Chunk(
                id=request_id,
                created=created_time,
                model=model,
                choices=[StreamChoice(delta=delta)],
            )
            chunk_dict = asdict(chunk)
            chunk_dict["choices"][0]["delta"] = {
                k: v for k, v in chunk_dict["choices"][0]["delta"].items() if v is not None
            }
            yield f"data: {json.dumps(chunk_dict)}\n\n"

        done_chunk = Chunk(
            id=request_id,
            created=created_time,
            model=model,
            choices=[StreamChoice(index=0, finish_reason="stop")],
        )
        done_dict = asdict(done_chunk)
        done_dict["choices"][0]["delta"] = {
            k: v for k, v in done_dict["choices"][0]["delta"].items() if v is not None
        }
        yield f"data: {json.dumps(done_dict)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        logger.exception("stream_generator failed request_id=%s model=%s", request_id, model)
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
    finally:
        if pending is not None:
            pending.cancel()


@app.get("/v1/models")
async def list_models() -> dict[str, Any]:
    """List available models from the configured backend in OpenAI-compatible format."""
    provider = create_provider(
        config.PROVIDER, base_url=config.OPENAI_BASE_URL, api_key=config.OPENAI_API_KEY
    )
    try:
        model_ids = await provider.list_models()
        models = [Model(id=model_id, created=int(time.time())) for model_id in model_ids]
        return asdict(ModelList(data=models))
    except Exception as e:
        logger.exception("list_models failed")
        raise HTTPException(status_code=500, detail=f"Failed to fetch models: {e}")


@app.post("/api/show")
async def show_model(request: dict[str, Any]) -> Any:
    """Proxy Ollama's native /api/show so Ollama-aware clients can query model metadata."""
    if config.PROVIDER != "ollama":
        raise HTTPException(
            status_code=501, detail="/api/show is only available with the Ollama provider"
        )
    provider = OllamaProvider()
    client = provider._get_client()
    try:
        response = await client.post(f"{provider.base_url}/api/show", json=request)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        logger.warning("show_model rejected by Ollama: %s", e.response.text)
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.HTTPError as e:
        logger.exception("show_model failed to reach Ollama")
        raise HTTPException(status_code=502, detail=f"Failed to reach Ollama: {e}")


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest) -> Any:
    """Handle chat completion requests, supporting streaming and non-streaming modes."""
    model = config.MODEL or request.model
    provider = create_provider(
        config.PROVIDER,
        model=model,
        base_url=config.OPENAI_BASE_URL,
        api_key=config.OPENAI_API_KEY,
    )

    messages_payload = [
        {"role": msg.role, "content": msg.content} for msg in request.messages
    ]

    temperature = request.temperature
    max_tokens = request.max_tokens

    request_id = f"chatcmpl-{uuid.uuid4()}"
    created_time = int(time.time())

    stream = request.stream and config.STREAMING_ENABLED

    # Extract only the latest user query so previous history does not pollute the router
    user_query = ""
    for msg in reversed(request.messages):
        if msg.role == "user":
            user_query = msg.content
            break

    capabilities = await provider.get_capabilities(model)
    decision: HybridDecision | None = None
    effort: ReasoningEffort = ReasoningEffort.NONE

    if not config.THINKING_ENABLED or not user_query.strip():
        effort = ReasoningEffort.NONE
    elif "thinking" in capabilities or config.PROVIDER == "openai_compatible":
        decision = await asyncio.to_thread(decide_reasoning_effort, user_query)
        effort = decision.effort_level
    else:
        effort = ReasoningEffort.NONE

    logger.info(
        "chat_completions request_id=%s model=%s stream=%s effort=%s source=%s router_ms=%.2f",
        request_id,
        model,
        stream,
        effort.value,
        decision.source if decision else ("disabled" if not config.THINKING_ENABLED else "no_capability"),
        decision.latency_ms if decision else 0.0,
    )

    if stream:
        return StreamingResponse(
            stream_generator(
                provider,
                messages_payload,
                model,
                request_id,
                created_time,
                temperature,
                max_tokens,
                effort,
            ),
            media_type="text/event-stream",
        )

    try:
        content = await provider.chat_async(
            messages_payload, temperature=temperature, max_tokens=max_tokens, think=effort
        )
        response = ChatCompletionResponse(
            id=request_id,
            created=created_time,
            model=model,
            choices=[Choice(message=AssistantMessage(content=content))],
        )
        return asdict(response)
    except Exception as e:
        logger.exception("chat_completions failed request_id=%s model=%s", request_id, model)
        raise HTTPException(status_code=500, detail=str(e))
