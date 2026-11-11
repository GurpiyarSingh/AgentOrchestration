"""Build a runnable LangGraph agent from an `AgentDef` (ADR-015)."""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
    ToolErrorMiddleware,
)
from langchain_core.language_models import BaseChatModel

from core.runtime.agent_def import AgentDef
from core.runtime.middleware import ToolPolicyMiddleware, tool_error_to_text
from core.tools.registry import DEFAULT_MAX_OUTPUT_CHARS, ToolEntry

APPROVAL_UNAVAILABLE = (
    "This tool requires human approval, which is not available yet (planned for M4). "
    "Do not call it again; continue without it or explain what you would have done."
)


def build_agent(
    defn: AgentDef,
    model: BaseChatModel,
    tools: list[ToolEntry],
    *,
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
    checkpointer: Any = None,
) -> Any:
    """Compile the agent graph: model ↔ tools loop with limits and tool-error handling.

    Middleware order is outermost first: policy (block/truncate) wraps error handling.
    """
    blocked = {e.name: APPROVAL_UNAVAILABLE for e in tools if e.requires_approval}
    middleware: list[AgentMiddleware[Any, Any, Any]] = [
        ModelCallLimitMiddleware(run_limit=defn.max_model_calls, exit_behavior="end"),
        ToolCallLimitMiddleware(run_limit=defn.max_tool_calls, exit_behavior="end"),
        ToolPolicyMiddleware(max_output_chars=max_output_chars, blocked=blocked),
        ToolErrorMiddleware(on_error=tool_error_to_text),
    ]
    return create_agent(
        model,
        [e.tool for e in tools],
        system_prompt=defn.system_prompt or None,
        middleware=middleware,
        checkpointer=checkpointer,
        name=defn.name,
    )
