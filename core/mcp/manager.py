"""MCP server lifecycle: persisted configs, persistent sessions, tool registration (ADR-005, ADR-016).

Each connected server runs in its own long-lived asyncio task that owns the MCP session
(the MCP client's task groups must be entered and exited in the same task). Its tools are
registered in the tool registry as `<server>__<tool>`, so agents can use them like any
other tool. Env/header values are secrets: they live in the OS credential store, and only
their names are stored in SQLite.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
from datetime import UTC, datetime
from typing import Any, Literal

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from pydantic import BaseModel, Field
from sqlalchemy import Engine
from sqlmodel import Session, select

from core.mcp.config import McpServerConfig, namespaced_tool_name
from core.models import McpServer
from core.secrets import SecretStore
from core.tools.registry import ToolRegistry

Status = Literal["disconnected", "connecting", "connected", "error"]
CONNECT_TIMEOUT_S = 90


class McpToolInfo(BaseModel):
    name: str
    original_name: str
    description: str
    read_only: bool | None = None
    destructive: bool | None = None


class McpServerView(BaseModel):
    """A server as shown in the UI/API (secret values never included)."""

    name: str
    transport: str
    command: str | None
    args: list[str]
    url: str | None
    env_keys: list[str]
    header_keys: list[str]
    enabled: bool
    status: Status
    error: str | None = None
    tools: list[McpToolInfo] = Field(default_factory=list)
    connected_at: datetime | None = None


class McpError(ValueError):
    """Invalid MCP request (unknown server, bad config, connection failure)."""


class _Conn:
    def __init__(self) -> None:
        self.task: asyncio.Task[None] | None = None
        self.stop = asyncio.Event()
        self.status: Status = "disconnected"
        self.error: str | None = None
        self.tools: list[McpToolInfo] = []
        self.registered: list[str] = []
        self.connected_at: datetime | None = None


class MCPManager:
    """Owns all MCP server connections for this process."""

    def __init__(self, db: Engine, registry: ToolRegistry, secrets: SecretStore) -> None:
        self.db = db
        self.registry = registry
        self.secrets = secrets
        self._conns: dict[str, _Conn] = {}

    # ---- configs ----------------------------------------------------------------------

    def _secret_key(self, server: str, kind: str, key: str) -> str:
        return f"mcp/{server}/{kind}/{key}"

    def list_configs(self) -> list[McpServerConfig]:
        with Session(self.db) as s:
            rows = s.exec(select(McpServer).order_by(McpServer.name)).all()
            return [self._config_from(r) for r in rows]

    def get_config(self, name: str) -> McpServerConfig:
        with Session(self.db) as s:
            rec = s.exec(select(McpServer).where(McpServer.name == name)).first()
            if rec is None:
                raise McpError(f"MCP server '{name}' not found.")
            return self._config_from(rec)

    def _config_from(self, r: McpServer) -> McpServerConfig:
        env_keys: list[str] = json.loads(r.env_refs_json or "[]") if r.env_refs_json.startswith("[") else []
        hdr_keys: list[str] = json.loads(r.headers_refs_json or "[]") if r.headers_refs_json.startswith("[") else []
        return McpServerConfig(
            name=r.name,
            transport="http" if r.transport == "http" else "stdio",
            command=r.command,
            args=json.loads(r.args_json or "[]"),
            url=r.url,
            enabled=r.enabled,
            env={k: self.secrets.get(self._secret_key(r.name, "env", k)) or "" for k in env_keys},
            headers={k: self.secrets.get(self._secret_key(r.name, "header", k)) or "" for k in hdr_keys},
        )

    def save_config(self, cfg: McpServerConfig, *, keep_existing_secrets: bool = True) -> McpServerConfig:
        """Create or update. Empty env/header values keep the stored secret when updating."""
        try:
            cfg.validate_complete()
        except ValueError as e:
            raise McpError(str(e)) from e
        with Session(self.db) as s:
            rec = s.exec(select(McpServer).where(McpServer.name == cfg.name)).first()
            old_env = set(json.loads(rec.env_refs_json)) if rec and rec.env_refs_json.startswith("[") else set()
            old_hdr = set(json.loads(rec.headers_refs_json)) if rec and rec.headers_refs_json.startswith("[") else set()
            rec = rec or McpServer(name=cfg.name, transport=cfg.transport)
            rec.transport, rec.command, rec.url, rec.enabled = cfg.transport, cfg.command, cfg.url, cfg.enabled
            rec.args_json = json.dumps(cfg.args)
            rec.env_refs_json = json.dumps(sorted(cfg.env))
            rec.headers_refs_json = json.dumps(sorted(cfg.headers))
            s.add(rec)
            s.commit()
        for kind, values, old in (("env", cfg.env, old_env), ("header", cfg.headers, old_hdr)):
            for k, v in values.items():
                if v or not keep_existing_secrets:
                    self.secrets.set(self._secret_key(cfg.name, kind, k), v)
            for k in old - set(values):
                self.secrets.delete(self._secret_key(cfg.name, kind, k))
        return self.get_config(cfg.name)

    async def delete(self, name: str) -> None:
        cfg = self.get_config(name)
        await self.disconnect(name)
        for k in cfg.env:
            self.secrets.delete(self._secret_key(name, "env", k))
        for k in cfg.headers:
            self.secrets.delete(self._secret_key(name, "header", k))
        with Session(self.db) as s:
            rec = s.exec(select(McpServer).where(McpServer.name == name)).first()
            if rec is not None:
                s.delete(rec)
                s.commit()
        self._conns.pop(name, None)

    # ---- connections ------------------------------------------------------------------

    def view(self, name: str) -> McpServerView:
        cfg = self.get_config(name)
        c = self._conns.get(name) or _Conn()
        return McpServerView(
            name=cfg.name,
            transport=cfg.transport,
            command=cfg.command,
            args=cfg.args,
            url=cfg.url,
            env_keys=sorted(cfg.env),
            header_keys=sorted(cfg.headers),
            enabled=cfg.enabled,
            status=c.status,
            error=c.error,
            tools=c.tools,
            connected_at=c.connected_at,
        )

    def views(self) -> list[McpServerView]:
        return [self.view(c.name) for c in self.list_configs()]

    def connected_count(self) -> int:
        return sum(1 for c in self._conns.values() if c.status == "connected")

    def _connection(self, cfg: McpServerConfig) -> dict[str, Any]:
        if cfg.transport == "http":
            conn: dict[str, Any] = {"transport": "streamable_http", "url": cfg.url}
            if any(cfg.headers.values()):
                conn["headers"] = {k: v for k, v in cfg.headers.items() if v}
            return conn
        command = cfg.command or ""
        resolved = shutil.which(command) or command  # npx -> npx.cmd on Windows
        conn = {"transport": "stdio", "command": resolved, "args": list(cfg.args)}
        env = {k: v for k, v in cfg.env.items() if v}
        if env:
            conn["env"] = env
        return conn

    async def connect(self, name: str) -> McpServerView:
        """(Re)connect a server and register its tools. Waits until connected or failed."""
        cfg = self.get_config(name)
        await self.disconnect(name)
        if cfg.transport == "stdio" and not shutil.which(cfg.command or ""):
            c = self._conns.setdefault(name, _Conn())
            c.status, c.error = "error", f"Command not found: '{cfg.command}'. Is it installed and on PATH?"
            return self.view(name)
        c = _Conn()
        c.status = "connecting"
        self._conns[name] = c
        ready: asyncio.Future[list[BaseTool]] = asyncio.get_running_loop().create_future()
        c.task = asyncio.create_task(self._run(cfg, c, ready), name=f"mcp-{name}")
        try:
            tools = await asyncio.wait_for(asyncio.shield(ready), CONNECT_TIMEOUT_S)
        except TimeoutError:
            await self.disconnect(name)
            c.status, c.error = "error", f"Timed out after {CONNECT_TIMEOUT_S}s while starting the server."
            self._conns[name] = c
            return self.view(name)
        except Exception as e:  # connection failure: keep the reason for the UI
            c.status, c.error = "error", _friendly(e)
            return self.view(name)
        self._register(name, c, tools)
        c.status, c.error, c.connected_at = "connected", None, datetime.now(UTC)
        return self.view(name)

    async def _run(self, cfg: McpServerConfig, c: _Conn, ready: asyncio.Future[list[BaseTool]]) -> None:
        client = MultiServerMCPClient({cfg.name: self._connection(cfg)})  # type: ignore[dict-item]
        try:
            async with client.session(cfg.name) as session:
                tools = await load_mcp_tools(session, server_name=cfg.name)
                if not ready.done():
                    ready.set_result(tools)
                await c.stop.wait()
        except BaseException as e:
            if not ready.done():
                ready.set_exception(e if isinstance(e, Exception) else RuntimeError(str(e)))
            elif not c.stop.is_set():  # the server died while connected
                c.status, c.error = "error", _friendly(e)
                self._unregister(c)
            if isinstance(e, asyncio.CancelledError):
                raise

    def _register(self, server: str, c: _Conn, tools: list[BaseTool]) -> None:
        self._unregister(c)
        for t in tools:
            meta = t.metadata or {}
            original = t.name
            t.name = namespaced_tool_name(server, original)
            destructive = meta.get("destructiveHint")
            read_only = meta.get("readOnlyHint")
            self.registry.register(
                t, "mcp", server=server, requires_approval=bool(destructive) and not read_only, replace=True
            )
            c.registered.append(t.name)
            c.tools.append(
                McpToolInfo(
                    name=t.name,
                    original_name=original,
                    description=t.description or "",
                    read_only=read_only,
                    destructive=destructive,
                )
            )

    def _unregister(self, c: _Conn) -> None:
        for n in c.registered:
            self.registry.unregister(n)
        c.registered, c.tools = [], []

    async def disconnect(self, name: str) -> None:
        c = self._conns.get(name)
        if c is None:
            return
        c.stop.set()
        if c.task is not None and not c.task.done():
            try:
                await asyncio.wait_for(c.task, 10)
            except TimeoutError, asyncio.CancelledError, Exception:
                c.task.cancel()
                with contextlib.suppress(BaseException):
                    await c.task
        self._unregister(c)
        c.status, c.error, c.connected_at = "disconnected", None, None

    async def connect_enabled(self) -> None:
        """Connect every enabled server (startup)."""
        await asyncio.gather(*(self.connect(c.name) for c in self.list_configs() if c.enabled), return_exceptions=True)

    async def shutdown(self) -> None:
        await asyncio.gather(*(self.disconnect(n) for n in list(self._conns)), return_exceptions=True)


def _friendly(e: BaseException) -> str:
    """Unwrap exception groups from the MCP client into a short message."""
    inner: BaseException = e
    while isinstance(inner, BaseExceptionGroup) and inner.exceptions:
        inner = inner.exceptions[0]
    msg = str(inner) or type(inner).__name__
    if "Connection closed" in msg or isinstance(inner, EOFError):
        return (
            "The server process exited during startup. Check the command, arguments and required environment variables."
        )
    return f"{type(inner).__name__}: {msg}"[:500]
