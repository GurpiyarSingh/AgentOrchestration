# How to Run

## 1. Prerequisites (once)

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.14 -e
winget install --id OpenJS.NodeJS.LTS -e
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
git config --global core.longpaths true
```

Restart the terminal.

## 2. Start

```powershell
cd "D:\D Drive\Codes\AgentOrchestration"
.\start.ps1
```

Open **http://127.0.0.1:8000**

The script installs dependencies into the project's `.venv` and `web/node_modules`, builds the UI if needed, and starts the server.

## 3. First use (in the UI)

1. **Settings → OpenAI connection:** paste your API key, then click **Verify & save**.
2. **Settings → Models:** choose a **Default model** (e.g. `gpt-5.4-mini`), then click **Save**.
3. **Build:** create a project, type a requirement, then click **Start build**.

## Other commands

| What | Command |
|---|---|
| Force a UI rebuild | `.\start.ps1 -Rebuild` |
| API docs (Swagger) | http://127.0.0.1:8000/docs |
| Backend tests | `uv run pytest` |
| UI dev server (hot reload, needs the backend running) | `npm --prefix web run dev` → http://127.0.0.1:5173 |
| Start the backend only | `uv run uvicorn api.main:app --host 127.0.0.1 --port 8000` |
