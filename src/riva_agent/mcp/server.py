"""Riva MCP Server.

Exposes Riva's persistent profile facts, episodic memory search, and proactive digests
as standard Model Context Protocol (MCP) tools and resources for external assistants
(Cursor, Claude Desktop, OpenClaw, Zed).
"""

import logging
from pathlib import Path

from mcp.server import MCPServer

from common import get_episodic_store, get_profile_store
from common.llm.embeddings import create_embedding_provider
from riva_agent import config

logger = logging.getLogger(__name__)


def create_mcp_server(
    data_dir: Path | None = None,
    digest_dir: Path | None = None,
    name: str = "riva",
) -> MCPServer:
    """Create and configure the Riva MCP Server instance."""
    resolved_data_dir = data_dir or config.DATA_DIR
    resolved_digest_dir = digest_dir or config.DIGEST_OUTPUT_DIR

    server = MCPServer(
        name=name,
        instructions=(
            "Riva is a private on-device personal AI platform. This MCP server exposes the user's "
            "durable personal profile facts, preferences, constraints, conversation memory, "
            "and daily briefing digests."
        ),
    )

    profile_store = get_profile_store(resolved_data_dir / "profile.db")
    episodic_store = get_episodic_store(
        resolved_data_dir / "memory.db",
        embedding_dim=config.EMBEDDING_DIMENSION,
    )

    # -------------------------------------------------------------------------
    # Tools
    # -------------------------------------------------------------------------

    @server.tool(
        name="riva_get_profile",
        description="Retrieve user profile facts, constraints, and preferences stored in Riva's durable profile store.",
    )
    def get_profile(category: str | None = None) -> str:
        """Retrieve profile facts optionally filtered by category."""
        clean_cat = category.strip() if category else None
        context = profile_store.format_context(category=clean_cat)
        if not context.strip():
            return "No profile facts found." + (f" (category: {clean_cat})" if clean_cat else "")
        return context

    @server.tool(
        name="riva_set_profile_fact",
        description="Save or update an explicit durable fact, constraint, or preference into the user's Riva profile.",
    )
    def set_profile_fact(key: str, value: str, category: str = "facts") -> str:
        """Store a fact into Riva's profile."""
        clean_key = key.strip()
        clean_val = value.strip()
        clean_cat = (category or "facts").strip().lower()
        if not clean_key or not clean_val:
            return "Error: key and value must not be empty."
        profile_store.set(clean_key, clean_val, category=clean_cat)
        return f"Successfully saved to profile [{clean_cat}]: {clean_key} = {clean_val}"

    @server.tool(
        name="riva_search_memory",
        description="Search past conversations in Riva's episodic and semantic memory store.",
    )
    async def search_memory(query: str, limit: int = 5) -> str:
        """Search past conversations using semantic similarity with keyword fallback."""
        clean_query = query.strip()
        if not clean_query:
            return "Error: query must not be empty."

        # 1. Attempt semantic vector search if sqlite-vec is enabled
        if episodic_store._vec_enabled:
            try:
                emb_provider = create_embedding_provider(
                    config.EMBEDDING_PROVIDER,
                    model=config.EMBEDDING_MODEL,
                    base_url=config.EMBEDDING_BASE_URL,
                    dimension=config.EMBEDDING_DIMENSION,
                )
                query_vec = await emb_provider.embed_query(clean_query)
                if query_vec:
                    matches = episodic_store.search_similar(
                        query_vec,
                        top_k=limit,
                        distance_threshold=config.SEMANTIC_DISTANCE_THRESHOLD,
                    )
                    if matches:
                        formatted = [
                            f"- [{m.session_id}] ({m.created_at}) [distance: {m.distance:.3f}]:\n  {m.content.strip()}"
                            for m in matches
                        ]
                        return f"Found {len(matches)} relevant memory turns:\n\n" + "\n\n".join(formatted)
            except Exception as e:
                logger.debug("Semantic vector search unavailable: %s", e)

        # 2. Fallback to keyword matching over recent conversation turns
        turns = episodic_store.list_turns(limit=50)
        matching = [t for t in turns if clean_query.lower() in t.content.lower()]
        if matching:
            formatted = [
                f"- [{t.session_id}] ({t.role} @ {t.created_at}):\n  {t.content.strip()}" for t in matching[:limit]
            ]
            return f"Found {len(matching[:limit])} matching memory turns (keyword match):\n\n" + "\n\n".join(formatted)

        return f"No memories found matching '{clean_query}'."

    @server.tool(
        name="riva_log_turn",
        description="Record a user or assistant conversation turn into Riva's episodic memory.",
    )
    def log_turn(session_id: str, role: str, content: str) -> str:
        """Record a turn into memory.db."""
        clean_sid = session_id.strip() or "default"
        clean_role = role.strip().lower()
        clean_content = content.strip()
        if clean_role not in ("user", "assistant", "system", "tool"):
            return f"Error: invalid role '{role}'. Expected user, assistant, system, or tool."
        if not clean_content:
            return "Error: content must not be empty."

        turn_id = episodic_store.log_turn(clean_sid, clean_role, clean_content)
        return f"Turn #{turn_id} logged for session '{clean_sid}'."

    @server.tool(
        name="riva_get_recent_turns",
        description="Retrieve the most recent conversation turns from Riva's episodic memory.",
    )
    def get_recent_turns(session_id: str | None = None, limit: int = 10) -> str:
        """Retrieve recent conversation turns."""
        clean_sid = session_id.strip() if session_id else None
        turns = episodic_store.get_recent_turns(clean_sid, limit=limit)
        if not turns:
            return "No recent conversation turns found."
        formatted = [f"[{t.role.upper()} @ {t.created_at}]: {t.content.strip()}" for t in turns]
        return "\n\n".join(formatted)

    # -------------------------------------------------------------------------
    # Resources
    # -------------------------------------------------------------------------

    @server.resource(
        "riva://profile",
        name="User Profile & Durable Facts",
        description="Current user profile facts, constraints, and preferences.",
        mime_type="text/markdown",
    )
    def resource_profile() -> str:
        ctx = profile_store.format_context()
        return ctx if ctx.strip() else "# Riva User Profile\n\nNo facts saved yet."

    @server.resource(
        "riva://memory/recent",
        name="Recent Conversation Memory",
        description="Most recent conversation turns from Riva's episodic memory.",
        mime_type="text/markdown",
    )
    def resource_memory_recent() -> str:
        turns = episodic_store.get_recent_turns(limit=10)
        if not turns:
            return "# Recent Conversation Turns\n\nNo turns recorded yet."
        lines = ["# Recent Conversation Turns\n"]
        for t in turns:
            lines.append(f"**{t.role.capitalize()}** (`{t.created_at}`):\n{t.content.strip()}\n")
        return "\n".join(lines)

    @server.resource(
        "riva://digests/latest",
        name="Latest Daily Digest",
        description="The most recent proactive daily briefing generated by Riva.",
        mime_type="text/markdown",
    )
    def resource_latest_digest() -> str:
        if not resolved_digest_dir.exists():
            return "# Latest Digest\n\nNo daily digest directory found."
        digest_files = list(resolved_digest_dir.glob("digest_*.md"))
        if not digest_files:
            return "# Latest Digest\n\nNo daily digest has been generated yet."
        latest = max(digest_files, key=lambda p: p.stat().st_mtime)
        try:
            return latest.read_text(encoding="utf-8")
        except Exception as e:
            return f"# Latest Digest\n\nError reading digest file: {e}"

    return server
