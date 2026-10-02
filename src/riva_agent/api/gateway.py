import asyncio
import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from typing import Any, AsyncGenerator, Callable

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from common import get_episodic_store, get_profile_store
from common.llm.providers import LLMProvider, OllamaProvider, create_provider
from riva_agent import config
from riva_agent.intelligence.memory_router import route_memory
from riva_agent.intelligence.reasoning import (
    HybridDecision,
    ReasoningEffort,
    decide_reasoning_effort,
    get_thinking_router,
)
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-warm ThinkingRouter at startup so initial requests don't pay model load latency."""
    if config.THINKING_ENABLED:
        try:
            logger.info("Pre-warming ThinkingRouter (spaCy)...")
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
    on_complete: Callable[[str], None] | None = None,
) -> AsyncGenerator[str, None]:
    """Generate server-sent events for chat completion chunks."""
    token_iter = provider.chat_stream(messages, temperature=temperature, max_tokens=max_tokens, think=think).__aiter__()
    pending: asyncio.Task[Any] | None = None
    collected_tokens: list[str] = []
    try:
        role_chunk = Chunk(
            id=request_id,
            created=created_time,
            model=model,
            choices=[StreamChoice(delta=Delta(role="assistant"))],
        )
        role_dict = asdict(role_chunk)
        role_dict["choices"][0]["delta"] = {k: v for k, v in role_dict["choices"][0]["delta"].items() if v is not None}
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
                collected_tokens.append(token_text)

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

        if on_complete:
            try:
                on_complete("".join(collected_tokens))
            except Exception as e:
                logger.warning("on_complete callback failed: %s", e)

        done_chunk = Chunk(
            id=request_id,
            created=created_time,
            model=model,
            choices=[StreamChoice(index=0, finish_reason="stop")],
        )
        done_dict = asdict(done_chunk)
        done_dict["choices"][0]["delta"] = {k: v for k, v in done_dict["choices"][0]["delta"].items() if v is not None}
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
    base_url = config.OPENAI_BASE_URL if config.PROVIDER.lower() == "openai" else config.OLLAMA_BASE_URL
    api_key = config.OPENAI_API_KEY if config.PROVIDER.lower() == "openai" else None
    provider = create_provider(config.PROVIDER, base_url=base_url, api_key=api_key)
    try:
        model_ids = await provider.list_models()
        if "riva" not in model_ids:
            model_ids.insert(0, "riva")
        models = [Model(id=model_id, created=int(time.time())) for model_id in model_ids]
        return asdict(ModelList(data=models))
    except Exception as e:
        logger.exception("list_models failed")
        raise HTTPException(status_code=500, detail=f"Failed to fetch models: {e}")


@app.post("/api/show")
async def show_model(request: dict[str, Any]) -> Any:
    """Proxy Ollama's native /api/show so Ollama-aware clients can query model metadata."""
    if config.PROVIDER != "ollama":
        raise HTTPException(status_code=501, detail="/api/show is only available with the Ollama provider")
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


_RESET_COMMAND_REGEX = re.compile(
    r"^(?:/(?:new|reset|clear|new_session|session_new|start)|/session\s+new|(?:please\s+)?(?:start\s+a\s+)?new\s+session)(?:\s+(.*))?$",
    re.IGNORECASE,
)


def get_current_session_id() -> str:
    """Retrieve or initialize the active assistant session ID."""
    session_file = config.DATA_DIR / "session.id"
    if session_file.exists():
        try:
            sid = session_file.read_text().strip()
            if sid:
                return sid
        except OSError:
            pass
    sid = str(uuid.uuid4())
    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        session_file.write_text(sid)
    except OSError:
        pass
    return sid


def reset_session_id() -> str:
    """Generate and persist a new active assistant session ID."""
    sid = str(uuid.uuid4())
    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        (config.DATA_DIR / "session.id").write_text(sid)
    except OSError:
        pass
    return sid


@app.post("/v1/session/new")
async def start_new_session_endpoint() -> dict[str, str]:
    """Start a new chat session and return the new session ID."""
    sid = reset_session_id()
    return {"status": "ok", "session_id": sid, "message": "✨ New chat session started."}


