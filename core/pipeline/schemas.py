"""Data shapes of the build pipeline (structured agent outputs and the run snapshot)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from core.workspace.runner import TestReport

StageKind = Literal["requirements", "architecture", "tests", "code", "run", "fix", "review"]
StageStatus = Literal["pending", "running", "done", "failed", "skipped"]
PipelineStatus = Literal["running", "done", "needs_attention", "failed", "cancelled"]


class Spec(BaseModel):
    """Requirements analyst output."""

    title: str = Field(description="Short name of the feature/module")
    summary: str = Field(description="2-4 sentence description of the required behaviour")
    acceptance_criteria: list[str] = Field(description="Concrete, testable criteria")
    assumptions: list[str] = Field(default_factory=list, description="Decisions taken to resolve ambiguity")
    out_of_scope: list[str] = Field(default_factory=list)


class PlannedFile(BaseModel):
    """One file in the architect's plan."""

    path: str = Field(description="Path relative to the project root")
    kind: Literal["source", "test"]
    purpose: str


class Plan(BaseModel):
    """Architect output."""

    approach: str
    files: list[PlannedFile]
    interfaces: str = Field(description="Exact public API (code signatures with behaviour comments)")


class ReviewIssue(BaseModel):
    """One review finding."""

    severity: Literal["high", "medium", "low"]
    file: str
    message: str


class Review(BaseModel):
    """Code reviewer output."""

    approved: bool
    summary: str
    issues: list[ReviewIssue] = Field(default_factory=list)


class StageRun(BaseModel):
    """One execution of a pipeline stage."""

    id: str
    stage: StageKind
    agent: str
    title: str
    status: StageStatus = "pending"
    attempt: int = 1
    started_at: datetime | None = None
    ended_at: datetime | None = None
    summary: str = ""
    model: str | None = None
    model_calls: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class PipelineTotals(BaseModel):
    """Usage across the whole build."""

    model_calls: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class PipelineRequest(BaseModel):
    """Start a build."""

    project_id: str
    requirement: str = Field(min_length=10, description="What to build, in plain language")
    model: str | None = Field(default=None, description='Override all agents\' model, e.g. "openai:gpt-5.4-mini"')
    max_fix_attempts: int = Field(default=3, ge=0, le=6)
    max_review_rounds: int = Field(default=1, ge=0, le=3)


class PipelineSnapshot(BaseModel):
    """Full state of a build, live or finished."""

    run_id: str
    project_id: str
    project_name: str
    language: str
    requirement: str
    status: PipelineStatus = "running"
    started_at: datetime
    ended_at: datetime | None = None
    stages: list[StageRun] = Field(default_factory=list)
    spec: Spec | None = None
    plan: Plan | None = None
    test_report: TestReport | None = None
    review: Review | None = None
    files: list[str] = Field(default_factory=list)
    branch: str = ""
    base_branch: str = ""
    worktree: str = ""
    repo_path: str = ""
    fix_attempts: int = 0
    review_rounds: int = 0
    final_action: Literal["merged", "kept", "discarded"] | None = None
    message: str = ""
    error: str | None = None
    totals: PipelineTotals = Field(default_factory=PipelineTotals)


class PipelineSummary(BaseModel):
    """Row in the builds list."""

    run_id: str
    project_id: str
    project_name: str
    title: str
    status: PipelineStatus
    final_action: str | None
    started_at: datetime
    ended_at: datetime | None
    tests: str
    total_tokens: int
