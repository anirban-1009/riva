"""Riva MCP Server.

Exposes Riva's persistent profile facts, episodic memory search, and proactive digests
as standard Model Context Protocol (MCP) tools and resources for external assistants
(Cursor, Claude Desktop, OpenClaw, Zed).
Includes header-based API key authentication for exposed endpoints and tool invocations.
"""

import hmac
import logging
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import Response

from common import get_episodic_store, get_profile_store
from common.llm.embeddings import create_embedding_provider
from riva_agent import config

logger = logging.getLogger(__name__)


def get_mcp_api_key() -> str | None:
    """Retrieve the configured MCP API key from environment variable or configuration."""
    key = os.environ.get("RIVA_MCP_API_KEY") or os.environ.get("RIVA_API_KEY") or config.MCP_API_KEY
    if key and str(key).strip():
        return str(key).strip()
    return None


def verify_api_key(
    headers: Mapping[str | bytes, str | bytes] | None = None,
    token: str | None = None,
    expected_key: str | None = None,
) -> bool:
    """Validate incoming API key against the expected secret.

    If expected_key is None or empty, authentication is considered disabled (returns True).
    If expected_key is set, extracts and validates:
    1. Explicit token argument
    2. 'X-Riva-API-Key' header
    3. 'Authorization: Bearer <key>' header
    """
    secret = expected_key if expected_key is not None else get_mcp_api_key()
    if not secret:
        return True

    provided_token: str | None = None

    if token is not None:
        provided_token = token.strip()
    elif headers:
        clean_headers: dict[str, str] = {}
        for k, v in headers.items():
            k_str = k.decode("utf-8").lower() if isinstance(k, bytes) else str(k).lower()
            v_str = v.decode("utf-8") if isinstance(v, bytes) else str(v)
            clean_headers[k_str] = v_str

        if "x-riva-api-key" in clean_headers:
            provided_token = clean_headers["x-riva-api-key"].strip()
        elif "authorization" in clean_headers:
            auth_val = clean_headers["authorization"].strip()
            if auth_val.lower().startswith("bearer "):
                provided_token = auth_val[7:].strip()
            else:
                provided_token = auth_val

    if not provided_token:
        return False

    return hmac.compare_digest(provided_token, secret)


class AuthMiddleware:
    """ASGI middleware enforcing header-based API key authentication for MCP endpoints."""

    def __init__(self, app: Any, api_key: str | None = None) -> None:
        self.app = app
        self.api_key = api_key

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "http" and self.api_key:
            headers = dict(scope.get("headers", []))
            if not verify_api_key(headers=headers, expected_key=self.api_key):
                response = Response(
                    "Unauthorized (401): Missing or invalid API key. "
                    "Please provide a valid key via the 'X-Riva-API-Key' or 'Authorization: Bearer <token>' header.\n",
                    status_code=401,
                    media_type="text/plain",
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_mcp_app(
    server: MCPServer,
    api_key: str | None = None,
    host: str = "127.0.0.1",
) -> Any:
    """Create the Starlette ASGI application for SSE transport wrapped with AuthMiddleware."""
    starlette_app = server.sse_app(
        host=host,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    resolved_key = api_key if api_key is not None else get_mcp_api_key()
    return AuthMiddleware(starlette_app, api_key=resolved_key)


async def run_mcp_sse_server(
    server: MCPServer,
    host: str = "127.0.0.1",
    port: int = 8086,
    api_key: str | None = None,
) -> None:
    """Run the MCP server over SSE with header-based authentication."""
    import uvicorn

    app = create_mcp_app(server, api_key=api_key, host=host)
    srv_config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level=server.settings.log_level.lower(),
    )
    server_runner = uvicorn.Server(srv_config)
    await server_runner.serve()


def create_mcp_server(
    data_dir: Path | None = None,
    digest_dir: Path | None = None,
    name: str = "riva",
    api_key: str | None = None,
) -> MCPServer:
    """Create and configure the Riva MCP Server instance."""
    resolved_data_dir = data_dir or config.DATA_DIR
    resolved_digest_dir = digest_dir or config.DIGEST_OUTPUT_DIR
    resolved_api_key = api_key if api_key is not None else get_mcp_api_key()

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

    def _check_tool_auth(auth_token: str | None = None, ctx: Context | None = None) -> str | None:
        """Validate tool execution against configured API key."""
        if not resolved_api_key:
            return None
        if auth_token is not None:
            if not verify_api_key(token=auth_token, expected_key=resolved_api_key):
                return (
                    "Error: Unauthorized: Invalid API key provided in 'auth_token'. "
                    "Please verify your key matches the server's RIVA_MCP_API_KEY environment variable."
                )
            return None
        if ctx is not None:
            try:
                req_headers = ctx.headers
                if req_headers is not None:
                    if not verify_api_key(headers=req_headers, expected_key=resolved_api_key):
                        return (
                            "Error: Unauthorized: Missing or invalid API key. "
                            "Please provide a valid key via the 'X-Riva-API-Key' header or "
                            "'Authorization: Bearer <token>' matching RIVA_MCP_API_KEY."
                        )
            except Exception:
                pass
        return None

    # -------------------------------------------------------------------------
    # Tools
    # -------------------------------------------------------------------------

    @server.tool(
        name="riva_get_profile",
        description="Retrieve user profile facts, constraints, and preferences stored in Riva's durable profile store.",
    )
    def get_profile(
        category: str | None = None,
        auth_token: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Retrieve profile facts optionally filtered by category."""
        auth_err = _check_tool_auth(auth_token=auth_token, ctx=ctx)
        if auth_err:
            return auth_err

        clean_cat = category.strip() if category else None
        context = profile_store.format_context(category=clean_cat)
        if not context.strip():
            return "No profile facts found." + (f" (category: {clean_cat})" if clean_cat else "")
        return context

    @server.tool(
        name="riva_set_profile_fact",
        description="Save or update an explicit durable fact, constraint, or preference into the user's Riva profile.",
    )
    def set_profile_fact(
        key: str,
        value: str,
        category: str = "facts",
        auth_token: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Store a fact into Riva's profile."""
        auth_err = _check_tool_auth(auth_token=auth_token, ctx=ctx)
        if auth_err:
            return auth_err

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
    async def search_memory(
        query: str,
        limit: int = 5,
        auth_token: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Search past conversations using semantic similarity with keyword fallback."""
        auth_err = _check_tool_auth(auth_token=auth_token, ctx=ctx)
        if auth_err:
            return auth_err

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
    def log_turn(
        session_id: str,
        role: str,
        content: str,
        auth_token: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Record a turn into memory.db."""
        auth_err = _check_tool_auth(auth_token=auth_token, ctx=ctx)
        if auth_err:
            return auth_err

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
    def get_recent_turns(
        session_id: str | None = None,
        limit: int = 10,
        auth_token: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Retrieve recent conversation turns."""
        auth_err = _check_tool_auth(auth_token=auth_token, ctx=ctx)
        if auth_err:
            return auth_err

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
