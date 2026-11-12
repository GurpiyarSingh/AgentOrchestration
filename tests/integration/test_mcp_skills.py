"""MCP servers (real stdio fixture server) and skills, end to end without network."""

from __future__ import annotations

import shutil
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage

from api.main import create_app
from core.chat import ChatTurn
from core.config import Settings
from core.llm.fake import ScriptedChatModel
from core.mcp.config import McpServerConfig, namespaced_tool_name, parse_mcp_json
from core.mcp.registry_client import parse_registry_response
from core.runtime.agent_def import AgentDef
from core.secrets import MemoryKeyring, SecretStore
from core.services import Services, build_services
from core.skills.loader import SkillError, SkillStore, apply_skills
from core.storage import create_db_engine

ROOT = Path(__file__).resolve().parents[2]
ECHO = ROOT / "tests" / "fixtures" / "mcp_echo_server.py"
USAGE = {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}


@pytest.fixture
def models() -> dict[str, ScriptedChatModel]:
    return {}


@pytest.fixture
def services(settings: Settings, tmp_path: Path, models: dict[str, ScriptedChatModel]) -> Services:
    shutil.copytree(ROOT / "skills", tmp_path / "skills")
    settings.config_dir = ROOT / "config"
    settings.samples_dir = tmp_path / "samples"
    settings.skills_dir = tmp_path / "skills"
    settings.default_model = "fake:model"
    return build_services(
        settings,
        model_factory=lambda ref, agent: models[agent.name],
        db=create_db_engine(":memory:"),
        secrets=SecretStore(MemoryKeyring(), tmp_path),
    )


def echo_config(**kw: Any) -> McpServerConfig:
    return McpServerConfig(name="echo-test", command=sys.executable, args=[str(ECHO)], **kw)


# ---- MCP ---------------------------------------------------------------------------------------


async def test_mcp_connect_register_call_disconnect(services: Services, models: dict[str, ScriptedChatModel]) -> None:
    services.mcp.save_config(echo_config(env={"ECHO_TOKEN": "super-secret-value"}))
    view = await services.mcp.connect("echo-test")
    assert view.status == "connected", view.error
    names = {t.name: t for t in view.tools}
    assert set(names) == {"echo_test__add", "echo_test__wipe"}
    flags = {e.name: e.requires_approval for e in services.tools.entries() if e.source == "mcp"}
    assert flags == {"echo_test__add": False, "echo_test__wipe": True}  # destructive -> approval
    assert (await services.tools.invoke("echo_test__add", {"a": 40, "b": 2})).output == "42"

    # an agent can use the MCP tool
    models["mathy"] = ScriptedChatModel(
        script=[
            AIMessage(
                "", tool_calls=[{"id": "1", "name": "echo_test__add", "args": {"a": 2, "b": 3}}], usage_metadata=USAGE
            ),
            AIMessage("5", usage_metadata=USAGE),
        ]
    )
    h = await services.runs.start(
        AgentDef(name="mathy", tools=["echo_test__add"]), [ChatTurn(role="user", content="2+3")]
    )
    snap = await services.runs.wait(h.run_id, max_wait_s=30)
    assert snap.status == "done" and snap.timeline[0].tool_output and "5" in snap.timeline[0].tool_output

    # secrets never land in the database
    from sqlmodel import Session, select

    from core.models import McpServer

    with Session(services.db) as s:
        rec = s.exec(select(McpServer)).one()
    assert "super-secret-value" not in rec.model_dump_json() and "ECHO_TOKEN" in rec.env_refs_json
    assert services.mcp.get_config("echo-test").env == {"ECHO_TOKEN": "super-secret-value"}

    await services.mcp.disconnect("echo-test")
    assert not [e for e in services.tools.entries() if e.source == "mcp"]
    assert services.mcp.view("echo-test").status == "disconnected"
    await services.mcp.delete("echo-test")
    assert services.mcp.views() == []


