"""Live smoke tests (opt-in): `uv run pytest -m live`. Need OPENAI_API_KEY and DEFAULT_MODEL."""

from __future__ import annotations

import os

import pytest

from core.chat import ChatTurn, chat_once
from core.config import Settings
from core.llm.models import build_chat_model, list_models

pytestmark = pytest.mark.live


@pytest.fixture
def live_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    key = os.environ.get("LIVE_OPENAI_API_KEY") or Settings().openai_api_key
    if not key:
        pytest.skip("no OpenAI key available")
    return Settings(openai_api_key=key)  # type: ignore[arg-type]


async def test_list_models(live_settings: Settings) -> None:
    models = await list_models("openai", live_settings)
    assert models


async def test_chat_round_trip(live_settings: Settings) -> None:
    if not live_settings.default_model:
        pytest.skip("DEFAULT_MODEL not set")
    model = build_chat_model(live_settings.default_model, live_settings)
    reply = await chat_once(model, [ChatTurn(role="user", content="Reply with exactly: pong")])
    assert "pong" in reply.text.lower()
    assert reply.input_tokens > 0
