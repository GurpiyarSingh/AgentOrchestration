"""Language profiles: how code is laid out, scaffolded and tested per language.

Tests run without installing anything per project:
- Python: `python -m pytest` with the app's own interpreter (pytest is a dev dependency).
- JavaScript / TypeScript: Node's built-in test runner (`node --test`); TypeScript runs
  through Node's built-in type stripping (Node 22.18+ / 24), so only erasable syntax works.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel


@dataclass(frozen=True)
class LanguageProfile:
    """Everything language-specific the pipeline needs."""

    id: str
    name: str
    test_dir: str
    test_glob: str
    conventions: str  # injected into agent prompts
    scaffold: dict[str, str] = field(default_factory=dict)

    def test_command(self, junit_path: Path) -> list[str]:
        """Command that runs all tests and writes a JUnit XML report."""
        if self.id == "python":
            return [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                f"--junitxml={junit_path}",
                self.test_dir,
            ]
        node = shutil.which("node") or "node"
        return [
            node,
            "--test",
            "--test-reporter=spec",
            "--test-reporter-destination=stdout",
            "--test-reporter=junit",
            f"--test-reporter-destination={junit_path}",
            f"{self.test_dir}/**/{self.test_glob}",
        ]

    def is_test_path(self, rel_path: str) -> bool:
        """True for files under the test folder."""
        return rel_path.replace("\\", "/").startswith(self.test_dir + "/")


_GITIGNORE_PY = "__pycache__/\n*.pyc\n.pytest_cache/\n.venv/\n"
_GITIGNORE_JS = "node_modules/\ncoverage/\n"

PROFILES: dict[str, LanguageProfile] = {
    "python": LanguageProfile(
        id="python",
        name="Python",
        test_dir="tests",
        test_glob="test_*.py",
        conventions=(
            "Language: Python 3.12+. Standard library only (no third-party packages).\n"
            "Layout: source modules or packages at the project root (e.g. `slugify.py` or `inventory/__init__.py`); "
            "tests in `tests/test_<topic>.py` using pytest (plain `assert`, `pytest.raises`).\n"
            "Tests import source directly, e.g. `from slugify import slugify` (pytest.ini puts the root on sys.path).\n"
            "Use type hints and docstrings. Do not create setup.py/pyproject.toml."
        ),
        scaffold={
            ".gitignore": _GITIGNORE_PY,
            "pytest.ini": "[pytest]\npythonpath = .\ntestpaths = tests\n",
            "tests/__init__.py": "",
        },
    ),
    "javascript": LanguageProfile(
        id="javascript",
        name="JavaScript (Node)",
        test_dir="tests",
        test_glob="*.test.js",
        conventions=(
            "Language: modern JavaScript (ES modules) on Node.js 22+. No npm dependencies.\n"
            "Layout: source in `src/<name>.js` with named `export`s; tests in `tests/<name>.test.js` using "
            "`import { test, describe } from 'node:test'` and `import assert from 'node:assert/strict'`.\n"
            "Relative imports must include the extension, e.g. `import { slugify } from '../src/slugify.js'`."
        ),
        scaffold={
            ".gitignore": _GITIGNORE_JS,
            "package.json": '{\n  "name": "project",\n  "private": true,\n  "type": "module",\n'
            '  "scripts": { "test": "node --test" }\n}\n',
        },
    ),
    "typescript": LanguageProfile(
        id="typescript",
        name="TypeScript (Node)",
        test_dir="tests",
        test_glob="*.test.ts",
        conventions=(
            "Language: TypeScript run directly by Node.js 22.18+/24 type stripping.\n"
            "No npm dependencies, no build step.\n"
            "Only erasable TypeScript syntax: NO enums, namespaces, parameter properties or `import =`. "
            "Use `type`/`interface`, union types and `as const` objects instead of enums.\n"
            "Use `import type` for types.\n"
            "Layout: source in `src/<name>.ts` with named exports; tests in `tests/<name>.test.ts` using "
            "`import { test, describe } from 'node:test'` and `import assert from 'node:assert/strict'`.\n"
            "Relative imports must include the `.ts` extension, e.g. `import { slugify } from '../src/slugify.ts'`."
        ),
        scaffold={
            ".gitignore": _GITIGNORE_JS,
            "package.json": '{\n  "name": "project",\n  "private": true,\n  "type": "module",\n'
            '  "scripts": { "test": "node --test" }\n}\n',
            "tsconfig.json": '{\n  "compilerOptions": {\n    "target": "ES2022",\n    "module": "NodeNext",\n'
            '    "moduleResolution": "NodeNext",\n    "allowImportingTsExtensions": true,\n'
            '    "noEmit": true,\n    "strict": true,\n    "verbatimModuleSyntax": true\n  }\n}\n',
        },
    ),
}


class LanguageInfo(BaseModel):
    """Profile summary for the UI/API."""

    id: str
    name: str
    available: bool
    toolchain: str


def get_profile(language_id: str) -> LanguageProfile:
    """Profile by id, or ValueError."""
    try:
        return PROFILES[language_id]
    except KeyError:
        raise ValueError(f"Unsupported language '{language_id}'. Choose one of: {', '.join(PROFILES)}.") from None


@lru_cache(maxsize=1)
def _node_version() -> str | None:
    node = shutil.which("node")
    if not node:
        return None
    try:
        out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10, check=True)
    except OSError, subprocess.SubprocessError:
        return None
    return out.stdout.strip() or None


def language_infos() -> list[LanguageInfo]:
    """All profiles with toolchain availability."""
    node = _node_version()
    py = f"Python {sys.version.split()[0]} + pytest"
    return [
        LanguageInfo(id="python", name=PROFILES["python"].name, available=True, toolchain=py),
        LanguageInfo(
            id="javascript",
            name=PROFILES["javascript"].name,
            available=node is not None,
            toolchain=f"Node {node}" if node else "Node.js not found",
        ),
        LanguageInfo(
            id="typescript",
            name=PROFILES["typescript"].name,
            available=node is not None,
            toolchain=f"Node {node} (type stripping)" if node else "Node.js not found",
        ),
    ]
