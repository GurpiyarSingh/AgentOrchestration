"""SQLModel tables for the registry, runs and traces (see docs/PLAN.md section 7).

JSON-valued columns are stored as TEXT holding JSON; helpers that encode/decode them
live next to the code that uses each table. Schema changes stay additive in the POC.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlmodel import Field, SQLModel


def new_id() -> str:
    """Generate a short unique id."""
    return uuid4().hex[:16]


def utcnow() -> datetime:
    """Timezone-aware current UTC time."""
    return datetime.now(UTC)


class AppSettingRecord(SQLModel, table=True):
    """Non-secret user preferences set in the UI (default model, git author, ...)."""

    __tablename__ = "app_settings"
    key: str = Field(primary_key=True)
    value_json: str
    updated_at: datetime = Field(default_factory=utcnow)


class McpServer(SQLModel, table=True):
    """A configured MCP server connection (stdio command or remote HTTP URL)."""

    __tablename__ = "mcp_servers"
    id: str = Field(default_factory=new_id, primary_key=True)
    name: str = Field(index=True, unique=True)
    transport: str  # "stdio" | "http"
    command: str | None = None
    args_json: str = "[]"
    env_refs_json: str = "{}"  # env var name -> secret reference, never raw secrets
    url: str | None = None
    headers_refs_json: str = "{}"
    enabled: bool = True
    status: str = "disconnected"
    last_error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class ToolRecord(SQLModel, table=True):
    """A tool known to the registry (python, mcp, agent or a2a)."""

    __tablename__ = "tools"
    id: str = Field(default_factory=new_id, primary_key=True)
    name: str = Field(index=True, unique=True)  # namespaced: "<source>__<name>"
    source: str  # "python" | "mcp" | "agent" | "a2a"
    server_id: str | None = Field(default=None, foreign_key="mcp_servers.id")
    agent_id: str | None = None
    description: str = ""
    input_schema_json: str = "{}"
    requires_approval: bool = False
    enabled: bool = True


class SkillRecord(SQLModel, table=True):
    """A skill folder (SKILL.md + files)."""

    __tablename__ = "skills"
    id: str = Field(default_factory=new_id, primary_key=True)
    name: str = Field(index=True, unique=True)
    description: str = ""
    path: str
    version: int = 1


class AgentRecord(SQLModel, table=True):
    """A persisted agent definition."""

    __tablename__ = "agents"
    id: str = Field(default_factory=new_id, primary_key=True)
    name: str = Field(index=True, unique=True)
    description: str = ""
    system_prompt: str = ""
    model: str = ""
    reasoning_effort: str | None = None
    kind: str = "llm"  # "llm" | "step" (deterministic, e.g. code runner)
    role: str = ""
    max_model_calls: int = 20
    max_tool_calls: int = 50
    tool_ids_json: str = "[]"
    skill_ids_json: str = "[]"
    a2a_exposed: bool = False
    version: int = 1
    updated_at: datetime = Field(default_factory=utcnow)


class WorkflowRecord(SQLModel, table=True):
    """A persisted workflow (pattern template or graph)."""

    __tablename__ = "workflows"
    id: str = Field(default_factory=new_id, primary_key=True)
    name: str = Field(index=True, unique=True)
    pattern: str = "graph"
    graph_json: str = "{}"
    version: int = 1
    updated_at: datetime = Field(default_factory=utcnow)


class RepositoryRecord(SQLModel, table=True):
    """A registered target repository for coding workflows."""

    __tablename__ = "repositories"
    id: str = Field(default_factory=new_id, primary_key=True)
    name: str = Field(index=True, unique=True)
    kind: str  # "local" | "new" | "cloned"
    path: str
    remote_url: str | None = None
    base_branch: str = "main"
    language_id: str | None = None
    install_cmd: str | None = None
    test_cmd: str | None = None
    lint_cmd: str | None = None
    protected_paths_json: str = "[]"
    created_at: datetime = Field(default_factory=utcnow)


class RunRecord(SQLModel, table=True):
    """One execution of an agent or workflow."""

    __tablename__ = "runs"
    id: str = Field(default_factory=new_id, primary_key=True)
    kind: str  # "agent" | "workflow"
    target_id: str
    input: str = ""
    output: str | None = None
    status: str = "running"
    started_at: datetime = Field(default_factory=utcnow)
    ended_at: datetime | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    model_calls: int = 0
    tool_calls: int = 0
    parent_run_id: str | None = Field(default=None, index=True)
    repo_id: str | None = None
    language_id: str | None = None
    branch: str | None = None
    worktree_path: str | None = None
    final_action: str | None = None  # "merged" | "kept" | "discarded"


class SpanRecord(SQLModel, table=True):
    """One traced event inside a run (LLM call, tool call, handoff, ...)."""

    __tablename__ = "spans"
    id: str = Field(default_factory=new_id, primary_key=True)
    run_id: str = Field(index=True, foreign_key="runs.id")
    parent_span_id: str | None = None
    type: str  # llm | tool | agent | handoff | approval | bus | error
    name: str
    input_json: str | None = None
    output_json: str | None = None
    started_at: datetime = Field(default_factory=utcnow)
    ended_at: datetime | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    meta_json: str = "{}"


class BusMessageRecord(SQLModel, table=True):
    """An agent-to-agent message on the in-process bus."""

    __tablename__ = "bus_messages"
    id: str = Field(default_factory=new_id, primary_key=True)
    run_id: str = Field(index=True, foreign_key="runs.id")
    from_agent: str
    to_agent: str
    content: str
    ts: datetime = Field(default_factory=utcnow)


class MemoryRecord(SQLModel, table=True):
    """Key/value agent memory (ADR-013)."""

    __tablename__ = "memory"
    id: str = Field(default_factory=new_id, primary_key=True)
    agent_id: str | None = Field(default=None, index=True)
    scope: str = "agent"  # "run" | "agent" | "global"
    key: str
    value: str
    ts: datetime = Field(default_factory=utcnow)


class RunArtifactRecord(SQLModel, table=True):
    """A named artifact produced by a run step (spec, plan, test_report, review, ...)."""

    __tablename__ = "run_artifacts"
    id: str = Field(default_factory=new_id, primary_key=True)
    run_id: str = Field(index=True, foreign_key="runs.id")
    name: str
    content_json: str
    step: int = 0
    ts: datetime = Field(default_factory=utcnow)
