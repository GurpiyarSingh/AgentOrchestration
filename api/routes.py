"""All REST routes, under /api (grouped by tag in Swagger)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import PlainTextResponse

from api.deps import S
from api.schemas import (
    AgentYaml,
    ChatRequest,
    ChatResponse,
    FinishRequest,
    Health,
    KeyRequest,
    PickFolderRequest,
    PickFolderResult,
    PricesBody,
    ProjectCreate,
    RunRequest,
    RunSummary,
    SettingsView,
    TokenRequest,
    ToolFlags,
    ToolInfo,
    ToolInvokeRequest,
    UsageReport,
)
from core.llm.errors import friendly_error
from core.llm.models import list_models
from core.pipeline.schemas import PipelineRequest, PipelineSnapshot, PipelineSummary
from core.prefs import UserPrefs
from core.pricing import ModelPrice
from core.runtime.agent_def import AgentDef, AgentDefError
from core.runtime.run_service import RunError, RunSnapshot
from core.services import GITHUB_TOKEN, KeyCheck
from core.tools.registry import ToolInvocation, UnknownToolError
from core.tracing.queries import SpanNode, get_run, list_runs, span_tree, start_of_local_day, usage_summary
from core.workspace.folders import FolderListing, FolderPickerError, list_folders, pick_folder_native
from core.workspace.languages import LanguageInfo, language_infos
from core.workspace.projects import FileEntry, Project, list_tree, read_text
from core.workspace.repo_tools import make_repo_tools

router = APIRouter(prefix="/api")
REPO_TOOL_USERS = {
    "repo__list_files": ["test_writer", "code_generator"],
    "repo__read_file": ["test_writer", "code_generator"],
    "repo__write_file": ["test_writer", "code_generator"],
    "repo__delete_file": ["code_generator"],
}


def _404(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, what)


# ---- system ----------------------------------------------------------------------------------


@router.get("/health", tags=["system"])
def health(s: S) -> Health:
    """Service status and counts."""
    return Health(
        openai_configured=s.settings.openai_configured,
        default_model=s.settings.default_model,
        agents=len(s.agents.list_all()),
        tools=len(s.tools.entries()),
        projects=len(s.projects.list_all()),
    )


@router.get("/usage", tags=["system"])
def usage(s: S) -> UsageReport:
    """Model calls, tool calls, tokens and cost: today (local time) and all time."""
    return UsageReport(today=usage_summary(s.db, since=start_of_local_day()), all_time=usage_summary(s.db))


@router.get("/models", tags=["system"])
async def models(s: S, all: bool | None = None) -> list[str]:
    """Models available to the saved API key (chat models unless `all` or the show-all preference)."""
    chat_only = not (all if all is not None else s.prefs.load().show_all_models)
    try:
        return await list_models("openai", s.settings, chat_only=chat_only)
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, friendly_error(exc)) from exc


@router.post("/system/pick-folder", tags=["system"])
async def pick_folder(body: PickFolderRequest) -> PickFolderResult:
    """Open the native folder dialog on this machine and return the chosen folder (local use only)."""
    import asyncio

    try:
        path = await asyncio.to_thread(pick_folder_native, body.title, body.initial)
    except FolderPickerError as exc:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, str(exc)) from exc
    return PickFolderResult(path=path, cancelled=path is None,
                            is_git=path is not None and (Path(path) / ".git").exists())


@router.get("/system/folders", tags=["system"])
def folders(path: str | None = None) -> FolderListing:
    """List sub-folders (drives when no path) for the in-app folder browser; git repos are flagged."""
    try:
        return list_folders(path)
    except FileNotFoundError as exc:
        raise _404(str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc


@router.get("/languages", tags=["system"])
def languages() -> list[LanguageInfo]:
    """Supported project languages and whether their toolchain is installed."""
    return language_infos()


# ---- settings --------------------------------------------------------------------------------


@router.get("/settings", tags=["settings"])
def get_settings_view(s: S) -> SettingsView:
    """Current settings (never returns secrets)."""
    return SettingsView(
        key=s.key_status(),
        prefs=s.prefs.load(),
        default_model=s.settings.default_model,
        cheap_model=s.settings.cheap_model,
        git_author_name=s.settings.git_author_name,
        git_author_email=s.settings.git_author_email,
        github_token_set=s.secrets.get(GITHUB_TOKEN) is not None,
        data_dir=str(s.settings.app_data_dir.resolve()),
        workspaces_dir=str(s.settings.workspaces_dir.resolve()),
        runner_timeout_s=s.settings.runner_timeout_seconds,
    )


@router.post("/settings/openai-key", tags=["settings"])
async def set_openai_key(body: KeyRequest, s: S) -> KeyCheck:
    """Verify an OpenAI key and (by default) save it to the OS credential store."""
    return await (s.save_openai_key(body.key) if body.save else s.verify_openai_key(body.key))


@router.delete("/settings/openai-key", tags=["settings"], status_code=status.HTTP_204_NO_CONTENT)
def delete_openai_key(s: S) -> None:
    """Remove the saved key."""
    s.remove_openai_key()


@router.put("/settings/preferences", tags=["settings"])
def put_preferences(body: dict[str, object], s: S) -> UserPrefs:
    """Update preferences (default_model, cheap_model, show_all_models, git_author_name, git_author_email)."""
    unknown = set(body) - set(UserPrefs.model_fields)
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown preferences: {', '.join(sorted(unknown))}")
    try:
        return s.save_prefs(**body)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.put("/settings/github-token", tags=["settings"], status_code=status.HTTP_204_NO_CONTENT)
def put_github_token(body: TokenRequest, s: S) -> None:
    """Save a (read-only) GitHub token to the OS credential store."""
    s.secrets.set(GITHUB_TOKEN, body.token.strip())


@router.delete("/settings/github-token", tags=["settings"], status_code=status.HTTP_204_NO_CONTENT)
def delete_github_token(s: S) -> None:
    """Remove the GitHub token."""
    s.secrets.delete(GITHUB_TOKEN)


@router.get("/settings/prices", tags=["settings"])
def get_prices(s: S) -> dict[str, ModelPrice]:
    """Price table (USD per 1M tokens)."""
    return dict(s.prices.models)


@router.put("/settings/prices", tags=["settings"])
def put_prices(body: PricesBody, s: S) -> dict[str, ModelPrice]:
    """Replace the price table."""
    s.save_prices({k.split(":", 1)[-1].strip(): v for k, v in body.models.items() if k.strip()})
    return dict(s.prices.models)


# ---- agents ----------------------------------------------------------------------------------


def _agent(s: S, name: str) -> AgentDef:
    agent = s.agents.get(name)
    if agent is None:
        raise _404(f"Agent '{name}' not found.")
    return agent


@router.get("/agents", tags=["agents"])
def list_agents(s: S) -> list[AgentDef]:
    """All agents."""
    return s.agents.list_all()


@router.get("/agents/{name}", tags=["agents"])
def get_agent(name: str, s: S) -> AgentDef:
    """One agent."""
    return _agent(s, name)


@router.put("/agents/{name}", tags=["agents"])
def put_agent(name: str, agent: AgentDef, s: S) -> AgentDef:
    """Create or replace an agent."""
    if agent.name != name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Body name must match the URL.")
    try:
        s.tools.resolve(agent.tools)
    except UnknownToolError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return s.agents.save(agent)


@router.delete("/agents/{name}", tags=["agents"], status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(name: str, s: S) -> None:
    """Delete an agent."""
    if not s.agents.delete(name):
        raise _404(f"Agent '{name}' not found.")


@router.get("/agents/{name}/yaml", tags=["agents"], response_class=PlainTextResponse)
def export_agent(name: str, s: S) -> str:
    """Export as YAML."""
    return _agent(s, name).to_yaml()


@router.post("/agents/import", tags=["agents"])
def import_agent(body: AgentYaml, s: S) -> AgentDef:
    """Import from YAML."""
    try:
        agent = AgentDef.from_yaml(body.yaml, source="request")
    except AgentDefError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    if s.agents.get(agent.name) and not body.overwrite:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Agent '{agent.name}' exists; set overwrite=true.")
    return s.agents.save(agent)


@router.post("/agents/restore-defaults", tags=["agents"])
def restore_defaults(s: S, overwrite: bool = False) -> list[str]:
    """Re-create the default agents from config/agents (overwrite=true resets edits)."""
    return s.agents.import_yaml_dir(s.settings.config_dir / "agents", overwrite=overwrite)


# ---- tools -----------------------------------------------------------------------------------


def _workspace_tools() -> list[ToolInfo]:

    out = []
    for t in make_repo_tools(Path(".")):
        schema = t.tool_call_schema
        out.append(
            ToolInfo(
                name=t.name,
                source="workspace",
                description=t.description,
                enabled=True,
                requires_approval=False,
                invokable=False,
                used_by=REPO_TOOL_USERS.get(t.name, []),
                args_schema=dict(schema.model_json_schema()) if hasattr(schema, "model_json_schema") else dict(schema),  # type: ignore[arg-type]
            )
        )
    return out


@router.get("/tools", tags=["tools"])
def list_tools(s: S) -> list[ToolInfo]:
    """Registry tools (invokable) plus the sandboxed workspace tools used by coding agents."""
    agents = s.agents.list_all()
    reg = [
        ToolInfo(
            name=e.name,
            source=e.source,
            description=e.tool.description,
            enabled=e.enabled,
            requires_approval=e.requires_approval,
            invokable=True,
            used_by=[a.name for a in agents if e.name in a.tools],
            args_schema=e.args_schema_json,
        )
        for e in s.tools.entries()
    ]
    return reg + _workspace_tools()


@router.patch("/tools/{name}", tags=["tools"])
def set_tool_flags(name: str, flags: ToolFlags, s: S) -> ToolInfo:
    """Enable/disable a tool or change whether it requires approval."""
    try:
        s.tools.set_flags(name, enabled=flags.enabled, requires_approval=flags.requires_approval)
        e = s.tools.get(name)
    except UnknownToolError as exc:
        raise _404(str(exc)) from exc
    return ToolInfo(
        name=e.name,
        source=e.source,
        description=e.tool.description,
        enabled=e.enabled,
        requires_approval=e.requires_approval,
        invokable=True,
        args_schema=e.args_schema_json,
    )


@router.post("/tools/{name}/invoke", tags=["tools"])
async def invoke_tool(name: str, body: ToolInvokeRequest, s: S) -> ToolInvocation:
    """Run a tool directly."""
    try:
        s.tools.get(name)
    except UnknownToolError as exc:
        raise _404(str(exc)) from exc
    return await s.tools.invoke(name, body.args, s.settings.max_tool_output_chars)


# ---- chat & runs -----------------------------------------------------------------------------


@router.post("/chat", tags=["runs"])
async def chat(body: ChatRequest, s: S) -> ChatResponse:
    """Chat with a model directly (recorded as a traced run)."""
    model = body.model or s.settings.default_model
    if not model:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a model (or set a default model in Settings).")
    try:
        run_id, reply = await s.runs.chat(model, body.messages)
    except RunError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, friendly_error(exc)) from exc
    return ChatResponse(
        run_id=run_id,
        text=reply.text,
        input_tokens=reply.input_tokens,
        output_tokens=reply.output_tokens,
        model=reply.model,
    )


@router.post("/runs", tags=["runs"], status_code=status.HTTP_202_ACCEPTED)
async def start_run(
    body: RunRequest, s: S, wait: bool = False, max_wait_s: Annotated[float, Query(gt=0, le=600)] = 120
) -> RunSnapshot:
    """Start an agent run (chat with tools). Poll `GET /api/runs/{id}` or pass `wait=true`."""
    agent = _agent(s, body.agent)
    try:
        handle = await s.runs.start(agent, body.history(), model_override=body.model)
    except RunError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if wait:
        try:
            return await s.runs.wait(handle.run_id, max_wait_s)
        except TimeoutError:
            pass
    return handle.snapshot()


@router.get("/runs", tags=["runs"])
def runs(s: S, limit: Annotated[int, Query(ge=1, le=500)] = 100) -> list[RunSummary]:
    """Recent runs of every kind (agent, chat, pipeline)."""
    return [RunSummary.of(r) for r in list_runs(s.db, limit)]


@router.get("/runs/{run_id}", tags=["runs"])
def run_detail(run_id: str, s: S) -> RunSnapshot | RunSummary:
    """Live state if running in this process, otherwise the stored summary."""
    if (h := s.runs.get(run_id)) is not None:
        return h.snapshot()
    rec = get_run(s.db, run_id)
    if rec is None:
        raise _404(f"Run '{run_id}' not found.")
    return RunSummary.of(rec)


@router.post("/runs/{run_id}/cancel", tags=["runs"])
async def cancel_run(run_id: str, s: S) -> dict[str, bool]:
    """Cancel a running agent run."""
    return {"cancelled": await s.runs.cancel(run_id)}


@router.get("/runs/{run_id}/spans", tags=["runs"])
def run_spans(run_id: str, s: S) -> list[SpanNode]:
    """Trace tree of a run."""
    if get_run(s.db, run_id) is None:
        raise _404(f"Run '{run_id}' not found.")
    return span_tree(s.db, run_id)


# ---- projects --------------------------------------------------------------------------------


@router.get("/projects", tags=["projects"])
def projects(s: S) -> list[Project]:
    """All projects."""
    return s.projects.list_all()


@router.post("/projects", tags=["projects"], status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, s: S) -> Project:
    """Create a new git project (with a language scaffold) or register an existing repo."""
    if body.mode == "existing":
        if not body.path:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "`path` is required for an existing repo.")
        return s.projects.add_existing(body.name, body.language, body.path)
    return s.projects.create(body.name, body.language, body.path)


@router.get("/projects/{project_id}", tags=["projects"])
def get_project(project_id: str, s: S) -> Project:
    """One project."""
    return s.projects.get(project_id)


@router.delete("/projects/{project_id}", tags=["projects"], status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, s: S) -> None:
    """Unregister a project (files stay on disk)."""
    s.projects.remove(project_id)


@router.get("/projects/{project_id}/files", tags=["projects"])
def project_files(project_id: str, s: S) -> list[FileEntry]:
    """Files in the project's main checkout."""

    return list_tree(Path(s.projects.get(project_id).path))


