from unittest.mock import MagicMock, patch

from riva_agent.digest.scheduler import (
    LAUNCHD_LABEL,
    generate_launchd_plist,
    get_launchd_schedule_status,
    install_launchd_schedule,
    parse_schedule_time,
    uninstall_launchd_schedule,
)


def test_parse_schedule_time():
    assert parse_schedule_time("08:00") == (8, 0)
    assert parse_schedule_time("07:30") == (7, 30)
    assert parse_schedule_time("23:59") == (23, 59)
    assert parse_schedule_time("invalid") == (8, 0)
    assert parse_schedule_time("") == (8, 0)


def test_generate_launchd_plist(tmp_path):
    plist = generate_launchd_plist(schedule_time="09:15", project_dir=tmp_path, log_dir=tmp_path)
    assert LAUNCHD_LABEL in plist
    assert "<integer>9</integer>" in plist
    assert "<integer>15</integer>" in plist
    assert str(tmp_path) in plist
    assert "riva" in plist
    assert "digest" in plist
    assert "generate" in plist


def test_install_launchd_schedule_dry_run(tmp_path):
    success, msg = install_launchd_schedule(
        schedule_time="08:00",
        agents_dir=tmp_path,
        dry_run=True,
    )
    assert success is True
    assert "[dry-run]" in msg
    assert list(tmp_path.glob("*.plist")) == []


def test_install_launchd_schedule_live(tmp_path):
    mock_proc = MagicMock(returncode=0, stderr="", stdout="")
    with patch("subprocess.run", return_value=mock_proc) as mock_run:
        success, msg = install_launchd_schedule(
            schedule_time="08:30",
            agents_dir=tmp_path,
            dry_run=False,
        )
        assert success is True
        assert "Successfully installed" in msg
        plist_file = tmp_path / f"{LAUNCHD_LABEL}.plist"
        assert plist_file.exists()
        assert "<integer>8</integer>" in plist_file.read_text()
        assert "<integer>30</integer>" in plist_file.read_text()
        # Verify launchctl commands called
        assert mock_run.call_count == 2


def test_uninstall_launchd_schedule(tmp_path):
    # Non-existent plist
    success, msg = uninstall_launchd_schedule(agents_dir=tmp_path)
    assert success is True
    assert "No launchd agent file found" in msg

    # Create dummy plist
    plist_file = tmp_path / f"{LAUNCHD_LABEL}.plist"
    plist_file.write_text("<plist></plist>", encoding="utf-8")

    # Dry run
    success, msg = uninstall_launchd_schedule(agents_dir=tmp_path, dry_run=True)
    assert success is True
    assert "[dry-run]" in msg
    assert plist_file.exists()

    # Live uninstall
    mock_proc = MagicMock(returncode=0)
    with patch("subprocess.run", return_value=mock_proc):
        success, msg = uninstall_launchd_schedule(agents_dir=tmp_path, dry_run=False)
        assert success is True
        assert "Successfully uninstalled" in msg
        assert not plist_file.exists()


def test_get_launchd_schedule_status(tmp_path):
    # Not installed
    status = get_launchd_schedule_status(agents_dir=tmp_path)
    assert status["installed"] is False
    assert status["loaded"] is False

    # Installed
    plist_content = generate_launchd_plist(schedule_time="07:45", project_dir=tmp_path)
    plist_file = tmp_path / f"{LAUNCHD_LABEL}.plist"
    plist_file.write_text(plist_content, encoding="utf-8")

    mock_proc = MagicMock(returncode=0)  # launchctl list succeeded
    with patch("subprocess.run", return_value=mock_proc):
        status = get_launchd_schedule_status(agents_dir=tmp_path)
        assert status["installed"] is True
        assert status["schedule_time"] == "07:45"
        assert status["loaded"] is True
        assert "active and loaded" in status["detail"]
