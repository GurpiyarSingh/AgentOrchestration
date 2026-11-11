"""Read-side queries for runs and spans (Runs page, API)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import Engine
from sqlmodel import Session, col, func, select

from core.models import RunRecord, SpanRecord


class SpanNode(BaseModel):
    """A span with its children, for tree display."""

    id: str
    type: str
    name: str
    started_at: str
    duration_ms: int | None
    tokens_in: int
    tokens_out: int
    meta: dict[str, Any]
    input: Any = None
    output: Any = None
    children: list[SpanNode] = Field(default_factory=list)

    @property
    def error(self) -> str | None:
        """Error message recorded on the span, if any."""
        err = self.meta.get("error")
        return str(err) if err else None


def _parse(text: str | None) -> Any:
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def list_runs(db: Engine, limit: int = 100) -> list[RunRecord]:
    """Most recent runs first."""
    with Session(db) as s:
        return list(s.exec(select(RunRecord).order_by(col(RunRecord.started_at).desc()).limit(limit)).all())


def get_run(db: Engine, run_id: str) -> RunRecord | None:
    """One run record."""
    with Session(db) as s:
        return s.get(RunRecord, run_id)


class UsageSummary(BaseModel):
    """Aggregate usage over a time window."""

    runs: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        """Input + output tokens."""
        return self.input_tokens + self.output_tokens


def start_of_local_day(now: datetime | None = None) -> datetime:
    """Local midnight today, as an aware UTC datetime."""
    local = (now or datetime.now().astimezone()).astimezone()
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


def usage_summary(db: Engine, since: datetime | None = None) -> UsageSummary:
    """Usage since `since` (None = all time).

    Calls and tokens come from spans (so in-progress runs count live); cost comes
    from finished runs.
    """
    with Session(db) as s:
        span_q = select(
            SpanRecord.type,
            func.count(),
            func.coalesce(func.sum(SpanRecord.tokens_in), 0),
            func.coalesce(func.sum(SpanRecord.tokens_out), 0),
        ).group_by(SpanRecord.type)
        run_q = select(func.count(), func.coalesce(func.sum(RunRecord.cost_usd), 0.0))
        if since is not None:
            span_q = span_q.where(SpanRecord.started_at >= since)
            run_q = run_q.where(RunRecord.started_at >= since)
        out = UsageSummary()
        for typ, count, tin, tout in s.exec(span_q).all():
            if typ == "llm":
                out.model_calls = int(count)
            elif typ == "tool":
                out.tool_calls = int(count)
            out.input_tokens += int(tin)
            out.output_tokens += int(tout)
        runs, cost = s.exec(run_q).one()
        out.runs, out.cost_usd = int(runs), float(cost)
        return out


def span_tree(db: Engine, run_id: str) -> list[SpanNode]:
    """All spans of a run as a forest ordered by start time."""
    with Session(db) as s:
        rows = list(
            s.exec(select(SpanRecord).where(SpanRecord.run_id == run_id).order_by(col(SpanRecord.started_at))).all()
        )
    nodes: dict[str, SpanNode] = {}
    for r in rows:
        dur = int((r.ended_at - r.started_at).total_seconds() * 1000) if r.ended_at else None
        nodes[r.id] = SpanNode(
            id=r.id,
            type=r.type,
            name=r.name,
            started_at=r.started_at.isoformat(timespec="milliseconds"),
            duration_ms=dur,
            tokens_in=r.tokens_in,
            tokens_out=r.tokens_out,
            meta=json.loads(r.meta_json or "{}"),
            input=_parse(r.input_json),
            output=_parse(r.output_json),
        )
    roots: list[SpanNode] = []
    for r in rows:
        node = nodes[r.id]
        parent = nodes.get(r.parent_span_id) if r.parent_span_id else None
        (parent.children if parent else roots).append(node)
    return roots
