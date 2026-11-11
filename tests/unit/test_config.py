from __future__ import annotations

from core.config import Settings


def test_missing_key_is_reported_not_raised() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.openai_configured is False
    assert "OPENAI_API_KEY" in s.missing_key_message()


def test_blank_key_counts_as_missing() -> None:
    s = Settings(_env_file=None, openai_api_key="   ")  # type: ignore[call-arg]
    assert s.openai_configured is False


def test_key_is_secret(settings: Settings) -> None:
    assert settings.openai_configured is True
    assert "sk-test" not in repr(settings)
    assert "sk-test" not in str(settings.model_dump())


def test_db_path_under_data_dir(settings: Settings) -> None:
    assert settings.db_path == settings.app_data_dir / "app.db"
