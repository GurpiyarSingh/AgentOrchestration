"""REST API tests (FastAPI TestClient, ScriptedChatModel, in-memory DB, fake keyring)."""

from __future__ import annotations

import shutil
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from api.main import create_app
from core.config import Settings
from core.llm.fake import ScriptedChatModel
from core.services import build_services
from core.storage import create_db_engine

ROOT = Path(__file__).resolve().parents[2]
USAGE = {"input_tokens": 7, "output_tokens": 2, "total_tokens": 9}


@pytest.fixture
def models() -> dict[str, ScriptedChatModel]:
    return {}


@pytest.fixture
def client(settings: Settings, tmp_path: Path, models: dict[str, ScriptedChatModel]) -> Iterator[TestClient]:
    shutil.copytree(ROOT / "config", tmp_path / "config")  # tests may write prices; never touch the real file
    settings.config_dir = tmp_path / "config"
    settings.samples_dir = tmp_path / "samples"
    settings.workspaces_dir = tmp_path / "ws"
    services = build_services(
        settings, model_factory=lambda ref, agent: models[agent.name], db=create_db_engine(":memory:")
    )
    services.save_prefs(default_model="fake:model")
    with TestClient(create_app(services)) as c:
        yield c


def _tool(name: str, args: dict[str, Any]) -> AIMessage:
    return AIMessage("", tool_calls=[{"id": name, "name": name, "args": args}], usage_metadata=USAGE)


def test_swagger_and_spa_fallback(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    spec = client.get("/openapi.json").json()
    assert {"/api/builds", "/api/projects", "/api/agents", "/api/tools", "/api/settings"} <= set(spec["paths"])
    assert client.get("/some/ui/route").status_code == 200  # SPA index or "build the UI" page
    assert client.get("/api/nope").status_code == 404


def test_health_and_default_team(client: TestClient) -> None:
    assert client.get("/api/health").json()["agents"] >= 7
    roles = {a["name"]: (a["kind"], a["role"]) for a in client.get("/api/agents").json()}
    assert roles["requirements_analyst"] == ("llm", "requirements")
    assert roles["code_runner"] == ("step", "runner")
    assert {"architect", "test_writer", "code_generator", "code_reviewer", "assistant"} <= set(roles)


def test_agent_crud(client: TestClient) -> None:
    agent = {"name": "helper", "system_prompt": "Be brief.", "tools": ["builtin__calculator"]}
    assert client.put("/api/agents/helper", json=agent).status_code == 200
    assert "name: helper" in client.get("/api/agents/helper/yaml").text
    assert client.put("/api/agents/bad", json={"name": "bad", "tools": ["nope__x"]}).status_code == 422
    assert client.delete("/api/agents/helper").status_code == 204
    assert client.delete("/api/agents/architect").status_code == 204
    assert client.post("/api/agents/restore-defaults").json() == ["architect"]


def test_key_is_ui_only(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import core.services as svc_mod

    view = client.get("/api/settings").json()  # the fixture's env-style key must be ignored
    assert view["key"]["source"] == "missing" and view["key"]["configured"] is False

    async def fake_list(provider: str, settings: Any, *, chat_only: bool = True) -> list[str]:
        if settings.openai_api_key.get_secret_value() != "sk-valid-key-0000":
            raise ValueError("bad key")
        return ["gpt-a"]

    monkeypatch.setattr(svc_mod, "list_models", fake_list)
    assert client.post("/api/settings/openai-key", json={"key": "sk-nope"}).json()["ok"] is False
    assert client.post("/api/settings/openai-key", json={"key": "sk-valid-key-0000"}).json()["ok"] is True
    key = client.get("/api/settings").json()["key"]
    assert (key["source"], key["configured"], key["hint"]) == ("saved", True, "…0000")
    assert client.delete("/api/settings/openai-key").status_code == 204
    assert client.get("/api/settings").json()["key"]["source"] == "missing"


def test_preferences_and_prices(client: TestClient) -> None:
    r = client.put("/api/settings/preferences", json={"default_model": "openai:gpt-x", "show_all_models": True})
    assert r.status_code == 200 and r.json()["default_model"] == "openai:gpt-x"
    assert client.get("/api/settings").json()["default_model"] == "openai:gpt-x"
    assert client.put("/api/settings/preferences", json={"bogus": 1}).status_code == 422
    prices = {"models": {"openai:gpt-x": {"input_per_1m": 1.5, "output_per_1m": 6}}}
    assert client.put("/api/settings/prices", json=prices).json()["gpt-x"]["output_per_1m"] == 6


def test_tools_include_workspace_tools(client: TestClient) -> None:
    tools = {t["name"]: t for t in client.get("/api/tools").json()}
    assert tools["builtin__calculator"]["invokable"] is True
    assert tools["repo__write_file"]["source"] == "workspace" and tools["repo__write_file"]["invokable"] is False
    assert "code_generator" in tools["repo__write_file"]["used_by"]
    calc = client.post("/api/tools/builtin__calculator/invoke", json={"args": {"expression": "6*7"}}).json()
    assert calc["output"] == "42"


def test_chat_and_agent_run(client: TestClient, models: dict[str, ScriptedChatModel]) -> None:
    models["chat"] = ScriptedChatModel(script=[AIMessage("hello!", usage_metadata=USAGE)])
    r = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]}).json()
    assert r["text"] == "hello!" and r["input_tokens"] == 7
    models["assistant"] = ScriptedChatModel(script=[AIMessage("ok", usage_metadata=USAGE)])
    snap = client.post("/api/runs?wait=true", json={"agent": "assistant", "message": "hi"}).json()
    assert snap["status"] == "done"
    usage = client.get("/api/usage").json()
    assert usage["today"]["model_calls"] == 2 and usage["all_time"]["input_tokens"] == 14
    assert {"chat", "agent"} <= {r["kind"] for r in client.get("/api/runs").json()}


