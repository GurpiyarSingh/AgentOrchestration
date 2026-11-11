"""FastAPI app: REST API under /api, Swagger at /docs, and the React UI at /.

Run:  uv run uvicorn api.main:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.routes import router
from core.config import get_settings
from core.pipeline.service import PipelineError
from core.services import Services, build_services
from core.workspace.git import GitError
from core.workspace.projects import ProjectError

WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"

TAGS = [
    {"name": "builds", "description": "The agent team: turn a requirement into tested, reviewed code."},
    {"name": "projects", "description": "Git projects that builds write code into."},
    {"name": "agents", "description": "Agent definitions (default team + your own)."},
    {"name": "tools", "description": "Tool catalog, flags and direct invocation."},
    {"name": "runs", "description": "Chat, agent runs and traces."},
    {"name": "settings", "description": "API key, models, preferences, prices."},
    {"name": "system", "description": "Health, usage, models, languages."},
]

_NO_UI = """<!doctype html><html><head><meta charset="utf-8"><title>Codeloom</title></head>
<body style="font-family:system-ui;background:#050a08;color:#eafaf1;display:grid;place-items:center;height:100vh">
<div style="max-width:560px"><h2>UI not built yet</h2>
<p>Build the web app once, then reload:</p>
<pre style="background:#0f1a14;padding:12px;border-radius:8px">npm --prefix web install
npm --prefix web run build</pre>
<p>The API is running: <a style="color:#34d399" href="/docs">Swagger UI</a></p></div></body></html>"""


def create_app(services: Services | None = None) -> FastAPI:
    """Build the app. Pass `services` in tests; otherwise they're built from settings."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.services = services or build_services(get_settings())
        yield

    app = FastAPI(
        title="Codeloom API",
        version="0.2.0",
        description="Codeloom: your AI software team. Turns requirements into tested, reviewed code. "
        "All endpoints are under `/api`. Local use only (binds to 127.0.0.1, no auth).",
        openapi_tags=TAGS,
        lifespan=lifespan,
    )

    async def _bad_request(request: Request, exc: Exception) -> JSONResponse:
        not_found = "not found" in str(exc).lower()
        return JSONResponse(status_code=404 if not_found else 400, content={"detail": str(exc)})

    for exc_type in (ProjectError, PipelineError, GitError):
        app.add_exception_handler(exc_type, _bad_request)

    app.include_router(router)

    if (WEB_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False, response_model=None)
    async def spa(path: str) -> FileResponse | HTMLResponse | JSONResponse:
        if path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        candidate = (WEB_DIST / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(WEB_DIST.resolve()):
            return FileResponse(candidate)
        index = WEB_DIST / "index.html"
        return FileResponse(index) if index.is_file() else HTMLResponse(_NO_UI)

    return app


app = create_app()
