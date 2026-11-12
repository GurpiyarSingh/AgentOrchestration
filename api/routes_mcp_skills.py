"""REST routes for MCP servers and skills (under /api)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.deps import S
from core.mcp.config import McpServerConfig, parse_mcp_json
from core.mcp.manager import McpError, McpServerView
from core.mcp.registry_client import RegistryEntry, RegistryError, search_registry
from core.skills.loader import Skill, SkillError

router = APIRouter(prefix="/api")


def _err(exc: Exception) -> HTTPException:
    msg = str(exc)
    code = status.HTTP_404_NOT_FOUND if "not found" in msg.lower() else status.HTTP_400_BAD_REQUEST
    return HTTPException(code, msg)


# ---- MCP servers -------------------------------------------------------------------------------


class McpImportBody(BaseModel):
    json_text: str = Field(description='Contents of an mcp.json / claude_desktop_config.json ({"mcpServers": {...}})')
    connect: bool = True


@router.get("/mcp/servers", tags=["mcp"])
def mcp_servers(s: S) -> list[McpServerView]:
    """Configured MCP servers with live status and tools (secret values are never returned)."""
    return s.mcp.views()


@router.put("/mcp/servers/{name}", tags=["mcp"])
async def put_mcp_server(name: str, body: McpServerConfig, s: S, connect: bool = True) -> McpServerView:
    """Create or update a server. Empty env/header values keep previously saved secrets. Connects by default."""
    if body.name != name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Body name must match the URL.")
    try:
        s.mcp.save_config(body)
    except McpError as exc:
        raise _err(exc) from exc
    if connect and body.enabled:
        return await s.mcp.connect(name)
    await s.mcp.disconnect(name)
    return s.mcp.view(name)


@router.delete("/mcp/servers/{name}", tags=["mcp"], status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_server(name: str, s: S) -> None:
    """Disconnect and remove a server, including its saved secrets."""
    try:
        await s.mcp.delete(name)
    except McpError as exc:
        raise _err(exc) from exc


@router.post("/mcp/servers/{name}/connect", tags=["mcp"])
async def connect_mcp_server(name: str, s: S) -> McpServerView:
    """(Re)connect a server and register its tools."""
    try:
        return await s.mcp.connect(name)
    except McpError as exc:
        raise _err(exc) from exc


@router.post("/mcp/servers/{name}/disconnect", tags=["mcp"])
async def disconnect_mcp_server(name: str, s: S) -> McpServerView:
    """Disconnect a server; its tools are removed from agents until reconnected."""
    try:
        await s.mcp.disconnect(name)
        return s.mcp.view(name)
    except McpError as exc:
        raise _err(exc) from exc


@router.post("/mcp/import", tags=["mcp"])
async def import_mcp(body: McpImportBody, s: S) -> list[McpServerView]:
    """Import servers from an mcp.json / claude_desktop_config.json document."""
    try:
        configs = parse_mcp_json(body.json_text)
        for cfg in configs:
            s.mcp.save_config(cfg)
    except (ValueError, McpError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if body.connect:
        return [await s.mcp.connect(c.name) for c in configs if c.enabled]
    return [s.mcp.view(c.name) for c in configs]


@router.get("/mcp/registry", tags=["mcp"])
async def mcp_registry(q: str = "", limit: Annotated[int, Query(ge=1, le=60)] = 30) -> list[RegistryEntry]:
    """Search the official public MCP Registry (registry.modelcontextprotocol.io)."""
    try:
        return await search_registry(q, limit)
    except RegistryError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


# ---- skills ------------------------------------------------------------------------------------


class SkillBody(BaseModel):
    name: str
    description: str
    body: str = ""


@router.get("/skills", tags=["skills"])
def skills(s: S) -> list[Skill]:
    """All skills (SKILL.md folders)."""
    return s.skills.list_all()


@router.get("/skills/{name}", tags=["skills"])
def get_skill(name: str, s: S) -> Skill:
    """One skill with its instructions and reference files."""
    try:
        return s.skills.get(name)
    except SkillError as exc:
        raise _err(exc) from exc


@router.put("/skills/{name}", tags=["skills"])
def put_skill(name: str, body: SkillBody, s: S) -> Skill:
    """Create or update a skill (writes skills/<name>/SKILL.md)."""
    if body.name != name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Body name must match the URL.")
    try:
        return s.skills.save(name, body.description, body.body)
    except SkillError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.delete("/skills/{name}", tags=["skills"], status_code=status.HTTP_204_NO_CONTENT)
def delete_skill(name: str, s: S) -> None:
    """Delete a skill folder and remove it from agents that use it."""
    try:
        s.skills.delete(name)
    except SkillError as exc:
        raise _err(exc) from exc
    for agent in s.agents.list_all():
        if name in agent.skills:
            s.agents.save(agent.model_copy(update={"skills": [x for x in agent.skills if x != name]}))
