import os
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
PROVIDER: str = (
    os.environ.get("RIVA_PROVIDER") or os.environ.get("PROVIDER") or _config.get("provider", "ollama") or "ollama"
).lower()

_ollama_config: dict = _config.get("ollama") or {}
OLLAMA_BASE_URL: str | None = os.environ.get("OLLAMA_BASE_URL", _ollama_config.get("base_url"))

_openai_config: dict = _config.get("openai") or {}

# Base URL / API key for the "openai" provider. Unset here falls back to the
# OPENAI_BASE_URL / OPENAI_API_KEY env vars (see
# common/src/common/llm/providers.py), so secrets don't have to live in
# config.yml if you'd rather keep them out of a file entirely.
OPENAI_BASE_URL: str | None = os.environ.get("OPENAI_BASE_URL", _openai_config.get("base_url"))
OPENAI_API_KEY: str | None = os.environ.get("OPENAI_API_KEY", _openai_config.get("api_key"))

# When set, every /v1/chat/completions request uses this model regardless of
# what the client asks for.
MODEL: str | None = os.environ.get("RIVA_MODEL", os.environ.get("MODEL", _config.get("model")))

# Kill switch for the extended-thinking heuristic. False disables "think"
# entirely regardless of prompt content or model capability; True (default)
# leaves the per-request heuristic in reasoning.py in charge.
THINKING_ENABLED: bool = _config.get("thinking", True)

# When False, every /v1/chat/completions request is forced non-streaming
# regardless of the client's "stream" field. True (default) respects
# whatever the client asks for.
STREAMING_ENABLED: bool = _config.get("streaming", True)

# Directory where local SQLite stores (profile.db, memory.db) reside.
DATA_DIR: Path = Path(os.environ.get("RIVA_DATA_DIR", _config.get("data_dir", Path.home() / ".riva")))

# Default concrete model to dispatch Assistant Mode ("riva") requests to.
ASSISTANT_MODEL: str = _config.get("assistant_model") or MODEL or "llama3:8b"


def _resolve_memory_router_laya(cfg: dict | None = None) -> bool:
    if cfg is None:
        cfg = _config
    if "RIVA_MEMORY_LAYA" in os.environ:
        return os.environ.get("RIVA_MEMORY_LAYA", "").lower() in ("true", "1", "yes")
    if "memory_router_laya" in cfg:
        return bool(cfg.get("memory_router_laya"))
    if "memory_laya" in cfg:
        return bool(cfg.get("memory_laya"))
    return bool((cfg.get("memory") or {}).get("laya", False))


# Toggle Laya MLX in MemoryRouter. False (default) uses fast, deterministic
# linguistic & syntactic regex heuristics (< 0.2ms, 0 MB extra RAM); True loads
# and uses the in-process aac6fef/laya-mlx SLM (~800 MB RAM).
MEMORY_ROUTER_LAYA_ENABLED: bool = _resolve_memory_router_laya(_config)
MEMORY_LAYA_ENABLED: bool = MEMORY_ROUTER_LAYA_ENABLED

# Embedding configuration for semantic memory retrieval (M4)
_embedding_config: dict = _config.get("embedding") or {}
EMBEDDING_PROVIDER: str = os.environ.get("RIVA_EMBEDDING_PROVIDER", _embedding_config.get("provider", "ollama"))
EMBEDDING_MODEL: str = os.environ.get("RIVA_EMBEDDING_MODEL", _embedding_config.get("model", "nomic-embed-text"))
EMBEDDING_BASE_URL: str | None = os.environ.get(
    "RIVA_EMBEDDING_BASE_URL", _embedding_config.get("base_url", OLLAMA_BASE_URL)
)
EMBEDDING_DIMENSION: int = int(os.environ.get("RIVA_EMBEDDING_DIMENSION", _embedding_config.get("dimension", 768)))

# Semantic recall parameters for Hybrid Context Assembly (M4 Phase 4)
SEMANTIC_RECALL_ENABLED: bool = os.environ.get(
    "RIVA_SEMANTIC_RECALL",
    str(_config.get("semantic_recall", True)),
).lower() in ("true", "1", "yes")

SEMANTIC_TOP_K: int = int(
    os.environ.get(
        "RIVA_SEMANTIC_TOP_K",
        str(_embedding_config.get("top_k", 3)),
    )
)

SEMANTIC_DISTANCE_THRESHOLD: float = float(
    os.environ.get(
        "RIVA_SEMANTIC_DISTANCE_THRESHOLD",
        str(_embedding_config.get("threshold", 0.38)),
    )
)
