"""Turn provider exceptions into short, actionable user messages (RULES.md section 4)."""

from __future__ import annotations

from core.llm.models import ModelConfigError


def friendly_error(exc: BaseException) -> str:
    """Return a one-line message suitable for the UI; details belong in the trace."""
    if isinstance(exc, ModelConfigError):
        return str(exc)

    try:
        import openai
    except ImportError:  # pragma: no cover - openai is a hard dependency today
        openai = None  # type: ignore[assignment]

    if openai is not None:
        if isinstance(exc, openai.AuthenticationError):
            return "OpenAI rejected the API key (401). Check OPENAI_API_KEY."
        if isinstance(exc, openai.NotFoundError):
            return "Model not found or not available to this key. Use Settings → LLM → List models."
        if isinstance(exc, openai.RateLimitError):
            return "OpenAI rate limit or quota exceeded (429). Try again later or check billing."
        if isinstance(exc, openai.BadRequestError):
            return f"OpenAI rejected the request: {exc.message}"
        if isinstance(exc, openai.APIConnectionError):
            return "Could not reach OpenAI. Check your network or OPENAI_BASE_URL."
        if isinstance(exc, openai.APIStatusError):
            return f"OpenAI error {exc.status_code}: {exc.message}"

    if isinstance(exc, TimeoutError):
        return "The model call timed out."
    return f"{type(exc).__name__}: {exc}"
