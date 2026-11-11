"""Remove secrets from anything written to traces or logs (SECURITY.md control 2)."""

from __future__ import annotations

import re
from collections.abc import Iterable

_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"(?i)(authorization:\s*bearer\s+)[A-Za-z0-9._\-]{16,}"),
]
REDACTED = "[REDACTED]"


class Redactor:
    """Replaces known secret values and common token patterns with a marker."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        self._secrets = sorted({s for s in secrets if s and len(s) >= 8}, key=len, reverse=True)

    def __call__(self, text: str) -> str:
        """Return `text` with secrets replaced."""
        for s in self._secrets:
            text = text.replace(s, REDACTED)
        for pat in _PATTERNS:
            text = pat.sub(lambda m: (m.group(1) if m.groups() else "") + REDACTED, text)
        return text
