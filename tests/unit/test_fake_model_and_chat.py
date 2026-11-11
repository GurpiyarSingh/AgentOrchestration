"""The scripted model must be able to drive a real LangGraph agent (basis for M1 tests)."""

from __future__ import annotations

import pytest
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from core.chat import ChatTurn, chat_once
from core.llm.fake import ScriptedChatModel, ScriptExhaustedError


@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


async def test_chat_once_returns_text_and_usage() -> None:
    model = ScriptedChatModel(
        script=[AIMessage("hello!", usage_metadata={"input_tokens": 5, "output_tokens": 2, "total_tokens": 7})]
    )
    reply = await chat_once(model, [ChatTurn(role="user", content="hi")], system_prompt="be brief")
    assert reply.text == "hello!"
    assert (reply.input_tokens, reply.output_tokens) == (5, 2)
    sent = model.calls[0]
    assert sent[0].type == "system" and sent[1].type == "human"


async def test_chat_once_requires_user_last() -> None:
    with pytest.raises(ValueError):
        await chat_once(ScriptedChatModel(), [ChatTurn(role="assistant", content="x")])


async def test_unscripted_call_fails_loudly() -> None:
    with pytest.raises(ScriptExhaustedError):
        await ScriptedChatModel().ainvoke("hi")


async def test_scripted_model_drives_langgraph_agent_with_tool_call() -> None:
    model = ScriptedChatModel(
        script=[
            AIMessage("", tool_calls=[{"id": "c1", "name": "add", "args": {"a": 2, "b": 3}}]),
            AIMessage("2 + 3 = 5"),
        ]
    )
    agent = create_agent(model, tools=[add], system_prompt="You add numbers.")
    result = await agent.ainvoke({"messages": [HumanMessage("what is 2+3?")]})

    msgs = result["messages"]
    tool_msgs = [m for m in msgs if isinstance(m, ToolMessage)]
    assert tool_msgs and tool_msgs[0].content == "5"
    assert msgs[-1].text == "2 + 3 = 5"
    assert [t["function"]["name"] for t in model.bound_tools] == ["add"]
    assert model.remaining == 0
