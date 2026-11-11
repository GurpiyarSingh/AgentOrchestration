"""Builtin Python tools, all named `builtin__<name>`."""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import BaseTool

from core.tools.builtin.calculator import make_calculator
from core.tools.builtin.system import make_current_time, make_read_text_file
from core.tools.builtin.web import make_http_get


def builtin_tools(samples_dir: Path) -> list[BaseTool]:
    """All builtin tools. `samples_dir` is the only folder `read_text_file` may read."""
    return [make_calculator(), make_http_get(), make_current_time(), make_read_text_file(samples_dir)]


__all__ = ["builtin_tools", "make_calculator", "make_current_time", "make_http_get", "make_read_text_file"]
