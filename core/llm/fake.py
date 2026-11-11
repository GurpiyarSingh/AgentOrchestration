"""Scripted chat model for tests (docs/TESTING.md section 2).

Returns pre-written `AIMessage`s in order (including tool calls), records every request,
and supports `bind_tools`, so it can drive LangGraph agents deterministically.
An unscripted call fails loudly.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field


class ScriptExhaustedError(AssertionError):
    """The code under test made more model calls than were scripted."""


class ScriptedChatModel(BaseChatModel):
    """Deterministic chat model that replays a script of AI messages."""

    script: list[AIMessage] = Field(default_factory=list)
    calls: list[list[BaseMessage]] = Field(default_factory=list)
    bound_tools: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append([m.model_copy(deep=True) for m in messages])
        if not self.script:
            raise ScriptExhaustedError(f"Unscripted model call #{len(self.calls)}")
        return ChatResult(generations=[ChatGeneration(message=self.script.pop(0))])

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        """Record the offered tools; the script decides which calls are made."""
        self.bound_tools = [convert_to_openai_tool(t) for t in tools]
        return self

    @property
    def remaining(self) -> int:
        """Number of scripted messages not yet consumed."""
        return len(self.script)