async def test_mcp_connection_errors(services: Services) -> None:
    services.mcp.save_config(McpServerConfig(name="nope", command="not-a-real-command-xyz"))
    assert "Command not found" in ((await services.mcp.connect("nope")).error or "")
    services.mcp.save_config(McpServerConfig(name="crash", command=sys.executable, args=["-c", "raise SystemExit(3)"]))
    view = await services.mcp.connect("crash")
    assert view.status == "error" and view.error


def test_mcp_config_parsing_and_names() -> None:
    cfgs = parse_mcp_json(
        '{"mcpServers": {"filesystem": {"command": "npx", "args": ["-y", "pkg", "C:/x"]},'
        ' "remote api": {"url": "https://example.com/mcp", "headers": {"Authorization": "Bearer t"}}}}'
    )
    assert [(c.name, c.transport) for c in cfgs] == [("filesystem", "stdio"), ("remote-api", "http")]
    assert cfgs[1].headers == {"Authorization": "Bearer t"}
    with pytest.raises(ValueError, match="Not valid JSON"):
        parse_mcp_json("{oops")
    with pytest.raises(ValueError, match="command is required"):
        parse_mcp_json('{"mcpServers": {"x1": {"args": []}}}')
    assert namespaced_tool_name("GitHub Server", "search.issues") == "github_server__search_issues"
    assert len(namespaced_tool_name("a" * 40, "b" * 60)) == 64


def test_registry_mapping_and_dedupe() -> None:
    official = "io.modelcontextprotocol.registry/official"
    data = {
        "servers": [
            {
                "server": {
                    "name": "io.github.x/files",
                    "description": "old",
                    "version": "1.0",
                    "packages": [
                        {
                            "registryType": "npm",
                            "identifier": "files-mcp",
                            "version": "1.0",
                            "transport": {"type": "stdio"},
                        }
                    ],
                },
                "_meta": {official: {"status": "active", "isLatest": False}},
            },
            {
                "server": {
                    "name": "io.github.x/files",
                    "description": "Read files",
                    "version": "2.0",
                    "packages": [
                        {
                            "registryType": "npm",
                            "identifier": "files-mcp",
                            "version": "2.0",
                            "transport": {"type": "stdio"},
                            "environmentVariables": [
                                {"name": "ROOT", "isRequired": True},
                                {"name": "TOKEN", "isSecret": True},
                            ],
                        }
                    ],
                },
                "_meta": {official: {"status": "active", "isLatest": True}},
            },
            {
                "server": {
                    "name": "com.acme/search",
                    "packages": [{"registryType": "pypi", "identifier": "acme-search", "transport": {"type": "stdio"}}],
                }
            },
            {
                "server": {
                    "name": "ai.remote/thing",
                    "remotes": [{"type": "streamable-http", "url": "https://r.example/mcp"}],
                }
            },
            {"server": {"name": "x.y/deleted"}, "_meta": {official: {"status": "deleted"}}},
        ]
    }
    entries = {e.name: e for e in parse_registry_response(data)}
    assert set(entries) == {"io.github.x/files", "com.acme/search", "ai.remote/thing"}
    files = entries["io.github.x/files"]
    assert files.draft.command == "npx" and files.draft.args == ["-y", "files-mcp@2.0"]
    assert [(v.name, v.required, v.secret) for v in files.env_vars] == [("ROOT", True, False), ("TOKEN", False, True)]
    assert entries["com.acme/search"].draft.command == "uvx"
    remote = entries["ai.remote/thing"]
    assert remote.kind == "remote" and remote.draft.transport == "http" and remote.draft.url == "https://r.example/mcp"


# ---- skills ------------------------------------------------------------------------------------


