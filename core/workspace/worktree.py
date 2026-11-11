"""Per-build branches and worktrees (local only; ADR-008, ADR-011)."""

from __future__ import annotations

import contextlib
import shutil
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from core.workspace.git import GitError, commit_all, git, is_clean

FinishAction = Literal["merge", "keep", "discard"]


class Workspace(BaseModel):
    """An isolated checkout for one build."""

    repo: str  # project root (main checkout)
    path: str  # worktree folder
    branch: str
    base_branch: str


def start_worktree(repo: Path, worktrees_dir: Path, run_id: str, base_branch: str) -> Workspace:
    """Create branch `agents/<run_id>` from the base branch in a new worktree."""
    worktrees_dir.mkdir(parents=True, exist_ok=True)
    path = (worktrees_dir / run_id).resolve()
    branch = f"agents/{run_id}"
    git(repo, "worktree", "add", "-q", "-b", branch, str(path), base_branch)
    return Workspace(repo=str(repo), path=str(path), branch=branch, base_branch=base_branch)


def commit(ws: Workspace, message: str, author: tuple[str, str]) -> str | None:
    """Commit everything in the worktree."""
    return commit_all(Path(ws.path), message, author)


def changed_files(repo: Path, base_branch: str, branch: str) -> list[str]:
    """Files changed on `branch` since it left `base_branch`."""
    out = git(repo, "diff", "--name-only", f"{base_branch}...{branch}")
    return [line for line in out.splitlines() if line.strip()]


def diff(repo: Path, base_branch: str, branch: str, max_chars: int = 80_000) -> str:
    """Unified diff of the branch against its base."""
    out = git(repo, "diff", f"{base_branch}...{branch}")
    return out if len(out) <= max_chars else out[:max_chars] + "\n[diff truncated]"


def show_file(repo: Path, ref: str, rel: str) -> str:
    """File content at a git ref."""
    if ".." in Path(rel).parts:
        raise GitError("Invalid path.")
    return git(repo, "show", f"{ref}:{rel}")


def remove_worktree(ws: Workspace) -> None:
    """Remove the worktree folder (keeps the branch)."""
    repo = Path(ws.repo)
    with contextlib.suppress(GitError):
        git(repo, "worktree", "remove", "--force", ws.path)
    shutil.rmtree(ws.path, ignore_errors=True)
    with contextlib.suppress(GitError):
        git(repo, "worktree", "prune")


def finish(ws: Workspace, action: FinishAction, author: tuple[str, str], message: str) -> str:
    """Merge, keep or discard a build branch. Returns a short description."""
    repo = Path(ws.repo)
    if action == "merge":
        from core.workspace.git import current_branch

        if current_branch(repo) != ws.base_branch:
            raise GitError(f"The project checkout is not on '{ws.base_branch}'; switch back before merging.")
        if not is_clean(repo):
            raise GitError("The project checkout has uncommitted changes; commit or stash them before merging.")
        remove_worktree(ws)
        git(repo, "merge", "--no-ff", "-q", "-m", message, ws.branch, author=author)
        git(repo, "branch", "-q", "-d", ws.branch)
        return f"Merged {ws.branch} into {ws.base_branch}."
    if action == "keep":
        remove_worktree(ws)
        return f"Kept branch {ws.branch} (not merged)."
    remove_worktree(ws)
    with contextlib.suppress(GitError):
        git(repo, "branch", "-q", "-D", ws.branch)
    return f"Discarded {ws.branch}."
