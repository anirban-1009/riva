import argparse
from pathlib import Path
from unittest.mock import patch

from riva_agent.cli import (
    cmd_digest_generate,
    cmd_digest_list,
    cmd_digest_schedule_install,
    cmd_digest_schedule_status,
    cmd_digest_schedule_uninstall,
    cmd_digest_show,
    cmd_digest_test_notify,
)
from riva_agent.digest.models import DigestRecord, NotificationResult


def test_cmd_digest_generate_dry_run(capsys):
    args = argparse.Namespace(
        date="2026-11-01",
        dry_run=True,
        no_notify=True,
        channel=None,
    )
    with (
        patch("riva_agent.digest.generator.collect_digest_context"),
        patch("riva_agent.digest.generator.generate_digest") as mock_gen,
    ):
        mock_gen.return_value = DigestRecord(
            id="d1",
            date="2026-11-01",
            title="Daily Briefing: 2026-11-01",
            content_markdown="# Preview content",
            filepath=None,
        )
        code = cmd_digest_generate(args)
        assert code == 0
        captured = capsys.readouterr().out
        assert "Digest created" in captured
        assert "Preview content" in captured


def test_cmd_digest_generate_with_notifications(capsys):
    args = argparse.Namespace(
        date="2026-11-01",
        dry_run=False,
        no_notify=False,
        channel="signal",
    )
    with (
        patch("riva_agent.digest.generator.collect_digest_context"),
        patch("riva_agent.digest.generator.generate_digest") as mock_gen,
        patch("riva_agent.digest.dispatcher.dispatch_digest_notifications") as mock_disp,
    ):
        mock_gen.return_value = DigestRecord(
            id="d1",
            date="2026-11-01",
            title="Daily Briefing: 2026-11-01",
            content_markdown="# Real content",
            filepath=Path("/tmp/d1.md"),
        )
        mock_disp.return_value = [NotificationResult(channel="signal", success=True, message="Delivered to Signal")]
        code = cmd_digest_generate(args)
        assert code == 0
        captured = capsys.readouterr().out
        assert "✔ Digest created" in captured
        assert "[SIGNAL] Delivered to Signal" in captured


def test_cmd_digest_list(capsys):
    # Empty
    args = argparse.Namespace(limit=10)
    with patch("riva_agent.digest.generator.list_digests", return_value=[]):
        code = cmd_digest_list(args)
        assert code == 0
        assert "No archived digests found" in capsys.readouterr().out

    # Populated
    records = [
        DigestRecord(
            id="d1",
            date="2026-11-01",
            title="Daily Briefing",
            content_markdown="Content",
            filepath=Path("/tmp/2026-11-01-digest.md"),
        )
    ]
    with patch("riva_agent.digest.generator.list_digests", return_value=records):
        code = cmd_digest_list(args)
        assert code == 0
        captured = capsys.readouterr().out
        assert "2026-11-01" in captured
        assert "Daily Briefing" in captured


def test_cmd_digest_show(capsys):
    # Not found
    args = argparse.Namespace(identifier="missing")
    with patch("riva_agent.digest.generator.read_digest", return_value=None):
        code = cmd_digest_show(args)
        assert code == 1
        assert "not found" in capsys.readouterr().err

    # Found
    record = DigestRecord(
        id="d1",
        date="2026-11-01",
        title="Daily Briefing",
        content_markdown="# Full Markdown Here",
        filepath=Path("/tmp/d1.md"),
    )
    with patch("riva_agent.digest.generator.read_digest", return_value=record):
        code = cmd_digest_show(args)
        assert code == 0
        captured = capsys.readouterr().out
        assert "Daily Briefing" in captured
        assert "# Full Markdown Here" in captured


def test_cmd_digest_test_notify(capsys):
    # Signal success
    args = argparse.Namespace(
        channel="signal",
        recipient="+1234567890",
        dry_run=True,
    )
    code = cmd_digest_test_notify(args)
    assert code == 0
    assert "[SIGNAL]" in capsys.readouterr().out

    # Signal missing recipient
    args_no_rec = argparse.Namespace(
        channel="signal",
        recipient=None,
        dry_run=True,
    )
    with patch("riva_agent.config.DIGEST_SIGNAL_RECIPIENT", None):
        code = cmd_digest_test_notify(args_no_rec)
        assert code == 1
        assert "No recipient specified" in capsys.readouterr().err

    # macOS success
    args_mac = argparse.Namespace(
        channel="macos",
        recipient=None,
        dry_run=True,
    )
    code = cmd_digest_test_notify(args_mac)
    assert code == 0
    assert "[MACOS]" in capsys.readouterr().out

    # Unknown channel
    args_unk = argparse.Namespace(
        channel="invalid_channel",
        recipient=None,
        dry_run=True,
    )
    code = cmd_digest_test_notify(args_unk)
    assert code == 1
    assert "Unknown channel" in capsys.readouterr().err


def test_cmd_digest_schedule_cli(capsys):
    # Install
    args_install = argparse.Namespace(time="08:00", dry_run=True)
    with patch("riva_agent.digest.scheduler.install_launchd_schedule", return_value=(True, "Installed mock")):
        code = cmd_digest_schedule_install(args_install)
        assert code == 0
        assert "Installed mock" in capsys.readouterr().out

    # Status
    args_status = argparse.Namespace()
    mock_status = {
        "installed": True,
        "loaded": True,
        "schedule_time": "08:00",
        "plist_path": "/tmp/plist",
        "detail": "Loaded and running",
    }
    with patch("riva_agent.digest.scheduler.get_launchd_schedule_status", return_value=mock_status):
        code = cmd_digest_schedule_status(args_status)
        assert code == 0
        captured = capsys.readouterr().out
        assert "Installed:       Yes" in captured
        assert "08:00" in captured

    # Uninstall
    args_uninstall = argparse.Namespace(dry_run=True)
    with patch("riva_agent.digest.scheduler.uninstall_launchd_schedule", return_value=(True, "Uninstalled mock")):
        code = cmd_digest_schedule_uninstall(args_uninstall)
        assert code == 0
        assert "Uninstalled mock" in capsys.readouterr().out
