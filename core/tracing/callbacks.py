"""LangChain callback handler that turns model and tool events into tracer spans.

Pass it on every invocation: `graph.astream(..., config={"callbacks": [handler]})`.
Chain events (graph nodes) are not written as spans; they are only used to find the
nearest traced ancestor, so tool calls that start nested agents nest correctly.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.outputs import LLMResult

from core.tracing.tracer import Tracer


def message_to_dict(m: BaseMessage) -> dict[str, Any]:
    """Compact, JSON-friendly view of a message for traces."""
    d: dict[str, Any] = {"role": m.type, "content": m.content}
    tool_calls = getattr(m, "tool_calls", None)
    if tool_calls:
        d["tool_calls"] = [{"id": tc.get("id"), "name": tc["name"], "args": tc["args"]} for tc in tool_calls]
    if isinstance(m, ToolMessage):
        d["tool_call_id"] = m.tool_call_id
        d["status"] = m.status
    return d


class TraceCallbackHandler(AsyncCallbackHandler):
    """Writes llm and tool spans under a root span."""

    raise_error = False
    run_inline = True

    def __init__(self, tracer: Tracer, root_span_id: str | None, default_model: str | None = None) -> None:
        self.tracer = tracer
        self.root_span_id = root_span_id
        self.default_model = default_model
        self._spans: dict[UUID, str] = {}
        self._models: dict[UUID, str] = {}
        self._parents: dict[UUID, UUID | None] = {}

    # ---- helpers -------------------------------------------------------------------

    def _parent_span(self, parent_run_id: UUID | None) -> str | None:
        seen = 0
        while parent_run_id is not None and seen < 1000:
            if parent_run_id in self._spans:
                return self._spans[parent_run_id]
            parent_run_id = self._parents.get(parent_run_id)
            seen += 1
        return self.root_span_id

    # ---- chains (graph nodes): only remember the tree ---------------------------------

    async def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kw: Any,
    ) -> None:
        self._parents[run_id] = parent_run_id

    # ---- models ----------------------------------------------------------------------

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any] | None,
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        **kw: Any,
    ) -> None:
        self._parents[run_id] = parent_run_id
        params = kw.get("invocation_params") or {}
        model = (
            (metadata or {}).get("ls_model_name")
            or params.get("model")
            or params.get("model_name")
            or self.default_model
            or (serialized or {}).get("name")
            or "model"
        )
        self._models[run_id] = str(model)
        msgs = [message_to_dict(m) for m in (messages[0] if messages else [])]
        self._spans[run_id] = self.tracer.start_span(
            "llm",
            str(model),
            parent_span_id=self._parent_span(parent_run_id),
            input=msgs,
            meta={"agent": (metadata or {}).get("lc_agent_name")},
        )

    async def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kw: Any) -> None:
        span_id = self._spans.get(run_id)
        if span_id is None:
            return
        msg = None
        if response.generations and response.generations[0]:
            msg = getattr(response.generations[0][0], "message", None)
        usage = (getattr(msg, "usage_metadata", None) or {}) if msg is not None else {}
        cached = (usage.get("input_token_details") or {}).get("cache_read", 0) or 0
        self.tracer.end_span(
            span_id,
            output=message_to_dict(msg) if msg is not None else None,
            model=self._models.get(run_id),
            tokens_in=int(usage.get("input_tokens", 0) or 0),
            tokens_out=int(usage.get("output_tokens", 0) or 0),
            cached_tokens=int(cached),
        )

    async def on_llm_error(self, error: BaseException, *, run_id: UUID, **kw: Any) -> None:
        if (span_id := self._spans.get(run_id)) is not None:
            self.tracer.end_span(span_id, error=f"{type(error).__name__}: {error}", model=self._models.get(run_id))

    # ---- tools -----------------------------------------------------------------------

    async def on_tool_start(
        self,
        serialized: dict[str, Any] | None,
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        inputs: dict[str, Any] | None = None,
        **kw: Any,
    ) -> None:
        self._parents[run_id] = parent_run_id
        name = (serialized or {}).get("name") or kw.get("name") or "tool"
        self._spans[run_id] = self.tracer.start_span(
            "tool", str(name), parent_span_id=self._parent_span(parent_run_id), input=inputs or input_str
        )

    async def on_tool_end(self, output: Any, *, run_id: UUID, **kw: Any) -> None:
        if (span_id := self._spans.get(run_id)) is None:
            return
        if isinstance(output, ToolMessage):
            err = output.content if output.status == "error" else None
            self.tracer.end_span(span_id, output=output.content, error=str(err) if err else None)
        else:
            self.tracer.end_span(span_id, output=output)

    async def on_tool_error(self, error: BaseException, *, run_id: UUID, **kw: Any) -> None:
        if (span_id := self._spans.get(run_id)) is not None:
            self.tracer.end_span(span_id, error=f"{type(error).__name__}: {error}")