def test_skill_store_crud_and_tools(tmp_path: Path) -> None:
    store = SkillStore(tmp_path / "skills")
    store.save("api-style", "How to design APIs.", "Use nouns for resources.")
    (tmp_path / "skills" / "api-style" / "examples.md").write_text("GET /users")
    skill = store.get("api-style")
    assert skill.description == "How to design APIs." and skill.files == ["examples.md"]
    with pytest.raises(SkillError):
        store.save("Bad Name", "x", "y")
    with pytest.raises(SkillError, match="description"):
        store.save("no-desc", "", "y")
    load, read = store.tools_for(["api-style"])
    assert "Use nouns" in load.invoke({"name": "api-style"}) and "examples.md" in load.invoke({"name": "api-style"})
    assert "not one of your skills" in load.invoke({"name": "other"})
    assert read.invoke({"name": "api-style", "path": "examples.md"}) == "GET /users"
    assert "not found" in read.invoke({"name": "api-style", "path": "../../etc/passwd"})
    agent, tools = apply_skills(AgentDef(name="writer", skills=["api-style"]), store)
    assert "skill__load" in agent.system_prompt and "api-style: How to design APIs." in agent.system_prompt
    assert len(tools) == 2
    store.delete("api-style")
    assert store.list_all() == []


async def test_agent_loads_skill_during_run(services: Services, models: dict[str, ScriptedChatModel]) -> None:
    models["tester"] = ScriptedChatModel(
        script=[
            AIMessage(
                "",
                tool_calls=[{"id": "s", "name": "skill__load", "args": {"name": "test-design"}}],
                usage_metadata=USAGE,
            ),
            AIMessage("I will use boundary values.", usage_metadata=USAGE),
        ]
    )
    agent = AgentDef(name="tester", skills=["test-design"])
    h = await services.runs.start(agent, [ChatTurn(role="user", content="plan tests")])
    snap = await services.runs.wait(h.run_id, max_wait_s=10)
    assert snap.status == "done"
    assert "Boundaries" in (snap.timeline[0].tool_output or "")
    first_call = models["tester"].calls[0]
    assert "test-design:" in str(first_call[0].content)  # skill advertised in the system prompt
    assert not any(isinstance(m, ToolMessage) for m in first_call)


# ---- API ---------------------------------------------------------------------------------------


@pytest.fixture
def client(services: Services) -> Iterator[TestClient]:
    with TestClient(create_app(services)) as c:
        yield c


def test_mcp_and_skills_api(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    body = echo_config().model_dump()
    view = client.put("/api/mcp/servers/echo-test", json=body).json()
    assert view["status"] == "connected" and len(view["tools"]) == 2
    tools = {t["name"]: t for t in client.get("/api/tools").json()}
    assert tools["echo_test__add"]["source"] == "mcp" and tools["echo_test__add"]["invokable"]
    assert client.get("/api/health").json()["mcp_connected"] == 1
    assert client.post("/api/mcp/servers/echo-test/disconnect").json()["status"] == "disconnected"
    assert client.delete("/api/mcp/servers/echo-test").status_code == 204
    assert client.post("/api/mcp/servers/ghost/connect").status_code == 404
    imported = client.post("/api/mcp/import", json={"json_text": '{"mcpServers": {"bad": {"url": "ftp://x"}}}'})
    assert imported.status_code == 400

    import api.routes_mcp_skills as r

    async def fake_search(q: str, limit: int = 30) -> list[Any]:
        return parse_registry_response(
            {
                "servers": [
                    {"server": {"name": "a.b/c", "remotes": [{"type": "streamable-http", "url": "https://x/mcp"}]}}
                ]
            }
        )

    monkeypatch.setattr(r, "search_registry", fake_search)
    assert client.get("/api/mcp/registry", params={"q": "c"}).json()[0]["kind"] == "remote"

    names = [s["name"] for s in client.get("/api/skills").json()]
    assert {"test-design", "code-review-checklist", "python-conventions"} <= set(names)
    assert (
        client.put("/api/skills/my-skill", json={"name": "my-skill", "description": "d", "body": "b"}).status_code
        == 200
    )
    agent = {"name": "skilled", "skills": ["my-skill"]}
    assert client.put("/api/agents/skilled", json=agent).status_code == 200
    assert client.put("/api/agents/bad", json={"name": "bad", "skills": ["ghost"]}).status_code == 422
    assert client.delete("/api/skills/my-skill").status_code == 204
    assert client.get("/api/agents/skilled").json()["skills"] == []
