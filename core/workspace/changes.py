"""Track what a build changes in a project folder, without git (ADR-023).

Before a build starts we record a hash of every file (plus the text of small files), so we can
later list created / modified / deleted files and render a unified diff. Nothing here writes to
the project folder or runs git.
"""

from __future__ import annotations

import difflib
import hashlib
from pathlib import Path

from pydantic import BaseModel, Field

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
MAX_TEXT_BYTES = 400_000  # keep the original text of files up to this size (for diffs)
MAX_TOTAL_TEXT = 40_000_000  # and up to this much in total


class FolderState(BaseModel):
    """File hashes (and small originals) of a folder at one moment."""

    hashes: dict[str, str] = Field(default_factory=dict)
    texts: dict[str, str] = Field(default_factory=dict)


class Change(BaseModel):
    """One changed file."""

    path: str
    kind: str  # "added" | "modified" | "deleted"


def _walk(root: Path) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    if not root.is_dir():
        return out
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts) or not p.is_file():
            continue
        out.append((rel.as_posix(), p))
    return sorted(out)


def _read(p: Path) -> bytes | None:
    try:
        return p.read_bytes()
    except OSError:
        return None


def capture(root: Path, keep_text: bool = True) -> FolderState:
    """Hash every file under `root` (skipping dependency/VCS folders)."""
    state = FolderState()
    budget = MAX_TOTAL_TEXT
    for rel, p in _walk(root.resolve()):
        data = _read(p)
        if data is None:
            continue
        state.hashes[rel] = hashlib.sha256(data).hexdigest()
        if keep_text and len(data) <= MAX_TEXT_BYTES and budget >= len(data) and b"\0" not in data[:8000]:
            state.texts[rel] = data.decode("utf-8", errors="replace")
            budget -= len(data)
    return state


def changes(before: FolderState, root: Path) -> list[Change]:
    """Files added, modified or deleted since `before`."""
    now = capture(root, keep_text=False).hashes
    out = [Change(path=r, kind="added") for r in now if r not in before.hashes]
    out += [Change(path=r, kind="modified") for r in now if r in before.hashes and now[r] != before.hashes[r]]
    out += [Change(path=r, kind="deleted") for r in before.hashes if r not in now]
    return sorted(out, key=lambda c: c.path)


def diff(before: FolderState, root: Path, max_chars: int = 80_000) -> str:
    """Unified diff of the changes since `before`."""
    root = root.resolve()
    parts: list[str] = []
    for c in changes(before, root):
        old = before.texts.get(c.path, "") if c.kind != "added" else ""
        new = ""
        if c.kind != "deleted":
            data = _read(root / c.path) or b""
            if b"\0" in data[:8000]:
                parts.append(f"Binary file {c.path} {c.kind}\n")
                continue
            new = data.decode("utf-8", errors="replace")
        if c.kind == "modified" and c.path not in before.texts:
            parts.append(f"--- a/{c.path}\n+++ b/{c.path}\n(modified; original too large to diff)\n")
            continue
        lines = difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile="/dev/null" if c.kind == "added" else f"a/{c.path}",
            tofile="/dev/null" if c.kind == "deleted" else f"b/{c.path}",
        )
        text = "".join(line if line.endswith("\n") else line + "\n" for line in lines)
        parts.append(text)
    out = "".join(parts)
    return out if len(out) <= max_chars else out[:max_chars] + "\n[diff truncated]"
