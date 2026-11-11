"""End-to-end build pipeline with scripted agents, a real git repo and real pytest (no network)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from core.config import Settings
from core.llm.fake import ScriptedChatModel
from core.pipeline.schemas import PipelineRequest
from core.pipeline.service import PipelineError
from core.services import Services, build_services
from core.storage import create_db_engine
from core.tracing.queries import get_run, usage_summary
from core.workspace.git import git

ROOT = Path(__file__).resolve().parents[2]

SPEC = {
    "title": "Slugify",
    "summary": "Convert text to URL slugs.",
    "acceptance_criteria": ["lowercases text", "replaces spaces with hyphens"],
    "assumptions": ["ASCII only"],
    "out_of_scope": [],
}
PLAN = {
    "approach": "One function.",
    "files": [
        {"path": "slug.py", "kind": "source", "purpose": "slugify"},
        {"path": "tests/test_slug.py", "kind": "test", "purpose": "tests"},
    ],
    "interfaces": "def slugify(text: str) -> str: ...",
}
TESTS = "from slug import slugify\n\n\ndef test_lower():\n    assert slugify('Hello World') == 'hello-world'\n"
GOOD = "def slugify(text: str) -> str:\n    return '-'.join(text.lower().split())\n"
BAD = "def slugify(text: str) -> str:\n    return text\n"
USAGE = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}


def _tool(name: str, args: dict[str, Any], cid: str) -> AIMessage:
    return AIMessage("", tool_calls=[{"id": cid, "name": name, "args": args}], usage_metadata=USAGE)


def _write(path: str, content: str, cid: str) -> AIMessage:
    return _tool("repo__write_file", {"path": path, "content": content}, cid)


@pytest.fixture
def env(settings: Settings, tmp_path: Path) -> tuple[Services, dict[str, ScriptedChatModel]]:
    models: dict[str, ScriptedChatModel] = {}
    settings.config_dir = ROOT / "config"
    settings.samples_dir = tmp_path / "samples"
    settings.workspaces_dir = tmp_path / "ws"
    settings.default_model = "fake:model"
    services = build_services(
        settings, model_factory=lambda ref, agent: models[agent.name], db=create_db_engine(":memory:")
    )
    return services, models


def _team(models: dict[str, ScriptedChatModel], code_script: list[AIMessage], approved: bool = True) -> None:
    models["requirements_analyst"] = ScriptedChatModel(script=[_tool("Spec", SPEC, "s1")])
    models["architect"] = ScriptedChatModel(script=[_tool("Plan", PLAN, "p1")])
    models["test_writer"] = ScriptedChatModel(
        script=[_write("tests/test_slug.py", TESTS, "t1"), AIMessage("Wrote 1 test.", usage_metadata=USAGE)]
    )
    models["code_generator"] = ScriptedChatModel(script=code_script)
    review = {"approved": approved, "summary": "Looks good." if approved else "Bug.", "issues": []}
    models["code_reviewer"] = ScriptedChatModel(script=[_tool("Review", review, "r1")])


async def test_happy_path_build_merges_into_project(
    env: tuple[Services, dict[str, ScriptedChatModel]],
) -> None:
    services, models = env
    _team(models, [_write("slug.py", GOOD, "c1"), AIMessage("Implemented slugify.", usage_metadata=USAGE)])
    project = services.projects.create("demo", "python")

    handle = await services.pipelines.start(
        PipelineRequest(project_id=project.id, requirement="Make a slugify function")
    )
    assert handle.task is not None
    await handle.task
    snap = services.pipelines.get(handle.run_id)

    assert snap.status == "done", (snap.error, [(s.stage, s.status, s.summary) for s in snap.stages])
    assert [s.stage for s in snap.stages][:2] == ["requirements", "architecture"]
    assert {s.stage for s in snap.stages} >= {"tests", "code", "run", "review"}
    assert snap.spec and snap.spec.title == "Slugify"
    assert snap.test_report and snap.test_report.ok and snap.test_report.passed == 1
    assert snap.review and snap.review.approved
    assert sorted(snap.files) == ["slug.py", "tests/test_slug.py"]
    assert snap.totals.model_calls >= 6 and snap.totals.input_tokens > 0

    # the test writer never saw the implementation
    seen = " ".join(str(m.content) for call in models["test_writer"].calls for m in call)
    assert "join(text.lower()" not in seen

    # files are viewable before merging; the project checkout is untouched
    assert "slugify" in services.pipelines.file_at(handle.run_id, "slug.py")
    assert not (Path(project.path) / "slug.py").exists()

    done = await services.pipelines.finish(handle.run_id, "merge")
    assert done.final_action == "merged"
    assert (Path(project.path) / "slug.py").read_text() == GOOD
    log = git(Path(project.path), "log", "--oneline")
    assert "Merge agent build: Slugify" in log
    rec = get_run(services.db, handle.run_id)
    assert rec is not None and rec.kind == "pipeline" and rec.final_action == "merged"
    assert usage_summary(services.db).model_calls == snap.totals.model_calls

    with pytest.raises(PipelineError, match="already merged"):
        await services.pipelines.finish(handle.run_id, "discard")


async def test_failing_tests_trigger_fix_loop(env: tuple[Services, dict[str, ScriptedChatModel]]) -> None:
    services, models = env
    _team(
        models,
        [
            _write("slug.py", BAD, "c1"),
            AIMessage("v1", usage_metadata=USAGE),  # initial (buggy)
            _tool("repo__read_file", {"path": "tests/test_slug.py"}, "c2"),  # fix: read test
            _write("slug.py", GOOD, "c3"),
            AIMessage("fixed", usage_metadata=USAGE),
        ],
    )
    project = services.projects.create("demo2", "python")
    handle = await services.pipelines.start(
        PipelineRequest(project_id=project.id, requirement="Make a slugify function")
    )
    assert handle.task is not None
    await handle.task
    snap = services.pipelines.get(handle.run_id)

    stages = [(s.stage, s.status) for s in snap.stages]
    assert ("run", "failed") in stages and ("fix", "done") in stages
    assert stages.index(("run", "failed")) < stages.index(("fix", "done"))
    assert snap.status == "done" and snap.fix_attempts == 1
    # the fixer was told what failed
    fix_prompt = " ".join(str(m.content) for m in models["code_generator"].calls[2])
    assert "test_lower" in fix_prompt

    discarded = await services.pipelines.finish(handle.run_id, "discard")
    assert discarded.final_action == "discarded"
    assert "agents/" not in git(Path(project.path), "branch")


async def test_tests_never_pass_needs_attention(env: tuple[Services, dict[str, ScriptedChatModel]]) -> None:
    services, models = env
    _team(models, [_write("slug.py", BAD, "c1"), AIMessage("v1", usage_metadata=USAGE)])
    project = services.projects.create("demo3", "python")
    handle = await services.pipelines.start(
        PipelineRequest(project_id=project.id, requirement="Make a slugify function", max_fix_attempts=0)
    )
    assert handle.task is not None
    await handle.task
    snap = services.pipelines.get(handle.run_id)
    assert snap.status == "needs_attention"
    assert snap.test_report and not snap.test_report.ok and snap.test_report.failed == 1
    kept = await services.pipelines.finish(handle.run_id, "keep")
    assert kept.final_action == "kept" and "agents/" in git(Path(project.path), "branch")


async def test_start_requires_model(env: tuple[Services, dict[str, ScriptedChatModel]]) -> None:
    services, _ = env
    services.settings.default_model = ""
    project = services.projects.create("demo4", "python")
    with pytest.raises(PipelineError, match="No model"):
        await services.pipelines.start(PipelineRequest(project_id=project.id, requirement="Make a slugify function"))
