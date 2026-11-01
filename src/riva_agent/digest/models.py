from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from riva_agent.config import (
    DIGEST_OUTPUT_DIR,
    get_digest_config,
)


@dataclass
class DigestConfig:
    """Resolved configuration for digest generation and dispatch."""

    enabled: bool = True
    output_dir: Path = field(default_factory=lambda: Path(DIGEST_OUTPUT_DIR))
    schedule_time: str = "08:00"
    signal_enabled: bool = True
    signal_recipient: str | None = None
    signal_send_full: bool = True
    macos_fallback: bool = True

    @classmethod
    def from_env_or_config(cls, cfg: dict | None = None) -> "DigestConfig":
        """Instantiate a DigestConfig using config.py resolution."""
        resolved = get_digest_config(cfg)
        return cls(
            enabled=resolved["enabled"],
            output_dir=resolved["output_dir"],
            schedule_time=resolved["schedule_time"],
            signal_enabled=resolved["signal_enabled"],
            signal_recipient=resolved["signal_recipient"],
            signal_send_full=resolved["signal_send_full"],
            macos_fallback=resolved["macos_fallback"],
        )


@dataclass
class NotificationResult:
    """Outcome of attempting to send a notification over a specific channel."""

    channel: str  # "signal" | "macos" | "none"
    success: bool
    message: str
    error: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DigestContext:
    """Context gathered from local stores used to synthesize a digest."""

    date: str  # YYYY-MM-DD
    profile_facts: list[dict[str, Any]] = field(default_factory=list)
    profile_goals: list[dict[str, Any]] = field(default_factory=list)
    profile_constraints: list[dict[str, Any]] = field(default_factory=list)
    profile_preferences: list[dict[str, Any]] = field(default_factory=list)
    recent_turns: list[dict[str, Any]] = field(default_factory=list)
    pending_memories: list[dict[str, Any]] = field(default_factory=list)
    additional_notes: list[str] = field(default_factory=list)


@dataclass
class DigestRecord:
    """A generated digest record and its storage metadata."""

    id: str
    date: str  # YYYY-MM-DD
    title: str
    content_markdown: str
    filepath: Path | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    notifications: list[NotificationResult] = field(default_factory=list)
