"""File tools for coding agents, sandboxed to one worktree (SECURITY.md T1, control 1)."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from langchain_core.tools import BaseTool, StructuredTool, ToolException

MAX_READ_CHARS = 60_000
MAX_WRITE_CHARS = 200_000
_PROTECTED = [re.compile(p, re.IGNORECASE) for p in (r"^\.git(/|$)", r"(^|/)\.env", r"\.(pem|key|pfx)$")]
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", ".venv"}


def normalize(rel: str) -> str:
    """Validate and normalise a repo-relative path, or raise ToolException."""
    raw = (rel or "").strip().replace("\\", "/")
    if not raw or raw in {".", "./"}:
        raise ToolException("Give a file path relative to the project root, e.g. 'src/app.py'.")
    if raw.startswith("/") or re.match(r"^[a-zA-Z]:", raw) or raw.startswith("//"):
        raise ToolException("Absolute paths are not allowed; use a path relative to the project root.")
    if ":" in raw:
        raise ToolException("Paths may not contain ':'.")
    parts = PurePosixPath(raw).parts
    if any(p == ".." for p in parts):
        raise ToolException("'..' is not allowed in paths.")
    clean = "/".join(p for p in parts if p not in {".", ""})
    if any(p.endswith((" ", ".")) and p not in {".", ".."} for p in clean.split("/")):
        raise ToolException("Path segments may not end with a space or dot.")
    if any(rx.search(clean) for rx in _PROTECTED):
        raise ToolException(f"'{clean}' is protected and cannot be accessed.")
    return clean


def resolve(root: Path, rel: str) -> Path:
    """Absolute path inside `root` (symlink-safe)."""
    clean = normalize(rel)
    root_real = root.resolve()
    target = (root_real / clean).resolve()
    if not target.is_relative_to(root_real):
        raise ToolException("Path escapes the project folder.")
    return target


def make_repo_tools(
    root: Path,
    *,
    can_write: Callable[[str], bool] = lambda _p: True,
    can_read: Callable[[str], bool] = lambda _p: True,
    write_rule: str = "",
) -> list[BaseTool]:
    """list_files / read_file / write_file / delete_file bound to `root`."""

    def list_files() -> str:
        """List all files in the project (relative paths, one per line)."""
        root_real = root.resolve()
        files = []
        for p in sorted(root_real.rglob("*")):
            rel = p.relative_to(root_real)
            if p.is_file() and not any(part in _SKIP_DIRS for part in rel.parts):
                files.append(rel.as_posix())
        return "\n".join(files) or "(empty project)"

    def read_file(path: str) -> str:
        """Read a UTF-8 text file from the project. `path` is relative to the project root."""
        clean = normalize(path)
        if not can_read(clean):
            raise ToolException(f"You are not allowed to read '{clean}' in this step.")
        target = resolve(root, clean)
        if not target.is_file():
            raise ToolException(f"File not found: {clean}. Call list_files to see what exists.")
        text = target.read_text(encoding="utf-8", errors="replace")
        return text if len(text) <= MAX_READ_CHARS else text[:MAX_READ_CHARS] + "\n[truncated]"

    def write_file(path: str, content: str) -> str:
        """Create or overwrite a UTF-8 text file in the project with the COMPLETE file content.

        `path` is relative to the project root; parent folders are created automatically.
        """
        clean = normalize(path)
        if not can_write(clean):
            raise ToolException(f"You may not write '{clean}' in this step. {write_rule}".strip())
        if len(content) > MAX_WRITE_CHARS:
            raise ToolException("File too large (max 200,000 characters).")
        target = resolve(root, clean)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        return f"Wrote {clean} ({len(content.splitlines())} lines)."

    def delete_file(path: str) -> str:
        """Delete a file from the project. `path` is relative to the project root."""
        clean = normalize(path)
        if not can_write(clean):
            raise ToolException(f"You may not delete '{clean}' in this step. {write_rule}".strip())
        target = resolve(root, clean)
        if not target.is_file():
            raise ToolException(f"File not found: {clean}.")
        target.unlink()
        return f"Deleted {clean}."

    return [
        StructuredTool.from_function(
            func=fn, name=f"repo__{fn.__name__}", description=fn.__doc__ or "", handle_tool_error=True
        )
        for fn in (list_files, read_file, write_file, delete_file)
    ]
