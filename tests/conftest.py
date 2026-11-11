"""Shared test fixtures. Default tests never touch the network or real API keys."""

from __future__ import annotations

import pytest

from core.config import Settings


@pytest.fixture
def settings(tmp_path) -> Settings:  # type: ignore[no-untyped-def]
    """Settings isolated from the developer's environment and .env file."""
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        openai_api_key="sk-test-not-a-real-key",
        app_data_dir=tmp_path / "data",
        workspaces_dir=tmp_path / "ws",
    )


@pytest.fixture(autouse=True)
def _no_real_secret_store(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    """Never read or write the developer's OS keyring or profile folder in tests."""
    from core import secrets

    monkeypatch.setattr(secrets, "_system_keyring", lambda: secrets.MemoryKeyring())
    monkeypatch.setattr(secrets, "DEFAULT_FALLBACK_DIR", tmp_path_factory.mktemp("profile"))


@pytest.fixture(autouse=True)
def _no_real_keys(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make sure no non-live test accidentally uses the developer's real credentials."""
    if request.node.get_closest_marker("live"):
        return
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GITHUB_TOKEN", "OPENAI_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
