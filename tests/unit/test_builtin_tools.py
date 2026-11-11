from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from core.tools.builtin import make_calculator, make_current_time, make_http_get, make_read_text_file
from core.tools.builtin.calculator import evaluate


@pytest.mark.parametrize(
    ("expr", "expected"),
    [("2+3*4", 14), ("sqrt(16) * (2 + 3)", 20.0), ("-2**2", -4), ("max(1, 7, 3)", 7), ("round(pi, 2)", 3.14)],
)
def test_calculator_evaluates(expr: str, expected: float) -> None:
    assert evaluate(expr) == expected


@pytest.mark.parametrize(
    ("expr", "error"),
    [
        ("1/0", "Division by zero"),
        ("__import__('os')", "Unsupported"),
        ("2**100000", "Exponent too large"),
        ("1 +", "Invalid expression"),
        ("x + 1", "Unsupported"),
    ],
)
async def test_calculator_errors_are_returned_not_raised(expr: str, error: str) -> None:
    out = await make_calculator().ainvoke({"expression": expr})
    assert error in out


async def test_current_time_utc_and_bad_zone() -> None:
    tool = make_current_time()
    assert "T" in await tool.ainvoke({"timezone": "UTC"})
    assert "Unknown timezone" in await tool.ainvoke({"timezone": "Mars/Base"})


@pytest.fixture
def sample_root(tmp_path: Path) -> Path:
    root = tmp_path / "samples"
    (root / "sub").mkdir(parents=True)
    (root / "a.txt").write_text("hello", encoding="utf-8")
    (root / "sub" / "b.txt").write_text("world", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("top secret", encoding="utf-8")
    return root


async def test_read_text_file_reads_and_lists(sample_root: Path) -> None:
    tool = make_read_text_file(sample_root)
    assert await tool.ainvoke({"path": "a.txt"}) == "hello"
    assert await tool.ainvoke({"path": "sub/b.txt"}) == "world"
    listing = await tool.ainvoke({"path": "."})
    assert "a.txt" in listing and "sub/b.txt" in listing


@pytest.mark.parametrize(
    "path",
    [
        "../secret.txt",
        "sub/../../secret.txt",
        "C:\\Windows\\win.ini",
        "/etc/passwd",
        "\\\\server\\share\\x",
        "a.txt:stream",
    ],
)
async def test_read_text_file_blocks_escapes(sample_root: Path, path: str) -> None:
    out = await make_read_text_file(sample_root).ainvoke({"path": path})
    assert "top secret" not in out
    assert any(word in out for word in ("escapes", "relative", "':'", "not found"))


async def test_http_get_with_mock_transport() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="x" * 30_000, headers={"content-type": "text/plain"})

    out = await make_http_get(transport=httpx.MockTransport(handler)).ainvoke({"url": "https://example.test"})
    assert out.startswith("HTTP 200 (text/plain)")
    assert "[truncated:" in out


async def test_http_get_rejects_non_http_and_handles_errors() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    tool = make_http_get(transport=httpx.MockTransport(boom))
    assert "Only http" in await tool.ainvoke({"url": "file:///etc/passwd"})
    assert "Request failed" in await tool.ainvoke({"url": "https://example.test"})
