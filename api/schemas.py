"""Request/response models for the REST API (they appear in Swagger)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from core.chat import ChatTurn
from core.models import RunRecord
from core.prefs import UserPrefs
from core.pricing import ModelPrice
from core.services import KeyStatus
from core.tracing.queries import UsageSummary


class Health(BaseModel):
    status: str = "ok"
    openai_configured: bool
    default_model: str
    agents: int
    tools: int
    projects: int
    mcp_connected: int = 0


class UsageReport(BaseModel):
    today: UsageSummary
    all_time: UsageSummary


# ---- settings ------------------------------------------------------------------------------


class SettingsView(BaseModel):
    key: KeyStatus
    prefs: UserPrefs
    default_model: str
    cheap_model: str
    git_author_name: str
    git_author_email: str
    github_token_set: bool
    data_dir: str
    workspaces_dir: str
    runner_timeout_s: int


class KeyRequest(BaseModel):
    key: str = Field(min_length=1)
    save: bool = True


class TokenRequest(BaseModel):
    token: str = Field(min_length=1)


class PricesBody(BaseModel):
    models: dict[str, ModelPrice]


# ---- tools ---------------------------------------------------------------------------------


class ToolInfo(BaseModel):
    name: str
    source: str
    description: str
    enabled: bool
    requires_approval: bool
    invokable: bool
    used_by: list[str] = Field(default_factory=list)
    args_schema: dict[str, Any]


class ToolFlags(BaseModel):
    enabled: bool | None = None
    requires_approval: bool | None = None


class ToolInvokeRequest(BaseModel):
    args: dict[str, Any] = Field(default_factory=dict, examples=[{"expression": "sqrt(16) * 5"}])


# ---- agents --------------------------------------------------------------------------------


class AgentYaml(BaseModel):
    yaml: str
    overwrite: bool = False


# ---- chat / runs ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    model: str | None = Field(default=None, description='"provider:model"; default model if omitted')
    messages: list[ChatTurn]


class ChatResponse(BaseModel):
    run_id: str
    text: str
    input_tokens: int
    output_tokens: int
    model: str | None


class RunRequest(BaseModel):
    agent: str = Field(examples=["assistant"])
    message: str | None = Field(default=None, examples=["What is 17% of 2,340? Use the calculator."])
    messages: list[ChatTurn] | None = None
    model: str | None = None

    @model_validator(mode="after")
    def _has_input(self) -> RunRequest:
        if not self.messages and not (self.message or "").strip():
            raise ValueError("Provide `message` or `messages`.")
        return self

    def history(self) -> list[ChatTurn]:
        return self.messages or [ChatTurn(role="user", content=self.message or "")]


class RunSummary(BaseModel):
    run_id: str
    kind: str
    target: str
    status: str
    input: str
    output: str | None
    started_at: datetime
    ended_at: datetime | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model_calls: int
    tool_calls: int

    @classmethod
    def of(cls, r: RunRecord) -> RunSummary:
        return cls(
            run_id=r.id,
            kind=r.kind,
            target=r.target_id,
            status=r.status,
            input=r.input,
            output=r.output,
            started_at=r.started_at,
            ended_at=r.ended_at,
            input_tokens=r.input_tokens,
            output_tokens=r.output_tokens,
            cost_usd=r.cost_usd,
            model_calls=r.model_calls,
            tool_calls=r.tool_calls,
        )


# ---- projects / builds -----------------------------------------------------------------------


class ProjectCreate(BaseModel):
    name: str = Field(examples=["text-utils"])
    language: Literal["python", "javascript", "typescript"] = "python"
    mode: Literal["new", "existing"] = "new"
    path: str | None = Field(default=None, description="Folder (optional for new, required for existing)")


class PickFolderRequest(BaseModel):
    title: str = "Choose a folder"
    initial: str | None = None


class PickFolderResult(BaseModel):
    path: str | None
    cancelled: bool
    is_git: bool = False
