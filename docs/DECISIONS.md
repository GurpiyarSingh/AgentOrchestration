# Decision Log

Short architecture decision records (ADRs). Add one whenever a choice is hard to reverse or affects several modules. Never delete an entry; mark it **Superseded by ADR‑NNN** instead.

Template:
```
## ADR-NNN: Title
- Date: YYYY-MM-DD
- Status: Accepted | Superseded by ADR-XXX
- Context: why a decision was needed
- Decision: what we chose
- Consequences: what this makes easier / harder
```

---

## ADR-001: Python + Streamlit for the POC UI
- Date: 2026-11-11
- Status: Superseded by ADR-019
- Context: Need a UI quickly to manage agents, tools, MCP servers, and runs.
- Decision: Streamlit multipage app as a thin shell over a UI‑independent `core/` engine.
- Consequences: Fast to build. Streamlit reruns and a lack of true push updates need a background event loop + polling. The UI can later be replaced (FastAPI + React) without touching `core/`.

## ADR-002: Own the agent loop instead of adopting a framework
- Date: 2026-11-11
- Status: Superseded by ADR-015
- Context: The goal is to learn and show orchestration, with full control over tracing, approvals, and budgets.
- Decision: Implement the LLM ↔ tool loop and orchestration patterns ourselves. Benchmark the OpenAI Agents SDK, LangGraph, etc. later.
- Consequences: More code to write; complete visibility and control. Must avoid accidentally re‑creating a framework; keep it small.

## ADR-003: OpenAI first, behind a provider‑neutral interface
- Date: 2026-11-11
- Status: Accepted
- Context: Only an OpenAI key is available now; Anthropic and others may follow.
- Decision: Models are referenced as `"provider:model"` and built as LangChain chat models by `core/llm/models.py` (amended by ADR‑015; originally an own `LLMProvider` protocol). `ChatOpenAI` uses the Responses API. Model chosen per agent.
- Consequences: Adding a provider means one adapter file. Provider‑specific features (hosted tools, server‑side state) are opt‑in only.

## ADR-004: Keep conversation state in the engine, not the provider
- Date: 2026-11-11
- Status: Accepted
- Context: Tracing, replay, handoffs, and provider switching need the full transcript.
- Decision: Send the full input each turn; don't depend on `previous_response_id` or similar. With ADR‑015 the transcript lives in LangGraph state/checkpoints and `ChatOpenAI` runs with `store=False`.
- Consequences: Slightly larger requests; full portability and auditability.

## ADR-005: Client‑side MCP via the official `mcp` Python SDK
- Date: 2026-11-11
- Status: Accepted
- Context: Most public MCP servers are stdio processes, and MCP tools must go through the same approval and tracing path as other tools.
- Decision: The app connects to MCP servers itself (stdio + Streamable HTTP), via `langchain-mcp-adapters` since ADR‑015, so MCP tools are LangChain tools. Provider‑hosted MCP tools are an optional per‑agent toggle only.
- Consequences: The app manages server processes and sessions (lifecycle, Windows paths). Full control over which tools each agent sees.

## ADR-006: Agents are data; agent‑to‑agent calls are tool calls
- Date: 2026-11-11
- Status: Accepted
- Context: Many agents and patterns, editable from the UI.
- Decision: Agents and workflows are YAML/DB definitions. Calling another agent is an `ask_<agent>` tool that starts a nested run; in M4, remote agents use the A2A protocol.
- Consequences: Supervisor/worker and nested traces come for free; no agent‑specific code in the engine.

## ADR-007: Flagship use case is an AI software team writing into a target repo
- Date: 2026-11-11
- Status: Accepted
- Context: Need a demo that exercises most patterns and has an objective success signal.
- Decision: Requirements → Architect → (Test writer ∥ Coder) → Runner → Reviewer, with fix and review loops and human gates. The test writer works from the spec only. The runner is a plain command, not an AI agent.
- Consequences: Requires the repo, workspace, and runner subsystem early (M2).

## ADR-008: Generated code is written only to a registered repo, on a per‑run branch + worktree
- Date: 2026-11-11
- Status: Superseded by ADR-023
- Context: Generated code must go to a repo the user chooses, without risking their files.
- Decision: Repos are registered in the UI (local / new / clone). Each run uses branch `agents/<run-id>-<slug>` in its own git worktree. Agents use sandboxed repo tools only. Merge, push, and PR happen after human approval.
- Consequences: Safe parallel runs and easy discard. Needs Windows long‑path handling and worktree cleanup.

## ADR-009: Language support via declarative language profiles
- Date: 2026-11-11
- Status: Accepted
- Context: The user picks the target language in the UI; more languages will follow.
- Decision: One YAML profile per language (commands, test framework, scaffold, parser, skill, Docker image). Python, JS, and TS are supported first; Java, C#, Go, and Rust are experimental.
- Consequences: Adding a language is mostly config + a test‑output parser + a skill.

