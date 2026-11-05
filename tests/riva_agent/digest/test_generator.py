from unittest.mock import AsyncMock, MagicMock

import pytest

from common.memory.store import PendingMemory, Turn
from common.profile.store import ProfileEntry
from riva_agent import config
from riva_agent.digest.generator import (
    build_digest_prompt,
    collect_digest_context,
    generate_digest,
    generate_digest_async,
    generate_offline_fallback_content,
    list_digests,
    read_digest,
    strip_thinking_tags,
)
from riva_agent.digest.models import DigestConfig, DigestContext


def test_strip_thinking_tags():
    raw = "<think>I should organize this well.</think># Daily Briefing\nHere are goals."
    assert strip_thinking_tags(raw) == "# Daily Briefing\nHere are goals."
    assert strip_thinking_tags("No think tags here.") == "No think tags here."


def test_collect_digest_context():
    mock_profile = MagicMock()
    mock_profile.list_all.side_effect = lambda category=None: {
        "facts": [ProfileEntry(key="location", value="Hyderabad", category="facts", updated_at="now")],
        "goals": [ProfileEntry(key="marathon", value="Sub 4 hours", category="goals", updated_at="now")],
        "constraints": [ProfileEntry(key="diet", value="Vegetarian", category="constraints", updated_at="now")],
        "preferences": [ProfileEntry(key="style", value="Concise", category="preferences", updated_at="now")],
    }.get(category, [])

    mock_episodic = MagicMock()
    mock_episodic.list_turns.return_value = [
        Turn(id=1, session_id="s1", role="user", content="Research local LLMs", created_at="2026-11-01T10:00:00Z"),
        Turn(id=2, session_id="s1", role="assistant", content="Here is a summary", created_at="2026-11-01T10:01:00Z"),
    ]
    mock_episodic.list_pending.return_value = [
        PendingMemory(
            id=42,
            fact="Prefers dark mode in code editors",
            source_snippet="I always use dark mode",
            status="pending",
            created_at="2026-11-01T10:05:00Z",
        ),
    ]

    ctx = collect_digest_context(
        profile_store=mock_profile,
        episodic_store=mock_episodic,
        date_str="2026-11-01",
    )

    assert ctx.date == "2026-11-01"
    assert len(ctx.profile_facts) == 1
    assert ctx.profile_facts[0]["key"] == "location"
    assert len(ctx.profile_goals) == 1
    assert ctx.profile_goals[0]["value"] == "Sub 4 hours"
    assert len(ctx.profile_constraints) == 1
    assert len(ctx.profile_preferences) == 1
    assert len(ctx.recent_turns) == 2
    assert len(ctx.pending_memories) == 1
    assert ctx.pending_memories[0]["id"] == 42


def test_build_digest_prompt():
    ctx = DigestContext(
        date="2026-11-01",
        profile_goals=[{"key": "marathon", "value": "Sub 4 hours"}],
        profile_constraints=[{"key": "diet", "value": "Vegetarian"}],
        profile_facts=[{"key": "location", "value": "Hyderabad"}],
        recent_turns=[{"role": "user", "content": "Help me run today."}],
        pending_memories=[{"id": 10, "fact": "Likes running in mornings", "source": "I run at 6am"}],
    )

    messages = build_digest_prompt(ctx)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "You are Riva" in messages[0]["content"]

    user_msg = messages[1]["content"]
    assert "Sub 4 hours" in user_msg
    assert "Vegetarian" in user_msg
    assert "Hyderabad" in user_msg
    assert "Help me run today." in user_msg
    assert "Likes running in mornings" in user_msg


@pytest.mark.asyncio
async def test_generate_digest_async_dry_run(tmp_path):
    cfg = DigestConfig(output_dir=tmp_path)
    ctx = DigestContext(
        date="2026-11-01",
        profile_goals=[{"key": "fitness", "value": "Run 5k"}],
    )

    record = await generate_digest_async(
        context=ctx,
        config_obj=cfg,
        dry_run=True,
    )

    assert record.date == "2026-11-01"
    assert "Dry-run preview" in record.content_markdown
    assert record.filepath is None
    # No file written on dry-run
    assert list(tmp_path.glob("*.md")) == []


@pytest.mark.asyncio
async def test_generate_digest_async_with_provider(tmp_path):
    cfg = DigestConfig(output_dir=tmp_path)
    ctx = DigestContext(date="2026-11-01")

    mock_provider = MagicMock()
    mock_provider.chat_async = AsyncMock(
        return_value="<think>internal thought</think># 🌅 Daily Briefing\nAll priorities set."
    )

    record = await generate_digest_async(
        context=ctx,
        provider=mock_provider,
        config_obj=cfg,
        dry_run=False,
    )

    assert record.date == "2026-11-01"
    assert "internal thought" not in record.content_markdown
    assert "# 🌅 Daily Briefing\nAll priorities set." in record.content_markdown
    assert record.filepath is not None
    assert record.filepath.exists()

    content = record.filepath.read_text(encoding="utf-8")
    assert "id: " in content
    assert "date: '2026-11-01'" in content or "date: 2026-11-01" in content
    assert "# 🌅 Daily Briefing" in content


