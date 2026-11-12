# Implementation Plan

This turns [PLAN.md](PLAN.md) (the *what* and *why*) into ordered, checkable tasks (the *how* and *in what order*).

- Rules every task must follow: [RULES.md](RULES.md)
- Environment setup: [SETUP.md](SETUP.md)
- Test strategy: [TESTING.md](TESTING.md)
- Security controls: [SECURITY.md](SECURITY.md)
- Decisions made so far: [DECISIONS.md](DECISIONS.md)

**Engine stack (ADR‑015):** LangChain chat models + tools, LangGraph agents (`create_agent`) and workflows (`StateGraph`), `langchain-mcp-adapters` for MCP, `AsyncSqliteSaver` for checkpoints. We build the registry, UI, tracing, repo sandbox, language profiles, and the dev‑team workflow.

---

## How to use this file

- Work **milestone by milestone**. Don't start a milestone until the previous one's exit criteria pass.
- Each task has an ID (`M2-T4`), the files it touches, and **acceptance criteria**. A task is done when its criteria pass *and* the [RULES.md § Definition of done](RULES.md#12-definition-of-done-per-task) checklist is met.
- Tick boxes in this file as you go (`- [x]`), in the same change as the work.
- If a task turns out wrong or too big, split or edit it here first, then build. If the change alters a design decision, add an entry to [DECISIONS.md](DECISIONS.md).

### Milestone overview

| Milestone | Goal | Exit demo | Est. |
|---|---|---|---|
| **M0** ✅ | Skeleton, config, storage, LangChain model factory, OpenAI hello | Streamlit app opens; Playground gets a reply from OpenAI | done |
| **M1** ✅ | Agent factory (`create_agent`), tools, tracing, Agents/Tools/Runs pages, REST API + Swagger | A custom agent uses 2 tools; the trace is visible | done |
| **M2** | MCP (adapters), Settings, Skills, Repositories, Language profiles | Public MCP server added from the registry; a coder agent writes a module + tests into a new repo branch | 3 days |
| **M3** | Workflow builder (LangGraph), patterns, message bus, Workflows page, dev team v1 | Supervisor + workers; the dev team builds a module end to end | 3 days |
| **M4** | Checkpoints, interrupts/HITL, dev team v2, A2A protocol | Dev team goes from request → approved spec → locally merged branch, with loops and gates | 3 days |
| **M5** | Hardening: budgets, Docker runner, memory, evals | Same demos, safer and measured | ongoing |

---

## Core contracts (change rarely)

These are what everything else builds on. They live in `core/` and must not import FastAPI or UI code. Changes to them are a decision (log it in DECISIONS.md).

```python
# core/llm/models.py  (done in M0)
def parse_model_ref(ref: str) -> ModelRef                     # "openai:gpt-x" | "gpt-x" → ModelRef(provider, model)
def build_chat_model(ref, settings, *, reasoning_effort=None, max_output_tokens=None) -> BaseChatModel
async def list_models(provider, settings, *, chat_only=True) -> list[str]
# core/llm/fake.py: ScriptedChatModel(script=[AIMessage(...), ...]) for tests; records calls + bound tools
```

```python
# core/runtime/agent_def.py
class AgentDef(BaseModel):  # loaded from config/agents/*.yaml or the agents table
    name: str
    description: str
    system_prompt: str
    model: str  # "provider:model"
    reasoning_effort: str | None
    tools: list[str]  # namespaced tool names: "builtin__http_get", "github__search_issues"
    skills: list[str]
    max_model_calls: int = 20
    max_tool_calls: int = 50
    response_schema: dict | None  # structured output for routers/planners/reviewers
```

```python
# core/runtime/agent_factory.py
def build_agent(defn: AgentDef, ctx: RunContext) -> CompiledStateGraph:
    """create_agent(model, tools, system_prompt, response_format, middleware=[
      ModelCallLimitMiddleware, ToolCallLimitMiddleware,
      HumanInTheLoopMiddleware(for requires_approval tools), ToolErrorMiddleware, ...],
    checkpointer=ctx.checkpointer, name=defn.name)"""
```

```python
# core/tools/registry.py
class ToolEntry(BaseModel):
    tool: BaseTool                    # LangChain tool (python / MCP adapter / agent-as-tool / repo tool)
    source: Literal["python", "mcp", "agent", "a2a", "repo"]
    requires_approval: bool
    enabled: bool
class ToolRegistry:
    def register(entry) -> None; def get(names: list[str], ctx: RunContext) -> list[BaseTool]
    # Tool outputs are truncated and errors returned as error ToolMessages, never raised.
```

```python
# core/runtime/context.py
class RunContext(BaseModel):
    run_id: str
    parent_run_id: str | None
    depth: int
    settings: Settings
    tracer: Tracer
    checkpointer: BaseCheckpointSaver  # AsyncSqliteSaver, thread_id = run_id
    workspace: Workspace | None  # repo worktree + language profile, for coding runs
    bus: MessageBus
```

```python
# core/runtime/run_service.py
async def start_run(target: AgentDef | WorkflowDef, input: str, ctx) -> str           # run_id
def stream_run(run_id) -> AsyncIterator[RunEvent]   # from graph.astream(stream_mode=["messages", "updates"])
async def resume_run(run_id, decision: ApprovalDecision) -> None   # Command(resume=...)
async def cancel_run(run_id) -> None
```

```python
# core/tracing/callbacks.py
class TraceCallbackHandler(AsyncCallbackHandler):
    # on_chat_model_start/end, on_tool_start/end/error, on_chain_start/end → Tracer spans
    # (model, tokens from usage_metadata, latency, cost); redacts secrets before writing.
```

```python
# core/workspace/repo_manager.py
class RepoManager:
    def add_local(path) -> Repo;  def create_new(name, location, language_id) -> Repo
    def clone(url, token_ref=None) -> Repo                      # read-only clone
    def start_run(repo, run_id, slug, base_branch=None) -> Workspace   # branch + worktree
    def commit_step(ws, message) -> str
    def diff(ws, from_ref=None) -> str
    def finish(ws, action: Literal["merge", "keep", "discard"]) -> FinishResult   # local only, no push/PR
```

---

## M0: Skeleton ✅

> Historical: M0/M1 shipped a Streamlit UI, since replaced by React (see *Re-plan* below).

**Exit criteria:** `uv run streamlit run app/Home.py` opens the app; all 8 pages exist (placeholders OK); the Playground sends a message to OpenAI and shows the reply; `uv run pytest`, `uv run ruff check .` and `uv run mypy core` pass.

- [x] **M0-T1 Project setup.** `pyproject.toml` (uv, Python 3.14, hatchling, packages `core` + `app`); deps: `streamlit`, `langchain`, `langchain-core`, `langchain-openai`, `langgraph`, `langgraph-checkpoint-sqlite`, `langchain-mcp-adapters`, `mcp<2`, `openai`, `pydantic`, `pydantic-settings`, `sqlmodel`, `pyyaml`, `keyring`, `httpx`, `python-dotenv`. Dev: `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `types-PyYAML`, `uv`. `.gitignore` covers `data/`, `workspaces/`. `.streamlit/config.toml` binds to 127.0.0.1.
- [x] **M0-T2 Settings.** `core/config.py` (`pydantic-settings`, env + `.env`, key as `SecretStr`). Missing key → clear UI message.
- [x] **M0-T3 Storage.** `core/models.py` (11 tables from PLAN §7), `core/storage.py` (SQLite, foreign keys on, WAL). Round‑trip test per table.
- [x] **M0-T4 Model layer.** `core/llm/models.py` (`"provider:model"` refs → `ChatOpenAI` with Responses API, `store=False`; chat‑model filtering for `list_models`), `core/llm/errors.py`, `core/llm/fake.py` (`ScriptedChatModel`, proven to drive a `create_agent` graph with a tool call).
- [x] **M0-T5 Streamlit shell.** `app/Home.py`, `app/pages/1..8`, shared sidebar, `app/engine.py` (background event loop singleton). Playground chats with any listed model.
- [x] **M0-T6 Tooling.** ruff (lint + format), mypy strict for `core/`, pytest (asyncio auto, `live` marker opt‑in), page smoke tests with Streamlit `AppTest`, live OpenAI smoke tests.

---

## M1: Single agent, tools, tracing, REST API ✅

**Exit criteria:** create an agent in the UI with `http_get` + `calculator`, chat with it, and inspect a trace showing each model call and tool call with tokens and timing.

- [x] **M1-T1 Builtin tools.** `core/tools/builtin/` as LangChain tools (`http_get`, `calculator`, `current_time`, `read_text_file` restricted to a sample dir), each with a precise description and argument schema.
  - *Accept:* unit tests per tool; errors come back as error strings or `ToolException`, never unhandled exceptions.
- [x] **M1-T2 Tool registry.** `core/tools/registry.py`: namespaced names, enabled/approval flags, output truncation wrapper, lookup for an agent's tool list.
  - *Accept:* unknown tool names give a clear config error; oversized output is truncated with a marker.
- [x] **M1-T3 Agent factory.** `AgentDef` + `build_agent()` on `create_agent` with limit middleware and tool‑error handling; YAML loader for `config/agents/`.
  - *Accept:* with `ScriptedChatModel`: multi‑turn, parallel tool calls, tool error recovery, model‑call limit stop, tool‑call limit stop.
- [x] **M1-T4 Run service + streaming.** `start_run` / `stream_run` / `cancel_run` using `astream(stream_mode=["messages", "updates"])`; Playground targets an agent, streams text and shows collapsible tool calls; Stop button.
  - *Accept:* a long answer streams; Stop cancels cleanly (run status `cancelled`).
- [x] **M1-T5 Tracing.** `Tracer` (spans → SQLite + live queue) and `TraceCallbackHandler` passed via `config={"callbacks": [...]}`; cost from the Settings price table; secret redaction.
  - *Accept:* a run produces run → model → tool → model spans with tokens and timing.
- [x] **M1-T6 Agents page.** CRUD, model picker (`list_models`), tool and skill multiselects, limits, YAML import/export.
  - *Accept:* create → edit → export → delete → import gives an identical agent.
- [x] **M1-T7 Tools page.** Catalog with source filters, argument schema viewer, "Try it" form from the schema (runs through the registry), approval and enabled toggles.
- [x] **M1-T8 Runs page v1.** Run list + indented span tree + span detail JSON.
- [x] **M1-T9 REST API + Swagger** (added by request, ADR‑017). `api/` FastAPI app over the same `Services`: `/health`, `/models`, `/agents` (CRUD, YAML import/export), `/tools` (list, flags, invoke), `/runs` (start with optional `wait`, poll, cancel, spans). Swagger UI at `/docs`, ReDoc at `/redoc`.
  - *Accept:* `TestClient` tests for every route group; Swagger served; live server smoke check.

- [x] **M1-T10 Usage header** (added by request). Every page shows today's model calls, tool calls, input/output/total tokens and cost, plus all-time totals; per-run footers show model/tool calls and tokens; plain model chats are traced as runs (`kind=chat`); `GET /usage` in the API.
- [x] **M1-T11 Settings page: AI models, keys, pricing** (added by request; pulls in part of M2-T5). Tabs: AI models (verify & save the OpenAI key to Windows Credential Manager via `keyring`, profile-folder fallback; list all models available to the key; default and cheap model; show-all-models toggle), MCP servers (layout, functional in M2), Integrations (git identity, optional GitHub token), Pricing (editable price table → `config/prices.yaml`), General (paths, limits). UI-saved values override `.env` (ADR-018).

**M1 notes (as built):**
- Verified live: the `assistant` agent on `gpt-5.4-nano` called `builtin__calculator`, streamed its answer, and produced the trace agent → llm → tool → llm with tokens.
- `AgentDef.response_schema` and `RunContext` move to M3, where workflows first need them. M1 runs use `RunService` + `RunHandle` directly.
- Approval‑required tools are blocked by `ToolPolicyMiddleware` with an explanation until M4 adds HITL.
- `storage.add_missing_columns()` provides additive migrations (new columns are backfilled with field defaults).
- Architecture is documented in [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Re-plan (2026-11-11): product rebuild ✅

After user feedback the product was rebuilt around the core use case:

- [x] **React UI** (`web/`) served by FastAPI; Streamlit removed (ADR‑019). Pages: Build, Projects, Agents, Tools, Chat, Runs & traces, Settings; usage header; onboarding banner.
- [x] **Build pipeline** (`core/pipeline/`), the six-agent team as a LangGraph graph with a fix loop and review (ADR‑020). Verified live in Python and TypeScript.
- [x] **Projects & workspaces** (`core/workspace/`): create or register git repos, per-build branch + worktree, merge/keep/discard (local only), sandboxed repo tools with per-stage permissions, test runner (pytest / `node --test`) with JUnit parsing, language profiles. This delivers M2‑T7…T11.
- [x] **Key in the UI only** (ADR‑021); model selection from all models available to the key; pricing editor.
- [x] REST API under `/api` (builds, projects, agents, tools, chat, runs, settings, usage, languages) with Swagger.

Remaining from the original M2–M4, still planned: clone-from-URL / apply_patch / extra languages (M2‑T7…T9 gaps), human approval gates mid-build (M4‑T2/T3), A2A (M4‑T6), Docker runner (M5‑T1).

## M2: MCP, Settings, Skills, Repositories, Languages ✅ (small gaps noted per task)

**Exit criteria:** (a) add a public MCP server from the registry, see its tools, and use them from an agent; (b) register a new Python repo from the UI, run a single coder agent that writes a module + tests on an agent branch, and see the diff and test report; same for a TypeScript repo.

### MCP
- [x] **M2-T1 MCPManager.** **Done** (`core/mcp/manager.py`): one long-lived task per server owns the session (stdio + Streamable HTTP via langchain-mcp-adapters); status/error per server; tools as `<server>__<tool>`; auto-connect enabled servers at startup.
  - *Accept:* works against the local fixture MCP server (tests) and `@modelcontextprotocol/server-filesystem` (manual).
- [x] **M2-T2 MCP tools in the registry.** **Done**: MCP tools registered with source `mcp`; tools with `destructiveHint` default to requires-approval; flags persist.
  - *Accept:* an agent calls an MCP tool and the call appears in the trace.
- [x] **M2-T3 Registry client.** **Done** (`core/mcp/registry_client.py`): official registry search, latest version per server, npm→npx / PyPI→uvx / OCI→docker / remote URL drafts with env-var hints. Verified against the live registry.
  - *Accept:* search returns results; "Add" pre‑fills the form; network failure shows a friendly message.
- [x] **M2-T4 Settings page: MCP tab** **Done** as the **MCP servers** page: registry browser, quick-start presets, manual add/edit, JSON import, connect/disconnect, tool lists.
- [x] **M2-T5 Settings page: LLM, Git tabs.** Done early in M1-T11 (key, providers, models, defaults, pricing, git identity, GitHub token).

### Skills
- [x] **M2-T6 SkillLoader + Skills page.** **Done** (`core/skills/loader.py`, Skills page): SKILL.md skills, name+description advertised in the prompt, `skill__load` / `skill__read_file`; one-shot stages get skills inline; 3 starter skills shipped.
  - *Accept:* an agent loads a skill only when relevant (visible in the trace).

### Repositories and languages
- [x] **M2-T7 Language profiles.** **Done in the rebuild** (`core/workspace/languages.py`): Python, JavaScript, TypeScript fully working (scaffold, conventions, tests via pytest / `node --test`, toolchain detection). *Differs:* profiles are Python code, not YAML; Java/C#/Go/Rust not added yet.
- [x] **M2-T8 RepoManager.** *(Reworked by ADR-023: no git; builds write into the folder; change tracking in `core/workspace/changes.py`.)* **Done in the rebuild** (`core/workspace/projects.py`, `worktree.py`): create new repo with scaffold, add existing local repo (folder picker), branch + worktree per build, commit per round, diff, merge/keep/discard. *Not yet:* clone from URL.
  - *Accept:* integration tests on temp repos; the user's checkout is never modified; no worktree is left after discard.
- [x] **M2-T9 Sandboxed repo tools.** **Done in the rebuild** (`core/workspace/repo_tools.py`): `repo__list_files/read_file/write_file/delete_file` with path sandbox and per-stage read/write rules. *Not yet:* `apply_patch`, `search_code`.
  - *Accept:* the path‑escape suite in TESTING.md passes (security‑critical).
- [x] **M2-T10 Code runner + test parsers.** **Done in the rebuild** (`core/workspace/runner.py`): JUnit-based parsing for pytest and node:test, timeout with process-tree kill, scrubbed env.
  - *Accept:* passing and failing fixture projects (Python, JS, TS) give correct reports.
- [x] **M2-T11 Repositories page + language pickers.** **Done in the rebuild** as the **Projects** page (create/add with folder picker, files, builds) and language chips in the New project dialog; toolchains shown in Settings → System.

---

## M3: Multi‑agent orchestration (LangGraph), dev team v1

**Exit criteria:** a supervisor with 3 workers and a writer↔critic loop run from templates with nested traces; dev team v1 turns "build a slugify module with tests" into a passing branch in a Python repo and a TS repo.

- [ ] **M3-T1 Agent‑as‑tool.** `ask_<agent>(task, context_refs)` invokes the child agent graph with `depth+1` (max 3) and returns a summary + artifact refs.
  - *Accept:* nested spans; the depth limit is enforced.
- [ ] **M3-T2 MessageBus + artifacts.** In‑proc pub/sub logged to `bus_messages`; `run_artifacts` store (`spec`, `plan`, `test_report`, `review`).
- [ ] **M3-T3 Workflow builder.** `WorkflowDef` (YAML/DB: nodes = agent | tool | router | join | approval | runner; edges with conditions) → LangGraph `StateGraph` over `WorkflowState`; `Send` for fan‑out; `Command(goto=...)` for handoffs.
  - *Accept:* every node type has a test with `ScriptedChatModel`; invalid graphs give clear validation errors.
- [ ] **M3-T4 Pattern templates.** Sequential, parallel, router, supervisor, handoff, critic loop as YAML in `config/workflows/`.
- [ ] **M3-T5 Workflows page.** List, create from template, edit nodes/edges as tables, diagram from `draw_mermaid()` or Graphviz, run with input. No drag‑and‑drop (ADR‑012).
- [ ] **M3-T6 A2A message log.** Mermaid `sequenceDiagram` from bus messages on the Runs page.
- [ ] **M3-T7 Dev‑team agents.** `config/agents/{requirements,architect,coder,test_writer,reviewer}.yaml` with prompts, structured‑output schemas for `spec`, `plan`, `review`, and language skills by profile.
- [ ] **M3-T8 Dev team v1 workflow.** `config/workflows/dev_team.yaml`: Requirements → Architect → (Test writer ∥ Coder) → Runner → Reviewer; a commit per step; no loops yet.
  - *Accept:* the exit demo works; the test writer's inputs contain no source code (checked in the trace).

---

## M4: Checkpoints, HITL, dev team v2, A2A

**Exit criteria:** the dev team goes from request → clarifying questions → approved spec → code + tests → fix loop → review loop → approved diff → merged locally into the base branch. Two app instances talk over A2A.

- [ ] **M4-T1 Checkpoints + resume.** `AsyncSqliteSaver` (thread_id = run_id) for all workflow and agent runs; resume after an app restart.
  - *Accept:* kill the app mid‑run, restart, and resume from the last checkpoint.
- [ ] **M4-T2 Approvals.** Approval nodes use `interrupt()`; `requires_approval` tools use `HumanInTheLoopMiddleware`; the UI shows Approve / Reject / Edit and resumes with `Command(resume=...)`.
- [ ] **M4-T3 Clarifying questions.** The requirements agent returns `questions[]`; the graph interrupts, the UI collects answers, the run resumes.
- [ ] **M4-T4 Dev team v2.** Fix loop (≤3), review loop (≤2), spec + final approval gates, `needs_human` status when limits are hit, cost cap.
- [ ] ~~**M4-T5 Finish actions (local only).**~~ *Dropped by ADR-023: the app runs no git and writes directly into the project folder.* Merge locally (merge commit message includes spec, review summary, and test report), keep branch (remove worktree, keep branch), or discard. No push or PRs (ADR‑011).
  - *Accept:* merge lands on the base branch with the summary message; keep leaves the branch and no worktree; discard leaves neither.
- [ ] **M4-T6 A2A server + client.** FastAPI sidecar: Agent Card at `/.well-known/agent.json` + task endpoints for agents marked `a2a_exposed`; an `a2a` tool type calling a remote URL. Bind 127.0.0.1 + shared secret.

---

## M5: Hardening (ongoing)

- [ ] **M5-T1 Docker runner.** Install/test/lint in the profile's `docker_image` with the worktree mounted and no network by default.
- [ ] **M5-T2 Budgets everywhere.** Per run: model calls, tool calls, tokens, cost, wall clock; global daily cost cap.
- [ ] **M5-T3 Memory.** Per‑agent key/value memory (`remember`, `recall`, `forget` tools + Memory view on the Agents page). No vector store (ADR‑013).
- [ ] **M5-T4 Evals.** `evals/dev_team/*.yaml` with hidden reference tests; score = hidden tests pass + reviewer verdict + cost; compare runs and models.
- [ ] **M5-T5 Replay & compare.** Re‑run with a different model or prompt; side‑by‑side diff.
- [ ] **M5-T6 Experimental languages.** Wire Java, C#, Go, Rust end to end and move them to "supported" one by one.
- [ ] **M5-T7 Anthropic provider.** Add `langchain-anthropic`, the `anthropic` branch in `build_chat_model`, and a mixed‑provider workflow demo.
- [ ] **M5-T8 LangSmith / OpenTelemetry export** (optional).

---

## Dependencies between tasks

```
M0 ✅ ─► M1 ✅ (T1 ─► M1-T2 ─► M1-T3 ─► M1-T4
                              └► M1-T5 ─► M1-T8 ─► T9)
M1-T3 ─► M2-T1 ─► M2-T2 ─► M2-T4
M1-T3 ─► M2-T6
M2-T7 ─► M2-T8 ─► M2-T9 ─► M2-T10 ─► M2-T11
M1-T3 + M2-T9 ─► M3-T1 ─► M3-T2 ─► M3-T3 ─► M3-T4 ─► M3-T8
M3-T3 ─► M4-T1 ─► M4-T2 ─► M4-T4 ─► M4-T5
```
