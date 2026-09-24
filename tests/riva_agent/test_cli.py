from unittest.mock import MagicMock, patch
import pytest

from riva_agent import cli, config
from common.profile.store import ProfileStore
from common.memory.store import EpisodicStore


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / ".riva"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    return data_dir


def test_cli_profile_lifecycle(capsys):
    parser = cli.build_parser()

    # 1. Profile Set
    args = parser.parse_args(["profile", "set", "location", "Munich", "-c", "facts"])
    ret = args.func(args)
    assert ret == 0
    captured = capsys.readouterr().out
    assert "Set profile [facts] 'location' = 'Munich'" in captured

    # 2. Profile Get
    args = parser.parse_args(["profile", "get", "location"])
    ret = args.func(args)
    assert ret == 0
    captured = capsys.readouterr().out
    assert captured.strip() == "Munich"

    # 3. Profile List
    args = parser.parse_args(["profile", "list"])
    ret = args.func(args)
    assert ret == 0
    captured = capsys.readouterr().out
    assert "location" in captured
    assert "Munich" in captured

    # 4. Profile Delete
    args = parser.parse_args(["profile", "delete", "location"])
    ret = args.func(args)
    assert ret == 0
    captured = capsys.readouterr().out
    assert "Deleted profile entry 'location'" in captured

    # Delete non-existent
    args = parser.parse_args(["profile", "delete", "location"])
    ret = args.func(args)
    assert ret == 1


def test_cli_memory_lifecycle(capsys):
    parser = cli.build_parser()

    # Populate episodic store
    mem_store = EpisodicStore(config.DATA_DIR / "memory.db")
    turn_id = mem_store.log_turn("session-1", "user", "Remember that I run at 7 AM")
    pending_id = mem_store.add_pending("User runs at 7 AM", "I run at 7 AM")

    # 1. Memory List (turns)
    args = parser.parse_args(["memory", "list"])
    ret = args.func(args)
    assert ret == 0
    captured = capsys.readouterr().out
    assert "Remember that I run at 7 AM" in captured

    # 2. Memory List (--pending)
    args = parser.parse_args(["memory", "list", "--pending"])
    ret = args.func(args)
    assert ret == 0
    captured = capsys.readouterr().out
    assert "User runs at 7 AM" in captured

    # 3. Memory Accept
    args = parser.parse_args(["memory", "accept", str(pending_id)])
    ret = args.func(args)
    assert ret == 0
    captured = capsys.readouterr().out
    assert f"Accepted memory ID {pending_id}" in captured

    # Verify fact added to profile
    prof_store = ProfileStore(config.DATA_DIR / "profile.db")
    assert prof_store.get("User runs at 7 AM") == "User runs at 7 AM"

    # 4. Memory Forget
    args = parser.parse_args(["memory", "forget", str(turn_id)])
    ret = args.func(args)
    assert ret == 0
    captured = capsys.readouterr().out
    assert f"Removed turn ID {turn_id}" in captured


def test_cli_ask_success(capsys):
    parser = cli.build_parser()
    args = parser.parse_args(["ask", "What is my job?"])

    # Mock streaming response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.iter_lines.return_value = [
        'data: {"choices": [{"delta": {"content": "You work "}}]}',
        'data: {"choices": [{"delta": {"content": "at Stripe."}}]}',
        'data: [DONE]',
    ]

    with patch("httpx.stream") as mock_stream:
        mock_stream.return_value.__enter__.return_value = mock_response
        ret = args.func(args)

    assert ret == 0
    captured = capsys.readouterr().out
    assert "You work at Stripe." in captured
