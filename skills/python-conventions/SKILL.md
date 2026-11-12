---
name: python-conventions
description: Idiomatic modern Python conventions (3.12+). Use when writing or fixing Python code.
---

# Python conventions

- Type-hint every function (`list[str]`, `X | None`); use `from __future__ import annotations` only if needed.
- Prefer pure functions and small, single-purpose helpers; no global mutable state.
- Validate inputs at the boundary and raise specific exceptions (`ValueError`, `TypeError`) with clear messages.
- Use the standard library: `pathlib`, `dataclasses`, `enum`, `re`, `unicodedata`, `itertools`, `functools`.
- Docstrings: one-line summary, then Args/Returns/Raises when helpful.
- Never use mutable default arguments; use `None` and create inside.
- f-strings for formatting; `==` for values and `is` only for `None`.
- Keep modules importable without side effects (no work at import time).
