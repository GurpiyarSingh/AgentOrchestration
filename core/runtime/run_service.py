"""Start, observe and cancel agent runs.

A run executes as an asyncio task on the caller's event loop. Its live state is kept in a
`RunHandle` (polled by the UI / API) and persisted to the `runs` and `spans` tables.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, ToolMessage
from pydantic import BaseModel, Field
from sqlalchemy import Engine
from sqlmodel import Session

from core.chat import ChatReply, ChatTurn, chat_once, to_langchain
from core.config import Settings
from core.llm.errors import friendly_error
from core.llm.models import build_chat_model
from core.models import RunRecord, new_id
from core.pricing import PriceTable
from core.runtime.agent_def import AgentDef
from core.runtime.agent_factory import build_agent
from core.tools.registry import ToolRegistry
from core.tracing.callbacks import TraceCallbackHandler
from core.tracing.redact import Redactor
from core.tracing.tracer import Tracer

RunStatus = Literal["running", "done", "failed", "cancelled"]
ModelFactory = Callable[[str, AgentDef], BaseChatModel]


class TimelineItem(BaseModel):
    """One visible step of a run: assistant text or a tool call."""

    kind: Literal["text", "tool"]
    text: str = ""
    tool_call_id: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    tool_output: str | None = None
    tool_status: Literal["running", "ok", "error"] | None = None


class RunSnapshot(BaseModel):
    """Point-in-time copy of a run's state (safe to read from another thread)."""

    run_id: str
    agent: str
    status: RunStatus
    timeline: list[TimelineItem]
    output: str | None = None
    error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    model_calls: int = 0
    tool_calls: int = 0


class RunHandle:
    """Live state of one run, updated by the run task."""

    def __init__(self, run_id: str, agent: str) -> None:
        self.run_id = run_id
        self.agent = agent
        self.status: RunStatus = "running"
        self.timeline: list[TimelineItem] = []
        self.output: str | None = None
        self.error: str | None = None
        self.tracer: Tracer | None = None
        self.task: asyncio.Task[None] | None = None
        self._lock = threading.Lock()
        self._open_text: TimelineItem | None = None

    # -- updates from the stream --------------------------------------------------------

    def text_delta(self, delta: str) -> None:
        """Append streamed assistant text."""
        if not delta:
            return
        with self._lock:
            if self._open_text is None:
                self._open_text = TimelineItem(kind="text")
                self.timeline.append(self._open_text)
            self._open_text.text += delta

    def ai_message(self, msg: AIMessage) -> None:
        """A completed model turn: authoritative text plus requested tool calls."""
        with self._lock:
            text = msg.text
            if self._open_text is not None:
                self._open_text.text = text or self._open_text.text
            elif text:
                self.timeline.append(TimelineItem(kind="text", text=text))
            self._open_text = None
            for tc in msg.tool_calls:
                self.timeline.append(
                    TimelineItem(
                        kind="tool",
                        tool_call_id=tc.get("id"),
                        tool_name=tc["name"],
                        tool_args=dict(tc.get("args") or {}),
                        tool_status="running",
                    )
                )
            if text and not msg.tool_calls:
                self.output = text

    def tool_result(self, msg: ToolMessage) -> None:
        """A finished tool call."""
        with self._lock:
            for item in self.timeline:
                if item.kind == "tool" and item.tool_call_id == msg.tool_call_id:
                    item.tool_output = msg.text if not isinstance(msg.content, str) else msg.content
                    item.tool_status = "error" if msg.status == "error" else "ok"
                    break

    def snapshot(self) -> RunSnapshot:
        """Thread-safe copy for the UI / API."""
        with self._lock:
            t = self.tracer
            return RunSnapshot(
                run_id=self.run_id,
                agent=self.agent,
                status=self.status,
                timeline=[i.model_copy() for i in self.timeline],
                output=self.output,
                error=self.error,
                input_tokens=t.input_tokens if t else 0,
                output_tokens=t.output_tokens if t else 0,
                cost_usd=t.cost_usd if t else 0.0,
                model_calls=t.model_calls if t else 0,
                tool_calls=t.tool_calls if t else 0,
            )


class RunError(Exception):
    """A run could not be started (unknown agent, no model, bad tools)."""


