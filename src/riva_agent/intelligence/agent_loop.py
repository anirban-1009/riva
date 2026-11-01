import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from common.llm.providers import AssistantTurn, LLMProvider, ToolCall
from common.mcp.manager import MCPClientManager
from common.mcp.models import ToolResult

logger = logging.getLogger(__name__)

CITATION_SYSTEM_INSTRUCTION = (
    "\n\nCITATION & PROVENANCE INSTRUCTIONS:\n"
    "When answering using information retrieved from external tools (such as web search, "
    "local files, knowledge bases, or APIs), you MUST cite your sources:\n"
    "1. Cite sources inline where relevant using markdown links [Title](URL) for web pages, "
    "or formatted paths `path/to/file` for local notes and files.\n"
    "2. At the end of your response, always include a '### Sources' section listing every "
    "consulted reference with its title and link or identifier.\n"
    "3. Never invent or hallucinate sources; only cite references present in the tool results."
)

_MUTATING_VERBS = {"delete", "remove", "drop", "write", "create", "update", "send", "post", "put", "patch", "modify"}


@dataclass
class SourceReference:
    """Represents a verifiable source or document consulted during tool execution."""

    title: str
    url: str | None = None
    identifier: str | None = None
    tool_name: str = ""

    def to_markdown(self) -> str:
        if self.url:
            return f"- [{self.title}]({self.url})"
        if self.identifier:
            return f"- **{self.title}** (`{self.identifier}`)"
        return f"- **{self.title}**"


@dataclass
class AgentResponse:
    """Complete outcome of an agentic ReAct turn."""

    content: str
    tool_calls_executed: list[tuple[ToolCall, ToolResult]] = field(default_factory=list)
    sources: list[SourceReference] = field(default_factory=list)
    iterations: int = 0


def is_tool_readonly(tool_name: str, is_marked_readonly: bool = False) -> bool:
    """Determine whether a tool is safe to execute without explicit human confirmation."""
    if is_marked_readonly:
        return True
    lower = tool_name.lower()
    for verb in _MUTATING_VERBS:
        if verb in lower:
            return False
    return True


def extract_sources_from_tool_result(tool_name: str, arguments: dict[str, Any], content: str) -> list[SourceReference]:
    """Extract verifiable source references (URLs, titles, file paths) from tool results."""
    sources: list[SourceReference] = []
    seen_urls: set[str] = set()

    # 1. Search engine results (DuckDuckGo / Brave format: URL: https://... and titles)
    url_matches = re.findall(r"(?:URL:\s*|href=['\"]?)(https?://[^\s'\"]+)", content)
    for url in url_matches:
        clean_url = url.strip().rstrip(".,;)")
        if clean_url in seen_urls:
            continue
        seen_urls.add(clean_url)
        # Attempt to find nearby title (e.g. "1. Official Docs\nURL: ...")
        title = "Web Source"
        title_match = re.search(rf"(?:^|\n)\d+\.\s+([^\n]+)(?:\n\s*URL:\s*{re.escape(clean_url)})", content)
        if title_match:
            title = title_match.group(1).strip()
        else:
            domain = clean_url.split("/")[2] if len(clean_url.split("/")) > 2 else clean_url
            title = domain
        sources.append(SourceReference(title=title, url=clean_url, tool_name=tool_name))

    # 2. File / document operations (path or file argument)
    file_target = arguments.get("path") or arguments.get("filepath") or arguments.get("file")
    if file_target and isinstance(file_target, str):
        sources.append(
            SourceReference(
                title=f"File: {file_target.split('/')[-1]}",
                identifier=file_target,
                tool_name=tool_name,
            )
        )

    # 3. Notion / Knowledge base (page_id or title argument)
    page_target = arguments.get("page_id") or arguments.get("title") or arguments.get("query")
    if "notion" in tool_name.lower() and page_target and isinstance(page_target, str):
        sources.append(
            SourceReference(
                title=f"Notion: {page_target}",
                identifier=page_target,
                tool_name=tool_name,
            )
        )

    return sources


def ensure_source_citations(response_text: str, sources: list[SourceReference]) -> str:
    """Ensure that any answer based on external tools contains a clean Sources section."""
    if not sources or not response_text.strip():
        return response_text

    lower_text = response_text.lower()
    if "### sources" in lower_text or "## sources" in lower_text or "\nsources:" in lower_text:
        return response_text

    sources_block = "\n\n### Sources\n" + "\n".join(s.to_markdown() for s in sources)
    return response_text.strip() + sources_block


