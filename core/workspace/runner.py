"""Code runner: executes a project's tests in its worktree (a plain step, not an LLM).

Safety (SECURITY.md T3): runs only inside the build worktree, with a timeout that kills
the whole process tree, and with secrets removed from the environment.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from pydantic import BaseModel, Field

from core.workspace.languages import LanguageProfile

_SECRET_ENV = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", re.IGNORECASE)
MAX_OUTPUT_CHARS = 30_000


class TestCase(BaseModel):
    """One test result."""

    name: str
    status: str  # passed | failed | error | skipped
    message: str = ""


class TestReport(BaseModel):
    """Outcome of running a project's tests."""

    ok: bool
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    exit_code: int | None = None
    timed_out: bool = False
    duration_s: float = 0.0
    command: str = ""
    output: str = ""
    cases: list[TestCase] = Field(default_factory=list)

    def failure_summary(self, limit: int = 12_000) -> str:
        """Compact text of failing tests for the fixer prompt."""
        lines = [f"{self.passed}/{self.total} passed, {self.failed} failed, {self.errors} errors."]
        if self.timed_out:
            lines.append("The test run TIMED OUT (infinite loop or blocking call?).")
        for c in self.cases:
            if c.status in {"failed", "error"}:
                lines.append(f"\n--- {c.status.upper()}: {c.name}\n{c.message[:3000]}")
        if self.total == 0 or not any(c.status in {"failed", "error"} for c in self.cases):
            lines.append("\nRunner output:\n" + self.output[-6000:])
        text = "\n".join(lines)
        return text[:limit]


def scrubbed_env() -> dict[str, str]:
    """Environment without secret-looking variables."""
    env = {k: v for k, v in os.environ.items() if not _SECRET_ENV.search(k)}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["NO_COLOR"] = "1"
    env["FORCE_COLOR"] = "0"
    return env


def parse_junit(path: Path) -> list[TestCase]:
    """Parse a JUnit XML report (pytest or node:test)."""
    if not path.is_file() or path.stat().st_size == 0:
        return []
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return []
    cases: list[TestCase] = []
    for tc in root.iter("testcase"):
        cls = tc.get("classname") or ""
        name = f"{cls}::{tc.get('name')}" if cls and cls != tc.get("name") else (tc.get("name") or "test")
        status, message = "passed", ""
        for tag, st in (("failure", "failed"), ("error", "error"), ("skipped", "skipped")):
            el = tc.find(tag)
            if el is not None:
                status = st
                message = ((el.get("message") or "") + "\n" + (el.text or "")).strip()
                break
        # node:test reports suites as testcases with nested testcases; keep leaves only
        if tc.find("testcase") is not None:
            continue
        cases.append(TestCase(name=name, status=status, message=message))
    return cases


def _kill_tree(proc: subprocess.Popen[str]) -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)
    else:
        proc.kill()


def run_tests(worktree: Path, profile: LanguageProfile, timeout_s: int = 120) -> TestReport:
    """Run the project's tests and return a structured report (blocking; call via to_thread)."""
    with tempfile.TemporaryDirectory(prefix="ao-junit-") as tmp:
        junit = Path(tmp) / "report.xml"
        cmd = profile.test_command(junit)
        start = time.perf_counter()
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=worktree,
                env=scrubbed_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=flags,
            )
        except OSError as e:
            return TestReport(ok=False, command=" ".join(cmd), output=f"Could not start the test runner: {e}")
        timed_out = False
        try:
            out, _ = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_tree(proc)
            out, _ = proc.communicate()
        duration = time.perf_counter() - start
        cases = parse_junit(junit)

    counts = {s: sum(c.status == s for c in cases) for s in ("passed", "failed", "error", "skipped")}
    total = len(cases)
    ok = (not timed_out) and proc.returncode == 0 and total > 0 and counts["failed"] == 0 and counts["error"] == 0
    output = out or ""
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[-MAX_OUTPUT_CHARS:]
    if total == 0 and not timed_out:
        output = "No tests were found or the test files failed to load.\n\n" + output
    return TestReport(
        ok=ok,
        total=total,
        passed=counts["passed"],
        failed=counts["failed"],
        errors=counts["error"],
        skipped=counts["skipped"],
        exit_code=proc.returncode,
        timed_out=timed_out,
        duration_s=round(duration, 2),
        command=" ".join(Path(cmd[0]).name if i == 0 else a for i, a in enumerate(cmd)),
        output=output,
        cases=cases,
    )
