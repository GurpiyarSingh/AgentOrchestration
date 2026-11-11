from __future__ import annotations

import pytest
from langchain_openai import ChatOpenAI

from core.config import Settings
from core.llm.errors import friendly_error
from core.llm.models import (
    ModelConfigError,
    ModelRef,
    build_chat_model,
    is_chat_model,
    parse_model_ref,
)


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("gpt-x", ModelRef("openai", "gpt-x")),
        ("openai:gpt-x", ModelRef("openai", "gpt-x")),
        ("  openai:gpt-x  ", ModelRef("openai", "gpt-x")),
        ("anthropic:claude-x", ModelRef("anthropic", "claude-x")),
    ],
)
def test_parse_model_ref(ref: str, expected: ModelRef) -> None:
    assert parse_model_ref(ref) == expected


@pytest.mark.parametrize("ref", ["", "unknown:model", "openai:"])
def test_parse_model_ref_rejects_bad_refs(ref: str) -> None:
    with pytest.raises(ModelConfigError):
        parse_model_ref(ref)


def test_build_openai_model_uses_responses_api_without_server_state(settings: Settings) -> None:
    m = build_chat_model("openai:gpt-x", settings, reasoning_effort="low", max_output_tokens=500)
    assert isinstance(m, ChatOpenAI)
    assert m.model_name == "gpt-x"
    assert m.use_responses_api is True
    assert m.store is False
    assert m.reasoning == {"effort": "low"}
    assert m.max_tokens == 500


def test_build_without_key_gives_friendly_error() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    with pytest.raises(ModelConfigError) as exc:
        build_chat_model("gpt-x", s)
    assert "OPENAI_API_KEY" in friendly_error(exc.value)


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("gpt-5-mini", True),
        ("gpt-4.1", True),
        ("o3", True),
        ("chat-latest", True),
        ("gpt-5-mini-2025-08-07", False),
        ("gpt-4o-mini-tts", False),
        ("gpt-4o-transcribe", False),
        ("gpt-realtime", False),
        ("gpt-image-2", False),
        ("text-embedding-3-small", False),
        ("omni-moderation-latest", False),
        ("whisper-1", False),
        ("ft:gpt-4o-2024-08-06:personal:x", False),
    ],
)
def test_is_chat_model(model_id: str, expected: bool) -> None:
    assert is_chat_model(model_id) is expected


def test_is_chat_model_opt_ins() -> None:
    assert is_chat_model("gpt-5-mini-2025-08-07", include_snapshots=True)
    assert is_chat_model("ft:gpt-4o:x", include_fine_tuned=True)


def test_unwired_provider_is_reported(settings: Settings) -> None:
    with pytest.raises(ModelConfigError):
        build_chat_model("anthropic:claude-x", settings)
