"""Build pipeline: requirement → spec → plan → tests ∥ code → run → fix loop → review.

Orchestrated as a LangGraph `StateGraph` (ADR-015). Every model call and tool call is
traced under the pipeline's run; artifacts and a full snapshot are persisted so finished
builds can be inspected after a restart. Code is written only into a per-build git
worktree and merged only on request (ADR-008, ADR-011).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import operator
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from core.config import Settings
from core.llm.errors import friendly_error
from core.models import RunArtifactRecord, RunRecord, new_id
from core.pipeline.schemas import (
    PipelineRequest,
    PipelineSnapshot,
    PipelineSummary,
    Plan,
    Review,
    Spec,
    StageKind,
    StageRun,
)
from core.pricing import PriceTable
from core.runtime.agent_def import AgentDef, AgentStore
from core.runtime.agent_factory import build_agent
from core.tools.registry import ToolEntry
from core.tracing.callbacks import TraceCallbackHandler
from core.tracing.redact import Redactor
from core.tracing.tracer import Tracer
from core.workspace import worktree as wt
from core.workspace.git import GitError
from core.workspace.languages import LanguageProfile, get_profile
from core.workspace.projects import Project, ProjectStore
from core.workspace.repo_tools import make_repo_tools
from core.workspace.runner import TestReport, run_tests

ROLES = {
    "requirements": "requirements_analyst",
    "architecture": "architect",
    "tests": "test_writer",
    "code": "code_generator",
    "fix": "code_generator",
    "run": "code_runner",
    "review": "code_reviewer",
}
TITLES = {
    "requirements": "Understand requirements",
    "architecture": "Design",
    "tests": "Write unit tests",
    "code": "Generate code",
    "run": "Run tests",
    "fix": "Fix",
    "review": "Review code",
}
ModelFactory = Callable[[str, AgentDef], BaseChatModel]


class PipelineError(ValueError):
    """The build could not be started (missing project/agent/model)."""


class _State(TypedDict, total=False):
    fix_attempts: int
    review_rounds: int
    tests_ok: bool
    approved: bool
    feedback: str
    log: Annotated[list[str], operator.add]


class PipelineHandle:
    """Live state of a build (thread-safe snapshot)."""

    def __init__(self, snap: PipelineSnapshot, ws: wt.Workspace, profile: LanguageProfile, tracer: Tracer) -> None:
        self.snap = snap
        self.ws = ws
        self.profile = profile
        self.tracer = tracer
        self.task: asyncio.Task[None] | None = None
        self.git_lock = asyncio.Lock()
        self.stage_meta: dict[str, tuple[tuple[int, int, int, int], str]] = {}  # stage id -> (usage before, span)
        self._lock = threading.Lock()

    @property
    def run_id(self) -> str:
        """The build's run id."""
        return self.snap.run_id

    def set(self, **fields: Any) -> None:
        """Set snapshot fields under the lock."""

        def _fn(s: PipelineSnapshot) -> None:
            for k, v in fields.items():
                setattr(s, k, v)

        self.update(_fn)

    def update(self, fn: Callable[[PipelineSnapshot], None]) -> None:
        """Mutate the snapshot under the lock and refresh totals."""
        with self._lock:
            fn(self.snap)
            t = self.snap.totals
            t.model_calls, t.tool_calls = self.tracer.model_calls, self.tracer.tool_calls
            t.input_tokens, t.output_tokens = self.tracer.input_tokens, self.tracer.output_tokens
            t.cost_usd = self.tracer.cost_usd

    def snapshot(self) -> PipelineSnapshot:
        """Deep copy for readers."""
        with self._lock:
            return self.snap.model_copy(deep=True)


