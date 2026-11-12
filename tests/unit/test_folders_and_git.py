from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from core.config import Settings
from core.storage import create_db_engine
from core.workspace.folders import list_folders
from core.workspace.projects import ProjectError, ProjectStore


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True, capture_output=True
    )


def test_list_folders_flags_git_and_skips_hidden(tmp_path: Path) -> None:
    (tmp_path / "plain").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    (tmp_path / "file.txt").write_text("x")
    listing = list_folders(str(tmp_path))
    names = {e.name: e.is_git for e in listing.entries}
    assert names == {"plain": False, "repo": True}
    assert listing.parent == str(tmp_path.parent)
    assert listing.shortcuts and listing.shortcuts[0].name == "Home"


def test_list_folders_roots_and_missing(tmp_path: Path) -> None:
    assert list_folders(None).entries  # drives (Windows) or "/"
    with pytest.raises(FileNotFoundError):
        list_folders(str(tmp_path / "nope"))


def test_existing_folders_need_no_git(tmp_path: Path, settings: Settings) -> None:
    """Any folder is a valid project: plain, git, or git with uncommitted changes. Git is never run."""
    store = ProjectStore(create_db_engine(":memory:"), settings)
    plain = tmp_path / "plain"
    plain.mkdir()
    project = store.add_existing("plain", "python", str(plain))
    assert project.kind == "local" and project.base_branch == ""
    assert not (plain / ".git").exists()
    dirty = tmp_path / "dirty"
    dirty.mkdir()
    _git(dirty, "init", "-q", "-b", "main")
    (dirty / "a.txt").write_text("uncommitted")
    store.add_existing("dirty", "python", str(dirty))
    with pytest.raises(ProjectError, match="Folder not found"):
        store.add_existing("ghost", "python", str(tmp_path / "ghost"))
    with pytest.raises(ProjectError, match="Name must be"):
        store.add_existing("bad name", "python", str(dirty))


def test_new_project_has_no_git(tmp_path: Path, settings: Settings) -> None:
    settings.workspaces_dir = tmp_path / "ws"
    store = ProjectStore(create_db_engine(":memory:"), settings)
    project = store.create("fresh", "python")
    root = Path(project.path)
    assert (root / "README.md").is_file() and not (root / ".git").exists()


def test_change_tracking(tmp_path: Path) -> None:
    from core.workspace import changes as ch

    (tmp_path / "keep.txt").write_text("same\n")
    (tmp_path / "edit.txt").write_text("old\n")
    (tmp_path / "gone.txt").write_text("bye\n")
    (tmp_path / "node_modules").mkdir()
    base = ch.capture(tmp_path)
    (tmp_path / "edit.txt").write_text("new\n")
    (tmp_path / "gone.txt").unlink()
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "added.py").write_text("x = 1\n")
    (tmp_path / "node_modules" / "dep.js").write_text("ignored")
    found = {(c.path, c.kind) for c in ch.changes(base, tmp_path)}
    assert found == {("edit.txt", "modified"), ("gone.txt", "deleted"), ("pkg/added.py", "added")}
    d = ch.diff(base, tmp_path)
    assert "-old" in d and "+new" in d and "+x = 1" in d and "-bye" in d and "keep.txt" not in d