def test_generate_digest_sync_wrapper(tmp_path):
    cfg = DigestConfig(output_dir=tmp_path)
    ctx = DigestContext(date="2026-11-01")

    record = generate_digest(
        context=ctx,
        config_obj=cfg,
        dry_run=True,
    )
    assert record.date == "2026-11-01"
    assert "Dry-run preview" in record.content_markdown


@pytest.mark.asyncio
async def test_generate_digest_sync_inside_running_loop(tmp_path):
    cfg = DigestConfig(output_dir=tmp_path)
    ctx = DigestContext(date="2026-11-01")

    # Call the synchronous generate_digest while an event loop is actively running
    record = generate_digest(
        context=ctx,
        config_obj=cfg,
        dry_run=True,
    )
    assert record.date == "2026-11-01"
    assert "Dry-run preview" in record.content_markdown


def test_list_and_read_digests(tmp_path):
    # Empty dir returns empty list
    assert list_digests(tmp_path) == []
    assert read_digest("2026-11-01", output_dir=tmp_path) is None

    # Write two test files
    file1 = tmp_path / "2026-11-01-digest.md"
    file1.write_text(
        "---\nid: 2026-11-01-abc\ndate: 2026-11-01\ntitle: Briefing 1\n---\n\nContent 1",
        encoding="utf-8",
    )
    file2 = tmp_path / "2026-11-02-digest.md"
    file2.write_text(
        "---\nid: 2026-11-02-def\ndate: 2026-11-02\ntitle: Briefing 2\n---\n\nContent 2",
        encoding="utf-8",
    )

    digests = list_digests(tmp_path)
    assert len(digests) == 2
    # Reverse chronological
    assert digests[0].date == "2026-11-02"
    assert digests[1].date == "2026-11-01"

    # Test read_digest
    rec1 = read_digest("2026-11-01", output_dir=tmp_path)
    assert rec1 is not None
    assert rec1.id == "2026-11-01-abc"
    assert rec1.content_markdown == "Content 1"

    rec2 = read_digest(file2)
    assert rec2 is not None
    assert rec2.id == "2026-11-02-def"
    assert rec2.content_markdown == "Content 2"


def test_generate_offline_fallback_content():
    ctx = DigestContext(
        date="2026-11-04",
        profile_goals=[{"key": "latency", "value": "<50ms"}],
        profile_facts=[{"key": "city", "value": "Hyderabad"}],
        recent_turns=[{"role": "user", "content": "How to tune models?"}],
        pending_memories=[{"id": 7, "fact": "Prefers vim"}],
        external_insights=["Notion: 2 tasks due"],
    )
    content = generate_offline_fallback_content(ctx, "Daily Briefing: 2026-11-04")
    assert "Daily Briefing: 2026-11-04" in content
    assert "offline fallback mode" in content
    assert "latency:" in content
    assert "Hyderabad" in content
    assert "How to tune models?" in content
    assert "[ID 7] Prefers vim" in content
    assert "Notion: 2 tasks due" in content


@pytest.mark.asyncio
async def test_generate_digest_fallback_to_ollama(tmp_path, monkeypatch):
    cfg = DigestConfig(output_dir=tmp_path)
    ctx = DigestContext(date="2026-11-04")

    # Mock primary provider failing and ollama provider succeeding
    mock_primary = MagicMock()
    mock_primary.chat_async = AsyncMock(side_effect=RuntimeError("Primary connection refused"))

    mock_ollama = MagicMock()
    mock_ollama.chat_async = AsyncMock(return_value="# 🌅 Ollama Digest\nGenerated successfully.")

    monkeypatch.setattr(config, "PROVIDER", "openai")

    def mock_create_provider(name, **kwargs):
        if name == "ollama":
            return mock_ollama
        return mock_primary

    monkeypatch.setattr("riva_agent.digest.generator.create_provider", mock_create_provider)

    record = await generate_digest_async(context=ctx, config_obj=cfg, dry_run=False)
    assert record.date == "2026-11-04"
    assert "# 🌅 Ollama Digest" in record.content_markdown
    assert record.filepath.exists()


@pytest.mark.asyncio
async def test_generate_digest_fallback_to_offline_content(tmp_path, monkeypatch):
    cfg = DigestConfig(output_dir=tmp_path)
    ctx = DigestContext(
        date="2026-11-04",
        profile_goals=[{"key": "deploy", "value": "Prod release"}],
    )

    mock_failing = MagicMock()
    mock_failing.chat_async = AsyncMock(side_effect=RuntimeError("All LLMs offline"))

    monkeypatch.setattr(config, "PROVIDER", "openai")
    monkeypatch.setattr("riva_agent.digest.generator.create_provider", lambda *args, **kwargs: mock_failing)

    record = await generate_digest_async(context=ctx, config_obj=cfg, dry_run=False)
    assert record.date == "2026-11-04"
    assert "offline fallback mode" in record.content_markdown
    assert "Prod release" in record.content_markdown
    assert record.filepath.exists()