def parse_prompt_tool_call(text: str) -> ToolCall | None:
    """Fallback extractor for models that emit tool calls as JSON in plain text."""
    if not text or "{" not in text:
        return None

    # Try ```json ... ``` fenced blocks
    json_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = list(json_blocks) if json_blocks else []

    # Also try extracting outer { ... } from the entire text
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidates.append(text[first_brace : last_brace + 1])

    for candidate in candidates:
        try:
            cand_str = candidate.strip()
            # If candidate starts with { and ends with }, parse it
            fb = cand_str.find("{")
            lb = cand_str.rfind("}")
            if fb != -1 and lb != -1 and lb > fb:
                cand_str = cand_str[fb : lb + 1]

            data = json.loads(cand_str)
            if not isinstance(data, dict):
                continue

            if "tool_call" in data and isinstance(data["tool_call"], dict):
                tc = data["tool_call"]
                return ToolCall(
                    id=f"call_{uuid.uuid4().hex[:8]}",
                    name=tc.get("name", ""),
                    arguments=dict(tc.get("arguments", {})),
                )
            if "name" in data and ("arguments" in data or "parameters" in data):
                return ToolCall(
                    id=f"call_{uuid.uuid4().hex[:8]}",
                    name=data.get("name", ""),
                    arguments=dict(data.get("arguments") or data.get("parameters") or {}),
                )
        except Exception:
            continue
    return None


async def run_agent_loop(
    messages: list[dict[str, Any]],
    provider: LLMProvider,
    mcp_manager: MCPClientManager | None = None,
    *,
    max_iterations: int = 5,
    auto_approve_readonly: bool = True,
    temperature: float | None = None,
    max_tokens: int | None = None,
    think: Any = None,
    on_tool_call: Callable[[ToolCall], None] | None = None,
    on_tool_result: Callable[[ToolResult], None] | None = None,
) -> AgentResponse:
    """Run an agentic ReAct loop, coordinating tool executions with the LLM provider."""
    current_messages = [dict(m) for m in messages]
    tools = mcp_manager.get_openai_tools() if mcp_manager else []

    # Inject citation requirement into the system message if tools are present
    if tools and current_messages:
        for msg in current_messages:
            if msg.get("role") == "system":
                if "CITATION & PROVENANCE" not in msg.get("content", ""):
                    msg["content"] = msg["content"] + CITATION_SYSTEM_INSTRUCTION
                break
        else:
            current_messages.insert(0, {"role": "system", "content": CITATION_SYSTEM_INSTRUCTION.strip()})

    executed_calls: list[tuple[ToolCall, ToolResult]] = []
    accumulated_sources: list[SourceReference] = []
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        turn: AssistantTurn
        if hasattr(provider, "chat_turn_async"):
            turn = await provider.chat_turn_async(
                current_messages,
                tools=tools if tools else None,
                temperature=temperature,
                max_tokens=max_tokens,
                think=think,
            )
        else:
            # Fallback for mock or basic providers
            text = await provider.chat_async(
                current_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                think=think,
            )
            fallback_call = parse_prompt_tool_call(text)
            if fallback_call:
                turn = AssistantTurn(content=None, tool_calls=[fallback_call])
            else:
                turn = AssistantTurn(content=text, tool_calls=[])

        # If no tool calls requested, we have the final assistant response
        if not turn.has_tool_calls:
            final_text = turn.content or ""
            if accumulated_sources:
                final_text = ensure_source_citations(final_text, accumulated_sources)
            return AgentResponse(
                content=final_text,
                tool_calls_executed=executed_calls,
                sources=accumulated_sources,
                iterations=iteration,
            )

        # Process tool calls
        for tc in turn.tool_calls:
            if on_tool_call:
                try:
                    on_tool_call(tc)
                except Exception as e:
                    logger.debug("on_tool_call callback failed: %s", e)

            # Check safety gate
            if not is_tool_readonly(tc.name) and not auto_approve_readonly:
                result = ToolResult(
                    name=tc.name,
                    tool_call_id=tc.id,
                    content=(
                        f"Action halted: Tool '{tc.name}' performs mutating side-effects "
                        f"and requires explicit user confirmation."
                    ),
                    is_error=True,
                )
            elif not mcp_manager:
                result = ToolResult(
                    name=tc.name,
                    tool_call_id=tc.id,
                    content=f"Error: No MCP manager configured to execute tool '{tc.name}'.",
                    is_error=True,
                )
            else:
                result = await mcp_manager.call_tool(tc.name, tc.arguments)
                result.tool_call_id = tc.id

            if on_tool_result:
                try:
                    on_tool_result(result)
                except Exception as e:
                    logger.debug("on_tool_result callback failed: %s", e)

            executed_calls.append((tc, result))

            # Extract source references for attribution
            new_sources = extract_sources_from_tool_result(tc.name, tc.arguments, result.content)
            accumulated_sources.extend(new_sources)

            # Append assistant message with tool_calls and tool result turn
            current_messages.append(
                {
                    "role": "assistant",
                    "content": turn.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                        }
                    ],
                }
            )
            current_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": result.content,
                }
            )

    # Max iterations exceeded: synthesize final response from gathered data
    final_response = await provider.chat_async(
        current_messages,
        temperature=temperature,
        max_tokens=max_tokens,
        think=think,
    )
    if accumulated_sources:
        final_response = ensure_source_citations(final_response, accumulated_sources)

    return AgentResponse(
        content=final_response,
        tool_calls_executed=executed_calls,
        sources=accumulated_sources,
        iterations=iteration,
    )
