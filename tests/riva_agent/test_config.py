import pytest
from unittest.mock import patch, mock_open
from pathlib import Path

from riva_agent import config
from riva_agent.config import (
    PROVIDER,
    THINKING_ENABLED,
    STREAMING_ENABLED,
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
    with patch.object(Path, "exists", return_value=True), \
         patch.object(Path, "open", mock_open(read_data=yaml_content)):
        loaded = _load_config()
        assert loaded["provider"] == "openai"
        assert loaded["model"] == "test-model"
        assert loaded["thinking"] is False
        assert loaded["memory_router_laya"] is True


def test_memory_router_laya_config_default():
    """Verify MEMORY_ROUTER_LAYA_ENABLED default is a boolean (False by default)."""
    from riva_agent.config import MEMORY_ROUTER_LAYA_ENABLED, MEMORY_LAYA_ENABLED
    assert isinstance(MEMORY_ROUTER_LAYA_ENABLED, bool)
    assert MEMORY_ROUTER_LAYA_ENABLED is False
    assert MEMORY_LAYA_ENABLED == MEMORY_ROUTER_LAYA_ENABLED

