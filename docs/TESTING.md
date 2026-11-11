# Testing Strategy

LLM output isn't deterministic, so tests are split into **deterministic tests** (fast, run on every commit, never call real APIs) and **evals** (real models, run on demand, measure quality and cost).

---

## 1. Test layers

| Layer | What | Real LLM? | Network? | When | Location |
|---|---|---|---|---|---|
| **Unit** | Pure functions, models, parsers, path sandbox, model factory | ❌ | ❌ | Every commit | `tests/unit/` |
| **Integration** | Agents (`create_agent`) and LangGraph workflows driven by `ScriptedChatModel`, tool registry, MCP adapters against local fixture servers, RepoManager on temp git repos, runner on fixture projects | ❌ (ScriptedChatModel) | ❌ | Every commit | `tests/integration/` |
| **API** | Every route group via FastAPI `TestClient` with `ScriptedChatModel` and an in‑memory DB | ❌ | ❌ | Every commit | `tests/integration/test_api.py` |
| **Security** | Attack cases for the sandbox, redaction, env scrubbing, approval gates | ❌ | ❌ | Every commit | `tests/security/` |
| **Live smoke** | One real call per provider feature (text, tools, structured output, streaming) | ✅ | ✅ | Manual / nightly: `pytest -m live` | `tests/live/` |
| **Evals** | Dev team and other workflows on a fixed task set; quality + cost scores | ✅ | ✅ | On demand, before/after prompt or model changes | `evals/` |
| **UI demo scripts** | Step‑by‑step manual checks per milestone | ✅ | ✅ | End of each milestone | `docs/demos/M<n>.md` |

Default `pytest` runs unit, integration, and security tests. `live` and `evals` are opt‑in markers.

## 2. ScriptedChatModel

`core/llm/fake.py` is a LangChain `BaseChatModel` that replays a **script** of `AIMessage`s, including tool calls, so it can drive real `create_agent` graphs and LangGraph workflows:

```python
model = ScriptedChatModel(
    script=[
        AIMessage("", tool_calls=[{"id": "c1", "name": "builtin__calculator", "args": {"expr": "2+2"}}]),
        AIMessage("The answer is 4."),
    ]
)
agent = create_agent(model, tools=[calculator])
```

- `model.calls` records every message list it received and `model.bound_tools` the tools offered, so tests can check that the test writer never sees code, which tools an agent was given, and so on.
- For multi‑agent workflows, give each agent its own `ScriptedChatModel`.
- An unscripted call raises `ScriptExhaustedError`. No silent defaults.

## 3. Fixtures

- `tests/fixtures/mcp_echo_server.py`: a tiny stdio MCP server (echo, add, slow, fail tools) built with the `mcp` SDK, so MCP tests don't need Node or the network.
- `tests/fixtures/repos/{python_pass,python_fail,js_pass,js_fail,ts_pass,ts_fail}/`: minimal projects for runner and test‑parser tests. JS/TS fixtures are skipped automatically if Node is not installed.
- Temp git repos are created per test with `tmp_path`; no test touches this repo's own git state.

## 4. Security tests

`tests/security/test_repo_sandbox.py` must cover, for read, write, delete, and list:

- `../outside.txt`, `sub/../../outside.txt`
- `/etc/passwd`, `C:\Windows\win.ini`, `\\server\share\x`
- A symlink and an NTFS junction inside the worktree pointing outside it
- `.env`, `.ENV`, `config/.env.local`, `.git/config`, `.github/workflows/ci.yml`
- `file.txt::$DATA` and `file.txt:stream` (alternate data streams)
- Very long paths, and names with trailing dots/spaces (Windows normalisation)

Plus:
- `test_redaction.py`: secrets in tool output, errors, and LLM responses never reach spans or logs.
- `test_runner_env.py`: the runner subprocess env has no secret‑like variables.
- `test_approvals.py`: `requires_approval` tools and finish actions never run without an approval event.

## 5. What to test per component

| Component | Must‑have tests |
|---|---|
| Model layer | `provider:model` parsing, `ChatOpenAI` config (Responses API, `store=False`, reasoning, max tokens), chat‑model filtering, friendly error mapping |
| Agent factory | multi‑turn, parallel tools, tool error recovery, model/tool call limits, structured output, cancellation, stream event order |
| Tool registry | namespacing, unknown tool, truncation, approval flag → HITL middleware |
| MCPManager | connect (adapters), list tools, call, server crash → reconnect, timeout, stderr capture |
| SkillLoader | frontmatter parsing, missing fields, `load_skill` output |
| RepoManager | add/new/clone (local bare remote), worktree start/commit/diff/discard, merge, no change to the user's checkout |
| Languages | profile validation, detection on fixture repos, toolchain check parsing |
| Runner + parsers | pass/fail/error/timeout per framework; process‑tree kill on timeout |
| Workflow builder / patterns | each node type and pattern with `ScriptedChatModel`; loop limits; `AsyncSqliteSaver` checkpoint + resume; `interrupt()` pause / `Command(resume=...)` |
| Tracing | callback handler produces the right span tree, tokens, and cost; secrets redacted |
| A2A | Agent Card shape; task round‑trip between two in‑process servers |

## 6. Evals (dev team)

- `evals/dev_team/tasks/*.yaml`: each has a request, a language, and **hidden reference tests** that the agents never see.
- Score per run:
  - hidden tests pass rate (main metric)
  - own tests pass
  - reviewer approved
  - fix iterations used
  - cost
  - wall time
- `uv run python -m evals.run dev_team --model <m> --repeat 3` writes results to SQLite; the Runs page compares eval batches.
- Run evals before and after any prompt, model, or workflow change, and record the result in the PR.

## 7. Commands

```powershell
uv run pytest                      # default suite (no network)
uv run pytest -m live              # live smoke tests (needs OPENAI_API_KEY)
uv run pytest tests/security -v    # security suite only
uv run pytest --cov=core           # coverage
```
