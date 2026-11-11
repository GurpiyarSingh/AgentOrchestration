"""Agent factory + run service + tracing, driven by ScriptedChatModel (no network)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import StructuredTool, ToolException

from core.chat import ChatTurn
from core.config import Settings
from core.llm.fake import ScriptedChatModel
from core.pricing import ModelPrice
from core.runtime.agent_def import AgentDef
from core.runtime.agent_factory import APPROVAL_UNAVAILABLE, build_agent
from core.runtime.run_service import RunError
from core.services import Services, build_services
from core.storage import create_db_engine
from core.tools.registry import ToolEntry
from core.tracing.queries import get_run, span_tree


def _usage(i: int, o: int) -> dict[str, int]:
    return {"input_tokens": i, "output_tokens": o, "total_tokens": i + o}


def _call(cid: str, name: str, **args: object) -> dict[str, object]:
    return {"id": cid, "name": name, "args": args}


@pytest.fixture
def svc(tmp_path: Path, settings: Settings) -> tuple[Services, dict[str, ScriptedChatModel]]:
    models: dict[str, ScriptedChatModel] = {}
    settings.samples_dir = tmp_path / "samples"
    settings.config_dir = tmp_path / "config"  # no seeded agents
    settings.default_model = "fake:model"
    services = build_services(
        settings, model_factory=lambda ref, agent: models[agent.name], db=create_db_engine(":memory:")
    )
    services.prices.models["model"] = ModelPrice(input_per_1m=1_000_000, output_per_1m=2_000_000)
    return services, models


def _agent(name: str = "calc", **kw: object) -> AgentDef:
    return AgentDef(name=name, tools=["builtin__calculator"], **kw)  # type: ignore[arg-type]


# ---- agent factory ---------------------------------------------------------------------


async def test_parallel_tool_calls_and_multi_turn() -> None:
    from core.tools.builtin import make_calculator

    model = ScriptedChatModel(
        script=[
            AIMessage(
                "",
                tool_calls=[
                    _call("1", "builtin__calculator", expression="2+2"),
                    _call("2", "builtin__calculator", expression="3*3"),
                ],
            ),
            AIMessage("4 and 9"),
        ]
    )
    graph = build_agent(_agent(), model, [ToolEntry(make_calculator(), "python")])
    out = await graph.ainvoke({"messages": [("user", "compute")]})
    results = sorted(m.content for m in out["messages"] if isinstance(m, ToolMessage))
    assert results == ["4", "9"]
    assert out["messages"][-1].text == "4 and 9"
    # second model call saw both tool results
    assert sum(isinstance(m, ToolMessage) for m in model.calls[1]) == 2


async def test_unexpected_tool_exception_goes_back_to_model() -> None:
    def explode(x: str) -> str:
        """Always fails."""
        raise RuntimeError("disk on fire")

    def soft(x: str) -> str:
        """Fails politely."""
        raise ToolException("bad input")

    tools = [
        ToolEntry(StructuredTool.from_function(func=explode, name="t__explode"), "python"),
        ToolEntry(StructuredTool.from_function(func=soft, name="t__soft", handle_tool_error=True), "python"),
    ]
    model = ScriptedChatModel(
        script=[
            AIMessage("", tool_calls=[_call("1", "t__explode", x="a"), _call("2", "t__soft", x="b")]),
            AIMessage("recovered"),
        ]
    )
    out = await build_agent(AgentDef(name="tester"), model, tools).ainvoke({"messages": [("user", "go")]})
    tool_msgs = {m.tool_call_id: m for m in out["messages"] if isinstance(m, ToolMessage)}
    assert "disk on fire" in tool_msgs["1"].content and tool_msgs["1"].status == "error"
    assert "bad input" in tool_msgs["2"].content
    assert out["messages"][-1].text == "recovered"


async def test_requires_approval_tool_is_blocked_until_m4() -> None:
    from core.tools.builtin import make_calculator

    model = ScriptedChatModel(
        script=[
            AIMessage("", tool_calls=[_call("1", "builtin__calculator", expression="1+1")]),
            AIMessage("ok"),
        ]
    )
    entry = ToolEntry(make_calculator(), "python", requires_approval=True)
    out = await build_agent(_agent(), model, [entry]).ainvoke({"messages": [("user", "x")]})
    tm = next(m for m in out["messages"] if isinstance(m, ToolMessage))
    assert tm.content == APPROVAL_UNAVAILABLE and tm.status == "error"


async def test_tool_output_is_truncated() -> None:
    big = StructuredTool.from_function(func=lambda: "z" * 5000, name="t__big", description="big")
    model = ScriptedChatModel(script=[AIMessage("", tool_calls=[_call("1", "t__big")]), AIMessage("ok")])
    out = await build_agent(AgentDef(name="tester"), model, [ToolEntry(big, "python")], max_output_chars=1000).ainvoke(
        {"messages": [("user", "x")]}
    )
    tm = next(m for m in out["messages"] if isinstance(m, ToolMessage))
    assert len(tm.content) < 1100 and "[truncated: 4000" in tm.content


async def test_model_call_limit_stops_the_loop() -> None:
    from core.tools.builtin import make_calculator

    looping = [AIMessage("", tool_calls=[_call(str(i), "builtin__calculator", expression="1+1")]) for i in range(10)]
    model = ScriptedChatModel(script=looping)
    out = await build_agent(_agent(max_model_calls=3), model, [ToolEntry(make_calculator(), "python")]).ainvoke(
        {"messages": [("user", "loop")]}
    )
    assert len(model.calls) == 3
    assert isinstance(out["messages"][-1], AIMessage)


async def test_tool_call_limit_stops_the_loop() -> None:
    from core.tools.builtin import make_calculator

    looping = [AIMessage("", tool_calls=[_call(str(i), "builtin__calculator", expression="1+1")]) for i in range(10)]
    model = ScriptedChatModel(script=looping)
    await build_agent(_agent(max_tool_calls=2), model, [ToolEntry(make_calculator(), "python")]).ainvoke(
        {"messages": [("user", "loop")]}
    )
    assert len(model.calls) <= 3


# ---- run service + tracing ---------------------------------------------------------------


async def test_run_records_timeline_spans_tokens_and_cost(
    svc: tuple[Services, dict[str, ScriptedChatModel]],
) -> None:
    services, models = svc
    models["calc"] = ScriptedChatModel(
        script=[
            AIMessage(
                "",
                tool_calls=[_call("1", "builtin__calculator", expression="6*7")],
                usage_metadata=_usage(10, 5),
            ),
            AIMessage("The answer is 42.", usage_metadata=_usage(20, 8)),
        ]
    )
    handle = await services.runs.start(_agent(), [ChatTurn(role="user", content="6*7?")])
    snap = await services.runs.wait(handle.run_id, max_wait_s=10)

    assert snap.status == "done" and snap.output == "The answer is 42."
    kinds = [(i.kind, i.tool_name, i.tool_status) for i in snap.timeline]
    assert ("tool", "builtin__calculator", "ok") in kinds
    assert snap.timeline[-1].text == "The answer is 42."
    assert (snap.input_tokens, snap.output_tokens) == (30, 13)
    assert snap.cost_usd == pytest.approx(30 * 1 + 13 * 2)

    rec = get_run(services.db, handle.run_id)
    assert rec is not None and rec.status == "done" and rec.input_tokens == 30
    roots = span_tree(services.db, handle.run_id)
    assert [r.type for r in roots] == ["agent"]
    assert [c.type for c in roots[0].children] == ["llm", "tool", "llm"]
    tool_span = roots[0].children[1]
    assert tool_span.name == "builtin__calculator" and str(tool_span.output) == "42"


async def test_run_cancel(svc: tuple[Services, dict[str, ScriptedChatModel]]) -> None:
    services, models = svc

    async def slow(seconds: float) -> str:
        """Sleeps."""
        await asyncio.sleep(seconds)
        return "done"

    services.tools.register(StructuredTool.from_function(coroutine=slow, name="t__slow"), "python")
    models["sleepy"] = ScriptedChatModel(script=[AIMessage("", tool_calls=[_call("1", "t__slow", seconds=30)])])
    handle = await services.runs.start(AgentDef(name="sleepy", tools=["t__slow"]), [ChatTurn(role="user", content="x")])
    await asyncio.sleep(0.3)
    assert await services.runs.cancel(handle.run_id)
    assert handle.snapshot().status == "cancelled"
    rec = get_run(services.db, handle.run_id)
    assert rec is not None and rec.status == "cancelled"


async def test_run_failure_is_recorded(svc: tuple[Services, dict[str, ScriptedChatModel]]) -> None:
    services, models = svc
    models["calc"] = ScriptedChatModel(script=[])  # first call raises ScriptExhaustedError
    handle = await services.runs.start(_agent(), [ChatTurn(role="user", content="x")])
    snap = await services.runs.wait(handle.run_id, max_wait_s=10)
    assert snap.status == "failed" and snap.error and "Unscripted" in snap.error


async def test_start_validation_errors(svc: tuple[Services, dict[str, ScriptedChatModel]]) -> None:
    services, _ = svc
    with pytest.raises(RunError, match="Unknown tool"):
        await services.runs.start(AgentDef(name="tester", tools=["nope__x"]), [ChatTurn(role="user", content="x")])
    with pytest.raises(RunError, match="must end with a user"):
        await services.runs.start(_agent(), [ChatTurn(role="assistant", content="x")])
    services.settings.default_model = ""
    with pytest.raises(RunError, match="no model"):
        await services.runs.start(_agent(), [ChatTurn(role="user", content="x")])


def test_build_services_seeds_shipped_agents(settings: Settings, tmp_path: Path) -> None:
    settings.config_dir = Path(__file__).resolve().parents[2] / "config"
    settings.samples_dir = tmp_path / "samples"
    services = build_services(settings, db=create_db_engine(":memory:"))
    assert services.agents.get("assistant") is not None
    names = {e.name for e in services.tools.entries()}
    assert {
        "builtin__calculator",
        "builtin__http_get",
        "builtin__current_time",
        "builtin__read_text_file",
    } <= names


# ---- usage + traced chat -------------------------------------------------------------------


async def test_usage_summary_counts_calls_tokens_and_runs(
    svc: tuple[Services, dict[str, ScriptedChatModel]],
) -> None:
    from datetime import UTC, datetime, timedelta

    from core.tracing.queries import usage_summary

    services, models = svc
    models["calc"] = ScriptedChatModel(
        script=[
            AIMessage(
                "",
                tool_calls=[_call("1", "builtin__calculator", expression="1+1")],
                usage_metadata=_usage(10, 2),
            ),
            AIMessage("2", usage_metadata=_usage(12, 1)),
        ]
    )
    h = await services.runs.start(_agent(), [ChatTurn(role="user", content="1+1")])
    snap = await services.runs.wait(h.run_id, max_wait_s=10)
    assert (snap.model_calls, snap.tool_calls) == (2, 1)

    u = usage_summary(services.db)
    assert (u.runs, u.model_calls, u.tool_calls) == (1, 2, 1)
    assert (u.input_tokens, u.output_tokens, u.total_tokens) == (22, 3, 25)
    assert u.cost_usd == pytest.approx(22 * 1 + 3 * 2)
    future = usage_summary(services.db, since=datetime.now(UTC) + timedelta(hours=1))
    assert future.model_calls == 0 and future.runs == 0
    rec = get_run(services.db, h.run_id)
    assert rec is not None and (rec.model_calls, rec.tool_calls) == (2, 1)


async def test_plain_chat_is_traced_as_a_run(svc: tuple[Services, dict[str, ScriptedChatModel]]) -> None:
    services, models = svc
    models["chat"] = ScriptedChatModel(script=[AIMessage("hi there", usage_metadata=_usage(5, 3))])
    run_id, reply = await services.runs.chat("fake:model", [ChatTurn(role="user", content="hello")])
    assert reply.text == "hi there"
    rec = get_run(services.db, run_id)
    assert rec is not None
    assert (rec.kind, rec.status, rec.model_calls, rec.input_tokens, rec.output_tokens) == (
        "chat",
        "done",
        1,
        5,
        3,
    )
    assert [n.type for n in span_tree(services.db, run_id)] == ["llm"]
