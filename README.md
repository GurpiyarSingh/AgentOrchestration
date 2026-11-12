# Codeloom

**Codeloom: your AI software team.** It turns a plain-language requirement into tested, reviewed code inside a folder you choose. It's built on **LangChain + LangGraph** with a **FastAPI** backend and a **React** UI.

```
Requirement ─► Requirements Analyst ─► Architect ─┬─► Unit Test Writer ─┬─► Code Runner ─► Code Reviewer
                                                  └─► Code Generator ───┘        ▲  │
                                                                                  └──┘ fix loop (Code Generator)
```

- **Build:** describe what you need; watch each agent work live (spec, design, files, test results, review, diff). The code is written straight into your project folder.
- **Projects:** any folder, for Python, JavaScript or TypeScript. Codeloom never runs git (no init, branches or commits); if the folder is a git repo, the changes are left uncommitted for you.
- **Agents:** the six-agent build team, with editable prompts, models and limits, plus your own agents.
- **Tools:** built-in tools with Try-it, the sandboxed workspace tools the coding agents use, and tools from **MCP servers**.
- **MCP servers:** browse the public MCP Registry, add or import servers (`mcp.json`), connect, and give their tools to agents.
- **Skills:** reusable know-how (`SKILL.md`) that agents load on demand.
- **Themes:** light, dark or follow Windows.
- **Chat:** talk to an agent (with tool calls) or to a model directly.
- **Runs & traces:** every model call and tool call, with tokens, timing and cost.
- **Settings:** the OpenAI key (verified, stored in the OS credential store), model choice and pricing.
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
