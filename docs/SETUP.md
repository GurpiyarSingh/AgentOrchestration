# Setup & Prerequisites

Everything needed on a dev machine before starting [M0](IMPLEMENTATION_PLAN.md#m0-skeleton). Written for **Windows 10/11** first; macOS and Linux commands are noted where they differ.

---

## 1. Required

| Tool | Version | Why | Check |
|---|---|---|---|
| **Git** | optional | Not used by the app (ADR-023); only needed to clone this repo | `git --version` |
| **Python** | 3.14.x | The app itself | `python --version` |
| **uv** | latest | Python packaging, venv, running the app | `uv --version` |
| **Node.js** | 22 LTS or newer (incl. `npm`, `npx`) | Most public MCP servers are `npx` packages; JS/TS language profiles | `node -v`, `npx -v` |
| **OpenAI API key** | with access to at least one tool‑calling model | The LLM | Settings → LLM → "List models" |

### Install on Windows (PowerShell)

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.14 -e
winget install --id OpenJS.NodeJS.LTS -e
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Restart the terminal afterwards so PATH updates take effect.

### Git settings (Windows)

```powershell
git config --global core.longpaths true      # worktrees + node_modules create long paths
git config --global core.autocrlf input      # keep LF in generated code
```

## 2. Optional (needed for specific features)

| Tool | Needed for | Check |
|---|---|---|
| **Read‑only git token** (e.g. GitHub fine‑grained, Contents: read) | Only for cloning **private** repos. The app never pushes or opens PRs | Settings → Git → "Test token" |
| **Docker Desktop** | Sandboxed code runner (M5) | `docker version` |
| **Java 21 + Maven** | Java language profile (experimental) | `java -version`, `mvn -v` |
| **.NET 8 SDK** | C# language profile (experimental) | `dotnet --version` |
| **Go 1.22+** | Go language profile (experimental) | `go version` |
| **Rust (rustup)** | Rust language profile (experimental) | `cargo --version` |

The Settings → Languages tab shows which toolchains it finds. Missing ones are greyed out in the language picker.

## 3. First‑time project setup

```powershell
git clone <this repo> AgentOrchestration
cd AgentOrchestration
.\start.ps1                     # installs deps into .venv and web/node_modules, builds the UI, starts the server
uv run pytest                   # should pass with no network or API calls
```

The app opens at http://127.0.0.1:8000 (bound to localhost only). Enter your OpenAI API key in **Settings**: environment variables are not used for the key (ADR‑021).

### Virtual environment

Everything the project needs lives in the project's own virtual env at `.venv\` (Python 3.14, all dependencies, and the dev tools: pytest, ruff, mypy, and `uv` itself). Nothing is installed globally except the `uv` launcher.

- `uv run <cmd>` always runs inside `.venv`, with no activation needed.
- To activate it in a shell instead: `.\.venv\Scripts\Activate.ps1` (PowerShell) or `source .venv/Scripts/activate` (Git Bash). Then `uvicorn api.main:app`, `pytest`, and so on work directly.
- VS Code: select `.venv\Scripts\python.exe` as the interpreter.
- To rebuild from scratch: delete `.venv` and run `uv sync`.

## 4. Environment variables

All variables are listed in [`.env.example`](../.env.example). Important ones:

| Variable | Required | Meaning |
|---|---|---|
| `OPENAI_API_KEY` | ✅ | OpenAI key. Never commit it. |
| `OPENAI_BASE_URL` | – | Override for proxies or OpenAI‑compatible gateways |
| `DEFAULT_MODEL` / `CHEAP_MODEL` | – | Defaults for new agents. Pick from Settings → LLM → "List models" |
| `APP_DATA_DIR` | – | SQLite DB + logs (default `./data`) |
| `WORKSPACES_DIR` | – | Default parent folder for new projects (default `./workspaces`). Use a short path on Windows, e.g. `C:\aw` |
| `GITHUB_TOKEN` | – | Only if not stored in the keyring via Settings |
| `MAX_COST_PER_RUN_USD` | – | Hard cap per run (default 2.00) |
| `LOG_LEVEL` | – | `INFO` by default |

## 5. Smoke test MCP servers (used in demos and tests)

These are public reference servers. No accounts needed:

```powershell
npx -y @modelcontextprotocol/server-filesystem C:\temp\mcp-sandbox
npx -y @modelcontextprotocol/server-memory
uvx mcp-server-fetch
uvx mcp-server-time
```

Each should start and wait on stdin (Ctrl+C to exit). If `npx` isn't found from the app, use the full path to `npx.cmd` in the server config.

## 6. Recommended editor setup (VS Code)

- Extensions: Python, Pylance, Ruff, Even Better TOML, YAML, markdownlint, GitLens.
- Select the interpreter at `.venv\Scripts\python.exe`.
- Format on save with Ruff.

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `npx` / `uvx` not found when the app starts an MCP server | Restart VS Code/terminal after installing; or set the full path (`C:\Program Files\nodejs\npx.cmd`) in the server config |
| MCP server shows "connected" but no tools | Check the server's stderr in Settings → MCP → server → Logs; many servers need env vars (API keys) |
| `Filename too long` during worktree or npm install | `git config --global core.longpaths true`; use a short `WORKSPACES_DIR` such as `C:\aw` |
| `401` from OpenAI | Key missing or wrong in `.env`; restart the app after editing `.env` |
| `model not found` | The model in the agent definition isn't available to your key. Use Settings → LLM → "List models" |
| `ImportError: cannot import name 'RequestContext' from 'mcp.shared.context'` | `mcp` 2.x got installed; it's incompatible with `langchain-mcp-adapters` 0.3. Run `uv sync` (the lockfile pins `mcp<2`, ADR‑016) |
| `DeprecationWarning ... asyncio.iscoroutinefunction` in test output | Comes from LangChain/LangSmith on Python 3.14; harmless |
| Browser shows "UI not built yet" | Run `.\start.ps1 -Rebuild` (or `npm --prefix web install; npm --prefix web run build`) |
| TypeScript project tests fail to load | Node.js 22.18+ is required for type stripping (`node -v`) |
