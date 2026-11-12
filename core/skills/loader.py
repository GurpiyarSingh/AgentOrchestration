"""Skills: folders with a SKILL.md (YAML front matter `name`, `description` + instructions) and
optional reference files.

Agents see only the name and description of their skills in the system prompt; they call
`skill__load` to read the full instructions when relevant (progressive disclosure), and
`skill__read_file` for reference files inside the skill folder.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import yaml
from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, Field

from core.runtime.agent_def import AgentDef

_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,48}$")
_FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.S)
MAX_SKILL_CHARS = 40_000


class SkillError(ValueError):
    """Invalid skill or skill request."""


class Skill(BaseModel):
    name: str
    description: str
    body: str
    files: list[str] = Field(default_factory=list)
    path: str


def parse_skill_md(text: str, fallback_name: str) -> tuple[str, str, str]:
    """(name, description, body) from SKILL.md content."""
    m = _FRONT.match(text.lstrip("﻿"))
    if not m:
        return fallback_name, "", text.strip()
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        raise SkillError(f"Invalid front matter in {fallback_name}/SKILL.md: {e}") from e
    if not isinstance(meta, dict):
        meta = {}
    return str(meta.get("name") or fallback_name), str(meta.get("description") or "").strip(), m.group(2).strip()


def render_skill_md(name: str, description: str, body: str) -> str:
    front = yaml.safe_dump({"name": name, "description": description}, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{front}\n---\n\n{body.strip()}\n"


class SkillStore:
    """Skills on disk under `root` (one folder per skill)."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def list_all(self) -> list[Skill]:
        if not self.root.is_dir():
            return []
        out = []
        for d in sorted(p for p in self.root.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()):
            try:
                out.append(self._load(d))
            except SkillError:
                continue
        return out

    def get(self, name: str) -> Skill:
        d = self.root / name
        if not _NAME_RE.match(name) or not (d / "SKILL.md").is_file():
            raise SkillError(f"Skill '{name}' not found.")
        return self._load(d)

    def _load(self, d: Path) -> Skill:
        _name, desc, body = parse_skill_md((d / "SKILL.md").read_text(encoding="utf-8"), d.name)
        files = sorted(p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file() and p.name != "SKILL.md")
        return Skill(name=d.name, description=desc, body=body, files=files, path=str(d))

    def save(self, name: str, description: str, body: str) -> Skill:
        name = name.strip()
        if not _NAME_RE.match(name):
            raise SkillError(
                "Skill name must be 2-49 characters: lowercase letters, digits and '-', starting with a letter."
            )
        if not description.strip():
            raise SkillError("A description is required: it is how agents decide when to load the skill.")
        if len(body) > MAX_SKILL_CHARS:
            raise SkillError("Skill instructions are too long (max 40,000 characters).")
        d = self.root / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(render_skill_md(name, description.strip(), body), encoding="utf-8", newline="\n")
        return self.get(name)

    def delete(self, name: str) -> None:
        skill = self.get(name)
        shutil.rmtree(skill.path)

    def read_file(self, name: str, rel: str) -> str:
        skill = self.get(name)
        root = Path(skill.path).resolve()
        target = (root / rel).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise SkillError(f"File '{rel}' not found in skill '{name}'.")
        return target.read_text(encoding="utf-8", errors="replace")[:MAX_SKILL_CHARS]

    # ---- agent integration --------------------------------------------------------------

    def prompt_section(self, names: list[str]) -> str:
        """System-prompt text listing the agent's skills (names + descriptions only)."""
        skills = [s for s in self.list_all() if s.name in names]
        if not skills:
            return ""
        lines = "\n".join(f"- {s.name}: {s.description}" for s in skills)
        return (
            "\n\n## Skills\nYou have these skills. When a task matches a skill's description, call "
            "skill__load with its name BEFORE doing the task and follow its instructions.\n" + lines
        )

    def tools_for(self, names: list[str]) -> list[BaseTool]:
        """`skill__load` / `skill__read_file`, restricted to the given skills."""
        allowed = set(names)

        def load(name: str) -> str:
            """Load the full instructions of one of your skills by name."""
            if name not in allowed:
                raise ToolException(f"'{name}' is not one of your skills: {', '.join(sorted(allowed))}.")
            try:
                s = self.get(name)
            except SkillError as e:
                raise ToolException(str(e)) from e
            files = f"\n\nReference files (read with skill__read_file): {', '.join(s.files)}" if s.files else ""
            return f"# Skill: {s.name}\n\n{s.body}{files}"

        def read_file(name: str, path: str) -> str:
            """Read a reference file that belongs to one of your skills."""
            if name not in allowed:
                raise ToolException(f"'{name}' is not one of your skills.")
            try:
                return self.read_file(name, path)
            except SkillError as e:
                raise ToolException(str(e)) from e

        return [
            StructuredTool.from_function(
                func=load, name="skill__load", description=load.__doc__ or "", handle_tool_error=True
            ),
            StructuredTool.from_function(
                func=read_file, name="skill__read_file", description=read_file.__doc__ or "", handle_tool_error=True
            ),
        ]


def apply_skills(agent: AgentDef, store: SkillStore | None) -> tuple[AgentDef, list[BaseTool]]:
    """Agent with its skills advertised in the system prompt, plus the skill tools to give it."""
    if store is None or not agent.skills:
        return agent, []
    section = store.prompt_section(agent.skills)
    if not section:
        return agent, []
    return agent.model_copy(update={"system_prompt": agent.system_prompt + section}), store.tools_for(agent.skills)


def inline_skills(agent: AgentDef, store: SkillStore | None) -> str:
    """Full skill instructions, for one-shot stages that can't call tools."""
    if store is None or not agent.skills:
        return ""
    parts = []
    for name in agent.skills:
        try:
            s = store.get(name)
        except SkillError:
            continue
        parts.append(f"## Skill: {s.name}\n{s.body}")
    return "\n\n# Skills to apply\n" + "\n\n".join(parts) if parts else ""
