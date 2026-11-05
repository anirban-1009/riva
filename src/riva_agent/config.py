import os
from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.yml"


def _load_dotenv(env_path: Path | None = None) -> None:
    """Load key-value environment variables from .env file into os.environ if present."""
    path = env_path or (Path(__file__).resolve().parent.parent.parent / ".env")
    if not path.is_file():
        return
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


_load_dotenv()


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
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", _ollama_config.get("model", "llama3:8b"))

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

# Proactive Local Digests (Phase 6 / M5) configuration
_digest_config: dict = _config.get("digest") or {}
_digest_signal_config: dict = _digest_config.get("signal") or {}


def get_digest_config(cfg: dict | None = None) -> dict:
    """Resolve digest configuration with environment variable overrides."""
    if cfg is None:
        cfg = _config
    d_cfg = cfg.get("digest") or {}
    sig_cfg = d_cfg.get("signal") or {}

    out_dir = os.environ.get("RIVA_DIGEST_OUTPUT_DIR", d_cfg.get("output_dir", str(DATA_DIR / "digests")))
    recipient = os.environ.get("RIVA_DIGEST_SIGNAL_RECIPIENT", sig_cfg.get("recipient"))
    if recipient:
        recipient = str(recipient).strip() or None
    else:
        recipient = None

    return {
        "enabled": os.environ.get("RIVA_DIGEST_ENABLED", str(d_cfg.get("enabled", True))).lower()
        in ("true", "1", "yes"),
        "output_dir": Path(out_dir).expanduser(),
        "schedule_time": os.environ.get("RIVA_DIGEST_SCHEDULE_TIME", str(d_cfg.get("schedule_time", "08:00"))),
        "signal_enabled": os.environ.get("RIVA_DIGEST_SIGNAL_ENABLED", str(sig_cfg.get("enabled", True))).lower()
        in ("true", "1", "yes"),
        "signal_recipient": recipient,
        "signal_send_full": os.environ.get("RIVA_DIGEST_SIGNAL_SEND_FULL", str(sig_cfg.get("send_full", True))).lower()
        in ("true", "1", "yes"),
        "macos_fallback": os.environ.get("RIVA_DIGEST_MACOS_FALLBACK", str(d_cfg.get("macos_fallback", True))).lower()
        in ("true", "1", "yes"),
    }


DIGEST_ENABLED: bool = get_digest_config()["enabled"]
DIGEST_OUTPUT_DIR: Path = get_digest_config()["output_dir"]
DIGEST_SCHEDULE_TIME: str = get_digest_config()["schedule_time"]
DIGEST_SIGNAL_ENABLED: bool = get_digest_config()["signal_enabled"]
DIGEST_SIGNAL_RECIPIENT: str | None = get_digest_config()["signal_recipient"]
DIGEST_SIGNAL_SEND_FULL: bool = get_digest_config()["signal_send_full"]
DIGEST_MACOS_FALLBACK: bool = get_digest_config()["macos_fallback"]

# MCP (Model Context Protocol) configuration
_mcp_config: dict = _config.get("mcp") or {}
MCP_ENABLED: bool = os.environ.get("RIVA_MCP_ENABLED", str(_mcp_config.get("enabled", True))).lower() in (
    "true",
    "1",
    "yes",
)
MCP_AUTO_APPROVE_READONLY: bool = bool(_mcp_config.get("auto_approve_readonly", True))
MCP_MAX_TOOL_ITERATIONS: int = int(
    os.environ.get("RIVA_MCP_MAX_ITERATIONS", str(_mcp_config.get("max_tool_iterations", 5)))
)
MCP_TIMEOUT_SECONDS: float = float(os.environ.get("RIVA_MCP_TIMEOUT", str(_mcp_config.get("timeout_seconds", 30.0))))
MCP_SERVERS: dict[str, Any] = dict(_mcp_config.get("servers", {}))
_mcp_server_config: dict = _mcp_config.get("server") or {}
MCP_API_KEY: str | None = os.environ.get(
    "RIVA_MCP_API_KEY",
    os.environ.get("RIVA_API_KEY", _mcp_server_config.get("api_key")),
)
if MCP_API_KEY:
    MCP_API_KEY = str(MCP_API_KEY).strip() or None