class PipelineService:
    """Starts, tracks and finishes builds."""

    def __init__(
        self,
        db: Engine,
        settings: Settings,
        agents: AgentStore,
        projects: ProjectStore,
        prices: PriceTable,
        model_factory: ModelFactory,
        redactor: Callable[[], Redactor],
    ) -> None:
        self.db = db
        self.settings = settings
        self.agents = agents
        self.projects = projects
        self.prices = prices
        self.model_factory = model_factory
        self.redactor = redactor
        self._handles: dict[str, PipelineHandle] = {}

    @property
    def author(self) -> tuple[str, str]:
        return (self.settings.git_author_name, self.settings.git_author_email)

    # ---- public API ---------------------------------------------------------------------

    async def start(self, req: PipelineRequest) -> PipelineHandle:
        """Validate, create the build worktree and launch the pipeline task."""
        project = self.projects.get(req.project_id)
        profile = get_profile(project.language)
        team = self._team()
        for stage, agent in team.items():
            if agent.kind == "llm" and not (req.model or agent.model or self.settings.default_model):
                raise PipelineError(f"No model for agent '{agent.name}' ({stage}). Choose a default model in Settings.")

        run_id = new_id()
        try:
            ws = wt.start_worktree(
                Path(project.path), self.settings.workspaces_dir / ".builds", run_id, project.base_branch
            )
        except GitError as exc:
            raise PipelineError(f"Could not create the build workspace: {exc}") from exc

        with Session(self.db) as s:
            s.add(
                RunRecord(
                    id=run_id,
                    kind="pipeline",
                    target_id=project.name,
                    input=req.requirement,
                    repo_id=project.id,
                    language_id=project.language,
                    branch=ws.branch,
                    worktree_path=ws.path,
                )
            )
            s.commit()

        snap = PipelineSnapshot(
            run_id=run_id,
            project_id=project.id,
            project_name=project.name,
            language=project.language,
            requirement=req.requirement,
            started_at=datetime.now(UTC),
            branch=ws.branch,
            base_branch=ws.base_branch,
            worktree=ws.path,
            repo_path=ws.repo,
        )
        tracer = Tracer(self.db, run_id, self.prices, self.redactor())
        handle = PipelineHandle(snap, ws, profile, tracer)
        self._handles[run_id] = handle
        self._persist(handle)
        graph = self._graph(handle, req, team, project)
        handle.task = asyncio.create_task(self._execute(handle, graph), name=f"pipeline-{run_id}")
        return handle

    def get(self, run_id: str) -> PipelineSnapshot:
        """Live snapshot, or the persisted one for builds from earlier sessions."""
        if (h := self._handles.get(run_id)) is not None:
            return h.snapshot()
        snap = self._load(run_id)
        if snap.status == "running":  # the process that ran it is gone
            snap.status, snap.error = (
                "failed",
                "Interrupted: the server stopped while this build was running.",
            )
        return snap

    def list_builds(self, project_id: str | None = None, limit: int = 50) -> list[PipelineSummary]:
        """Recent builds."""
        with Session(self.db) as s:
            q = select(RunRecord).where(RunRecord.kind == "pipeline")
            if project_id:
                q = q.where(RunRecord.repo_id == project_id)
            rows = s.exec(q.order_by(col(RunRecord.started_at).desc()).limit(limit)).all()
            ids = [r.id for r in rows]
        out = []
        for rid in ids:
            with contextlib.suppress(PipelineError):
                snap = self.get(rid)
                tr = snap.test_report
                out.append(
                    PipelineSummary(
                        run_id=snap.run_id,
                        project_id=snap.project_id,
                        project_name=snap.project_name,
                        title=snap.spec.title if snap.spec else snap.requirement[:80],
                        status=snap.status,
                        final_action=snap.final_action,
                        started_at=snap.started_at,
                        ended_at=snap.ended_at,
                        tests=f"{tr.passed}/{tr.total}" if tr else "-",
                        total_tokens=snap.totals.input_tokens + snap.totals.output_tokens,
                    )
                )
        return out

    async def cancel(self, run_id: str) -> bool:
        """Cancel a running build."""
        h = self._handles.get(run_id)
        if h is None or h.task is None or h.task.done():
            return False
        h.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await h.task
        return True

    async def finish(self, run_id: str, action: wt.FinishAction) -> PipelineSnapshot:
        """Merge / keep / discard the build branch (only when the build is not running)."""
        snap = self.get(run_id)
        if snap.status == "running":
            raise PipelineError("The build is still running; cancel it first.")
        if snap.final_action is not None:
            raise PipelineError(f"This build was already {snap.final_action}.")
        ws = wt.Workspace(repo=snap.repo_path, path=snap.worktree, branch=snap.branch, base_branch=snap.base_branch)
        title = snap.spec.title if snap.spec else "agent build"
        message = f"Merge agent build: {title}\n\nRequirement: {snap.requirement[:500]}\nRun: {run_id}"
        try:
            text = await asyncio.to_thread(wt.finish, ws, action, self.author, message)
        except GitError as exc:
            raise PipelineError(str(exc)) from exc
        final = {"merge": "merged", "keep": "kept", "discard": "discarded"}[action]
        snap.final_action, snap.message = final, text  # type: ignore[assignment]
        if (h := self._handles.get(run_id)) is not None:
            h.set(final_action=final, message=text)
            self._persist(h)
        else:
            self._save_snapshot(snap)
        with Session(self.db) as s:
            rec = s.get(RunRecord, run_id)
            if rec is not None:
                rec.final_action = final
                s.add(rec)
                s.commit()
        return snap

    def file_at(self, run_id: str, rel: str) -> str:
        """Content of a file produced by the build."""
        snap = self.get(run_id)
        if snap.final_action is None and Path(snap.worktree).is_dir():
            from core.workspace.projects import read_text

            return read_text(Path(snap.worktree), rel)
        ref = snap.base_branch if snap.final_action == "merged" else snap.branch
        try:
            return wt.show_file(Path(snap.repo_path), ref, rel)
        except GitError as exc:
            raise PipelineError(f"File not available: {rel}") from exc

    def diff(self, run_id: str) -> str:
        """Unified diff of the build."""
        snap = self.get(run_id)
        if snap.final_action in ("merged", "discarded"):
            return "(branch already merged or discarded)"
        try:
            return wt.diff(Path(snap.repo_path), snap.base_branch, snap.branch)
        except GitError as exc:
            raise PipelineError(str(exc)) from exc

    # ---- graph --------------------------------------------------------------------------

    def _team(self) -> dict[str, AgentDef]:
        team: dict[str, AgentDef] = {}
        for stage in ("requirements", "architecture", "tests", "code", "run", "review"):
            name = ROLES[stage]
            agent = self.agents.get(name)
            if agent is None:
                raise PipelineError(f"Default agent '{name}' is missing. Restore defaults on the Agents page.")
            team[stage] = agent
        return team

    def _graph(self, h: PipelineHandle, req: PipelineRequest, team: dict[str, AgentDef], project: Project) -> Any:
        profile = h.profile
        root = Path(h.ws.path)
        conventions = f"Project language conventions:\n{profile.conventions}"

        def model_for(agent: AgentDef) -> tuple[str, BaseChatModel]:
            ref = req.model or agent.model or self.settings.default_model
            return ref, self.model_factory(ref, agent)

        async def structured(stage: StageKind, agent: AgentDef, schema: type, user: str) -> Any:
            ref, model = model_for(agent)
            span, cfg = self._stage_begin(h, stage, agent, ref)
            try:
                result = await model.with_structured_output(schema).ainvoke(
                    [SystemMessage(agent.system_prompt + "\n\n" + conventions), HumanMessage(user)],
                    config=cfg,  # type: ignore[arg-type]
                )
            except BaseException as exc:
                self._stage_end(h, span, "failed", f"{type(exc).__name__}: {exc}")
                raise
            return span, result

        async def agentic(stage: StageKind, agent: AgentDef, user: str, tools: list[Any]) -> str:
            ref, model = model_for(agent)
            span, cfg = self._stage_begin(h, stage, agent, ref)
            graph = build_agent(
                agent,
                model,
                [ToolEntry(t, "repo") for t in tools],
                max_output_chars=self.settings.max_tool_output_chars,
            )
            try:
                out = await graph.ainvoke(
                    {"messages": [HumanMessage(conventions + "\n\n" + user)]},
                    config={**cfg, "recursion_limit": 200},
                )
            except BaseException as exc:
                self._stage_end(h, span, "failed", f"{type(exc).__name__}: {exc}")
                raise
            last = next((m for m in reversed(out["messages"]) if isinstance(m, AIMessage) and m.text), None)
            summary = last.text if last else "(no summary)"
            self._stage_end(h, span, "done", summary)
            return summary

        def spec_text() -> str:
            s = h.snap.spec
            assert s is not None
            crit = "\n".join(f"{i}. {c}" for i, c in enumerate(s.acceptance_criteria, 1))
            return (
                f"# Specification: {s.title}\n{s.summary}\n\nAcceptance criteria:\n{crit}\n\n"
                f"Assumptions:\n" + "\n".join(f"- {a}" for a in s.assumptions)
            )

        def plan_text() -> str:
            p = h.snap.plan
            assert p is not None
            files = "\n".join(f"- {f.path} ({f.kind}): {f.purpose}" for f in p.files)
            return f"# Plan\n{p.approach}\n\nFiles:\n{files}\n\nPublic interface:\n```\n{p.interfaces}\n```"

        async def n_requirements(state: _State) -> _State:
            span, spec = await structured(
                "requirements",
                team["requirements"],
                Spec,
                f"Project: {project.name} ({profile.name})\n\nRequirement:\n{req.requirement}",
            )
            h.update(lambda s: setattr(s, "spec", spec))
            self._stage_end(h, span, "done", f"{spec.title}: {len(spec.acceptance_criteria)} acceptance criteria")
            self._save_artifact(h, "spec", spec.model_dump())
            return {"log": ["spec"]}

        async def n_architecture(state: _State) -> _State:
            files = await asyncio.to_thread(make_repo_tools(root)[0].invoke, {})
            span, plan = await structured(
                "architecture",
                team["architecture"],
                Plan,
                f"{spec_text()}\n\nExisting files in the project:\n{files}",
            )
            h.update(lambda s: setattr(s, "plan", plan))
            self._stage_end(h, span, "done", f"{len(plan.files)} files planned")
            self._save_artifact(h, "plan", plan.model_dump())
            return {"log": ["plan"]}

        async def n_tests(state: _State) -> _State:
            tools = make_repo_tools(
                root,
                can_write=profile.is_test_path,
                can_read=lambda p: profile.is_test_path(p) or ("/" not in p and not p.endswith((".py", ".js", ".ts"))),
                write_rule=f"Test writers may only write under '{profile.test_dir}/'.",
            )
            await agentic("tests", team["tests"], f"{spec_text()}\n\n{plan_text()}\n\nWrite the unit tests now.", tools)
            return {"log": ["tests"]}

        async def n_code(state: _State) -> _State:
            tools = make_repo_tools(
                root,
                can_write=lambda p: not profile.is_test_path(p),
                write_rule="Implementation files only; tests are written by the test writer.",
            )
            await agentic(
                "code",
                team["code"],
                f"{spec_text()}\n\n{plan_text()}\n\nImplement all source files now.",
                tools,
            )
            return {"log": ["code"]}

        async def n_run(state: _State) -> _State:
            attempt = state.get("fix_attempts", 0)
            message = (
                "[test_writer, code_generator] tests and implementation"
                if attempt == 0 and not state.get("review_rounds")
                else f"[code_generator] fix #{attempt}"
            )
            async with h.git_lock:
                await asyncio.to_thread(wt.commit, h.ws, message, self.author)
            span, _cfg = self._stage_begin(h, "run", team["run"], None)
            report: TestReport = await asyncio.to_thread(run_tests, root, profile, self.settings.runner_timeout_seconds)
            h.update(lambda s: setattr(s, "test_report", report))
            files = await asyncio.to_thread(wt.changed_files, Path(h.ws.repo), h.ws.base_branch, h.ws.branch)
            h.update(lambda s: setattr(s, "files", files))
            verdict = "all passed" if report.ok else ("timed out" if report.timed_out else "failing")
            self._stage_end(
                h,
                span,
                "done" if report.ok else "failed",
                f"{report.passed}/{report.total} tests passed ({verdict}, {report.duration_s}s)",
                output=report.model_dump(exclude={"cases"}),
            )
            self._save_artifact(h, "test_report", report.model_dump())
            return {
                "tests_ok": report.ok,
                "feedback": report.failure_summary() if not report.ok else "",
                "log": ["run"],
            }

        async def n_fix(state: _State) -> _State:
            attempt = state.get("fix_attempts", 0) + 1
            h.update(lambda s: setattr(s, "fix_attempts", attempt))
            source = "review findings" if state.get("tests_ok") or state.get("review_rounds") else "failing tests"
            await agentic(
                "fix",
                team["code"],
                f"{spec_text()}\n\n{plan_text()}\n\nFix attempt {attempt} for {source}:\n\n{state.get('feedback', '')}"
                "\n\nFor each failure, first decide from the specification whether the implementation or the "
                "test is wrong (recompute expected values yourself), then fix the right one.",
                make_repo_tools(root),
            )
            return {"fix_attempts": attempt, "log": ["fix"]}

        async def n_review(state: _State) -> _State:
            rounds = state.get("review_rounds", 0) + 1
            h.update(lambda s: setattr(s, "review_rounds", rounds))
            diff = await asyncio.to_thread(wt.diff, Path(h.ws.repo), h.ws.base_branch, h.ws.branch, 60_000)
            report = h.snap.test_report
            tr = (
                report.failure_summary()
                if report and not report.ok
                else (f"All {report.total} tests passed." if report else "No test report.")
            )
            span, review = await structured(
                "review",
                team["review"],
                Review,
                f"{spec_text()}\n\nTest results: {tr}\n\nDiff:\n```diff\n{diff}\n```",
            )
            h.update(lambda s: setattr(s, "review", review))
            verdict = "approved" if review.approved else f"changes requested ({len(review.issues)} issues)"
            self._stage_end(h, span, "done" if review.approved else "failed", f"{verdict}: {review.summary}")
            self._save_artifact(h, "review", review.model_dump())
            actionable = [
                f"- [{i.severity}] {i.file}: {i.message}" for i in review.issues if i.severity in ("high", "medium")
            ]
            feedback = "Code review requested changes:\n" + "\n".join(actionable) if actionable else ""
            return {
                "approved": review.approved,
                "review_rounds": rounds,
                "feedback": feedback,
                "log": ["review"],
            }

        def after_run(state: _State) -> str:
            if not state.get("tests_ok") and state.get("fix_attempts", 0) < req.max_fix_attempts:
                return "fix"
            return "review"  # always reviewed: the reviewer may spot a wrong test the fixer missed

        def after_review(state: _State) -> str:
            if state.get("approved") or not state.get("feedback"):
                return END  # approved, or nothing actionable to fix
            if state.get("review_rounds", 0) > req.max_review_rounds:
                return END
            if state.get("fix_attempts", 0) >= req.max_fix_attempts + req.max_review_rounds:
                return END
            return "fix"

        g = StateGraph(_State)
        for name, fn in [
            ("requirements", n_requirements),
            ("architecture", n_architecture),
            ("tests", n_tests),
            ("code", n_code),
            ("run", n_run),
            ("fix", n_fix),
            ("review", n_review),
        ]:
            g.add_node(name, fn)
        g.add_edge(START, "requirements")
        g.add_edge("requirements", "architecture")
        g.add_edge("architecture", "tests")
        g.add_edge("architecture", "code")
        g.add_edge(["tests", "code"], "run")
        g.add_conditional_edges("run", after_run, ["review", "fix", END])
        g.add_edge("fix", "run")
        g.add_conditional_edges("review", after_review, ["fix", END])
        return g.compile()

    # ---- execution ------------------------------------------------------------------------

    async def _execute(self, h: PipelineHandle, graph: Any) -> None:
        try:
            await graph.ainvoke({"fix_attempts": 0, "review_rounds": 0, "log": []}, config={"recursion_limit": 60})
            snap = h.snapshot()
            ok = bool(snap.test_report and snap.test_report.ok and snap.review and snap.review.approved)
            status = "done" if ok else "needs_attention"
            msg = (
                "Tests pass and the reviewer approved. Merge it when you're happy."
                if ok
                else "Finished with open problems (see Tests / Review). You can still keep, merge or discard it."
            )
            h.set(status=status, message=msg)
        except asyncio.CancelledError:
            h.set(status="cancelled", message="Cancelled.")
            self._close(h)
            raise
        except Exception as exc:
            err = friendly_error(exc)
            h.set(status="failed", error=err)
        self._close(h)

    def _close(self, h: PipelineHandle) -> None:
        def _fn(s: PipelineSnapshot) -> None:
            s.ended_at = datetime.now(UTC)
            for st in s.stages:
                if st.status == "running":
                    st.status, st.ended_at = "failed", s.ended_at

        h.update(_fn)
        snap = h.snapshot()
        with Session(self.db) as s:
            rec = s.get(RunRecord, snap.run_id)
            if rec is not None:
                rec.status = snap.status
                rec.output = snap.message or snap.error
                rec.ended_at = snap.ended_at
                t = h.tracer
                rec.input_tokens, rec.output_tokens, rec.cost_usd = (
                    t.input_tokens,
                    t.output_tokens,
                    t.cost_usd,
                )
                rec.model_calls, rec.tool_calls = t.model_calls, t.tool_calls
                s.add(rec)
                s.commit()
        self._persist(h)

    def _stage_begin(
        self, h: PipelineHandle, stage: StageKind, agent: AgentDef, model_ref: str | None
    ) -> tuple[StageRun, dict[str, Any]]:
        attempt = 1 + sum(1 for s in h.snap.stages if s.stage == stage)
        st = StageRun(
            id=new_id(),
            stage=stage,
            agent=agent.name,
            title=TITLES[stage],
            status="running",
            attempt=attempt,
            started_at=datetime.now(UTC),
            model=model_ref,
        )
        before = (h.tracer.model_calls, h.tracer.tool_calls, h.tracer.input_tokens, h.tracer.output_tokens)
        st_span = h.tracer.start_span("agent", f"{stage}:{agent.name}", input={"stage": stage, "attempt": attempt})
        h.update(lambda s: s.stages.append(st))
        self._persist(h)
        cfg: dict[str, Any] = {"callbacks": [TraceCallbackHandler(h.tracer, st_span, default_model=model_ref)]}
        h.stage_meta[st.id] = (before, st_span)
        return st, cfg

    def _stage_end(self, h: PipelineHandle, st: StageRun, status: str, summary: str, output: Any = None) -> None:
        (mc, tc, ti, to), span_id = h.stage_meta.get(st.id, ((0, 0, 0, 0), ""))

        def _fn(s: PipelineSnapshot) -> None:
            st.status = status  # type: ignore[assignment]
            st.summary = summary[:4000]
            st.ended_at = datetime.now(UTC)
            st.model_calls = h.tracer.model_calls - mc
            st.tool_calls = h.tracer.tool_calls - tc
            st.input_tokens = h.tracer.input_tokens - ti
            st.output_tokens = h.tracer.output_tokens - to

        h.update(_fn)
        if span_id:
            h.tracer.end_span(
                span_id,
                output=output if output is not None else summary,
                error=None if status != "failed" or st.stage in ("run", "review") else summary,
            )
        self._persist(h)

    # ---- persistence ------------------------------------------------------------------------

    def _save_artifact(self, h: PipelineHandle, name: str, content: Any) -> None:
        step = sum(1 for s in h.snap.stages)
        with Session(self.db) as s:
            s.add(
                RunArtifactRecord(
                    run_id=h.snap.run_id, name=name, content_json=json.dumps(content, default=str), step=step
                )
            )
            s.commit()

    def _persist(self, h: PipelineHandle) -> None:
        self._save_snapshot(h.snapshot())

    def _save_snapshot(self, snap: PipelineSnapshot) -> None:
        with Session(self.db) as s:
            rec = s.exec(
                select(RunArtifactRecord).where(
                    RunArtifactRecord.run_id == snap.run_id, RunArtifactRecord.name == "snapshot"
                )
            ).first()
            rec = rec or RunArtifactRecord(run_id=snap.run_id, name="snapshot", content_json="{}")
            rec.content_json = snap.model_dump_json()
            rec.ts = datetime.now(UTC)
            s.add(rec)
            s.commit()

    def _load(self, run_id: str) -> PipelineSnapshot:
        with Session(self.db) as s:
            rec = s.exec(
                select(RunArtifactRecord).where(
                    RunArtifactRecord.run_id == run_id, RunArtifactRecord.name == "snapshot"
                )
            ).first()
            if rec is None:
                raise PipelineError(f"Build '{run_id}' not found.")
            return PipelineSnapshot.model_validate_json(rec.content_json)
