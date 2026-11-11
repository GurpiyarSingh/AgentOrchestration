"""SQLite storage: engine creation and session helper."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from core import models  # noqa: F401  (registers tables on SQLModel.metadata)


def create_db_engine(db_path: Path | str) -> Engine:
    """Create a SQLite engine, creating the parent folder and all tables if needed.

    Pass ":memory:" for an in-memory database (tests).
    """
    if str(db_path) == ":memory:":
        # One shared connection, so every thread (tool callbacks run in worker threads) sees the same DB.
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    else:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # type: ignore[no-untyped-def]
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    SQLModel.metadata.create_all(engine)
    add_missing_columns(engine)
    return engine


def add_missing_columns(engine: Engine) -> list[str]:
    """Additive migration: add columns that exist in the models but not in the DB (RULES.md 8).

    New columns are added without NOT NULL; existing rows are backfilled with the field's
    default (constant or factory). Returns the "table.column" names added.
    """
    added: list[str] = []
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            existing = {row[1] for row in conn.exec_driver_sql(f'PRAGMA table_info("{table.name}")')}
            for col in table.columns:
                if col.name in existing:
                    continue
                found, default = _column_default(table.name, col.name, col)
                if not found and not col.nullable:
                    raise RuntimeError(
                        f"Cannot add required column {table.name}.{col.name} without a default; "
                        "reset the database (delete data/app.db)."
                    )
                ddl_type = col.type.compile(dialect=engine.dialect)
                conn.exec_driver_sql(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl_type}')
                if found and default is not None:
                    conn.execute(table.update().values({col.name: default}))
                added.append(f"{table.name}.{col.name}")
    return added


def _column_default(table_name: str, column_name: str, column: Any) -> tuple[bool, Any]:
    """(found, value): SQL-side scalar default, else the SQLModel field default or factory value."""
    if column.default is not None and getattr(column.default, "is_scalar", False):
        return True, getattr(column.default, "arg", None)
    for mapper in SQLModel._sa_registry.mappers:
        if getattr(mapper.local_table, "name", None) == table_name:
            field = mapper.class_.model_fields.get(column_name)
            if field is None or field.is_required():
                return False, None
            if field.default_factory is not None:
                return True, field.default_factory()
            return True, field.default
    return False, None


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """Session that commits on success and rolls back on error."""
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
