"""Plain chat with a model (M0 Playground). Replaced by agent runs in M1."""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel


class ChatTurn(BaseModel):
    """One message in a UI chat history."""

    role: Literal["user", "assistant"]
    content: str


class ChatReply(BaseModel):
    """The model's answer plus token usage."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str | None = None


def to_langchain(history: list[ChatTurn], system_prompt: str | None = None) -> list[BaseMessage]:
    """Convert UI chat history to LangChain messages."""
    msgs: list[BaseMessage] = [SystemMessage(system_prompt)] if system_prompt else []
    for t in history:
        msgs.append(HumanMessage(t.content) if t.role == "user" else AIMessage(t.content))
    return msgs


async def chat_once(
    model: BaseChatModel,
    history: list[ChatTurn],
    system_prompt: str | None = None,
    callbacks: list[Any] | None = None,
) -> ChatReply:
    """Send the history to the model and return its reply."""
    if not history or history[-1].role != "user":
        raise ValueError("history must end with a user message")
    config = {"callbacks": callbacks} if callbacks else None
    msg = await model.ainvoke(to_langchain(history, system_prompt), config=config)  # type: ignore[arg-type]
    usage = getattr(msg, "usage_metadata", None) or {}
    return ChatReply(
        text=msg.text,
        input_tokens=int(usage.get("input_tokens", 0)),
        output_tokens=int(usage.get("output_tokens", 0)),
        model=(msg.response_metadata or {}).get("model_name"),
    )
