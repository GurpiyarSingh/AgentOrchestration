"""Agent middleware we add on top of LangChain's built-ins."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from core.tools.registry import truncate

ToolResult = ToolMessage | Command[Any]


class ToolPolicyMiddleware(AgentMiddleware):
    """Blocks selected tools and truncates oversized tool output.

    `blocked` maps tool name → message returned to the model instead of running it.
    In M1 this blocks `requires_approval` tools until approvals exist (M4).
    """

    def __init__(self, *, max_output_chars: int, blocked: dict[str, str] | None = None) -> None:
        super().__init__()
        self.max_output_chars = max_output_chars
        self.blocked = blocked or {}

    def _blocked_message(self, request: ToolCallRequest) -> ToolMessage | None:
        name = request.tool_call["name"]
        if name not in self.blocked:
            return None
        return ToolMessage(content=self.blocked[name], tool_call_id=request.tool_call["id"], name=name, status="error")

    def _truncate(self, result: ToolResult) -> ToolResult:
        if isinstance(result, ToolMessage) and isinstance(result.content, str):
            cut = truncate(result.content, self.max_output_chars)
            if cut is not result.content:
                return result.model_copy(update={"content": cut})
        return result

    def wrap_tool_call(self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], ToolResult]) -> ToolResult:
        """Sync path."""
        return self._blocked_message(request) or self._truncate(handler(request))

    async def awrap_tool_call(
        self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], Awaitable[ToolResult]]
    ) -> ToolResult:
        """Async path."""
        return self._blocked_message(request) or self._truncate(await handler(request))


def tool_error_to_text(exc: Exception, request: ToolCallRequest) -> str:
    """Turn an unexpected tool exception into a message the model can act on."""
    return f"Tool '{request.tool_call['name']}' failed with {type(exc).__name__}: {exc}"
