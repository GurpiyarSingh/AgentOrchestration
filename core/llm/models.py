"""Chat model construction: the provider layer (ADR-015).

Agents reference models as "<provider>:<model>" (e.g. "openai:gpt-x"); a bare name means
OpenAI. Everything returns a LangChain `BaseChatModel`, so adding a provider means adding
one branch here plus its `langchain-<provider>` package. Provider SDKs are imported only
inside `core/llm/` (RULES.md section 1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib.util import find_spec
from typing import Any

from langchain_core.language_models import BaseChatModel

from core.config import Settings

DEFAULT_PROVIDER = "openai"


@dataclass(frozen=True)
class ProviderInfo:
    """Static description of a supported model provider."""

    id: str
    label: str
    package: str  # python import name of the LangChain integration
    key_env: str

    @property
    def installed(self) -> bool:
        """True when the LangChain integration package is importable."""
        return find_spec(self.package) is not None


PROVIDERS: dict[str, ProviderInfo] = {
    "openai": ProviderInfo("openai", "OpenAI", "langchain_openai", "OPENAI_API_KEY"),
    "anthropic": ProviderInfo("anthropic", "Anthropic", "langchain_anthropic", "ANTHROPIC_API_KEY"),
}


class ModelConfigError(Exception):
    """The requested model cannot be built (unknown provider, missing package or key)."""


@dataclass(frozen=True)
class ModelRef:
    """A parsed "<provider>:<model>" reference."""

    provider: str
    model: str

    def __str__(self) -> str:
        return f"{self.provider}:{self.model}"


def parse_model_ref(ref: str) -> ModelRef:
    """Parse "provider:model" (or a bare model name, meaning OpenAI)."""
    ref = ref.strip()
    if not ref:
        raise ModelConfigError("No model selected. Set DEFAULT_MODEL or choose a model in the UI.")
    provider, sep, model = ref.partition(":")
    if not sep:
        return ModelRef(DEFAULT_PROVIDER, ref)
    if provider not in PROVIDERS:
        raise ModelConfigError(f"Unknown model provider '{provider}'. Known: {', '.join(PROVIDERS)}.")
    if not model:
        raise ModelConfigError(f"Model reference '{ref}' has no model name.")
    return ModelRef(provider, model)


def build_chat_model(
    ref: str | ModelRef,
    settings: Settings,
    *,
    reasoning_effort: str | None = None,
    max_output_tokens: int | None = None,
    timeout_s: float = 120.0,
) -> BaseChatModel:
    """Build a LangChain chat model for `ref` using credentials from `settings`."""
    mref = parse_model_ref(ref) if isinstance(ref, str) else ref
    info = PROVIDERS[mref.provider]
    if not info.installed:
        raise ModelConfigError(f"{info.label} support is not installed (missing package '{info.package}').")

    if mref.provider == "openai":
        if not settings.openai_configured or settings.openai_api_key is None:
            raise ModelConfigError(settings.missing_key_message())
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "model": mref.model,
            "api_key": settings.openai_api_key,
            "base_url": settings.openai_base_url,
            "use_responses_api": True,
            # The engine keeps the transcript (ADR-004): no server-side conversation state.
            "store": False,
            "timeout": timeout_s,
            "max_retries": 2,
        }
        if reasoning_effort:
            kwargs["reasoning"] = {"effort": reasoning_effort}
        if max_output_tokens:
            kwargs["max_tokens"] = max_output_tokens
        return ChatOpenAI(**kwargs)

    raise ModelConfigError(f"Provider '{mref.provider}' is not wired up yet (planned: M5-T7).")


_NON_CHAT_MARKERS = (
    "tts",
    "transcribe",
    "audio",
    "image",
    "realtime",
    "live",
    "whisper",
    "embedding",
    "moderation",
    "search-api",
    "dall-e",
    "davinci",
    "babbage",
)
_DATED_SNAPSHOT = re.compile(r"-\d{4}-\d{2}-\d{2}$")


def is_chat_model(model_id: str, *, include_snapshots: bool = False, include_fine_tuned: bool = False) -> bool:
    """Heuristic: True for text chat/reasoning models usable by agents."""
    if model_id.startswith("ft:"):
        return include_fine_tuned
    if any(marker in model_id for marker in _NON_CHAT_MARKERS):
        return False
    return include_snapshots or not _DATED_SNAPSHOT.search(model_id)


async def list_models(provider: str, settings: Settings, *, chat_only: bool = True) -> list[str]:
    """Model ids available to the configured credentials for `provider`.

    With `chat_only` (default), audio/image/embedding models, dated snapshots and
    fine-tunes are filtered out.
    """
    if provider != "openai":
        raise ModelConfigError(f"Listing models for '{provider}' is not supported yet.")
    if not settings.openai_configured or settings.openai_api_key is None:
        raise ModelConfigError(settings.missing_key_message())
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=settings.openai_api_key.get_secret_value(), base_url=settings.openai_base_url, timeout=30
    )
    page = await client.models.list()
    ids = (m.id for m in page.data)
    return sorted(i for i in ids if not chat_only or is_chat_model(i))
