# Engineering Rules

These rules apply to every change in this repo, whether a person or an AI coding assistant writes it. If a rule blocks you, change the rule here in the same PR and say why. Don't silently break it.

The **MUST** rules are hard requirements. **SHOULD** rules are strong defaults; break one only with a reason written in the code or PR.

---

## 1. Architecture boundaries

- **MUST:** `core/` never imports FastAPI or anything under `api/`. The engine must run headless (tests, scripts).
- **MUST:** `web/` (React) talks to the backend only through `/api` via `web/src/api.ts`. No business logic in the UI beyond presentation.
- **MUST:** `api/` is equally thin: routes call `core.services.Services` and map errors to HTTP codes. No business logic in routes. Request/response models live in `api/schemas.py` so they appear in Swagger.
- **MUST:** Agents, workflows, MCP servers, and language profiles are **data** (YAML/DB). No agent‑specific `if agent.name == "coder"` logic in the engine.
- **MUST:** Chat models are built only by `core/llm/models.py` (`build_chat_model`). No provider packages (`openai`, `langchain_openai`, `langchain_anthropic`, …) imported outside `core/llm/`.
- **MUST:** Agents get tools only from the tool registry (`core/tools/registry.py`), which applies naming, approval flags, and output truncation. The Tools page "Try it" also goes through the registry.
- **MUST:** LangGraph / `langchain.agents` are used only in `core/runtime/` and `core/orchestration/`; MCP adapters only in `core/mcp/`. Pages never build agents or graphs.
- **MUST:** Every agent and workflow invocation passes our trace callback handler (`config={"callbacks": [...]}`) and a `thread_id` equal to the run id.
- **MUST:** All repo file access by agents goes through the sandboxed repo tools in `core/workspace/repo_tools.py`.
- **SHOULD:** Dependencies point inward: `app → core.orchestration → core.runtime → core.tools / core.llm → core.models`. No cycles.

## 2. Python style

- Python **3.14**, managed with **uv** in the project virtual env (`.venv`). Add dependencies with `uv add`, never `pip install` into the venv by hand, and never install project deps globally.
- **Pin deliberately:** LangChain, LangGraph, and MCP packages move fast. Upgrade them in a dedicated change with the full test suite (ADR‑016).
- **Formatting and linting:** `ruff format` + `ruff check` (config in `pyproject.toml`). CI and pre‑commit run both.
- **Typing:** type hints on every function signature. `mypy --strict` for `core/`; relaxed for `app/`.
- **Data shapes:** Pydantic models (or SQLModel for tables) for anything crossing a module boundary. Don't pass raw `dict`s around except JSON Schemas and raw provider payloads.
- **Naming:** `snake_case` modules and functions, `PascalCase` classes, `UPPER_CASE` constants. Tool names are `<source>__<name>` (e.g. `builtin__http_get`, `github__create_issue`).
- **Size:** keep functions under ~50 lines and modules under ~400. Split when they grow.
- **Comments:** explain *why*, not *what*. Every public class and function in `core/` gets a one‑line docstring.
- **No dead code.** Don't commit commented‑out code or unused feature flags.

## 3. Async and concurrency

- **MUST:** The engine is `asyncio`. Blocking work (subprocess, git, file I/O on large trees) goes through `asyncio.to_thread` or `asyncio.create_subprocess_exec`.
- **MUST:** Long-running work (builds, agent runs) runs as asyncio tasks on the server's event loop; HTTP handlers return immediately and the UI polls. Never call `asyncio.run()` inside a request handler.
- **MUST:** Every awaited external call (LLM, MCP, HTTP, subprocess) has a timeout.
- **MUST:** Runs are cancellable. Cancellation must close spans, mark the run `cancelled`, and kill child processes.
- **SHOULD:** Use `asyncio.TaskGroup` for fan‑out so one failure cancels siblings cleanly.

## 4. Errors and results

- **MUST:** Tool failures never crash a run. They come back to the model as an error `ToolMessage` ("<what went wrong and how to fix it>") via `ToolException` / tool‑error middleware, so the model can recover.
- **MUST:** Every agent run ends in exactly one status: `done`, `failed`, `cancelled`, `needs_human`, or `waiting_approval`. No silent ends.
- **MUST:** Never swallow exceptions (`except Exception: pass`). Catch narrowly, record on the span, and re‑raise or convert.
- **SHOULD:** Show users short, actionable messages ("OpenAI key missing: add `OPENAI_API_KEY` to `.env`"), with details in the trace.

## 5. LLM and prompt rules

