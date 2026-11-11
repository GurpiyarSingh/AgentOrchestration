# Codeloom

**Codeloom: your AI software team.** It turns a plain-language requirement into tested, reviewed code inside a git repository you choose. It's built on **LangChain + LangGraph** with a **FastAPI** backend and a **React** UI.

```
Requirement ─► Requirements Analyst ─► Architect ─┬─► Unit Test Writer ─┬─► Code Runner ─► Code Reviewer ─► Merge / Keep / Discard
                                                  └─► Code Generator ───┘        ▲  │
                                                                                  └──┘ fix loop (Code Generator)
```

- **Build:** describe what you need; watch each agent work live (spec, design, files, test results, review, diff), then merge.
- **Projects:** git repos in Python, JavaScript or TypeScript. Every build runs on its own branch in an isolated worktree; nothing touches your project until you merge. Git stays local and is never pushed.
- **Agents:** the six-agent build team, with editable prompts, models and limits, plus your own agents.
- **Tools:** built-in tools with Try-it, and the sandboxed workspace tools the coding agents use.
- **Chat:** talk to an agent (with tool calls) or to a model directly.
- **Runs & traces:** every model call and tool call, with tokens, timing and cost.
- **Settings:** the OpenAI key (verified, stored in the OS credential store), model choice, pricing and git identity.
- **Usage** (model calls, tool calls, tokens, cost) is always visible in the header.
- **REST API** with Swagger at `/docs`.

## Quick start

```powershell
.\start.ps1          # then open http://127.0.0.1:8000
```

Full steps: [docs/RUN.md](docs/RUN.md).

## Documents

| File | Purpose |
|---|---|
| [docs/RUN.md](docs/RUN.md) | How to install and run |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, diagrams, build pipeline, data model |
| [docs/PLAN.md](docs/PLAN.md) | Vision, concepts, roadmap context |
| [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Milestones and tasks |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Architecture decision records |
| [docs/RULES.md](docs/RULES.md) | Engineering rules |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model and controls |
| [docs/TESTING.md](docs/TESTING.md) | Test strategy |
| [docs/SETUP.md](docs/SETUP.md) | Detailed setup and troubleshooting |
| [CLAUDE.md](CLAUDE.md) | Instructions for AI coding assistants |

## Repository layout

```
api/        FastAPI app: REST routes under /api, Swagger at /docs, serves the React build at /
core/       Engine: agents (LangGraph), build pipeline, workspace/git, tools, tracing, settings
web/        React + TypeScript UI (Vite)
config/     Default agent team (YAML) and price table
tests/      Unit and integration tests (no network; scripted models)
docs/       Documentation
start.ps1   Build the UI if needed and start everything
```
