"""Secret storage for keys entered in the UI (SECURITY.md: never in the database).

Primary backend: the OS credential store via `keyring` (Windows Credential Manager,
macOS Keychain, Secret Service). Fallback: a JSON file in the user profile folder
(`~/.agent-orchestration/secrets.json`) when no keyring backend is usable.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Protocol

SERVICE = "agent-orchestration"
DEFAULT_FALLBACK_DIR = Path.home() / ".agent-orchestration"


class KeyringLike(Protocol):
    """The subset of the `keyring` module API we use (injectable for tests)."""

    def get_password(self, service_name: str, username: str) -> str | None: ...
    def set_password(self, service_name: str, username: str, password: str) -> None: ...
    def delete_password(self, service_name: str, username: str) -> None: ...


class SecretStore:
    """Get/set/delete named secrets."""

    def __init__(self, backend: KeyringLike | None = None, fallback_dir: Path | None = None) -> None:
        self._fallback_file = (fallback_dir or DEFAULT_FALLBACK_DIR) / "secrets.json"
        self._backend: KeyringLike | None = backend if backend is not None else _system_keyring()

    @property
    def location(self) -> str:
        """Human-readable description of where secrets are kept."""
        if self._backend is not None:
            name = type(self._backend).__name__
            return "Windows Credential Manager" if "Win" in name else f"OS keyring ({name})"
        return str(self._fallback_file)

    def get(self, name: str) -> str | None:
        """Return the secret or None."""
        if self._backend is not None:
            try:
                return self._backend.get_password(SERVICE, name)
            except Exception:
                self._backend = None  # backend broken: fall back to the file
        return self._read_file().get(name)

    def set(self, name: str, value: str) -> None:
        """Store a secret."""
        if self._backend is not None:
            try:
                self._backend.set_password(SERVICE, name, value)
                return
            except Exception:
                self._backend = None
        data = self._read_file()
        data[name] = value
        self._write_file(data)

    def delete(self, name: str) -> None:
        """Remove a secret if present."""
        if self._backend is not None:
            with contextlib.suppress(Exception):
                self._backend.delete_password(SERVICE, name)
        data = self._read_file()
        if data.pop(name, None) is not None:
            self._write_file(data)

    def _read_file(self) -> dict[str, str]:
        if not self._fallback_file.is_file():
            return {}
        try:
            data = json.loads(self._fallback_file.read_text(encoding="utf-8"))
        except OSError, json.JSONDecodeError:
            return {}
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}

    def _write_file(self, data: dict[str, str]) -> None:
        self._fallback_file.parent.mkdir(parents=True, exist_ok=True)
        self._fallback_file.write_text(json.dumps(data), encoding="utf-8")
        with contextlib.suppress(OSError):
            os.chmod(self._fallback_file, 0o600)


class MemoryKeyring:
    """In-memory keyring for tests."""

    def __init__(self) -> None:
        self.data: dict[tuple[str, str], str] = {}

    def get_password(self, service_name: str, username: str) -> str | None:
        return self.data.get((service_name, username))

    def set_password(self, service_name: str, username: str, password: str) -> None:
        self.data[(service_name, username)] = password

    def delete_password(self, service_name: str, username: str) -> None:
        self.data.pop((service_name, username), None)


def _system_keyring() -> KeyringLike | None:
    """The OS keyring if a real (non-fail) backend is available."""
    try:
        import keyring
        from keyring.backends.fail import Keyring as FailKeyring

        backend = keyring.get_keyring()
        if isinstance(backend, FailKeyring):
            return None
        return backend
    except Exception:
        return None