- **MUST:** System prompts live in agent YAML (`config/agents/`), not in Python strings. Shared fragments go in skills.
- **MUST:** Routers, planners, extractors, and reviewers return **structured output** (`response_format=` on `create_agent` or `with_structured_output`) validated against a schema. Never parse free text to make a control‑flow decision.
- **MUST:** Every model call records model, input/output tokens (`usage_metadata`), latency, and cost on a span (via the trace callback handler).
- **MUST:** The transcript lives in LangGraph state / checkpoints. Don't rely on provider‑side conversation state (`ChatOpenAI(store=False)`, no `previous_response_id`).
- **MUST:** Tool outputs and fetched web or file content are **untrusted data**. Never put them in a system prompt, and don't let them change budgets, tools, or approval settings. See [SECURITY.md](SECURITY.md).
- **SHOULD:** Agents pass **artifacts by reference** (`spec`, `plan`, `test_report`, `review`) instead of whole transcripts, to keep context small.
- **SHOULD:** Prompts are short and specific: role, inputs, output format, constraints, stop condition. No "you are the world's best…" filler.
- **SHOULD:** Model names come from config/agent definitions, never hard‑coded in Python.

## 6. Tools and MCP

- **MUST:** Every tool has a precise description (when to use it, what it returns) and a JSON Schema with `required` fields and `additionalProperties: false`.
- **MUST:** Tools with side effects (write, delete, send, push, pay, execute) default to `requires_approval: true`.
- **MUST:** Tool output is truncated to a configured maximum (default 20k chars) with a clear `[truncated]` marker.
- **MUST:** MCP servers are only connected after the user has seen the exact command or URL.
- **SHOULD:** Prefer a small set of well‑described tools per agent (≤ 15) over giving every agent everything.

## 7. Coding‑agent and repository rules

- **MUST:** Coding agents write **only** inside the project folder, through sandboxed repo tools. No general filesystem MCP for coding agents.
- **MUST:** The app never runs git: no init, branch, worktree, commit, merge or push (ADR‑023).
- **MUST:** Protected paths (`.env*`, `.git/`, `.github/workflows/`, `*.pem`, `*.key`, plus repo‑specific ones) are never readable or writable by agents.
- **MUST:** Only one build writes to a project at a time.
- **MUST:** The code runner runs with a timeout, in the project folder, with secrets removed from the environment.
- **MUST:** The test writer never receives source code written in the same run (only spec + plan).

## 8. Data, config, and secrets

- **MUST:** Secrets come from `.env` or the OS keyring. The DB stores only *references* (env var names / keyring keys). Never log, trace, or display a secret.
- **MUST:** `.env`, `data/`, and `workspaces/` are git‑ignored. Never commit them.
- **MUST:** YAML config is validated with Pydantic on load. An invalid file gives a clear error naming the file and field.
- **SHOULD:** Schema changes to SQLite tables are additive in the POC. If a breaking change is needed, provide a reset script and note it in DECISIONS.md.

## 9. UI rules (React, `web/`)

- **MUST:** Pages are thin: fetch from `/api` through `web/src/api.ts`, render, send actions. No business logic in the UI.
- **MUST:** Types in `web/src/types.ts` mirror the API models; update both together.
- **MUST:** `npm --prefix web run typecheck` passes (strict TypeScript, no unused code).
- **SHOULD:** Use the shared components in `web/src/components/ui.tsx` and the design tokens in `styles.css`; no ad-hoc colours.
- **SHOULD:** Every destructive button (delete agent, discard branch, disconnect server) asks for confirmation.

## 10. Testing

Full strategy in [TESTING.md](TESTING.md). In short:
- **MUST:** Unit and integration tests never call real LLM APIs or the network. Use `ScriptedChatModel` (`core/llm/fake.py`) and local fixture MCP servers.
- **MUST:** Security‑critical code (path sandbox, protected paths, secret scrubbing, approval gates) has dedicated tests, including attack cases.
- **MUST:** Every bug fix comes with a test that fails before the fix.
- **SHOULD:** Over 80% line coverage in `core/`; the UI is tested by manual demo scripts per milestone.

## 11. Git workflow (for this repo)

- **Branches:** `main` is always runnable. Work on `feat/<milestone>-<short-name>` or `fix/<short-name>`.
- **Commits:** small and focused, imperative mood ("Add MCP registry client"). Reference the task ID: `M2-T3: add MCP registry client`.
- **Before merging:** `ruff format --check`, `ruff check`, `mypy core`, `pytest` all pass; the milestone demo still works.
- **Never commit:** secrets, `.env`, `data/`, `workspaces/`, large binaries, generated test repos.

## 12. Definition of done (per task)

- [ ] Acceptance criteria in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) pass
- [ ] Tests added or updated; `pytest` green; no real network calls in tests
- [ ] `ruff format`, `ruff check`, `mypy core` clean
- [ ] New behaviour is visible in traces (spans for new LLM, tool, or agent actions)
- [ ] No secrets in code, logs, traces, or fixtures
- [ ] Docs updated if behaviour or config changed (PLAN, SETUP, `.env.example`, this file)
- [ ] Task box ticked in IMPLEMENTATION_PLAN.md
