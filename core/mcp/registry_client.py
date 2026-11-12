"""Search the official public MCP Registry (registry.modelcontextprotocol.io) and turn entries into draft configs."""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field

from core.mcp.config import McpServerConfig

REGISTRY_URL = "https://registry.modelcontextprotocol.io/v0/servers"


class EnvVarSpec(BaseModel):
    name: str
    description: str = ""
    required: bool = False
    secret: bool = False
    default: str | None = None


class RegistryEntry(BaseModel):
    """A server from the public registry, plus a ready-to-edit draft config."""

    name: str
    title: str
    description: str
    version: str = ""
    repository: str | None = None
    kind: str  # "npm" | "pypi" | "oci" | "remote" | ...
    draft: McpServerConfig
    env_vars: list[EnvVarSpec] = Field(default_factory=list)
    supported: bool = True
    note: str = ""


class RegistryError(RuntimeError):
    """The registry could not be reached or returned something unexpected."""


def _short_name(full: str) -> str:
    """'io.github.owner/server-name' → 'server-name' (valid config name)."""
    base = full.split("/")[-1] or full
    base = "".join(c if c.isalnum() or c in "-_." else "-" for c in base).strip("-.")
    if len(base) < 2 or not base[0].isalpha():
        base = "mcp-" + base
    return base[:49]


def entry_from_server(s: dict[str, Any]) -> RegistryEntry:
    """Map one registry `server` object to a RegistryEntry."""
    full = s.get("name", "server")
    short = _short_name(full)
    common = dict(
        name=full,
        title=s.get("title") or short,
        description=s.get("description") or "",
        version=s.get("version") or "",
        repository=(s.get("repository") or {}).get("url"),
    )
    for pkg in s.get("packages") or []:
        kind = pkg.get("registryType", "")
        ident = pkg.get("identifier", "")
        envs = [
            EnvVarSpec(
                name=e.get("name", ""),
                description=e.get("description", ""),
                required=bool(e.get("isRequired")),
                secret=bool(e.get("isSecret")),
                default=e.get("default"),
            )
            for e in pkg.get("environmentVariables") or []
            if e.get("name")
        ]
        transport = (pkg.get("transport") or {}).get("type", "stdio")
        if transport != "stdio":
            continue
        if kind == "npm":
            ver = pkg.get("version")
            draft = McpServerConfig(
                name=short, transport="stdio", command="npx", args=["-y", f"{ident}@{ver}" if ver else ident]
            )
        elif kind == "pypi":
            ver = pkg.get("version")
            draft = McpServerConfig(
                name=short, transport="stdio", command="uvx", args=[f"{ident}=={ver}" if ver else ident]
            )
        elif kind == "oci":
            draft = McpServerConfig(name=short, transport="stdio", command="docker", args=["run", "-i", "--rm", ident])
        else:
            continue
        for arg in pkg.get("packageArguments") or []:
            if arg.get("type") == "positional" and arg.get("value"):
                draft.args.append(str(arg["value"]))
        draft.env = {e.name: e.default or "" for e in envs}
        note = {
            "npm": "Runs with npx (needs Node.js).",
            "pypi": "Runs with uvx (needs uv).",
            "oci": "Runs in Docker (needs Docker Desktop).",
        }[kind]
        return RegistryEntry(**common, kind=kind, draft=draft, env_vars=envs, note=note)
    for remote in s.get("remotes") or []:
        if remote.get("type") in ("streamable-http", "http") and remote.get("url"):
            headers = {h.get("name", ""): "" for h in remote.get("headers") or [] if h.get("name")}
            draft = McpServerConfig(name=short, transport="http", url=remote["url"], headers=headers)
            envs = [
                EnvVarSpec(
                    name=h.get("name", ""),
                    description=h.get("description", ""),
                    required=bool(h.get("isRequired")),
                    secret=bool(h.get("isSecret", True)),
                )
                for h in remote.get("headers") or []
                if h.get("name")
            ]
            return RegistryEntry(**common, kind="remote", draft=draft, env_vars=envs, note="Remote server over HTTP.")
    draft = McpServerConfig(name=short, transport="stdio", command="")
    return RegistryEntry(
        **common, kind="unknown", draft=draft, supported=False, note="No supported install method (needs manual setup)."
    )


def parse_registry_response(data: dict[str, Any]) -> list[RegistryEntry]:
    """Latest version of each server only."""
    seen: dict[str, RegistryEntry] = {}
    for item in data.get("servers") or []:
        s = item.get("server") or {}
        meta = (item.get("_meta") or {}).get("io.modelcontextprotocol.registry/official") or {}
        if meta.get("status") not in (None, "active"):
            continue
        try:
            entry = entry_from_server(s)
        except ValueError:  # malformed public entry: skip it, never fail the whole search
            continue
        if entry.name not in seen or meta.get("isLatest"):
            seen[entry.name] = entry
    return list(seen.values())


async def search_registry(
    query: str, limit: int = 30, transport: httpx.AsyncBaseTransport | None = None
) -> list[RegistryEntry]:
    """Search the public registry by name/description."""
    params: dict[str, str | int] = {"limit": min(max(limit * 3, 30), 100)}
    if query.strip():
        params["search"] = query.strip()
    try:
        async with httpx.AsyncClient(
            transport=transport, timeout=20, headers={"User-Agent": "codeloom-mcp-client"}
        ) as client:
            resp = await client.get(REGISTRY_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        raise RegistryError(f"Could not reach the MCP Registry: {type(e).__name__}.") from e
    except ValueError as e:
        raise RegistryError("The MCP Registry returned an unexpected response.") from e
    return parse_registry_response(data)[:limit]