## ADR-010: SQLite for all persistence in the POC
- Date: 2026-11-11
- Status: Accepted
- Context: Zero‑setup local POC.
- Decision: SQLite via SQLModel; additive schema changes only; a reset script for breaking changes.
- Consequences: Single‑user only. Move to Postgres if this becomes hosted or multi‑user.

---

## ADR-011: Local‑only git: no push, no pull requests
- Date: 2026-11-11
- Status: Superseded by ADR-023 (the app now runs no git at all)
- Context: Decide where finished dev‑team runs go.
- Decision: Finish actions are local only: **merge** into the base branch, **keep** the agent branch (worktree removed), or **discard**. The app never runs `git push` or opens PRs. Cloning from a URL is allowed (read‑only).
- Consequences: No hosting tokens with write scope, a smaller attack surface, and no GitHub/GitLab/Azure DevOps adapters. You push yourself if you want to. Adding PRs later would be a new ADR.

## ADR-012: Workflow editing via table + rendered diagram
- Date: 2026-11-11
- Status: Accepted
- Context: Choose the workflow editing UX for the POC.
- Decision: Nodes and edges edited in tables with a live Graphviz/Mermaid render. No drag‑and‑drop canvas.
- Consequences: Fast to build, no third‑party canvas component. A visual editor can come with a future non‑Streamlit UI.

## ADR-013: Key/value agent memory only
- Date: 2026-11-11
- Status: Accepted
- Context: Decide memory scope.
- Decision: Per‑agent and per‑run key/value memory in SQLite (`remember` / `recall` / `forget` tools). No embeddings or vector store in the POC.
- Consequences: Simple and inspectable. RAG‑style agents use keyword search over local docs for now.

## ADR-014: Python 3.14 for the app
- Date: 2026-11-11
- Status: Accepted
- Context: Python 3.14 is already installed on the dev machine; the plan originally said 3.12.
- Decision: The app targets Python 3.14 (`requires-python = ">=3.14"`), managed by uv. Generated code in target repos is independent; language profiles choose their own versions.
- Consequences: No extra interpreter to install. If a dependency lacks 3.14 wheels, pin an older compatible version or fall back to 3.13 via `uv python install` and record a new ADR.

## ADR-015: Build the engine on LangChain + LangGraph
- Date: 2026-11-11
- Status: Accepted (supersedes ADR-002)
- Context: The user asked to use LangChain. Writing our own agent loop, graph executor, checkpoints, and human‑in‑the‑loop would duplicate what LangGraph already provides.
- Decision: LangChain for chat models, tools, and MCP (`langchain-openai`, `langchain-mcp-adapters`); LangGraph for agents (`langchain.agents.create_agent` + middleware for limits, approvals, retries) and workflows (`StateGraph`, `Send`, `Command`, `interrupt`, `AsyncSqliteSaver`). We still own the registry, the UI, tracing (own callback handler → SQLite; LangSmith optional), the repo sandbox, language profiles, and the dev‑team workflow.
- Consequences: Much less engine code; M3–M4 shrink. Framework concepts appear in our code, so keep them inside `core/llm`, `core/runtime`, `core/orchestration`, and `core/mcp`. Upgrades need care (fast‑moving packages). Adding providers becomes "install `langchain-<provider>`".

## ADR-016: Pin `mcp` below 2.0 for `langchain-mcp-adapters`
- Date: 2026-11-11
- Status: Accepted
- Context: `langchain-mcp-adapters` 0.3.1 declares `mcp>=1.24` but fails to import with `mcp` 2.x (`RequestContext` moved).
- Decision: Pin `mcp>=1.24,<2` until the adapters support MCP 2.x.
- Consequences: We don't get MCP 2.x client features yet. Revisit when a newer adapters release is available; run the MCP tests when unpinning.

## ADR-017: REST API with Swagger (FastAPI) alongside the Streamlit UI
- Date: 2026-11-11
- Status: Accepted
- Context: The user asked for Swagger. Agents and runs should also be usable from scripts and other services, not only the UI.
- Decision: A FastAPI app in `api/` over the same `core.services.Services` as the Streamlit app. OpenAPI/Swagger UI at `/docs`, ReDoc at `/redoc`. It binds to 127.0.0.1 and has no auth in the POC (local only). Runs execute in the process that started them; both processes share the SQLite database.
- Consequences: Anything the UI can do is scriptable and testable over HTTP. Live run progress is per process (a run started in the UI is visible via the API only once it is in the database). Auth is required before exposing the API beyond localhost.

