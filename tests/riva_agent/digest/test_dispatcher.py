import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from riva_agent.digest.dispatcher import (
    _split_text_chunks,
    dispatch_digest_notifications,
    send_macos_notification,
    send_signal_message,
)
from riva_agent.digest.models import DigestConfig, DigestRecord, NotificationResult


def test_split_text_chunks():
    short = "Hello world"
    assert _split_text_chunks(short, max_chars=100) == ["Hello world"]

    # Paragraph split
    p1 = "A" * 60
    p2 = "B" * 60
    combined = f"{p1}\n\n{p2}"
    chunks = _split_text_chunks(combined, max_chars=80)
    assert len(chunks) == 2
    assert chunks[0] == p1
    assert chunks[1] == p2

    # Monolithic long string
    mono = "X" * 150
    mono_chunks = _split_text_chunks(mono, max_chars=50)
    assert len(mono_chunks) == 3
    assert mono_chunks[0] == "X" * 50


def test_send_signal_message_validation():
    # Empty recipient
    res = send_signal_message("", "Hello")
    assert res.channel == "signal"
    assert res.success is False
    assert "No Signal recipient" in res.message


def test_send_signal_message_dry_run():
    res = send_signal_message("+1234567890", "Briefing test", dry_run=True)
    assert res.channel == "signal"
    assert res.success is True
    assert "[dry-run]" in res.message


def test_send_signal_message_openclaw_missing():
    with patch("shutil.which", return_value=None):
        res = send_signal_message("+1234567890", "Test")
        assert res.channel == "signal"
        assert res.success is False
        assert "openclaw CLI executable not found" in res.message


def test_send_signal_message_success():
    mock_proc = MagicMock(returncode=0, stdout="sent", stderr="")
    with (
        patch("shutil.which", return_value="/usr/local/bin/openclaw"),
        patch("subprocess.run", return_value=mock_proc) as mock_run,
    ):
        res = send_signal_message("+1234567890", "Test message")
        assert res.success is True
        assert "Delivered 1 chunk" in res.message
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[:5] == ["/usr/local/bin/openclaw", "message", "send", "--channel", "signal"]
        assert cmd[5:8] == ["--target", "+1234567890", "--message"]


def test_send_signal_message_failure():
    mock_proc = MagicMock(returncode=1, stdout="", stderr="Channel offline")
    with patch("shutil.which", return_value="/usr/local/bin/openclaw"), patch("subprocess.run", return_value=mock_proc):
        res = send_signal_message("+1234567890", "Test message")
        assert res.success is False
        assert "Channel offline" in res.message


def test_send_signal_message_timeout():
    with (
        patch("shutil.which", return_value="/usr/local/bin/openclaw"),
        patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["openclaw"], timeout=5)),
    ):
        res = send_signal_message("+1234567890", "Test message", timeout=5)
        assert res.success is False
        assert "Timed out" in res.message


def test_send_macos_notification_dry_run():
    res = send_macos_notification("Riva Briefing", "Ready today", dry_run=True)
    assert res.channel == "macos"
    assert res.success is True
    assert "[dry-run]" in res.message


def test_send_macos_notification_subprocess():
    mock_proc = MagicMock(returncode=0, stdout="", stderr="")
    with patch("subprocess.run", return_value=mock_proc) as mock_run:
        res = send_macos_notification('Title "with quotes"', "Message \\with backslash\nand newline")
        assert res.success is True
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "osascript"
        assert "display notification" in cmd[2]


def test_dispatch_digest_force_channel():
    rec = DigestRecord(
        id="d1",
        date="2026-11-01",
        title="Test Brief",
        content_markdown="Content",
        filepath=Path("/tmp/d1.md"),
    )
    with patch("riva_agent.digest.dispatcher.send_macos_notification") as mock_mac:
        mock_mac.return_value = NotificationResult(channel="macos", success=True, message="ok")
        results = dispatch_digest_notifications(rec, force_channel="macos")
        assert len(results) == 1
        assert results[0].channel == "macos"
        mock_mac.assert_called_once()


def test_dispatch_digest_signal_success_no_fallback():
    rec = DigestRecord(
        id="d1",
        date="2026-11-01",
        title="Test Brief",
        content_markdown="Content",
        filepath=Path("/tmp/d1.md"),
    )
    cfg = DigestConfig(
        signal_enabled=True,
        signal_recipient="+1234567890",
        macos_fallback=True,
    )
    with (
        patch("riva_agent.digest.dispatcher.send_signal_message") as mock_sig,
        patch("riva_agent.digest.dispatcher.send_macos_notification") as mock_mac,
    ):
        mock_sig.return_value = NotificationResult(channel="signal", success=True, message="sent")
        results = dispatch_digest_notifications(rec, config_obj=cfg)
        assert len(results) == 1
        assert results[0].channel == "signal"
        mock_sig.assert_called_once()
        mock_mac.assert_not_called()


def test_dispatch_digest_signal_failure_triggers_fallback():
    rec = DigestRecord(
        id="d1",
        date="2026-11-01",
        title="Test Brief",
        content_markdown="Content",
        filepath=Path("/tmp/d1.md"),
    )
    cfg = DigestConfig(
        signal_enabled=True,
        signal_recipient="+1234567890",
        macos_fallback=True,
    )
    with (
        patch("riva_agent.digest.dispatcher.send_signal_message") as mock_sig,
        patch("riva_agent.digest.dispatcher.send_macos_notification") as mock_mac,
    ):
        mock_sig.return_value = NotificationResult(channel="signal", success=False, message="failed")
        mock_mac.return_value = NotificationResult(channel="macos", success=True, message="fallback sent")

        results = dispatch_digest_notifications(rec, config_obj=cfg)
        assert len(results) == 2
        assert results[0].channel == "signal"
        assert results[0].success is False
        assert results[1].channel == "macos"
        assert results[1].success is True
        mock_mac.assert_called_once()


def test_dispatch_digest_missing_recipient_triggers_fallback():
    rec = DigestRecord(
        id="d1",
        date="2026-11-01",
        title="Test Brief",
        content_markdown="Content",
        filepath=Path("/tmp/d1.md"),
    )
    cfg = DigestConfig(
        signal_enabled=True,
        signal_recipient=None,
        macos_fallback=True,
    )
    with patch("riva_agent.digest.dispatcher.send_macos_notification") as mock_mac:
        mock_mac.return_value = NotificationResult(channel="macos", success=True, message="fallback sent")
        results = dispatch_digest_notifications(rec, config_obj=cfg)
        assert len(results) == 2
        assert results[0].channel == "signal"
        assert results[0].success is False
        assert results[1].channel == "macos"
        assert results[1].success is True
