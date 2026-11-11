from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.tools import StructuredTool

from core.pricing import ModelPrice, PriceTable
from core.runtime.agent_def import AgentDef, AgentDefError, AgentStore
from core.storage import create_db_engine
from core.tools.registry import ToolRegistry, UnknownToolError, truncate
from core.tracing.redact import REDACTED, Redactor


def _tool(name: str, out: str = "ok") -> StructuredTool:
    def f(x: str = "") -> str:
        """Echo."""
        return out

    return StructuredTool.from_function(func=f, name=name, description="Echo tool")


# ---- registry ---------------------------------------------------------------------------


def test_registry_requires_namespaced_unique_names() -> None:
    reg = ToolRegistry()
    reg.register(_tool("test__echo"), "python")
    with pytest.raises(ValueError):
        reg.register(_tool("echo"), "python")
    with pytest.raises(ValueError):
        reg.register(_tool("test__echo"), "python")


def test_resolve_unknown_and_disabled() -> None:
    reg = ToolRegistry()
    reg.register(_tool("test__a"), "python")
    reg.register(_tool("test__b"), "python", enabled=False)
    with pytest.raises(UnknownToolError) as e:
        reg.resolve(["test__a", "test__zzz"])
    assert "test__zzz" in str(e.value)
    assert [t.name for t in reg.resolve(["test__a", "test__b"])] == ["test__a"]


def test_flags_persist_in_db() -> None:
    db = create_db_engine(":memory:")
    reg = ToolRegistry(db)
    reg.register(_tool("test__a"), "python")
    reg.set_flags("test__a", enabled=False, requires_approval=True)
    reg2 = ToolRegistry(db)
    entry = reg2.register(_tool("test__a"), "python")
    assert entry.enabled is False and entry.requires_approval is True


async def test_invoke_truncates_and_never_raises() -> None:
    reg = ToolRegistry()
    reg.register(_tool("test__big", out="y" * 100), "python")
    res = await reg.invoke("test__big", {}, max_chars=10)
    assert res.ok and res.output.startswith("y" * 10) and "[truncated: 90" in res.output

    def broken(x: str) -> str:
        """Breaks."""
        raise RuntimeError("kaputt")

    reg.register(StructuredTool.from_function(func=broken, name="test__broken"), "python")
    res = await reg.invoke("test__broken", {"x": "1"})
    assert not res.ok and "kaputt" in res.output


def test_truncate_keeps_short_text() -> None:
    assert truncate("abc", 10) == "abc"


# ---- agent definitions -----------------------------------------------------------------


def test_agent_name_and_effort_validation() -> None:
    with pytest.raises(ValueError):
        AgentDef(name="Bad Name")
    with pytest.raises(ValueError):
        AgentDef(name="ok", reasoning_effort="extreme")
    assert AgentDef(name="ok", reasoning_effort="").reasoning_effort is None


def test_yaml_errors_name_source_and_field() -> None:
    with pytest.raises(AgentDefError, match=r"x.yaml: field 'max_model_calls'"):
        AgentDef.from_yaml("name: ok\nmax_model_calls: 0\n", source="x.yaml")
    with pytest.raises(AgentDefError, match="mapping"):
        AgentDef.from_yaml("- a\n- b\n")


def test_store_crud_yaml_round_trip(tmp_path: Path) -> None:
    store = AgentStore(create_db_engine(":memory:"))
    a = AgentDef(
        name="researcher",
        description="Finds things",
        system_prompt="Be thorough.",
        model="openai:gpt-x",
        reasoning_effort="low",
        tools=["builtin__http_get"],
        max_model_calls=7,
        max_tool_calls=9,
    )
    store.save(a)
    assert store.get("researcher") == a
    path = store.export_yaml("researcher", tmp_path)
    assert store.delete("researcher") and store.get("researcher") is None
    assert store.import_yaml_dir(tmp_path) == ["researcher"]
    assert store.get("researcher") == a
    assert AgentDef.from_yaml(path.read_text(encoding="utf-8")) == a


def test_shipped_agent_yaml_is_valid() -> None:
    root = Path(__file__).resolve().parents[2] / "config" / "agents"
    for path in root.glob("*.yaml"):
        AgentDef.from_yaml(path.read_text(encoding="utf-8"), source=str(path))


# ---- pricing and redaction -------------------------------------------------------------


def test_price_table_cost_and_unknown_model() -> None:
    table = PriceTable(models={"m": ModelPrice(input_per_1m=2, output_per_1m=10, cached_input_per_1m=0.5)})
    assert table.cost("openai:m", 1_000_000, 100_000, cached_input_tokens=500_000) == pytest.approx(
        0.5 * 2 + 0.25 + 1.0
    )
    assert table.cost("unknown", 10, 10) is None


def test_redactor_removes_known_and_pattern_secrets() -> None:
    r = Redactor(["my-super-secret-value"])
    text = r("key my-super-secret-value and sk-abcdefghijklmnopqrstuv and ghp_abcdefghijklmnopqrstuvwxyz12")
    assert "my-super-secret-value" not in text and "sk-abc" not in text and "ghp_" not in text
    assert text.count(REDACTED) == 3
