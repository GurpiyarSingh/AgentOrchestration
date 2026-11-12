"""Tool registry: every tool an agent can use, with its flags (RULES.md section 6).

Tools are LangChain `BaseTool`s named `<source-or-server>__<name>`. Flags (`enabled`,
`requires_approval`) are persisted in the `tools` table so the UI can change them.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Literal

from langchain_core.tools import BaseTool
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlmodel import Session, select

from core.models import ToolRecord

ToolSource = Literal["python", "mcp", "agent", "a2a", "repo"]
DEFAULT_MAX_OUTPUT_CHARS = 20_000


class UnknownToolError(KeyError):
    """An agent references tools that are not registered."""

    def __init__(self, names: list[str]) -> None:
        super().__init__(names)
        self.names = names

    def __str__(self) -> str:
        return f"Unknown tool(s): {', '.join(self.names)}. Check the Tools page for available names."


@dataclass
class ToolEntry:
    """A registered tool plus its flags."""

    tool: BaseTool
    source: ToolSource
    requires_approval: bool = False
    enabled: bool = True
    server: str | None = None

    @property
    def name(self) -> str:
        """Namespaced tool name."""
        return self.tool.name

    @property
    def args_schema_json(self) -> dict[str, Any]:
        """JSON Schema of the tool's arguments."""
        schema: Any = self.tool.tool_call_schema
        if isinstance(schema, dict):
            return dict(schema)
        if hasattr(schema, "model_json_schema"):
            return dict(schema.model_json_schema())
        return dict(schema.schema())


class ToolInvocation(BaseModel):
    """Result of running a tool directly (Tools page "Try it", API)."""

    ok: bool
    output: str
    duration_ms: int


def _as_text(out: Any) -> str:
    """Tool output → display text (MCP tools return lists of content blocks)."""
    if isinstance(out, str):
        return out
    if isinstance(out, list) and out and all(isinstance(b, dict) and "type" in b for b in out):
        parts = [str(b.get("text", "")) if b.get("type") == "text" else f"[{b.get('type')} content]" for b in out]
        return "\n".join(parts)
    return json.dumps(out, default=str)


def truncate(text: str, max_chars: int = DEFAULT_MAX_OUTPUT_CHARS) -> str:
    """Cut `text` to `max_chars`, adding a visible marker."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n[truncated: {len(text) - max_chars} more chars]"


class ToolRegistry:
    """In-memory catalog of tools, with flags synced to the database."""

    def __init__(self, db: Engine | None = None) -> None:
        self._entries: dict[str, ToolEntry] = {}
        self._db = db

    def register(
        self,
        tool: BaseTool,
        source: ToolSource,
        *,
        requires_approval: bool = False,
        enabled: bool = True,
        server: str | None = None,
        replace: bool = False,
    ) -> ToolEntry:
        """Add a tool. Flags already stored in the database take precedence."""
        if "__" not in tool.name:
            raise ValueError(f"Tool name '{tool.name}' must be namespaced as '<prefix>__<name>'.")
        if tool.name in self._entries and not replace:
            raise ValueError(f"Tool '{tool.name}' is already registered.")
        entry = ToolEntry(tool, source, requires_approval, enabled, server)
        self._entries[tool.name] = entry
        self._sync_entry(entry)
        return entry

    def unregister(self, name: str) -> None:
        """Remove a tool (e.g. when its MCP server disconnects)."""
        self._entries.pop(name, None)

    def entries(self) -> list[ToolEntry]:
        """All registered tools, sorted by name."""
        return sorted(self._entries.values(), key=lambda e: e.name)

    def get(self, name: str) -> ToolEntry:
        """Look up one tool."""
        try:
            return self._entries[name]
        except KeyError:
            raise UnknownToolError([name]) from None

    def resolve(self, names: list[str]) -> list[ToolEntry]:
        """Entries for an agent's tool list. Unknown names raise; disabled tools are skipped."""
        missing = [n for n in names if n not in self._entries]
        if missing:
            raise UnknownToolError(missing)
        return [self._entries[n] for n in names if self._entries[n].enabled]

    def set_flags(self, name: str, *, enabled: bool | None = None, requires_approval: bool | None = None) -> None:
        """Change a tool's flags and persist them."""
        entry = self.get(name)
        if enabled is not None:
            entry.enabled = enabled
        if requires_approval is not None:
            entry.requires_approval = requires_approval
        if self._db is not None:
            with Session(self._db) as s:
                rec = s.exec(select(ToolRecord).where(ToolRecord.name == name)).first()
                if rec is not None:
                    rec.enabled, rec.requires_approval = entry.enabled, entry.requires_approval
                    s.add(rec)
                    s.commit()

    async def invoke(
        self, name: str, args: dict[str, Any], max_chars: int = DEFAULT_MAX_OUTPUT_CHARS
    ) -> ToolInvocation:
        """Run a tool directly. Never raises for tool failures."""
        entry = self.get(name)
        start = time.perf_counter()
        try:
            out = await entry.tool.ainvoke(args)
            ok = True
            text = _as_text(out)
        except Exception as exc:
            ok, text = False, f"{type(exc).__name__}: {exc}"
        return ToolInvocation(
            ok=ok, output=truncate(text, max_chars), duration_ms=int((time.perf_counter() - start) * 1000)
        )

    def _sync_entry(self, entry: ToolEntry) -> None:
        if self._db is None:
            return
        with Session(self._db) as s:
            rec = s.exec(select(ToolRecord).where(ToolRecord.name == entry.name)).first()
            if rec is None:
                rec = ToolRecord(
                    name=entry.name,
                    source=entry.source,
                    requires_approval=entry.requires_approval,
                    enabled=entry.enabled,
                )
            else:  # persisted flags win
                entry.enabled, entry.requires_approval = rec.enabled, rec.requires_approval
            rec.description = entry.tool.description
            rec.input_schema_json = json.dumps(entry.args_schema_json)
            s.add(rec)
            s.commit()
