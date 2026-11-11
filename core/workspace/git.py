"""Thin, safe wrapper around the git CLI (local operations only; never pushes)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

GIT_TIMEOUT_S = 60


class GitError(RuntimeError):
    """A git command failed."""


def git(cwd: Path, *args: str, author: tuple[str, str] | None = None, check: bool = True) -> str:
    """Run `git <args>` in `cwd` and return stdout."""
    exe = shutil.which("git")
    if exe is None:
        raise GitError("git is not installed or not on PATH.")
    if "push" in args:
        raise GitError("Pushing is not allowed (ADR-011: local git only).")
    cmd = [exe]
    if author:
        cmd += ["-c", f"user.name={author[0]}", "-c", f"user.email={author[1]}"]
    # Respect the user's own git config (e.g. core.autocrlf on Windows); only enable long paths.
    cmd += ["-c", "core.longpaths=true", *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as e:
        raise GitError(f"git {' '.join(args)} timed out") from e
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {(proc.stderr or proc.stdout).strip()[:500]}")
    return proc.stdout


def is_repo(path: Path) -> bool:
    """True if `path` is the top level of a git work tree."""
    try:
        top = git(path, "rev-parse", "--show-toplevel").strip()
    except GitError, OSError:
        return False
    return Path(top).resolve() == path.resolve()


def current_branch(path: Path) -> str:
    """Checked-out branch name."""
    return git(path, "rev-parse", "--abbrev-ref", "HEAD").strip()


def is_clean(path: Path) -> bool:
    """No uncommitted changes."""
    return git(path, "status", "--porcelain").strip() == ""


def commit_all(path: Path, message: str, author: tuple[str, str]) -> str | None:
    """Stage everything and commit; returns the commit sha, or None if nothing changed."""
    git(path, "add", "-A")
    if git(path, "diff", "--cached", "--name-only").strip() == "":
        return None
    git(path, "commit", "-q", "-m", message, author=author)
    return git(path, "rev-parse", "HEAD").strip()
