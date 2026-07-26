from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.yml"


def _load_config() -> dict:
    if not _CONFIG_PATH.exists():
        return {}
    with _CONFIG_PATH.open() as f:
        return yaml.safe_load(f) or {}


_config = _load_config()

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
