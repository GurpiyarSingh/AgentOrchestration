"""Agent definitions: the data that describes an agent (ADR-006).

Stored in the `agents` table; importable/exportable as YAML in `config/agents/`.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import Engine
from sqlmodel import Session, select

from core.models import AgentRecord

_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,48}$")


class AgentDef(BaseModel):
    """Everything needed to build an agent."""

    name: str
    description: str = ""
    kind: Literal["llm", "step"] = "llm"  # "step" = deterministic pipeline step (no model)
    role: str = ""  # pipeline role, e.g. "requirements", "coder"; empty for general agents
    system_prompt: str = "You are a helpful assistant."
    model: str = ""  # "provider:model"; empty = settings.default_model
    reasoning_effort: str | None = None
    tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    max_model_calls: int = Field(default=20, ge=1, le=200)
    max_tool_calls: int = Field(default=50, ge=1, le=500)

    @field_validator("name")
    @classmethod
    def _valid_name(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError("name must be 2-49 chars: lowercase letters, digits, '-' or '_', starting with a letter")
        return v

    @field_validator("reasoning_effort")
    @classmethod
    def _valid_effort(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if v not in {"minimal", "low", "medium", "high", "xhigh"}:
            raise ValueError("reasoning_effort must be one of minimal, low, medium, high, xhigh")
        return v

    # ---- YAML -------------------------------------------------------------------

    def to_yaml(self) -> str:
        """Serialise to YAML (stable key order)."""
        return yaml.safe_dump(self.model_dump(), sort_keys=False, allow_unicode=True)

    @classmethod
    def from_yaml(cls, text: str, source: str = "<yaml>") -> AgentDef:
        """Parse and validate YAML; errors name the source and field."""
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as e:
            raise AgentDefError(f"{source}: invalid YAML: {e}") from e
        if not isinstance(data, dict):
            raise AgentDefError(f"{source}: expected a mapping at the top level")
        try:
            return cls.model_validate(data)
        except ValidationError as e:
            first = e.errors()[0]
            loc = ".".join(str(p) for p in first["loc"])
            raise AgentDefError(f"{source}: field '{loc}': {first['msg']}") from e

    # ---- DB ---------------------------------------------------------------------

    def to_record(self, record: AgentRecord | None = None) -> AgentRecord:
        """Copy into a (new or existing) `AgentRecord`."""
        rec = record or AgentRecord(name=self.name)
        rec.name = self.name
        rec.description = self.description
        rec.kind = self.kind
        rec.role = self.role
        rec.system_prompt = self.system_prompt
        rec.model = self.model
        rec.reasoning_effort = self.reasoning_effort
        rec.tool_ids_json = json.dumps(self.tools)
        rec.skill_ids_json = json.dumps(self.skills)
        rec.max_model_calls = self.max_model_calls
        rec.max_tool_calls = self.max_tool_calls
        rec.updated_at = datetime.now(UTC)
        return rec

    @classmethod
    def from_record(cls, rec: AgentRecord) -> AgentDef:
        """Build from a database row."""
        return cls(
            name=rec.name,
            description=rec.description,
            kind="step" if rec.kind == "step" else "llm",
            role=rec.role or "",
            system_prompt=rec.system_prompt,
            model=rec.model,
            reasoning_effort=rec.reasoning_effort,
            tools=json.loads(rec.tool_ids_json or "[]"),
            skills=json.loads(rec.skill_ids_json or "[]"),
            max_model_calls=rec.max_model_calls,
            max_tool_calls=rec.max_tool_calls,
        )


class AgentDefError(ValueError):
    """Invalid agent definition (bad YAML or field)."""


class AgentStore:
    """CRUD for agent definitions in SQLite, plus YAML import/export."""

    def __init__(self, db: Engine) -> None:
        self._db = db

    def list_all(self) -> list[AgentDef]:
        """All agents sorted by name."""
        with Session(self._db) as s:
            return [AgentDef.from_record(r) for r in s.exec(select(AgentRecord).order_by(AgentRecord.name)).all()]

    def get(self, name: str) -> AgentDef | None:
        """One agent by name."""
        with Session(self._db) as s:
            rec = s.exec(select(AgentRecord).where(AgentRecord.name == name)).first()
            return AgentDef.from_record(rec) if rec else None

    def save(self, agent: AgentDef) -> AgentDef:
        """Create or update by name."""
        with Session(self._db) as s:
            rec = s.exec(select(AgentRecord).where(AgentRecord.name == agent.name)).first()
            if rec is not None:
                rec.version += 1
            s.add(agent.to_record(rec))
            s.commit()
        return agent

    def delete(self, name: str) -> bool:
        """Delete by name; returns whether it existed."""
        with Session(self._db) as s:
            rec = s.exec(select(AgentRecord).where(AgentRecord.name == name)).first()
            if rec is None:
                return False
            s.delete(rec)
            s.commit()
            return True

    def import_yaml_dir(self, folder: Path, *, overwrite: bool = False) -> list[str]:
        """Import every `*.yaml` in `folder`; returns imported names."""
        imported: list[str] = []
        for path in sorted(folder.glob("*.yaml")):
            agent = AgentDef.from_yaml(path.read_text(encoding="utf-8"), source=str(path))
            if overwrite or self.get(agent.name) is None:  # never clobber user edits
                self.save(agent)
                imported.append(agent.name)
        return imported

    def export_yaml(self, name: str, folder: Path) -> Path:
        """Write one agent to `<folder>/<name>.yaml`."""
        agent = self.get(name)
        if agent is None:
            raise KeyError(name)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{name}.yaml"
        path.write_text(agent.to_yaml(), encoding="utf-8")
        return path


def agent_summary(agent: AgentDef) -> dict[str, Any]:
    """Compact dict for tables."""
    return {
        "name": agent.name,
        "kind": agent.kind,
        "role": agent.role,
        "model": agent.model or "(default)",
        "tools": len(agent.tools),
        "skills": len(agent.skills),
        "description": agent.description,
    }
