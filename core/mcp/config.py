"""MCP server configuration: shapes, validation and import from mcp.json-style files."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]{1,48}$")


class McpServerConfig(BaseModel):
    """How to reach one MCP server. Env/header *values* are secrets and stored outside the DB."""

    name: str
    transport: Literal["stdio", "http"] = "stdio"
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)  # values only in memory / secret store
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not _NAME_RE.match(v):
            raise ValueError("Name must be 2-49 characters: letters, digits, '.', '-' or '_', starting with a letter.")
        return v

    def validate_complete(self) -> None:
        """Raise ValueError if required fields for the transport are missing."""
        if self.transport == "stdio" and not (self.command or "").strip():
            raise ValueError("A command is required for a local (stdio) server, e.g. npx or uvx.")
        if self.transport == "http" and not (self.url or "").startswith(("http://", "https://")):
            raise ValueError("A http:// or https:// URL is required for a remote server.")


def tool_prefix(server_name: str) -> str:
    """Server name → tool-name prefix: lowercase letters, digits and '_'."""
    p = re.sub(r"[^a-z0-9]+", "_", server_name.lower()).strip("_")
    return (p or "mcp")[:24]


def namespaced_tool_name(server_name: str, tool_name: str) -> str:
    """`<prefix>__<tool>` limited to OpenAI's function-name rules (^[a-zA-Z0-9_-]{1,64}$)."""
    t = re.sub(r"[^a-zA-Z0-9_-]+", "_", tool_name)
    return f"{tool_prefix(server_name)}__{t}"[:64]


def parse_mcp_json(text: str) -> list[McpServerConfig]:
    """Parse a Claude Desktop / Cursor / VS Code style config: {"mcpServers": {name: {...}}} (or {"servers": ...})."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Not valid JSON: {e.msg} (line {e.lineno})") from e
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object.")
    servers: Any = data.get("mcpServers") or data.get("servers") or data
    if not isinstance(servers, dict) or not servers:
        raise ValueError('No servers found. Expected {"mcpServers": {"name": {...}}}.')
    out: list[McpServerConfig] = []
    for raw_name, spec in servers.items():
        if not isinstance(spec, dict):
            continue
        name = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(raw_name)).strip("-") or "server"
        if not name[0].isalpha():
            name = "mcp-" + name
        url = spec.get("url") or spec.get("serverUrl")
        cfg = McpServerConfig(
            name=name[:49],
            transport="http" if url else "stdio",
            command=spec.get("command"),
            args=[str(a) for a in spec.get("args") or []],
            env={str(k): str(v) for k, v in (spec.get("env") or {}).items()},
            url=url,
            headers={str(k): str(v) for k, v in (spec.get("headers") or {}).items()},
        )
        cfg.validate_complete()
        out.append(cfg)
    return out