## ADR-018: Keys and preferences entered in the UI
- Date: 2026-11-11
- Status: Accepted
- Context: The user wants to add the API key and choose models from the UI rather than editing `.env`.
- Decision: Secrets (OpenAI key, GitHub token) entered in Settings are verified first and stored in the **OS credential store** via `keyring` (Windows Credential Manager on this machine), falling back to `~/.agent-orchestration/secrets.json` if no keyring backend works. Never in SQLite. Non-secret preferences (default/cheap model, show-all-models, git identity) go in the `app_settings` table. UI-saved values override `.env`; removing them falls back to `.env`. Both the Streamlit app and the API re-apply them (the API on every request).
- Consequences: No file editing needed to get started. Secrets stay out of the DB and out of traces (they're added to the redactor). Keys live per OS user, not per project. Tests swap in an in-memory keyring so they never touch the real one.

## ADR-019: React UI served by FastAPI (Streamlit removed)
- Date: 2026-11-11
- Status: Accepted (supersedes ADR-001)
- Context: The Streamlit UI didn't look or behave like a product, and the user asked for React.
- Decision: A React + TypeScript single-page app (Vite, React Router, lucide icons, hand-built design system) in `web/`. FastAPI serves it at `/`, the REST API at `/api`, and Swagger at `/docs`, as one server on 127.0.0.1:8000. `start.ps1` builds the UI when needed and starts the server.
- Consequences: A professional, responsive UI with live polling views. Node.js is required to build the UI. All UI logic goes through the REST API, which is now the single contract.

## ADR-020: The build pipeline: a six-agent team on per-build git worktrees
- Date: 2026-11-11
- Status: Accepted; the worktree / merge part is superseded by ADR-023
- Context: The core use case is "enter a requirement, get working code". It was missing from the first UI.
- Decision: A LangGraph `StateGraph`: Requirements Analyst → Architect → (Unit Test Writer ∥ Code Generator) → Code Runner → fix loop → Code Reviewer, then merge/keep/discard. Spec, Plan and Review are structured outputs. Coding stages use sandboxed workspace tools with per-stage permissions: the test writer never sees source and the coder never writes tests. The runner is deterministic: pytest for Python, `node --test` with type stripping for JS/TS, with JUnit parsing. The fixer must judge whether the test or the code is wrong, and the reviewer always runs.
- Consequences: Verified live with gpt-5.4-mini in Python and TypeScript (all tests passing, approved, ~45-50k tokens per build). Generated code is limited to the standard library, because tests run without installing packages. Approval gates mid-build are future work.

## ADR-021: The API key is entered in the UI only
- Date: 2026-11-11
- Status: Accepted (amends ADR-018)
- Context: The user wants the key managed in the UI, not picked up from the environment.
- Decision: `OPENAI_API_KEY` from the environment or `.env` is ignored. The key is entered in Settings, verified against OpenAI, stored in the OS credential store and removable there. Live tests read their own key explicitly.
- Consequences: Behaviour is predictable (one source of truth). The UI shows an onboarding banner until a key is saved.

## ADR-022: MCP connections and skills
- Date: 2026-11-12
- Status: Accepted
- Context: M2 adds MCP servers and skills.
- Decision:
  - Each connected MCP server runs in a dedicated asyncio task that owns its session (the MCP client's task groups must enter and exit in the same task).
  - Tools are registered as `<server>__<tool>`.
  - Env/header **values** are secrets in the OS credential store (key `mcp/<server>/<kind>/<name>`); only their names are in SQLite.
  - Tools annotated `destructiveHint` default to requires-approval.
  - Enabled servers auto-connect at startup without blocking it.
  - Skills are `skills/<name>/SKILL.md` folders. Agents see only names and descriptions, and load the full text through `skill__load`. One-shot structured stages get their skills inline.
- Consequences:
  - Any public MCP server can extend agents without code.
  - Connection failures are shown per server and never block the app.
  - Local MCP servers run third-party code on your machine, so the exact command is always shown and connecting is an explicit action.

## ADR-023: No git: agents write directly into the project folder
- Date: 2026-11-12
- Status: Accepted (supersedes ADR-008 and ADR-011, and the worktree/merge part of ADR-020)
- Context: The user does not want the app to commit anything to git. Builds that sat on unmerged `agents/<id>` branches also looked like "the agents wrote nothing", because the project folder only changed after Merge.
- Decision:
  - The app never runs git: no `init`, branch, worktree, commit or merge. The git wrapper and worktree module were deleted.
  - A project is any folder. New projects are a plain folder with the language scaffold. Existing folders may or may not be git repos, and may have uncommitted changes.
  - Agents write straight into the project folder, live, through the same sandboxed repo tools (path checks and protected paths unchanged).
  - Before a build starts, the app records a hash of every file (and the text of small files), skipping `.git`, `node_modules`, virtualenvs and caches. Changed files and the diff are computed against that snapshot (`core/workspace/changes.py`). The final diff is saved with the build.
  - Only one build may write to a project at a time.
  - There is no Merge / Keep / Discard step. If the folder is a git repo, the changes show up as ordinary uncommitted files for the user to review and commit.
- Consequences:
  - What you see in the folder is what the agents wrote, as they write it.
  - There is no automatic undo. A bad build leaves files behind that the user removes or reverts themselves (with their own git, if they use it).
  - Tests run in the real project folder, so their side effects land there too (still with the timeout and scrubbed environment).
  - Builds from before this change still show their saved results, but their `agents/<id>` branches were left in those repos untouched.

---

## Open (to decide)

- **Single‑user local vs hosted / multi‑user** later (affects auth, secrets, stdio MCP). Assumed single‑user local for the POC.
- **Second, non‑coding demo** (e.g. research report team) to sit alongside the dev team.
