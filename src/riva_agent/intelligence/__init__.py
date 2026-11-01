"""Intelligence subpackage for Riva Agent, providing reasoning and memory routing."""

from riva_agent.intelligence.agent_loop import (
    AgentResponse,
    SourceReference,
    ensure_source_citations,
    extract_sources_from_tool_result,
    is_tool_readonly,
    parse_prompt_tool_call,
    run_agent_loop,
)
from riva_agent.intelligence.memory_router import (
    AgentMemoryEvent,
    MemoryRouter,
    get_memory_router,
    route_memory,
)
from riva_agent.intelligence.reasoning import (
    HybridDecision,
    ReasoningEffort,
    ThinkingRouter,
    decide_reasoning_effort,
    get_thinking_router,
    should_use_extended_thinking,
)

__all__ = [
    "AgentMemoryEvent",
    "AgentResponse",
    "SourceReference",
    "MemoryRouter",
    "get_memory_router",
    "route_memory",
    "run_agent_loop",
    "ensure_source_citations",
    "extract_sources_from_tool_result",
    "is_tool_readonly",
    "parse_prompt_tool_call",
    "HybridDecision",
    "ReasoningEffort",
    "ThinkingRouter",
    "decide_reasoning_effort",
    "get_thinking_router",
    "should_use_extended_thinking",
]
