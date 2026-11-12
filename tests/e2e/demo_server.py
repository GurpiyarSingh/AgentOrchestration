"""Codeloom with scripted agents, for end-to-end UI tests and demos (no API key, no network).

    uv run python tests/e2e/demo_server.py --port 8768 --data <tmp dir>

Every agent gets a fresh scripted model per call, so any number of builds and chats work.
Model listing and key verification are faked; everything else (git, worktrees, pytest,
tracing, API, UI) is real.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import uvicorn
from langchain_core.messages import AIMessage

from api.main import create_app
from core.config import Settings
from core.llm.fake import ScriptedChatModel
from core.runtime.agent_def import AgentDef
from core.secrets import MemoryKeyring, SecretStore
from core.services import build_services

ROOT = Path(__file__).resolve().parents[2]
USAGE = {"input_tokens": 1200, "output_tokens": 300, "total_tokens": 1500}
FAKE_MODELS = ["gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.5"]


def _tool(name: str, args: dict[str, Any], cid: str) -> AIMessage:
    return AIMessage("", tool_calls=[{"id": cid, "name": name, "args": args}], usage_metadata=USAGE)


SPEC = {
    "title": "Number Formatter",
    "summary": "Format integers with thousands separators.",
    "acceptance_criteria": ["1234567 -> '1,234,567'", "Negative numbers keep the sign", "0 -> '0'"],
    "assumptions": ["Integers only"],
    "out_of_scope": ["Locales"],
}
PLAN = {
    "approach": "One pure function using Python formatting.",
    "files": [
        {"path": "numfmt.py", "kind": "source", "purpose": "format_thousands()"},
        {"path": "tests/test_numfmt.py", "kind": "test", "purpose": "unit tests"},
    ],
    "interfaces": "def format_thousands(n: int) -> str: ...",
}
TESTS = (
    "from numfmt import format_thousands\n\n\n"
    "def test_basic():\n    assert format_thousands(1234567) == '1,234,567'\n\n\n"
    "def test_negative():\n    assert format_thousands(-1000) == '-1,000'\n\n\n"
    "def test_zero():\n    assert format_thousands(0) == '0'\n"
)
CODE = 'def format_thousands(n: int) -> str:\n    """Format with thousands separators."""\n    return f"{n:,}"\n'


def script_for(agent: AgentDef) -> list[AIMessage]:
    """A fresh script per model instance, keyed by agent."""
    match agent.name:
        case "requirements_analyst":
            return [_tool("Spec", SPEC, "spec")]
        case "architect":
            return [_tool("Plan", PLAN, "plan")]
        case "test_writer":
            return [
                _tool("repo__write_file", {"path": "tests/test_numfmt.py", "content": TESTS}, "t"),
                AIMessage("Wrote 3 tests.", usage_metadata=USAGE),
            ]
        case "code_generator":
            return [
                _tool("repo__write_file", {"path": "numfmt.py", "content": CODE}, "c"),
                AIMessage("Implemented format_thousands().", usage_metadata=USAGE),
            ]
        case "code_reviewer":
            return [_tool("Review", {"approved": True, "summary": "Correct and well tested.", "issues": []}, "r")]
        case "chat":
            return [AIMessage("Hello from the scripted model.", usage_metadata=USAGE)]
        case _:  # any chat agent: one calculator call, then an answer
            return [
                _tool("builtin__calculator", {"expression": "17.5 * 2340 / 100"}, "calc"),
                AIMessage("17.5% of 2,340 is 409.5.", usage_metadata=USAGE),
            ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8768)
    ap.add_argument("--data", required=True)
    args = ap.parse_args()
    data = Path(args.data)

    import api.routes
    import core.services

    async def fake_list_models(provider: str, settings: Settings, *, chat_only: bool = True) -> list[str]:
        key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else ""
        if not key.startswith("sk-"):
            raise ValueError("OpenAI rejected the API key (401). Check the key.")
        return FAKE_MODELS

    core.services.list_models = fake_list_models  # type: ignore[assignment]
    api.routes.list_models = fake_list_models  # type: ignore[assignment]

    # Offline MCP registry: one entry that installs the local fixture server.
    import sys

    import api.routes_mcp_skills
    from core.mcp.config import McpServerConfig
    from core.mcp.registry_client import RegistryEntry

    echo = str(ROOT / "tests" / "fixtures" / "mcp_echo_server.py")

    async def fake_registry(query: str, limit: int = 30) -> list[RegistryEntry]:
        return [
            RegistryEntry(
                name="io.codeloom/echo-math",
                title="Echo Math",
                description="Adds numbers (test fixture server).",
                version="1.0.0",
                kind="pypi",
                note="Runs locally with Python.",
                draft=McpServerConfig(name="echo-math", transport="stdio", command=sys.executable, args=[echo]),
            )
        ]

    api.routes_mcp_skills.search_registry = fake_registry  # type: ignore[assignment]

    import shutil

    if not (data / "config").exists():  # never write to the real config (prices, agents)
        shutil.copytree(ROOT / "config", data / "config")
    settings = Settings(
        _env_file=None,
        app_data_dir=data / "data",
        workspaces_dir=data / "ws",
        config_dir=data / "config",
        samples_dir=data / "samples",
    )
    services = build_services(
        settings,
        model_factory=lambda ref, agent: ScriptedChatModel(script=script_for(agent)),
        secrets=SecretStore(MemoryKeyring(), data),
    )
    uvicorn.run(create_app(services), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