class RunService:
    """Creates and tracks agent runs."""

    def __init__(
        self,
        db: Engine,
        settings: Settings,
        registry: ToolRegistry,
        prices: PriceTable,
        *,
        model_factory: ModelFactory | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.registry = registry
        self.prices = prices
        self._model_factory = model_factory or self._default_model_factory
        self._handles: dict[str, RunHandle] = {}
        secret = settings.openai_api_key.get_secret_value() if settings.openai_api_key else ""
        self._redactor = Redactor([secret])

    @property
    def model_factory(self) -> ModelFactory:
        """The factory used to build chat models (shared with the pipeline)."""
        return self._model_factory

    @property
    def redactor(self) -> Redactor:
        """Current secret redactor."""
        return self._redactor

    def refresh_secrets(self, secrets: set[str]) -> None:
        """Redact these secret values from traces (called when keys change)."""
        self._redactor = Redactor(secrets)

    def _default_model_factory(self, ref: str, agent: AgentDef) -> BaseChatModel:
        return build_chat_model(ref, self.settings, reasoning_effort=agent.reasoning_effort)

    def get(self, run_id: str) -> RunHandle | None:
        """Live handle for a run started by this process."""
        return self._handles.get(run_id)

    async def start(self, agent: AgentDef, history: list[ChatTurn], *, model_override: str | None = None) -> RunHandle:
        """Validate, record and launch a run on the current event loop."""
        if not history or history[-1].role != "user":
            raise RunError("The conversation must end with a user message.")
        model_ref = model_override or agent.model or self.settings.default_model
        if not model_ref:
            raise RunError(f"Agent '{agent.name}' has no model and DEFAULT_MODEL is not set.")
        try:
            tools = self.registry.resolve(agent.tools)
            model = self._model_factory(model_ref, agent)
        except Exception as exc:
            raise RunError(friendly_error(exc)) from exc

        run_id = new_id()
        with Session(self.db) as s:
            s.add(RunRecord(id=run_id, kind="agent", target_id=agent.name, input=history[-1].content))
            s.commit()

        handle = RunHandle(run_id, agent.name)
        handle.tracer = Tracer(self.db, run_id, self.prices, self._redactor)
        graph = build_agent(agent, model, tools, max_output_chars=self.settings.max_tool_output_chars)
        messages = to_langchain(history)
        handle.task = asyncio.create_task(self._execute(handle, graph, messages, model_ref), name=f"run-{run_id}")
        self._handles[run_id] = handle
        return handle

    async def cancel(self, run_id: str) -> bool:
        """Cancel a running run; returns False if it isn't running."""
        handle = self._handles.get(run_id)
        if handle is None or handle.task is None or handle.task.done():
            return False
        handle.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await handle.task
        return True

    async def wait(self, run_id: str, max_wait_s: float | None = None) -> RunSnapshot:
        """Wait for a run to finish and return its final snapshot."""
        handle = self._handles[run_id]
        if handle.task is not None:
            await asyncio.wait_for(asyncio.shield(handle.task), max_wait_s)
        return handle.snapshot()

    async def _execute(self, handle: RunHandle, graph: Any, messages: list[BaseMessage], model_ref: str) -> None:
        assert handle.tracer is not None
        tracer = handle.tracer
        root = tracer.start_span(
            "agent", handle.agent, input={"messages": [m.content for m in messages], "model": model_ref}
        )
        callbacks = [TraceCallbackHandler(tracer, root, default_model=model_ref)]
        config = {
            "callbacks": callbacks,
            "configurable": {"thread_id": handle.run_id},
            "recursion_limit": 500,
        }
        try:
            async for mode, data in graph.astream(
                {"messages": messages}, config=config, stream_mode=["messages", "updates"]
            ):
                if mode == "messages":
                    chunk, meta = data
                    if isinstance(chunk, AIMessageChunk) and meta.get("langgraph_node") == "model":
                        handle.text_delta(chunk.text)
                elif mode == "updates":
                    for update in data.values():
                        for msg in (update or {}).get("messages", []) if isinstance(update, dict) else []:
                            if isinstance(msg, AIMessage):
                                handle.ai_message(msg)
                            elif isinstance(msg, ToolMessage):
                                handle.tool_result(msg)
            handle.status = "done"
            tracer.end_span(root, output=handle.output)
        except asyncio.CancelledError:
            handle.status = "cancelled"
            tracer.end_span(root, error="cancelled by user")
            self._finish(handle)
            raise
        except Exception as exc:
            handle.status = "failed"
            handle.error = friendly_error(exc)
            tracer.end_span(root, error=f"{type(exc).__name__}: {exc}")
        self._finish(handle)

    def _finish(self, handle: RunHandle) -> None:
        t = handle.tracer
        with Session(self.db) as s:
            rec = s.get(RunRecord, handle.run_id)
            if rec is None:
                return
            rec.status = handle.status
            rec.output = handle.output if handle.status == "done" else handle.error
            rec.ended_at = datetime.now(UTC)
            if t is not None:
                _copy_totals(t, rec)
            s.add(rec)
            s.commit()

    async def chat(
        self, model_ref: str, history: list[ChatTurn], system_prompt: str | None = None
    ) -> tuple[str, ChatReply]:
        """Plain model chat (no tools), recorded as a traced run of kind "chat".

        Returns (run_id, reply). Raises `RunError` for configuration problems; model
        errors propagate after the run is marked failed.
        """
        if not history or history[-1].role != "user":
            raise RunError("The conversation must end with a user message.")
        try:
            model = self._model_factory(model_ref, _CHAT_AGENT)
        except Exception as exc:
            raise RunError(friendly_error(exc)) from exc
        run_id = new_id()
        with Session(self.db) as s:
            s.add(RunRecord(id=run_id, kind="chat", target_id=model_ref, input=history[-1].content))
            s.commit()
        tracer = Tracer(self.db, run_id, self.prices, self._redactor)
        handler = TraceCallbackHandler(tracer, None, default_model=model_ref)
        status, output = "failed", None
        try:
            reply = await chat_once(model, history, system_prompt, callbacks=[handler])
            status, output = "done", reply.text
            return run_id, reply
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except Exception as exc:
            output = friendly_error(exc)
            raise
        finally:
            with Session(self.db) as s:
                rec = s.get(RunRecord, run_id)
                if rec is not None:
                    rec.status, rec.output, rec.ended_at = status, output, datetime.now(UTC)
                    _copy_totals(tracer, rec)
                    s.add(rec)
                    s.commit()


_CHAT_AGENT = AgentDef(name="chat", description="Plain model chat")


def _copy_totals(t: Tracer, rec: RunRecord) -> None:
    """Copy token, cost and call totals from a tracer onto a run record."""
    rec.input_tokens, rec.output_tokens, rec.cost_usd = t.input_tokens, t.output_tokens, t.cost_usd
    rec.model_calls, rec.tool_calls = t.model_calls, t.tool_calls
