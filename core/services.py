"""Wire up the engine's services. Shared by the Streamlit app and the REST API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import yaml
from pydantic import BaseModel, SecretStr
from sqlalchemy import Engine

from core.config import Settings
from core.llm.errors import friendly_error
from core.llm.models import list_models
from core.pipeline.service import PipelineService
from core.prefs import PrefStore, UserPrefs
from core.pricing import ModelPrice, PriceTable
from core.runtime.agent_def import AgentStore
from core.runtime.run_service import ModelFactory, RunService
from core.secrets import SecretStore
from core.storage import create_db_engine
from core.tools.builtin import builtin_tools
from core.tools.registry import ToolRegistry
from core.workspace.projects import ProjectStore

OPENAI_KEY = "openai_api_key"
GITHUB_TOKEN = "github_token"
KeySource = Literal["saved", "missing"]


class KeyStatus(BaseModel):
    """Where the active OpenAI key comes from (never the key itself)."""

    configured: bool
    source: KeySource
    hint: str | None = None  # last 4 characters
    location: str


class KeyCheck(BaseModel):
    """Result of verifying a key against the provider."""

    ok: bool
    message: str
    models: int = 0


@dataclass
class Services:
    """Everything a front end needs."""

    settings: Settings
    db: Engine
    tools: ToolRegistry
    agents: AgentStore
    prices: PriceTable
    runs: RunService
    secrets: SecretStore
    prefs: PrefStore
    projects: ProjectStore
    pipelines: PipelineService
    env_openai_key: SecretStr | None = None
    env_default_model: str = ""
    env_cheap_model: str = ""
    _known_secrets: set[str] = field(default_factory=set)

    # ---- user config (UI-saved values override .env) -----------------------------

    def reload_user_config(self) -> UserPrefs:
        """Re-apply the saved key and preferences onto `settings` (cheap; call per request)."""
        saved = self.secrets.get(OPENAI_KEY)
        # The key is entered in the UI only (ADR-018 amended): environment variables are ignored.
        self.settings.openai_api_key = SecretStr(saved) if saved else None
        prefs = self.prefs.load()
        self.settings.default_model = prefs.default_model or self.env_default_model
        self.settings.cheap_model = prefs.cheap_model or self.env_cheap_model
        if prefs.git_author_name:
            self.settings.git_author_name = prefs.git_author_name
        if prefs.git_author_email:
            self.settings.git_author_email = prefs.git_author_email
        key = self.settings.openai_api_key.get_secret_value() if self.settings.openai_api_key else ""
        if key and key not in self._known_secrets:
            self._known_secrets.add(key)
            self.runs.refresh_secrets(self._known_secrets)
        return prefs

    def key_status(self) -> KeyStatus:
        """Status of the OpenAI key."""
        saved = self.secrets.get(OPENAI_KEY)
        active = self.settings.openai_api_key.get_secret_value() if self.settings.openai_api_key else ""
        source: KeySource = "saved" if saved else "missing"
        return KeyStatus(
            configured=bool(active.strip()),
            source=source,
            hint=f"…{active[-4:]}" if len(active) >= 8 else None,
            location=self.secrets.location,
        )

    async def verify_openai_key(self, key: str) -> KeyCheck:
        """Check a key by listing models with it (nothing is saved)."""
        key = key.strip()
        if not key:
            return KeyCheck(ok=False, message="Enter a key.")
        trial = self.settings.model_copy(update={"openai_api_key": SecretStr(key)})
        try:
            models = await list_models("openai", trial, chat_only=False)
        except Exception as exc:
            return KeyCheck(ok=False, message=friendly_error(exc))
        return KeyCheck(ok=True, message=f"Key works: {len(models)} models available.", models=len(models))

    async def save_openai_key(self, key: str) -> KeyCheck:
        """Verify, then store the key in the secret store and activate it."""
        check = await self.verify_openai_key(key)
        if check.ok:
            self.secrets.set(OPENAI_KEY, key.strip())
            self.reload_user_config()
        return check

    def remove_openai_key(self) -> None:
        """Delete the saved key."""
        self.secrets.delete(OPENAI_KEY)
        self.reload_user_config()

    def save_prefs(self, **changes: object) -> UserPrefs:
        """Persist preferences and apply them."""
        self.prefs.save(**changes)
        return self.reload_user_config()

    # ---- prices -------------------------------------------------------------------

    def save_prices(self, prices: dict[str, ModelPrice]) -> None:
        """Replace the price table in memory and in `config/prices.yaml`."""
        self.prices.models.clear()
        self.prices.models.update(prices)
        path = self.settings.config_dir / "prices.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        body = {"models": {k: v.model_dump(exclude_none=True) for k, v in sorted(prices.items())}}
        header = "# Model prices in USD per 1M tokens (edited from Settings → Pricing).\n"
        path.write_text(header + yaml.safe_dump(body, sort_keys=False), encoding="utf-8")


def build_services(
    settings: Settings,
    *,
    model_factory: ModelFactory | None = None,
    db: Engine | None = None,
    secrets: SecretStore | None = None,
) -> Services:
    """Create the DB, register builtin tools, seed agents, apply UI-saved key/preferences."""
    db = db or create_db_engine(settings.db_path)
    tools = ToolRegistry(db)
    settings.samples_dir.mkdir(parents=True, exist_ok=True)
    for tool in builtin_tools(settings.samples_dir):
        tools.register(tool, "python", replace=True)

    agents = AgentStore(db)
    agents_dir = settings.config_dir / "agents"
    if agents_dir.is_dir():
        agents.import_yaml_dir(agents_dir)  # adds missing defaults, keeps user edits

    prices = PriceTable.load(settings.config_dir / "prices.yaml")
    runs = RunService(db, settings, tools, prices, model_factory=model_factory)
    projects = ProjectStore(db, settings)
    pipelines = PipelineService(
        db,
        settings,
        agents,
        projects,
        prices,
        model_factory=runs.model_factory,
        redactor=lambda: runs.redactor,
    )
    services = Services(
        settings=settings,
        db=db,
        tools=tools,
        agents=agents,
        prices=prices,
        runs=runs,
        secrets=secrets or SecretStore(),
        prefs=PrefStore(db),
        projects=projects,
        pipelines=pipelines,
        env_openai_key=settings.openai_api_key,
        env_default_model=settings.default_model,
        env_cheap_model=settings.cheap_model,
    )
    services.reload_user_config()
    return services
