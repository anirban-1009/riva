from pathlib import Path
from unittest.mock import mock_open, patch

from riva_agent.config import (
    PROVIDER,
    STREAMING_ENABLED,
    THINKING_ENABLED,
    _load_config,
)


def test_config_defaults():
    """Verify that configuration defaults are loaded without crashing."""
    assert isinstance(PROVIDER, str)
    assert isinstance(THINKING_ENABLED, bool)
    assert isinstance(STREAMING_ENABLED, bool)


def test_load_config_missing_file():
    """Verify _load_config returns empty dict when file does not exist."""
    with patch.object(Path, "exists", return_value=False):
        loaded = _load_config()
        assert loaded == {}


def test_load_config_valid_yaml():
    """Verify _load_config parses YAML when config file exists."""
    yaml_content = "provider: openai\nmodel: test-model\nthinking: false\nmemory_router_laya: true\n"
    with (
        patch.object(Path, "exists", return_value=True),
        patch.object(Path, "open", mock_open(read_data=yaml_content)),
    ):
        loaded = _load_config()
        assert loaded["provider"] == "openai"
        assert loaded["model"] == "test-model"
        assert loaded["thinking"] is False
        assert loaded["memory_router_laya"] is True


def test_memory_router_laya_config_default():
    """Verify MEMORY_ROUTER_LAYA_ENABLED default is a boolean and resolves to False when unconfigured."""
    from riva_agent.config import (
        MEMORY_LAYA_ENABLED,
        MEMORY_ROUTER_LAYA_ENABLED,
        _resolve_memory_router_laya,
    )

    assert isinstance(MEMORY_ROUTER_LAYA_ENABLED, bool)
    assert MEMORY_LAYA_ENABLED == MEMORY_ROUTER_LAYA_ENABLED

    # When no env var and no config entry is provided, default must be False
    with patch.dict("os.environ", {}, clear=True):
        assert _resolve_memory_router_laya({}) is False
        assert _resolve_memory_router_laya({"memory_router_laya": True}) is True
        assert _resolve_memory_router_laya({"memory": {"laya": True}}) is True

    # Env var override takes precedence
    with patch.dict("os.environ", {"RIVA_MEMORY_LAYA": "true"}):
        assert _resolve_memory_router_laya({}) is True
        assert _resolve_memory_router_laya({"memory_router_laya": False}) is True


def test_load_dotenv(tmp_path):
    """Verify _load_dotenv parses .env key-value pairs without overriding existing env."""
    import os

    from riva_agent.config import _load_dotenv

    env_file = tmp_path / ".env"
    env_file.write_text(
        "# Comment line\n"
        "\n"
        "RIVA_MCP_API_KEY=my_secret_token\n"
        'OPENAI_API_KEY="sk-12345"\n'
        "EXISTING_KEY=new_val\n"
        "MALFORMED_LINE\n"
    )

    with patch.dict(os.environ, {"EXISTING_KEY": "original_val"}, clear=True):
        _load_dotenv(env_file)
        assert os.environ["RIVA_MCP_API_KEY"] == "my_secret_token"
        assert os.environ["OPENAI_API_KEY"] == "sk-12345"
        assert os.environ["EXISTING_KEY"] == "original_val"  # Did not overwrite
