"""Time and restricted file-reading tools."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.tools import BaseTool, StructuredTool, ToolException

MAX_FILE_CHARS = 20_000


def make_current_time() -> BaseTool:
    """Build the current_time tool."""

    def current_time(timezone: str = "UTC") -> str:
        """Return the current date and time in ISO 8601 format for an IANA timezone, e.g. "Europe/Berlin"."""
        try:
            tz = UTC if timezone.upper() == "UTC" else ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ToolException(f"Unknown timezone '{timezone}'. Use an IANA name like 'Asia/Kolkata'.") from e
        return datetime.now(tz).isoformat(timespec="seconds")

    return StructuredTool.from_function(
        func=current_time,
        name="builtin__current_time",
        description=current_time.__doc__ or "",
        handle_tool_error=True,
    )


def resolve_inside(root: Path, relative: str) -> Path:
    """Resolve `relative` under `root`, rejecting anything that escapes it."""
    if not relative or Path(relative).is_absolute() or Path(relative).drive or relative.startswith(("\\", "/")):
        raise ToolException("Path must be relative to the sample folder.")
    if ":" in relative:
        raise ToolException("Path may not contain ':'.")
    root_real = root.resolve()
    target = (root_real / relative).resolve()
    if not target.is_relative_to(root_real):
        raise ToolException("Path escapes the sample folder.")
    return target


def make_read_text_file(root: Path) -> BaseTool:
    """Build a read_text_file tool restricted to files under `root`."""

    def read_text_file(path: str) -> str:
        """Read a UTF-8 text file from the sample folder. `path` is relative, e.g. "notes/todo.txt".

        Use path "." to list the available files.
        """
        if path.strip() in {".", ""}:
            files = sorted(p.relative_to(root.resolve()).as_posix() for p in root.resolve().rglob("*") if p.is_file())
            return "\n".join(files) or "(no files)"
        target = resolve_inside(root, path)
        if not target.is_file():
            raise ToolException(f"File not found: {path}. Use path '.' to list files.")
        try:
            text = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            raise ToolException("File is not UTF-8 text.") from e
        if len(text) > MAX_FILE_CHARS:
            text = text[:MAX_FILE_CHARS] + f"\n[truncated: {len(text) - MAX_FILE_CHARS} more chars]"
        return text

    return StructuredTool.from_function(
        func=read_text_file,
        name="builtin__read_text_file",
        description=read_text_file.__doc__ or "",
        handle_tool_error=True,
    )
