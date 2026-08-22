import json
from unittest.mock import MagicMock

import pytest

from job_genie.generator.dashboard_generator import DashboardGenerator


@pytest.fixture
def config(tmp_path):
    return {"obsidian": {"vault_path": str(tmp_path), "folders": {}}}


def _mock_db(applied_ats):
    db = MagicMock()
    db.get_all_jobs.return_value = [{"id": str(i), "applied_at": ts} for i, ts in enumerate(applied_ats)]
    return db


def test_generate_with_no_db_writes_empty_state(config, tmp_path):
    generator = DashboardGenerator(config)
    path = generator.generate(None)

    assert path == tmp_path / "Dashboard.canvas"
    data = json.loads(path.read_text(encoding="utf-8"))
    texts = " ".join(n.get("text", "") for n in data["nodes"])
    assert "No applications tracked yet" in texts


def test_generate_with_no_applications_writes_empty_state(config, tmp_path):
    db = _mock_db([])
    generator = DashboardGenerator(config)
    path = generator.generate(db)

    data = json.loads(path.read_text(encoding="utf-8"))
    texts = " ".join(n.get("text", "") for n in data["nodes"])
    assert "No applications tracked yet" in texts


def test_generate_skips_unparseable_applied_at(config):
    db = _mock_db(["not-a-date", None, ""])
    generator = DashboardGenerator(config)

    dates = generator._get_applied_dates(db)

    assert dates == []


def test_monthly_counts_buckets_by_month():
    generator = DashboardGenerator({"obsidian": {"vault_path": "/tmp/x", "folders": {}}})
    import datetime as dt

    dates = [
        dt.datetime(2026, 6, 5),
        dt.datetime(2026, 6, 20),
        dt.datetime(2026, 8, 1),
    ]

    result = generator._monthly_counts(dates)

    assert result == [("Jun 2026", 2), ("Jul 2026", 0), ("Aug 2026", 1)]


def test_weekly_counts_buckets_by_monday_start_week():
    generator = DashboardGenerator({"obsidian": {"vault_path": "/tmp/x", "folders": {}}})
    import datetime as dt

    # Mon 2026-08-10 and Wed 2026-08-12 fall in the same week; Mon 2026-08-17 is the next week.
    dates = [
        dt.datetime(2026, 8, 10),
        dt.datetime(2026, 8, 12),
        dt.datetime(2026, 8, 17),
    ]

    result = generator._weekly_counts(dates)

    assert result == [("Aug 10", 2), ("Aug 17", 1)]


def test_generate_builds_month_and_week_bars(config, tmp_path):
    applied_ats = [
        "2026-08-10 10:00:00",
        "2026-08-12 10:00:00",
        "2026-08-17 10:00:00",
    ]
    db = _mock_db(applied_ats)
    generator = DashboardGenerator(config)

    path = generator.generate(db)

    data = json.loads(path.read_text(encoding="utf-8"))
    texts = " ".join(n.get("text", "") for n in data["nodes"])
    assert "Applications by Month" in texts
    assert "Applications by Week" in texts
    assert "3** total applications tracked" in texts
    # One month bar (Aug, 3 applications) and two week bars (Aug 10: 2, Aug 17: 1).
    bar_counts = [n["text"].strip("*") for n in data["nodes"] if n.get("text", "").strip("*").isdigit()]
    assert bar_counts == ["3", "2", "1"]
