"""Application settings loaded from environment variables and `.env`."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. See `.env.example` for documentation of each field."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = None
    default_model: str = ""
    cheap_model: str = ""

    # Storage
    app_data_dir: Path = Path("data")
    workspaces_dir: Path = Path("workspaces")
    config_dir: Path = Path("config")
    samples_dir: Path = Path("samples")
    skills_dir: Path = Path("skills")  # the only folder builtin__read_text_file may read
    max_tool_output_chars: int = Field(default=20_000, ge=1_000)

    # Git
    git_author_name: str = "Agent Orchestrator"
    git_author_email: str = "agents@localhost"

    # Safety limits
    max_cost_per_run_usd: float = Field(default=2.0, ge=0)
    max_daily_cost_usd: float = Field(default=10.0, ge=0)
    max_agent_depth: int = Field(default=3, ge=1)
    runner_timeout_seconds: int = Field(default=300, ge=1)

    log_level: str = "INFO"

    @property
    def openai_configured(self) -> bool:
        """True when an OpenAI API key is available."""
        return self.openai_api_key is not None and bool(self.openai_api_key.get_secret_value().strip())

    @property
    def db_path(self) -> Path:
        """Location of the SQLite database file."""
        return self.app_data_dir / "app.db"

    def missing_key_message(self) -> str:
        """User-facing explanation of how to configure the OpenAI key."""
        return (
            "OpenAI API key not found. Add it on the Settings page (AI models tab), or set "
            "`OPENAI_API_KEY` in your environment / `.env` file and restart."
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