def test_projects_and_build_end_to_end(client: TestClient, models: dict[str, ScriptedChatModel]) -> None:
    assert client.get("/api/languages").json()[0]["id"] == "python"
    assert client.post("/api/projects", json={"name": "1bad", "language": "python"}).status_code == 400
    project = client.post("/api/projects", json={"name": "api-demo", "language": "python"}).json()
    files = [f["path"] for f in client.get(f"/api/projects/{project['id']}/files").json()]
    assert "pytest.ini" in files and "README.md" in files

    spec = {"title": "Adder", "summary": "Adds.", "acceptance_criteria": ["2+3=5"]}
    plan = {
        "approach": "fn",
        "files": [{"path": "adder.py", "kind": "source", "purpose": "add"}],
        "interfaces": "def add(a: int, b: int) -> int",
    }
    test_src = "from adder import add\n\ndef test_add():\n    assert add(2, 3) == 5\n"
    models["requirements_analyst"] = ScriptedChatModel(script=[_tool("Spec", spec)])
    models["architect"] = ScriptedChatModel(script=[_tool("Plan", plan)])
    models["test_writer"] = ScriptedChatModel(
        script=[
            _tool("repo__write_file", {"path": "tests/test_adder.py", "content": test_src}),
            AIMessage("tests written", usage_metadata=USAGE),
        ]
    )
    models["code_generator"] = ScriptedChatModel(
        script=[
            _tool(
                "repo__write_file",
                {"path": "adder.py", "content": "def add(a: int, b: int) -> int:\n    return a + b\n"},
            ),
            AIMessage("done", usage_metadata=USAGE),
        ]
    )
    models["code_reviewer"] = ScriptedChatModel(script=[_tool("Review", {"approved": True, "summary": "ok"})])

    snap = client.post(
        "/api/builds", json={"project_id": project["id"], "requirement": "Add two numbers please"}
    ).json()
    run_id = snap["run_id"]
    for _ in range(150):
        snap = client.get(f"/api/builds/{run_id}").json()
        if snap["status"] != "running":
            break
        time.sleep(0.1)
    assert snap["status"] == "done", snap
    assert snap["test_report"]["passed"] == 1 and snap["review"]["approved"] is True
    assert "return a + b" in client.get(f"/api/builds/{run_id}/file", params={"path": "adder.py"}).text
    assert "+def add" in client.get(f"/api/builds/{run_id}/diff").text
    assert client.get("/api/builds").json()[0]["title"] == "Adder"
    # written straight into the project folder; there is no merge step any more
    assert "adder.py" in [f["path"] for f in client.get(f"/api/projects/{project['id']}/files").json()]
    assert client.post(f"/api/builds/{run_id}/finish", json={"action": "merge"}).status_code in (404, 405)
    assert client.get("/api/builds/nope").status_code == 404
