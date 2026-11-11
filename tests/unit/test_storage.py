from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, select

from core.models import (
    AgentRecord,
    BusMessageRecord,
    McpServer,
    MemoryRecord,
    RepositoryRecord,
    RunArtifactRecord,
    RunRecord,
    SkillRecord,
    SpanRecord,
    ToolRecord,
    WorkflowRecord,
)
from core.storage import create_db_engine, session_scope

EXPECTED_TABLES = {
    "mcp_servers",
    "tools",
    "skills",
    "agents",
    "workflows",
    "repositories",
    "runs",
    "spans",
    "bus_messages",
    "memory",
    "run_artifacts",
}


def test_creates_db_file_and_all_tables(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db = tmp_path / "nested" / "app.db"
    create_db_engine(db)
    assert db.exists()
    assert set(SQLModel.metadata.tables) >= EXPECTED_TABLES


def _rows(run_id: str) -> list[SQLModel]:
    return [
        McpServer(name="fs", transport="stdio", command="npx"),
        ToolRecord(name="builtin__calculator", source="python"),
        SkillRecord(name="report-writing", path="skills/report-writing"),
        AgentRecord(name="researcher", model="openai:some-model"),
        WorkflowRecord(name="dev_team"),
        RepositoryRecord(name="demo", kind="new", path="workspaces/demo", language_id="python"),
        RunRecord(id=run_id, kind="agent", target_id="researcher"),
        SpanRecord(run_id=run_id, type="llm", name="call"),
        BusMessageRecord(run_id=run_id, from_agent="a", to_agent="b", content="hi"),
        MemoryRecord(key="k", value="v"),
        RunArtifactRecord(run_id=run_id, name="spec", content_json="{}"),
    ]


def test_round_trip_one_row_per_table() -> None:
    engine = create_db_engine(":memory:")
    rows = _rows("run1")
    parents = [r for r in rows if isinstance(r, (McpServer, RunRecord))]
    with session_scope(engine) as s:
        s.add_all(parents)
        s.flush()  # foreign keys are enforced: parents must exist first
        s.add_all([r for r in rows if r not in parents])
    with Session(engine) as s:
        for row in rows:
            got = s.exec(select(type(row))).all()
            assert len(got) == 1, type(row).__name__


def test_session_scope_rolls_back_on_error() -> None:
    engine = create_db_engine(":memory:")
    with pytest.raises(RuntimeError), session_scope(engine) as s:
        s.add(AgentRecord(name="temp"))
        raise RuntimeError("boom")
    with Session(engine) as s:
        assert s.exec(select(AgentRecord)).all() == []


def test_additive_migration_adds_new_columns(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import sqlite3

    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE agents (id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL)")
    con.execute("INSERT INTO agents (id, name) VALUES ('1', 'legacy')")
    con.commit()
    con.close()

    engine = create_db_engine(db)  # runs add_missing_columns
    with Session(engine) as s:
        rec = s.exec(select(AgentRecord)).one()
    assert rec.name == "legacy" and rec.max_model_calls == 20 and rec.max_tool_calls == 50
