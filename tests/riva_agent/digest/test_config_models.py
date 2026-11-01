from pathlib import Path
from unittest.mock import patch

from riva_agent.config import (
    DIGEST_ENABLED,
    DIGEST_MACOS_FALLBACK,
    DIGEST_OUTPUT_DIR,
    DIGEST_SCHEDULE_TIME,
    DIGEST_SIGNAL_ENABLED,
    get_digest_config,
)
from riva_agent.digest.models import (
    DigestConfig,
    DigestContext,
    DigestRecord,
    NotificationResult,
)


def test_digest_config_defaults():
    """Verify that digest config defaults are loaded properly."""
    assert isinstance(DIGEST_ENABLED, bool)
    assert isinstance(DIGEST_OUTPUT_DIR, Path)
    assert isinstance(DIGEST_SCHEDULE_TIME, str)
    assert isinstance(DIGEST_SIGNAL_ENABLED, bool)
    assert isinstance(DIGEST_MACOS_FALLBACK, bool)


def test_get_digest_config_custom_dict():
    """Verify get_digest_config parses custom config dict correctly."""
    cfg = {
        "digest": {
            "enabled": False,
            "output_dir": "/custom/digests",
            "schedule_time": "09:30",
            "signal": {
                "enabled": True,
                "recipient": "+1234567890",
                "send_full": False,
            },
            "macos_fallback": False,
        }
    }
    with patch.dict("os.environ", {}, clear=True):
        resolved = get_digest_config(cfg)
        assert resolved["enabled"] is False
        assert resolved["output_dir"] == Path("/custom/digests")
        assert resolved["schedule_time"] == "09:30"
        assert resolved["signal_enabled"] is True
        assert resolved["signal_recipient"] == "+1234567890"
        assert resolved["signal_send_full"] is False
        assert resolved["macos_fallback"] is False


def test_get_digest_config_env_overrides():
    """Verify environment variables override dict configurations."""
    cfg = {
        "digest": {
            "enabled": False,
            "output_dir": "/custom/digests",
            "schedule_time": "09:30",
            "signal": {
                "enabled": False,
                "recipient": "+1111111111",
                "send_full": False,
            },
            "macos_fallback": False,
        }
    }
    env = {
        "RIVA_DIGEST_ENABLED": "true",
        "RIVA_DIGEST_OUTPUT_DIR": "/env/digests",
        "RIVA_DIGEST_SCHEDULE_TIME": "07:15",
        "RIVA_DIGEST_SIGNAL_ENABLED": "true",
        "RIVA_DIGEST_SIGNAL_RECIPIENT": "+9999999999",
        "RIVA_DIGEST_SIGNAL_SEND_FULL": "true",
        "RIVA_DIGEST_MACOS_FALLBACK": "true",
    }
    with patch.dict("os.environ", env, clear=True):
        resolved = get_digest_config(cfg)
        assert resolved["enabled"] is True
        assert resolved["output_dir"] == Path("/env/digests")
        assert resolved["schedule_time"] == "07:15"
        assert resolved["signal_enabled"] is True
        assert resolved["signal_recipient"] == "+9999999999"
        assert resolved["signal_send_full"] is True
        assert resolved["macos_fallback"] is True


def test_digest_config_model():
    """Verify DigestConfig model behavior and from_env_or_config factory."""
    cfg_obj = DigestConfig.from_env_or_config()
    assert isinstance(cfg_obj.enabled, bool)
    assert isinstance(cfg_obj.output_dir, Path)
    assert isinstance(cfg_obj.schedule_time, str)


def test_models_instantiation():
    """Verify data models instantiation and default fields."""
    notif = NotificationResult(
        channel="signal",
        success=True,
        message="Sent 120 chars",
    )
    assert notif.channel == "signal"
    assert notif.success is True
    assert notif.error is None
    assert notif.timestamp is not None

    ctx = DigestContext(
        date="2026-11-01",
        profile_goals=[{"key": "fitness", "value": "Run 5k"}],
        pending_memories=[{"id": 1, "fact": "Likes green tea"}],
    )
    assert ctx.date == "2026-11-01"
    assert len(ctx.profile_goals) == 1
    assert len(ctx.pending_memories) == 1
    assert ctx.recent_turns == []

    record = DigestRecord(
        id="2026-11-01-brief",
        date="2026-11-01",
        title="Daily Briefing",
        content_markdown="# Daily Briefing\nReady for today.",
        filepath=Path("/tmp/2026-11-01-brief.md"),
        notifications=[notif],
    )
    assert record.id == "2026-11-01-brief"
    assert record.date == "2026-11-01"
    assert len(record.notifications) == 1
    assert record.filepath == Path("/tmp/2026-11-01-brief.md")