@router.get("/projects/{project_id}/file", tags=["projects"], response_class=PlainTextResponse)
def project_file(project_id: str, path: str, s: S) -> str:
    """File content from the project's main checkout."""

    return read_text(Path(s.projects.get(project_id).path), path)


# ---- builds (the agent team pipeline) ---------------------------------------------------------


@router.post("/builds", tags=["builds"], status_code=status.HTTP_202_ACCEPTED)
async def start_build(body: PipelineRequest, s: S) -> PipelineSnapshot:
    """Start a build: requirements → design → tests ∥ code → run → fix → review, on its own branch."""
    handle = await s.pipelines.start(body)
    return handle.snapshot()


@router.get("/builds", tags=["builds"])
def builds(
    s: S, project_id: str | None = None, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[PipelineSummary]:
    """Recent builds."""
    return s.pipelines.list_builds(project_id, limit)


@router.get("/builds/{run_id}", tags=["builds"])
def build_detail(run_id: str, s: S) -> PipelineSnapshot:
    """Full live state of a build: stages, spec, plan, tests, review, files, usage."""
    return s.pipelines.get(run_id)


@router.post("/builds/{run_id}/cancel", tags=["builds"])
async def cancel_build(run_id: str, s: S) -> dict[str, bool]:
    """Cancel a running build."""
    return {"cancelled": await s.pipelines.cancel(run_id)}


@router.post("/builds/{run_id}/finish", tags=["builds"])
async def finish_build(run_id: str, body: FinishRequest, s: S) -> PipelineSnapshot:
    """Merge the build into the project, keep its branch, or discard it."""
    return await s.pipelines.finish(run_id, body.action)


@router.get("/builds/{run_id}/file", tags=["builds"], response_class=PlainTextResponse)
def build_file(run_id: str, path: str, s: S) -> str:
    """Content of a file produced by the build."""
    return s.pipelines.file_at(run_id, path)


@router.get("/builds/{run_id}/diff", tags=["builds"], response_class=PlainTextResponse)
def build_diff(run_id: str, s: S) -> str:
    """Unified diff of the build against the project's base branch."""
    return s.pipelines.diff(run_id)
