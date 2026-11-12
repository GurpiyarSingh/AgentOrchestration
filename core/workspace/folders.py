"""Folder selection for the UI.

Browsers can't reveal real filesystem paths, but Codeloom's server runs on the user's own
machine, so it can (a) open the native OS folder dialog, and (b) list folders for the
in-app folder browser. Both are local-only features (the server binds to 127.0.0.1).
"""

from __future__ import annotations

import os
import string
import subprocess
import sys
from pathlib import Path

from pydantic import BaseModel

PICKER_TIMEOUT_S = 600
MAX_ENTRIES = 600

# Runs in a separate process: Tk must own the main thread, which the web server can't give it.
_PICKER = r"""
import sys, tkinter as tk
from tkinter import filedialog
root = tk.Tk()
root.withdraw()
root.attributes("-topmost", True)
root.update()
path = filedialog.askdirectory(parent=root, title=sys.argv[1], initialdir=sys.argv[2] or None, mustexist=True)
root.destroy()
sys.stdout.write(path or "")
"""


class FolderPickerError(RuntimeError):
    """The native folder dialog could not be shown."""


class FolderEntry(BaseModel):
    name: str
    path: str
    is_git: bool


class FolderListing(BaseModel):
    path: str | None  # None = the list of drives / roots
    parent: str | None
    is_git: bool
    entries: list[FolderEntry]
    shortcuts: list[FolderEntry]


def pick_folder_native(title: str = "Choose a folder", initial: str | None = None) -> str | None:
    """Open the OS folder dialog (blocking). Returns the chosen path, or None if cancelled."""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _PICKER, title, initial or ""],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=PICKER_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as e:
        raise FolderPickerError("The folder dialog was left open too long.") from e
    except OSError as e:
        raise FolderPickerError(f"Could not open the folder dialog: {e}") from e
    if proc.returncode != 0:
        raise FolderPickerError("The system folder dialog is not available here; use the in-app browser.")
    chosen = proc.stdout.strip()
    return str(Path(chosen).resolve()) if chosen else None


def _is_git(p: Path) -> bool:
    try:
        return (p / ".git").exists()
    except OSError:
        return False


def _roots() -> list[FolderEntry]:
    if os.name == "nt":
        drives = [f"{d}:\\" for d in string.ascii_uppercase if Path(f"{d}:\\").exists()]
        return [FolderEntry(name=d, path=d, is_git=False) for d in drives]
    return [FolderEntry(name="/", path="/", is_git=False)]


def _shortcuts() -> list[FolderEntry]:
    home = Path.home()
    out = [FolderEntry(name="Home", path=str(home), is_git=False)]
    for name in ("Desktop", "Documents", "source", "repos", "projects", "code"):
        p = home / name
        if p.is_dir():
            out.append(FolderEntry(name=name, path=str(p), is_git=_is_git(p)))
    return out


def list_folders(path: str | None) -> FolderListing:
    """Sub-folders of `path` (or the drives when None), flagging git repositories."""
    if not path:
        return FolderListing(path=None, parent=None, is_git=False, entries=_roots(), shortcuts=_shortcuts())
    p = Path(path).expanduser()
    try:
        p = p.resolve()
    except OSError as e:
        raise FileNotFoundError(f"Folder not found: {path}") from e
    if not p.is_dir():
        raise FileNotFoundError(f"Folder not found: {path}")
    entries: list[FolderEntry] = []
    try:
        children = sorted((c for c in p.iterdir() if c.is_dir()), key=lambda c: c.name.lower())
    except PermissionError as e:
        raise PermissionError(f"No permission to open {p}") from e
    for c in children:
        if c.name.startswith(("$", ".")) or c.name in {"node_modules", "__pycache__", "System Volume Information"}:
            continue
        try:
            entries.append(FolderEntry(name=c.name, path=str(c), is_git=_is_git(c)))
        except OSError:
            continue
        if len(entries) >= MAX_ENTRIES:
            break
    parent = None if p.parent == p else str(p.parent)
    return FolderListing(path=str(p), parent=parent, is_git=_is_git(p), entries=entries, shortcuts=_shortcuts())