@app.get("/v1/session")
async def get_session_endpoint() -> dict[str, str]:
    """Get the active chat session ID."""
    return {"session_id": get_current_session_id()}


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest) -> Any:
    """Handle chat completion requests, supporting streaming, non-streaming, and assistant mode."""
    is_assistant_mode = request.model.strip().lower() == "riva"

    if is_assistant_mode:
        model = config.MODEL or config.ASSISTANT_MODEL
    else:
        model = config.MODEL or request.model

    base_url = config.OPENAI_BASE_URL if config.PROVIDER.lower() == "openai" else config.OLLAMA_BASE_URL
    api_key = config.OPENAI_API_KEY if config.PROVIDER.lower() == "openai" else None
    provider = create_provider(
        config.PROVIDER,
        model=model,
        base_url=base_url,
        api_key=api_key,
    )

    messages_payload = [{"role": msg.role, "content": msg.content} for msg in request.messages]

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

    session_id = get_current_session_id() if is_assistant_mode else request_id
    profile_store = None
    episodic_store = None

    if is_assistant_mode:
        profile_store = get_profile_store(config.DATA_DIR / "profile.db")
        episodic_store = get_episodic_store(config.DATA_DIR / "memory.db")

        # 1. Profile Context injection
        profile_ctx = profile_store.format_context()
        assistant_persona = "You are Riva, a private personal assistant that knows me."
        system_instruction = f"{assistant_persona}\n\n{profile_ctx}" if profile_ctx else assistant_persona

        if messages_payload and messages_payload[0]["role"] == "system":
            messages_payload[0]["content"] = f"{system_instruction}\n\n{messages_payload[0]['content']}"
        else:
            messages_payload.insert(0, {"role": "system", "content": system_instruction})

        # 2. Check for Session Reset / New Session commands (triggerable via Signal, CLI, or API)
        reset_match = _RESET_COMMAND_REGEX.match(user_query.strip())
        if reset_match:
            session_id = reset_session_id()
            tail = reset_match.group(1)
            if tail:
                tail = tail.strip()

            if not tail:
                reset_text = "✨ New chat session started. Previous conversation context has been cleared."
                logger.info("Session reset command triggered via chat. New session_id=%s", session_id)
                if stream:

                    async def _reset_stream():
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
                        yield f"data: {json.dumps(role_dict, ensure_ascii=False)}\n\n"

                        msg_chunk = Chunk(
                            id=request_id,
                            created=created_time,
                            model=model,
                            choices=[StreamChoice(delta=Delta(content=reset_text))],
                        )
                        msg_dict = asdict(msg_chunk)
                        msg_dict["choices"][0]["delta"] = {
                            k: v for k, v in msg_dict["choices"][0]["delta"].items() if v is not None
                        }
                        yield f"data: {json.dumps(msg_dict, ensure_ascii=False)}\n\n"

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
                        yield f"data: {json.dumps(done_dict, ensure_ascii=False)}\n\n"
                        yield "data: [DONE]\n\n"

                    return StreamingResponse(_reset_stream(), media_type="text/event-stream")

                return asdict(
                    ChatCompletionResponse(
                        id=request_id,
                        created=created_time,
                        model=model,
                        choices=[Choice(message=AssistantMessage(content=reset_text))],
                    )
                )

            # Tail query present: reset history payload to just system instruction and the fresh user query
            messages_payload = [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": tail},
            ]
            user_query = tail

        # 2. Conversational Recency Replay (for single-turn requests such as `riva ask`)
        non_system_req = [m for m in request.messages if m.role != "system"]
        if len(non_system_req) <= 1 and episodic_store and not reset_match:
            past_turns = episodic_store.get_recent_turns(session_id, limit=6)
            if past_turns:
                history_msgs = [{"role": t.role, "content": t.content} for t in past_turns]
                current_non_system = [m for m in messages_payload if m["role"] != "system"]
                messages_payload = [messages_payload[0]] + history_msgs + current_non_system

        # 3. Episodic Log & Directive / Candidate Extraction
        if user_query:
            episodic_store.log_turn(session_id, "user", user_query)
            try:
                mem_event = route_memory(user_query)
                if mem_event.is_explicit:
                    clean_fact = re.sub(
                        r"^(please\s+)?(remember|keep in mind|take note|don't forget)\s*(that\s*)?",
                        "",
                        user_query,
                        flags=re.IGNORECASE,
                    ).strip()
                    if clean_fact:
                        profile_store.set(clean_fact[:50], clean_fact, category="facts")
                        logger.info("Explicit memory saved to profile: %s", clean_fact)
                elif mem_event.should_extract_memory:
                    # Passive candidate memory detected (§6 of Product Definition)
                    fact_candidate = user_query.strip()
                    existing_profile = profile_store.get(fact_candidate[:50])
                    pending_proposals = [p.fact for p in episodic_store.list_pending(status="pending")]
                    if not existing_profile and fact_candidate not in pending_proposals:
                        cand_id = episodic_store.add_pending(fact_candidate, user_query)
                        logger.info("Passive memory candidate #%d staged for review: %s", cand_id, fact_candidate)
            except Exception as e:
                logger.warning("Failed to evaluate memory route for query: %s", e)

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
        "chat_completions request_id=%s requested_model=%s concrete_model=%s assistant_mode=%s stream=%s effort=%s",
        request_id,
        request.model,
        model,
        is_assistant_mode,
        stream,
        effort.value,
    )

    on_complete_cb: Callable[[str], None] | None = None
    if is_assistant_mode and episodic_store:

        def _save_assistant_turn(text: str) -> None:
            if text.strip():
                episodic_store.log_turn(session_id, "assistant", text)

        on_complete_cb = _save_assistant_turn

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
                on_complete=on_complete_cb,
            ),
            media_type="text/event-stream",
        )

    try:
        content = await provider.chat_async(
            messages_payload, temperature=temperature, max_tokens=max_tokens, think=effort
        )
        if on_complete_cb:
            on_complete_cb(content)

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
