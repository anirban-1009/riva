import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from common import get_episodic_store, get_profile_store
from common.llm.providers import LLMProvider, create_provider
from common.memory.store import EpisodicStore
from common.profile.store import ProfileStore
from riva_agent import config
from riva_agent.digest.models import DigestConfig, DigestContext, DigestRecord

logger = logging.getLogger(__name__)


def strip_thinking_tags(text: str) -> str:
    """Remove <think>...</think> reasoning blocks from text to keep final output clean."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def collect_digest_context(
    profile_store: ProfileStore | None = None,
    episodic_store: EpisodicStore | None = None,
    date_str: str | None = None,
) -> DigestContext:
    """Gather profile facts, active goals, constraints, recent conversation turns,

    and pending memories from local SQLite stores.
    """
    if profile_store is None:
        profile_store = get_profile_store(config.DATA_DIR / "profile.db")
    if episodic_store is None:
        episodic_store = get_episodic_store(config.DATA_DIR / "memory.db")

    current_date = date_str or datetime.now().strftime("%Y-%m-%d")

    facts = [{"key": e.key, "value": e.value} for e in profile_store.list_all(category="facts")]
    goals = [{"key": e.key, "value": e.value} for e in profile_store.list_all(category="goals")]
    constraints = [{"key": e.key, "value": e.value} for e in profile_store.list_all(category="constraints")]
    preferences = [{"key": e.key, "value": e.value} for e in profile_store.list_all(category="preferences")]

    raw_turns = episodic_store.list_turns(limit=15)
    recent_turns = [
        {
            "id": t.id,
            "session_id": t.session_id,
            "role": t.role,
            "content": t.content,
            "created_at": t.created_at,
        }
        for t in reversed(raw_turns)  # Chronological order
    ]

    pending_raw = episodic_store.list_pending(status="pending")
    pending_memories = [
        {
            "id": p.id,
            "fact": p.fact,
            "source": p.source_snippet,
            "created_at": p.created_at,
        }
        for p in pending_raw
    ]

    return DigestContext(
        date=current_date,
        profile_facts=facts,
        profile_goals=goals,
        profile_constraints=constraints,
        profile_preferences=preferences,
        recent_turns=recent_turns,
        pending_memories=pending_memories,
    )


def build_digest_prompt(context: DigestContext) -> list[dict[str, str]]:
    """Assemble system and user messages instructing the LLM to generate a personalized briefing."""
    system_instruction = (
        "You are Riva, a private personal assistant. Generate a high-signal, personal daily digest "
        "and morning briefing for the user based strictly on their active goals, constraints, recent "
        "conversations, and pending memory candidates.\n\n"
        "Guidelines:\n"
        "- Format as clean GitHub-style Markdown with clear sections.\n"
        "- Include: 1) Active Priorities & Goals, 2) Recent Context & Momentum, "
        "3) Pending Memory Review (if any candidates exist, mention 'riva memory accept <id>' or 'reject'), "
        "and 4) Actionable Recommendations.\n"
        "- Keep it concise, high-signal, and personal. Do not include boilerplate fluff or generic filler."
    )

    context_lines = [f"Date: {context.date}"]

    if context.profile_goals:
        context_lines.append("\n[Active Goals]")
        for g in context.profile_goals:
            context_lines.append(f"- {g['key']}: {g['value']}")

    if context.profile_constraints:
        context_lines.append("\n[Key Constraints]")
        for c in context.profile_constraints:
            context_lines.append(f"- {c['key']}: {c['value']}")

    if context.profile_facts:
        context_lines.append("\n[Durable Profile Facts]")
        for f in context.profile_facts:
            context_lines.append(f"- {f['key']}: {f['value']}")

    if context.recent_turns:
        context_lines.append("\n[Recent Conversation Turns]")
        for t in context.recent_turns[-10:]:
            context_lines.append(f"[{t['role']}]: {t['content'][:250]}")

    if context.pending_memories:
        context_lines.append("\n[Pending Memory Candidates Awaiting Review]")
        for p in context.pending_memories:
            context_lines.append(f'- ID {p["id"]}: "{p["fact"]}" (Source: {p.get("source", "")[:100]})')

    user_prompt = (
        "Here is my current profile and context:\n"
        + "\n".join(context_lines)
        + f"\n\nPlease generate my daily briefing for {context.date}."
    )

    return [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_prompt},
    ]


async def generate_digest_async(
    context: DigestContext | None = None,
    provider: LLMProvider | None = None,
    config_obj: DigestConfig | None = None,
    dry_run: bool = False,
    profile_store: ProfileStore | None = None,
    episodic_store: EpisodicStore | None = None,
) -> DigestRecord:
    """Asynchronously synthesize a digest and archive it to local Markdown storage."""
    cfg = config_obj or DigestConfig.from_env_or_config()
    ctx = context or collect_digest_context(
        profile_store=profile_store,
        episodic_store=episodic_store,
    )

    digest_id = f"{ctx.date}-{uuid.uuid4().hex[:8]}"
    title = f"Daily Briefing: {ctx.date}"
    now_utc = datetime.now(timezone.utc)

    if dry_run:
        content_markdown = (
            f"# 🌅 {title}\n\n"
            f"*(Dry-run preview generated at {now_utc.isoformat()})*\n\n"
            f"### 🎯 Goals ({len(ctx.profile_goals)})\n"
            + "\n".join(f"- **{g['key']}**: {g['value']}" for g in ctx.profile_goals)
            + f"\n\n### 📝 Pending Memories ({len(ctx.pending_memories)})\n"
            + "\n".join(f"- [ID {p['id']}] {p['fact']}" for p in ctx.pending_memories)
            + "\n\n### 💡 Status\nRiva dry-run digest completed successfully."
        )
    else:
        if provider is None:
            backend_url = config.OPENAI_BASE_URL if config.PROVIDER == "openai" else config.OLLAMA_BASE_URL
            provider = create_provider(
                config.PROVIDER,
                model=config.ASSISTANT_MODEL,
                base_url=backend_url,
                api_key=config.OPENAI_API_KEY,
            )

        messages = build_digest_prompt(ctx)
        raw_output = await provider.chat_async(
            messages,
            temperature=0.7,
            max_tokens=1500,
        )
        content_markdown = strip_thinking_tags(raw_output)

    # Prepare file write with YAML frontmatter
    frontmatter = {
        "id": digest_id,
        "date": ctx.date,
        "created_at": now_utc.isoformat(),
        "title": title,
    }
    frontmatter_str = yaml.dump(frontmatter, sort_keys=False).strip()
    full_file_text = f"---\n{frontmatter_str}\n---\n\n{content_markdown}\n"

    output_path = cfg.output_dir / f"{ctx.date}-digest.md"

    if not dry_run:
        cfg.output_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_text(full_file_text, encoding="utf-8")

    return DigestRecord(
        id=digest_id,
        date=ctx.date,
        title=title,
        content_markdown=content_markdown,
        filepath=output_path if not dry_run else None,
        created_at=now_utc,
    )


def generate_digest(
    context: DigestContext | None = None,
    provider: LLMProvider | None = None,
    config_obj: DigestConfig | None = None,
    dry_run: bool = False,
    profile_store: ProfileStore | None = None,
    episodic_store: EpisodicStore | None = None,
) -> DigestRecord:
    """Synchronous wrapper for generate_digest_async."""
    coro = generate_digest_async(
        context=context,
        provider=provider,
        config_obj=config_obj,
        dry_run=dry_run,
        profile_store=profile_store,
        episodic_store=episodic_store,
    )
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # If an event loop is already running in the current thread (e.g. notebook or async runtime),
    # run the coroutine in a dedicated worker thread using standard library concurrent.futures
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coro).result()


def list_digests(output_dir: Path | None = None, limit: int = 10) -> list[DigestRecord]:
    """List archived digest markdown files in descending chronological order."""
    dir_path = output_dir or DigestConfig.from_env_or_config().output_dir
    if not dir_path.exists():
        return []

    files = sorted(dir_path.glob("*-digest*.md"), reverse=True)
    records: list[DigestRecord] = []

    for file in files[:limit]:
        try:
            content = file.read_text(encoding="utf-8")
            record = _parse_digest_file(file, content)
            if record:
                records.append(record)
        except Exception as e:
            logger.warning("Failed to parse digest file %s: %s", file, e)
            continue

    return records


def read_digest(filepath_or_id: str | Path, output_dir: Path | None = None) -> DigestRecord | None:
    """Read a specific digest by file path, filename, or date/id."""
    dir_path = output_dir or DigestConfig.from_env_or_config().output_dir
    target_path = Path(filepath_or_id)

    if not target_path.exists():
        # Try finding in output_dir
        candidate = dir_path / filepath_or_id
        if candidate.exists():
            target_path = candidate
        else:
            # Try matching *-digest.md with date/id prefix
            matches = list(dir_path.glob(f"*{filepath_or_id}*.md"))
            if matches:
                target_path = matches[0]
            else:
                return None

    try:
        content = target_path.read_text(encoding="utf-8")
        return _parse_digest_file(target_path, content)
    except Exception as e:
        logger.error("Error reading digest file %s: %s", target_path, e)
        return None


def _parse_digest_file(path: Path, content: str) -> DigestRecord | None:
    """Parse a markdown file containing YAML frontmatter into a DigestRecord."""
    frontmatter_match = re.match(r"^---\n(.*?)\n---\n\n?(.*)$", content, re.DOTALL)
    if not frontmatter_match:
        # Fallback without frontmatter
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
        date_str = date_match.group(1) if date_match else "unknown"
        return DigestRecord(
            id=path.stem,
            date=date_str,
            title=f"Digest: {path.stem}",
            content_markdown=content.strip(),
            filepath=path,
        )

    fm_raw, body = frontmatter_match.groups()
    try:
        meta = yaml.safe_load(fm_raw) or {}
    except Exception:
        meta = {}

    created_at = datetime.now(timezone.utc)
    if "created_at" in meta:
        try:
            created_at = datetime.fromisoformat(meta["created_at"])
        except Exception:
            pass

    return DigestRecord(
        id=str(meta.get("id", path.stem)),
        date=str(meta.get("date", path.stem.split("-digest")[0])),
        title=str(meta.get("title", f"Digest: {path.stem}")),
        content_markdown=body.strip(),
        filepath=path,
        created_at=created_at,
    )
