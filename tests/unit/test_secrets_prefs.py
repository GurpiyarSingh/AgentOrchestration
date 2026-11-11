from __future__ import annotations

from pathlib import Path

import pytest

from core.config import Settings
from core.pricing import ModelPrice, PriceTable
from core.secrets import MemoryKeyring, SecretStore
from core.services import OPENAI_KEY, build_services
from core.storage import create_db_engine


class BrokenKeyring(MemoryKeyring):
    def get_password(self, service_name: str, username: str) -> str | None:
        raise RuntimeError("no backend")

    def set_password(self, service_name: str, username: str, password: str) -> None:
        raise RuntimeError("no backend")


def test_secret_store_keyring_roundtrip(tmp_path: Path) -> None:
    store = SecretStore(backend=MemoryKeyring(), fallback_dir=tmp_path)
    assert store.get("k") is None
    store.set("k", "v1")
    assert store.get("k") == "v1"
    store.delete("k")
    assert store.get("k") is None
    assert not (tmp_path / "secrets.json").exists()  # keyring used, no file written


def test_secret_store_falls_back_to_profile_file(tmp_path: Path) -> None:
    store = SecretStore(backend=BrokenKeyring(), fallback_dir=tmp_path)
    store.set("k", "v2")
    assert store.get("k") == "v2"
    assert (tmp_path / "secrets.json").is_file()
    assert store.location == str(tmp_path / "secrets.json")
    store.delete("k")
    assert store.get("k") is None


@pytest.fixture
def services(settings: Settings, tmp_path: Path):  # type: ignore[no-untyped-def]
    settings.config_dir = tmp_path / "config"
    settings.samples_dir = tmp_path / "samples"
    settings.default_model = "openai:env-model"
    return build_services(settings, db=create_db_engine(":memory:"), secrets=SecretStore(MemoryKeyring(), tmp_path))


def test_key_is_ui_only_saved_then_removed(services, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    import asyncio

    import core.services as svc_mod

    # an environment/.env key is ignored: the key must be entered in the UI
    assert services.key_status().source == "missing"
    assert services.settings.openai_api_key is None

    async def fake_list(provider, settings, *, chat_only=True):  # type: ignore[no-untyped-def]
        if settings.openai_api_key.get_secret_value() != "sk-good-key-123456":
            raise ValueError("bad key")
        return ["gpt-a", "gpt-b"]

    monkeypatch.setattr(svc_mod, "list_models", fake_list)
    bad = asyncio.run(services.save_openai_key("sk-wrong"))
    assert not bad.ok and services.secrets.get(OPENAI_KEY) is None

    good = asyncio.run(services.save_openai_key("  sk-good-key-123456 "))
    assert good.ok and good.models == 2
    st = services.key_status()
    assert (st.source, st.hint, st.configured) == ("saved", "…3456", True)
    assert services.settings.openai_api_key.get_secret_value() == "sk-good-key-123456"

    services.remove_openai_key()
    assert services.key_status().source == "missing" and services.settings.openai_api_key is None


def test_prefs_override_env_defaults_and_clear(services) -> None:  # type: ignore[no-untyped-def]
    assert services.settings.default_model == "openai:env-model"
    services.save_prefs(default_model="openai:ui-model", show_all_models=True, git_author_name="Bot")
    assert services.settings.default_model == "openai:ui-model"
    assert services.settings.git_author_name == "Bot"
    assert services.prefs.load().show_all_models is True
    services.save_prefs(default_model=None)
    assert services.settings.default_model == "openai:env-model"
    with pytest.raises(KeyError):
        services.prefs.save(not_a_pref=1)


def test_save_prices_updates_table_and_yaml(services) -> None:  # type: ignore[no-untyped-def]
    services.save_prices({"gpt-a": ModelPrice(input_per_1m=1, output_per_1m=4)})
    assert services.prices.cost("openai:gpt-a", 1_000_000, 0) == 1
    loaded = PriceTable.load(services.settings.config_dir / "prices.yaml")
    assert loaded.models["gpt-a"].output_per_1m == 4


def test_saved_key_redacted_from_traces(services) -> None:  # type: ignore[no-untyped-def]
    services.secrets.set(OPENAI_KEY, "sk-saved-secret-abcdefgh")
    services.reload_user_config()
    assert "sk-saved-secret-abcdefgh" not in services.runs._redactor("key=sk-saved-secret-abcdefgh")
