"""Tracer: writes spans for one run to SQLite and keeps run totals."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session

from core.models import SpanRecord, new_id
from core.pricing import PriceTable
from core.tracing.redact import Redactor

MAX_FIELD_CHARS = 50_000


def _dump(value: Any, redact: Redactor) -> str | None:
    if value is None:
        return None
    text = value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)
    text = redact(text)
    if len(text) > MAX_FIELD_CHARS:
        text = text[:MAX_FIELD_CHARS] + f"…[truncated {len(text) - MAX_FIELD_CHARS} chars]"
    return text


class Tracer:
    """Span writer for a single run. Thread-safe; DB writes are small and synchronous."""

    def __init__(self, db: Engine, run_id: str, prices: PriceTable, redactor: Redactor) -> None:
        self.db = db
        self.run_id = run_id
        self.prices = prices
        self.redact = redactor
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0
        self.model_calls = 0
        self.tool_calls = 0
        self.unpriced_models: set[str] = set()
        self._lock = threading.Lock()

    def start_span(
        self,
        type: str,
        name: str,
        *,
        parent_span_id: str | None = None,
        input: Any = None,
        meta: dict[str, Any] | None = None,
    ) -> str:
        """Create a span and return its id."""
        span_id = new_id()
        span = SpanRecord(
            id=span_id,
            run_id=self.run_id,
            parent_span_id=parent_span_id,
            type=type,
            name=name,
            input_json=_dump(input, self.redact),
            meta_json=json.dumps(meta or {}, default=str),
        )
        with self._lock, Session(self.db) as s:
            s.add(span)
            s.commit()
            if type == "llm":
                self.model_calls += 1
            elif type == "tool":
                self.tool_calls += 1
        return span_id

    def end_span(
        self,
        span_id: str,
        *,
        output: Any = None,
        error: str | None = None,
        model: str | None = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cached_tokens: int = 0,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Close a span with its output, usage and cost."""
        cost = self.prices.cost(model, tokens_in, tokens_out, cached_tokens) if (tokens_in or tokens_out) else None
        with self._lock, Session(self.db) as s:
            span = s.get(SpanRecord, span_id)
            if span is None:
                return
            span.ended_at = datetime.now(UTC)
            span.output_json = _dump(output, self.redact)
            span.tokens_in, span.tokens_out = tokens_in, tokens_out
            extra = json.loads(span.meta_json or "{}")
            extra.update(meta or {})
            if model:
                extra["model"] = model
            if cost is not None:
                extra["cost_usd"] = cost
            if error:
                extra["error"] = self.redact(error)
            span.meta_json = json.dumps(extra, default=str)
            s.add(span)
            s.commit()
            self.input_tokens += tokens_in
            self.output_tokens += tokens_out
            if cost is not None:
                self.cost_usd += cost
            elif model and (tokens_in or tokens_out):
                self.unpriced_models.add(model)
