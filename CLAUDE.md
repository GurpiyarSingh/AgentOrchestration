# Instructions for AI coding assistants

This repo is a proof of concept for **multi‑agent orchestration** with a React UI served by FastAPI. Read these before changing code:

1. [docs/PLAN.md](docs/PLAN.md): what we're building and why (architecture, concepts, UI pages, flagship dev‑team use case).
2. [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md): ordered tasks with acceptance criteria. Work on the current milestone only.
3. [docs/RULES.md](docs/RULES.md): engineering rules. The **MUST** rules are not optional.
4. [docs/SECURITY.md](docs/SECURITY.md): controls you must not weaken.
5. [docs/TESTING.md](docs/TESTING.md): how to test. No real API calls in default tests.
6. [docs/DECISIONS.md](docs/DECISIONS.md): decisions already made. Don't relitigate them; propose a new ADR instead.
7. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): components, run flow, data model (keep it current when structure changes).

## Quick facts

- Python 3.14 in the project venv (`.venv`, managed by **uv**), FastAPI, React + TypeScript (Vite, `web/`), **LangChain** (models, tools, MCP adapters) + **LangGraph** (agents, workflows, checkpoints, interrupts), SQLite/SQLModel, Pydantic.
- `core/` = engine (no FastAPI imports); `core/services.py` wires it. `api/` = thin FastAPI routes under `/api` (Swagger at `/docs`) that also serve the React build. `web/` = React + TypeScript UI (Vite); it only talks to `/api`.
- The build pipeline is `core/pipeline/service.py` (LangGraph). The default agent team is YAML in `config/agents/`.
- Chat models only via `core/llm/models.py` (`build_chat_model("provider:model", settings)`). Tools only via the tool registry. LangGraph only in `core/runtime` and `core/orchestration`; MCP adapters only in `core/mcp`.
- Tests use `ScriptedChatModel` (`core/llm/fake.py`), never real API calls (except `-m live`).
- Agents, workflows, MCP servers, and language profiles are YAML/DB data, not code.
- The platform is Windows‑first. Use `pathlib`, handle `npx.cmd`, long paths, and file locks.

## Commands

```powershell
uv sync
.\start.ps1                       # build UI if needed + start on :8000
npm --prefix web run dev          # UI dev server with hot reload (:5173)
npm --prefix web run typecheck
uv run pytest
uv run ruff format . ; uv run ruff check . ; uv run mypy core
```

## Working agreements

- Pick the next unchecked task in the current milestone, implement it with tests, then tick it in IMPLEMENTATION_PLAN.md.
- Commit messages: `M<n>-T<k>: <imperative summary>`.
- Never commit `.env`, `data/`, or `workspaces/`. Never print or log secrets.
- If a task's design doesn't hold up, update IMPLEMENTATION_PLAN.md (and DECISIONS.md if it's a design change) before coding around it.
