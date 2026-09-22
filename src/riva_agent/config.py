from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.yml"


def _load_config() -> dict:
    if not _CONFIG_PATH.exists():
        return {}
    with _CONFIG_PATH.open() as f:
        return yaml.safe_load(f) or {}


_config = _load_config()

# Which LLM backend to talk to: "ollama" or "openai" (any OpenAI-compatible
# API — OpenAI itself, Groq, OpenRouter, a self-hosted vLLM/LM Studio server,
# etc, configured below). Defaults to Ollama so existing local setups keep
# working without a config change.
PROVIDER: str = _config.get("provider", "ollama")

_openai_config: dict = _config.get("openai") or {}

# Base URL / API key for the "openai" provider. Unset here falls back to the
# OPENAI_BASE_URL / OPENAI_API_KEY env vars (see
# common/src/common/llm/providers.py), so secrets don't have to live in
# config.yml if you'd rather keep them out of a file entirely.
OPENAI_BASE_URL: str | None = _openai_config.get("base_url")
OPENAI_API_KEY: str | None = _openai_config.get("api_key")

# When set, every /v1/chat/completions request uses this model regardless of
# what the client asks for.
MODEL: str | None = _config.get("model")

# Kill switch for the extended-thinking heuristic. False disables "think"
# entirely regardless of prompt content or model capability; True (default)
# leaves the per-request heuristic in reasoning.py in charge.
THINKING_ENABLED: bool = _config.get("thinking", True)

# When False, every /v1/chat/completions request is forced non-streaming
# regardless of the client's "stream" field. True (default) respects
# whatever the client asks for.
STREAMING_ENABLED: bool = _config.get("streaming", True)
