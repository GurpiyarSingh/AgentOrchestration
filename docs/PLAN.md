# Agent Orchestration POC: Plan

> Goal: a working sandbox where I can define agents, give them tools (local + MCP), attach skills, wire them into multi‑agent workflows (sequential, parallel, supervisor, handoff, graph), run them from a UI, and **see exactly what happened**: every LLM call, tool call, and agent‑to‑agent message.
>
> **Note:** this plan predates the product rebuild. The UI is now React served by FastAPI (ADR‑019), and the build pipeline (§5.4) is implemented (ADR‑020). For the current system see [ARCHITECTURE.md](ARCHITECTURE.md); sections below that mention Streamlit describe the original design.
>
> Stack: **React + TypeScript** UI served by **FastAPI** (Streamlit was replaced; ADR‑019), **LangChain** for models, tools, and MCP (`langchain-openai` now, other providers later), **LangGraph** for agents and multi‑agent workflows (state, checkpoints, human‑in‑the‑loop), **SQLite** for persistence. See ADR‑015.

---

## 1. Where this is heading

This isn't a chatbot with tools. It's the start of a small **agent platform**, built in layers:

1. **Registry**: a catalog of *Agents*, *Tools*, *Skills*, *MCP servers*, and *Workflows*. Everything is data (YAML/DB rows), not hard‑coded Python.
2. **Runtime**: every agent definition is compiled into a LangGraph agent (`langchain.agents.create_agent`: model ↔ tools loop, plus middleware for limits, approvals, and retries).
3. **Orchestration**: patterns that compose agents, built as LangGraph `StateGraph`s: sequential, parallel fan‑out/fan‑in, router, supervisor/worker, handoff, reviewer loop, and arbitrary graphs.
4. **Agent‑to‑Agent (A2A)**: agents call other agents as if they were tools, through a message bus, and later over the network using the A2A protocol (Agent Cards + tasks).
5. **Observability**: every run produces a trace tree you can inspect, replay, and compare.
6. **UI + API**: a React UI to build, manage agents and tools, and inspect traces, over a REST API with Swagger (`/docs`) (ADR‑017, ADR‑019).

Keep the **core engine UI‑agnostic**. Streamlit is a thin shell. Later you can replace it with FastAPI + React without touching the engine.

---

## 2. Core concepts (the vocabulary)

| Concept | What it is | Example |
|---|---|---|
| **Tool** | A callable with a JSON schema. Comes from one of three sources: `python` (local function), `mcp` (discovered from an MCP server), or `agent` (another agent wrapped as a tool). | `web_fetch`, `github.search_issues`, `ask_researcher` |
| **MCP Server** | A connection config (stdio command or remote HTTP URL). On connect, its tools/resources/prompts are discovered and registered. | `@modelcontextprotocol/server-filesystem`, a remote HTTP server |
| **Skill** | A folder with `SKILL.md` (name, description, instructions) plus optional scripts or reference files. The agent sees only the *description* until it decides to load the skill (progressive disclosure). | `skills/pdf-report/SKILL.md` |
| **Agent** | `name + role/system prompt + model + effort + tools[] + skills[] + memory policy + limits`. | `researcher`, `writer`, `critic`, `supervisor` |
| **Workflow** | A graph of nodes (agents, routers, joins, human‑approval gates) and edges, plus a shared state object. | "Research → Write → Critique (loop ≤3) → Publish" |
| **Run** | One execution of an agent or workflow. Produces a **Trace**. | run `r_0192…` |
| **Trace / Span** | A tree of events: LLM call, tool call, agent handoff, A2A message, approval, error. Each span has tokens, cost, and latency. | |
| **Message Bus** | An in‑process pub/sub that agents use to talk to each other. Every message is logged. | `researcher → writer: "findings.md ready"` |

---

## 3. Architecture

```
┌──────────────────────────── Streamlit UI ─────────────────────────────┐
│ Playground │ Agents │ Tools │ Skills │ Workflows │ Runs/Traces │ Settings │
└──────────────────────────────────┬────────────────────────────────────┘
                                   │ (plain Python calls, no HTTP yet)
┌──────────────────────────────────▼────────────────────────────────────┐
│                              CORE ENGINE                              │
│                                                                       │
│  Registry ──────── Workflow builder ─────────── Tracer                │
│  (agents, tools,   (YAML/DB → LangGraph        (LangChain callback    │
│   skills, mcp,      StateGraph; checkpoints     handler → spans in    │
│   repos, langs)     in SQLite; interrupts)      SQLite + live events) │
│      │                      │                                         │
│      │        Agent factory: AgentDef → create_agent(model, tools,    │
│      │        middleware: limits, human‑in‑the‑loop, retries)         │
│      │                      │                                         │
│  ┌───┴──────────┬───────────┴───────┬──────────────┬───────────────┐  │
│  │ Tool registry│ MCP (langchain‑   │ SkillLoader  │ MessageBus    │  │
│  │ (LangChain   │ mcp‑adapters,     │ (SKILL.md,   │ (A2A in‑proc, │  │
│  │  BaseTools:  │  stdio + HTTP,    │  load_skill  │  later A2A    │  │
│  │  python/mcp/ │  tools → Base‑    │  tool)       │  protocol)    │  │
│  │  agent/repo) │  Tool)            │              │               │  │
│  └──────────────┴───────────────────┴──────────────┴───────────────┘  │
│                                                                       │
│  Models: LangChain chat models, "provider:model" refs                 │
│          (ChatOpenAI now; langchain‑anthropic etc. later)             │
│  Storage (SQLite: registry, runs, spans, checkpoints, memory)         │
└───────────────────────────────────────────────────────────────────────┘
```

### Key design decisions

- **LangChain + LangGraph for the engine (ADR‑015).** We don't hand‑write the agent loop or the graph executor. Each agent is a LangGraph agent built with `create_agent`; workflows are LangGraph `StateGraph`s compiled from our YAML/DB definitions. LangGraph gives us checkpoints (`AsyncSqliteSaver`), human‑in‑the‑loop (`interrupt()` / `HumanInTheLoopMiddleware`), parallel branches, and cycles. **What we still own:** the registry, the UI, tracing into our own SQLite, the repo sandbox, language profiles, and the dev‑team workflow.
- **Models through LangChain chat models.** Agents reference models as `"provider:model"` (e.g. `"openai:gpt-5.4-mini"`). `core/llm/models.py` builds a `BaseChatModel` (today `ChatOpenAI` on the Responses API with `store=False`). Adding Anthropic means installing `langchain-anthropic` and adding one branch. Mixing providers in one workflow works because every node just receives a chat model.
- **Our own tracing, LangSmith optional.** A LangChain callback handler writes every model call, tool call, and agent step as spans in our SQLite, so the Runs page works offline and without an account. LangSmith can be switched on later via its env vars.
- **Client‑side MCP via `langchain-mcp-adapters`.** `MultiServerMCPClient` connects to stdio and Streamable HTTP servers and turns their tools into LangChain tools, so they go through the same approval, limit, and tracing path as local tools. OpenAI's hosted MCP tool is not used by default.
- **Agents as tools.** An agent‑to‑agent call is a LangChain tool (`ask_<agent>(task, context)`) that invokes the child agent's graph. You get the supervisor/worker pattern and nested traces with no extra machinery; handoffs use LangGraph `Command(goto=...)`.
- **Async core, sync UI bridge.** The engine is `asyncio` (`ainvoke` / `astream`) because MCP sessions and parallel fan‑out need it. Streamlit calls it through a small runner that owns a background event loop and keeps MCP sessions alive across reruns.
- **Everything is declarative.** Agents, workflows, and MCP configs are YAML or DB rows editable in the UI. That makes import/export and versioning trivial.

---

## 4. Orchestration patterns to implement (in this order)

Each pattern is one demo workflow, built as a LangGraph graph from a YAML template. The LangGraph mechanism used is noted per row.

| # | Pattern | What it shows (LangGraph mechanism) | Demo |
|---|---|---|---|
| 1 | **Single agent + tools** | Base loop, tool calling, MCP tools (`create_agent`) | "Summarise this repo" with the filesystem MCP |
| 2 | **Sequential pipeline** | Passing output and state between agents (nodes + edges) | Researcher → Writer → Editor |
| 3 | **Parallel fan‑out / fan‑in** | Parallel branches via `Send`, then a merge node | 3 researchers on sub‑topics → Synthesizer |
| 4 | **Router** | A classifier picks the next agent (structured output + conditional edge) | Support triage: billing / tech / general |
| 5 | **Supervisor / workers** | Supervisor has `ask_<worker>` tools and decides dynamically (agents as tools) | Supervisor delegates to coder, tester, doc‑writer |
| 6 | **Handoff** | An agent transfers control (and conversation) to another (`Command(goto=...)`) | Triage agent hands off to specialist, who replies directly |
| 7 | **Reviewer / critic loop** | Generate → critique → revise until pass or N iterations (cycle with a counter in state) | Writer ↔ Critic with a rubric |
| 8 | **Graph workflow** | Nodes + conditional edges + shared state + cycles + checkpoints (`StateGraph` + `AsyncSqliteSaver`) | Visual builder in the UI; the general form of 2–7 |
| 9 | **Human‑in‑the‑loop** | Approval gate node; tool calls flagged `requires_approval` (`interrupt()` / `HumanInTheLoopMiddleware`, resume with `Command(resume=...)`) | Pause before "send email" / "write file" |
| 10 | **A2A over network** | Expose an agent as an A2A endpoint with an Agent Card; call a remote agent | Two engine instances talking |

**Shared state model** (LangGraph state schema for workflows; reducers merge parallel branch results):
```python
class WorkflowState(BaseModel):
    input: str
    messages: list[BusMessage]  # A2A messages
    artifacts: dict[str, Any]  # named outputs, e.g. "findings", "draft"
    scratch: dict[str, Any]  # node-private data
    step: int
    status: Literal["running", "waiting_approval", "done", "failed"]
```

---

## 5. Agents you can build with this

Every agent is the same runtime with a different **prompt + model + tools + skills + limits**. What makes one agent different from another is configuration, so all of the types below are built in the UI, not in new code. (New *tools* or *MCP servers* sometimes need code or config; new *agents* don't.)

### 5.1 Building blocks: single‑agent types

These are the roles you combine into multi‑agent systems.

| Agent type | What it does | Typical tools / MCP | Notes |
|---|---|---|---|
| **Tool‑using assistant** | Answers by calling tools in a loop until done | Any | The base case; every other type is a specialisation |
| **Researcher** | Searches, reads pages, collects sources, returns findings + citations | `fetch` MCP, web search, Playwright MCP | Returns findings as an artifact, not a long transcript |
| **Planner** | Breaks a goal into an ordered task list (structured output) | None; output only | Feeds a supervisor or an executor |
| **Executor** | Works through a plan step by step | Whatever the steps need | Pairs with the Planner |
| **Router / classifier** | Picks a category or next agent; returns strict JSON | None | Cheap, small model; a node in router workflows |
| **Supervisor** | Delegates to other agents through `ask_<agent>` tools, merges results | Agent tools | Usually the strongest model |
| **Critic / evaluator** | Scores output against a rubric, returns pass/fail + fixes | None | Drives the reviewer loop |
| **Writer / editor** | Turns findings into a document in a given style | `filesystem` MCP, skills (style guides, templates) | Skills hold the house style |
| **Extractor** | Pulls structured fields from text, PDFs, emails | `filesystem`, PDF tool | Strict JSON schema output |
| **Coder** | Reads, edits, and explains code; proposes patches | `filesystem`, `git`, GitHub MCP | Write tools behind approval |
| **Data analyst** | Queries databases, computes, explains results | SQLite / Postgres MCP, Python sandbox tool | Read‑only DB user |
| **Browser agent** | Navigates sites, fills forms, scrapes | Playwright MCP | Approval before submitting anything |
| **Knowledge / RAG agent** | Answers from your documents with citations | Search over local docs (keyword search; vector search is out of POC scope) | |
| **Memory / personal assistant** | Remembers preferences and facts across runs | `memory` MCP or built‑in memory table | |
| **Notifier / integrator** | Posts results to Slack, email, tickets | Slack / GitHub / email MCP | Always approval‑gated |
| **Remote A2A agent** | A proxy for an agent running somewhere else | A2A client tool | Phase 4 |

### 5.2 Multi‑agent systems to build as demos

Each one exercises different patterns from §4. Pick 2–3 as the POC showcase.

| System | Agents | Patterns | MCP / tools |
|---|---|---|---|
| **Research report team** | Planner → 3 parallel Researchers → Writer ↔ Critic | Sequential, parallel, critic loop | `fetch`, web search, `filesystem` |
| **Customer support desk** | Triage router → Billing / Tech / General specialists, escalation to a human | Router, handoff, HITL | Knowledge‑base search, ticket tool |
| **Code review crew** | Supervisor → Security reviewer, Style reviewer, Test‑gap reviewer → Summariser | Supervisor, parallel | `git`, GitHub MCP, `filesystem` |
| **Software mini‑team** | Planner → Coder → Tester → Reviewer, loop until tests pass | Graph with cycle, critic loop | `filesystem`, shell (sandboxed), `git` |
| **Data analyst desk** | Question router → SQL agent → Chart agent → Explainer | Sequential, router | SQLite/Postgres MCP, Python tool |
| **Content pipeline** | Idea generator → Writer → SEO checker → Editor → Publisher (approval) | Sequential, HITL | `fetch`, CMS/Slack MCP |
| **Document processor** | Classifier → Extractor (per doc type) → Validator → Filer | Router, parallel fan‑out | `filesystem`, PDF tool |
| **Incident responder** | Log reader + Metrics reader (parallel) → Diagnoser → Runbook executor (approval) | Parallel, HITL | Log/metrics MCP, shell |
| **Meeting → actions** | Transcript summariser → Action‑item extractor → Ticket creator | Sequential | `filesystem`, GitHub/Jira MCP |
| **Travel / event planner** | Supervisor → Flights, Hotels, Activities agents → Itinerary writer | Supervisor, parallel | `fetch`, Playwright |
| **Debate / second opinion** | Two agents on different models argue → Judge decides | Parallel + judge | None |
| **Cross‑instance delegation** | Local supervisor calls a remote specialist over A2A | A2A | A2A client |

### 5.3 What *can't* be built (yet) without new code

- **Voice / realtime agents**: needs an audio pipeline; out of scope for Streamlit.
- **Long‑running background agents** (run every night, wake on events): needs a scheduler/worker process. Add a small APScheduler worker in phase 5 if wanted.
- **Agents that need custom integrations with no MCP server**: write a Python tool, or wrap the API as a small local MCP server.
- **Autonomous agents with full shell/computer access**: possible, but only inside a sandbox (Docker) with approval gates. Not on your host machine.

### 5.4 Flagship use case: AI software team writing into a target repository

This is the main demo. It uses almost every pattern in §4, and its output can be checked automatically: do the tests pass, and did the reviewer approve?

#### The team

| Agent | Input | Output (artifact) | Model tier |
|---|---|---|---|
| **Requirements analyst** | User request + repo summary | `spec.md`: goal, numbered acceptance criteria, out‑of‑scope, open questions. Asks the user clarifying questions first. | Strong |
| **Architect / planner** | `spec.md` + repo structure | `plan.json`: files to create or change, interfaces/signatures, steps | Strong |
| **Code generator** | `plan.json` + relevant files | Code changes in the repo workspace | Strong or mid |
| **Unit test writer** | `spec.md` + `plan.json` (**not the code**) | Test files in the repo workspace | Mid |
| **Code runner** (plain step, not an AI agent) | Workspace + repo's test/lint commands | `test_report.json`: pass/fail per test, errors, lint results | None |
| **Code reviewer** | Diff + `spec.md` + `test_report.json` | `review.json`: issues with severity, overall `approved: bool` | Strong |

The test writer works from the spec, not the code, so the tests are an independent check and don't just mirror the coder's bugs. The code runner is a fixed command (with a timeout, Docker later); only *interpreting* failures needs a model. Later additions: security reviewer, docs writer, debugger.

#### The workflow (graph with feedback loops)

```
Request ─► Requirements ─► [Human approves spec] ─► Architect
                                                      │
                            ┌─────────────────────────┴────────────────┐
                            ▼                                          ▼
                      Test writer (from spec)                   Code generator
                            └──────────────────┬───────────────────────┘
                                               ▼
                                         Code runner
                                  fail ◄───────┴───────► pass
                                   │                       │
                      Coder fixes (≤ 3 attempts)     Code reviewer
                                   └──► Runner     issues ◄┴► approved
                                                     │           │
                                           Coder (≤ 2 rounds)  [Human approval]
                                                                 │
                                                       Merge locally / keep / discard
```

Hard stops: at most 3 fix attempts and 2 review rounds, plus a cost cap per run. Hitting a limit ends the run with status `needs_human` and keeps everything for inspection.

#### Target repository: where generated code goes

The user registers repositories in the UI (**Repositories** page, §6.8) and picks one when starting a run. **Generated code is written only inside that repository**, never anywhere else on disk.

- **Adding a repo**, in one of three ways:
  - **Local folder**: path to an existing git repo.
  - **New repo**: name and location; the app runs `git init` and adds a starter `.gitignore` / README.
  - **Clone from a URL**: any git URL (a token is only needed for private repos); cloned into the app's workspace folder. Nothing is ever pushed back.
- **Per‑repo settings**:
  - language (dropdown of language profiles, see "Language choice" below). Auto‑detected for existing repos from `pyproject.toml`, `package.json`, `tsconfig.json`, `pom.xml`, `go.mod`…
  - install / test / lint commands, pre‑filled from the language profile and editable per repo
  - default base branch
  - **protected paths** the agents may never touch (`.env`, `.git/`, `.github/workflows/`, secrets)
- **Isolation per run.** Each run creates a branch `agents/<run-id>-<slug>` from the base branch, checked out as a **git worktree** in a separate folder. Agents work in that worktree only, so your current checkout and `main` are never touched, and several runs can work on the same repo at once.
- **A sandboxed file layer.** Agents get repo tools (`list_files`, `read_file`, `write_file`, `apply_patch`, `search_code`) that resolve every path against the worktree root. They reject anything outside it (`..`, absolute paths, symlinks out) or in a protected path. General‑purpose filesystem MCP servers are **not** given to coding agents, so this rule can't be bypassed.
- **A commit per step** (`[architect] plan`, `[coder] attempt 2`, `[tests] add tests`…). The UI can show the diff of each step, and a bad step can be rolled back.
- **Finishing** is **local only**: no push and no pull requests in the POC. After the human approves the final diff:
  - **Merge locally** into the base branch, with the spec, review summary, and test report in the merge commit message, or
  - **Keep the branch**: remove the worktree but leave `agents/<run-id>-<slug>` for you to inspect, merge, or push yourself, or
  - **Discard**: delete the branch and worktree.

  Pushing and PRs (GitHub/GitLab/Azure DevOps) could be added later; they're out of scope for now.
- **Running code safely.** The code runner executes the repo's commands inside the worktree with a timeout and no secrets in its environment. Phase 5 moves this into a Docker container with the worktree mounted.

#### Language choice (selectable in the UI)

The target language is chosen in the UI: a default per repository, which you can change per run when starting the dev team. Each language is a **language profile**, a YAML file in `config/languages/`. Agents and the code runner read everything language‑specific from the profile, so adding a language means adding a profile, not writing code.

A profile defines:
- **Basics:** display name, file extensions, source and test folder conventions.
- **Commands:** install, build/compile (if any), test, lint, and format.
- **Test framework:** used by the test writer, plus a test file naming pattern (`test_*.py`, `*.test.ts`, `*Test.java`…).
- **Scaffold:** starter files for a **new** repo (`pyproject.toml`, `package.json` + `tsconfig.json`, `pom.xml`…).
- **Toolchain check:** commands that confirm the tools are installed (`python --version`, `node -v`…). Settings shows a ✅ / ❌ per language.
- **Coding skill:** a `skills/lang-<id>/SKILL.md` with conventions and idioms that the coder, test writer, and reviewer load automatically.
- **Docker image** for sandboxed runs (phase 5), e.g. `python:3.12-slim`, `node:22-slim`.

| Language | Status in POC | Package / install | Test | Lint / format | New‑repo scaffold |
|---|---|---|---|---|---|
| **Python** | ✅ Supported (first) | `uv sync` (or `pip install -r requirements.txt`) | `pytest -q` | `ruff check .` / `ruff format` | `pyproject.toml`, `src/`, `tests/` |
| **JavaScript (Node)** | ✅ Supported | `npm install` | `npx vitest run` (or Jest) | `npx eslint .` / `npx prettier --write .` | `package.json`, `src/`, `tests/` |
| **TypeScript (Node)** | ✅ Supported | `npm install` | `npx vitest run` | `npx tsc --noEmit` + `npx eslint .` / Prettier | `package.json`, `tsconfig.json`, `src/`, `tests/` |
| **Java** | 🧪 Experimental | `mvn -q install -DskipTests` | `mvn -q test` (JUnit 5) | Checkstyle / `google-java-format` | `pom.xml`, `src/main/java`, `src/test/java` |
| **C# (.NET)** | 🧪 Experimental | `dotnet restore` | `dotnet test` (xUnit) | `dotnet format --verify-no-changes` | `.sln` + project + test project |
| **Go** | 🧪 Experimental | `go mod download` | `go test ./...` | `go vet ./...` / `gofmt` | `go.mod`, `main.go`, `*_test.go` |
| **Rust** | 🧪 Experimental | `cargo fetch` | `cargo test` | `cargo clippy` / `cargo fmt` | `Cargo.toml`, `src/` |
| **Kotlin**, **PHP**, **Ruby** | 📋 Later | Add a profile | | | |

"Supported" means tested end to end in the POC. "Experimental" means the profile exists and is selectable, but expect rough edges. The UI greys out a language whose toolchain isn't installed and shows the install hint.

Example profile (`config/languages/typescript.yaml`):
```yaml
id: typescript
name: TypeScript (Node)
status: supported
extensions: [".ts", ".tsx"]
source_dir: src
test_dir: tests
test_pattern: "*.test.ts"
test_framework: vitest
commands:
  install: npm install
  build: npx tsc --noEmit
  test: npx vitest run --reporter=json
  lint: npx eslint .
  format: npx prettier --write .
toolchain_check: ["node -v", "npm -v"]
scaffold: scaffolds/typescript/
skill: lang-typescript
docker_image: node:22-slim
```

The runner parses test output per framework (pytest JSON/JUnit XML, Vitest/Jest JSON, JUnit XML for Java/.NET, `go test -json`) into the same `test_report.json` shape, so the reviewer and the UI don't care which language ran.

#### Scope ladder

1. Small, self‑contained modules with tests, in a **new** repo (e.g. "URL shortener module with tests"), first in Python, then in JS and TS.
2. Small multi‑file features in a new or small repo.
3. Changes to an **existing** codebase. This needs a repo‑summary step (structure, conventions) and is much harder; do it last.

---

## 6. Streamlit UI: pages

Use `st.navigation` / multipage app. The sidebar shows the global API key status, the default model, and connected MCP server count.

### 6.1 Playground (chat)
- Pick **an agent or a workflow** and chat with it.
- Live stream: assistant text, collapsible tool calls (input/output), agent handoffs shown as "🔀 researcher → writer".
- Right panel: live trace tree, token and cost counter, a **Stop** button.
- Approval prompts render inline (Approve / Reject / Edit args).

### 6.2 Agents
- Table of all agents: name, model, #tools, #skills, last run.
- Create/edit form: name, description, system prompt (text area), model, effort, max turns, token budget, tool multiselect (grouped by source: Python / MCP:<server> / Agents), skill multiselect, "expose as A2A" toggle.
- **Test** button: opens the Playground with this agent.
- Import/export YAML.

### 6.3 Tools
- Unified catalog across sources, with filter chips: `python`, `mcp`, `agent`.
- Each row: name, source, server, description, JSON schema viewer, `requires_approval` toggle, enabled toggle.
- **Try it**: auto‑generated form from the JSON schema runs the tool directly. This is very useful for debugging MCP servers.

### 6.4 Skills
- List the skills found in `skills/` (plus uploaded zips).
- Show SKILL.md rendered, its files, and which agents use it.
- Create a new skill from a template; edit SKILL.md inline.

### 6.5 Workflows
- List and create workflows.
- **Pattern templates** (Sequential, Parallel, Router, Supervisor, Critic loop) produce a pre‑filled graph.
- Graph editor (decided): a table of nodes and edges plus a live **Mermaid/Graphviz** render (`st.graphviz_chart`). Drag‑and‑drop is out of scope for the POC.
- Run with an input; the result goes to Runs.

### 6.6 Runs & Traces
- Run history: status, duration, tokens, cost, root agent/workflow.
- Trace view: indented span tree (LLM call → tool call → child agent run …) with timing bars; click a span to see the full request/response JSON.
- **A2A message log**: sequence‑diagram style (Mermaid `sequenceDiagram` generated from bus messages).
- Replay a run with a different model or prompt; diff the outputs side by side.

### 6.7 Settings
- **AI models** ✅: OpenAI API key entered and verified in the UI (stored in Windows Credential Manager, never in the DB; `.env` also works), list of all models available to the key, default and cheap model, show‑all‑models toggle. Anthropic later.
- **Pricing** ✅: editable price table used for run cost.
- **Usage header** ✅ (every page): today's model calls, tool calls, input/output/total tokens and cost, plus all‑time totals.
- **MCP Servers** (the main settings feature):
  - **Browse public registry**: search the official MCP Registry (`registry.modelcontextprotocol.io`, REST API) and optionally Smithery. Show name, description, transport, required env vars. Click **Add** to pre‑fill the config.
  - **Add manually**:
    - `stdio`: command (`npx`, `uvx`, `docker`), args, env vars (secrets masked).
    - `http` (Streamable HTTP / SSE): URL, headers, OAuth token.
  - Per server: **Connect / Disconnect / Test**, status light, discovered tools/resources/prompts count, last error, enable/disable individual tools.
  - Import a `claude_desktop_config.json` / `.mcp.json`, since many public servers document their config in that format.
- **Skills folder path**, **storage path**, **tracing** (local only, or also export OpenTelemetry).
- **Safety**: global "require approval for all write/side‑effect tools", max turns, max cost per run.
- **Git**: git author name and email for agent commits, default workspace folder for cloned repos, optional token (keyring) only for cloning private repos.

### 6.8 Repositories
- List registered repos: name, path or remote, base branch, last run, open agent branches.
- **Add repo**: local folder / new repo (`git init` + **language dropdown** → scaffold from that language profile) / clone from a git URL.
- Per‑repo settings: **language** (dropdown; auto‑detected for existing repos, overridable), install/test/lint commands (pre‑filled from the language profile), base branch, protected paths.
- Repo browser: file tree + file viewer (read‑only), recent commits.
- **Agent branches**: each run's branch with status, per‑step diff viewer, test results, review comments, and **Merge locally / Keep branch / Discard** buttons.
- The Playground and Workflows pages get a **target repo** picker and a **language** picker (defaults to the repo's language). Any workflow that writes code requires both.

### 6.9 Languages (tab in Settings)
- Table of language profiles: name, status (supported / experimental / later), toolchain check ✅/❌ with versions, and the install hint when a tool is missing.
- View and edit a profile's commands, test framework, scaffold, and linked coding skill. **Add language** creates a new profile from a template.
- **Test profile** runs the toolchain check and scaffolds a throwaway repo, then runs its install + test commands to confirm the profile works.

---

## 7. Data model (SQLite via SQLModel)

```
mcp_servers(id, name, transport, command, args_json, env_json_ref, url, headers_ref,
            enabled, status, last_error, created_at)
tools(id, name, source[python|mcp|agent], server_id?, agent_id?, description,
      input_schema_json, requires_approval, enabled)
skills(id, name, description, path, version)
agents(id, name, description, system_prompt, model, effort, max_turns, budget_tokens,
       tool_ids_json, skill_ids_json, a2a_exposed, version, updated_at)
workflows(id, name, pattern, graph_json, version, updated_at)
repositories(id, name, kind[local|new|cloned], path, remote_url?, base_branch, language_id,
             install_cmd, test_cmd, lint_cmd, protected_paths_json, created_at)
runs(id, kind[agent|workflow], target_id, input, output, status, started_at, ended_at,
     input_tokens, output_tokens, cost_usd, parent_run_id?,
     repo_id?, language_id?, branch?, worktree_path?, final_action[merged|kept|discarded]?)
run_artifacts(id, run_id, name[spec|plan|test_report|review|...], content_json, step, ts)
spans(id, run_id, parent_span_id?, type[llm|tool|agent|handoff|approval|bus|error],
      name, input_json, output_json, started_at, ended_at, tokens_in, tokens_out, meta_json)
bus_messages(id, run_id, from_agent, to_agent, content, ts)
memory(id, agent_id, scope[run|agent|global], key, value, ts)
```
Secrets: env var names and keyring references only. Never store raw secrets in the DB.

---

## 8. Project layout

```
AgentOrchestration/
├── app/                         # Streamlit (thin)
│   ├── Home.py
│   ├── pages/
│   │   ├── 1_Playground.py
│   │   ├── 2_Agents.py
│   │   ├── 3_Tools.py
│   │   ├── 4_Skills.py
│   │   ├── 5_Workflows.py
│   │   ├── 6_Runs.py
│   │   ├── 7_Settings.py
│   │   └── 8_Repositories.py
│   └── components/              # trace_tree.py, chat_stream.py, schema_form.py, graph_view.py
├── core/
│   ├── models.py                # Pydantic/SQLModel schemas
│   ├── storage.py
│   ├── registry.py
│   ├── config.py                # Settings (env / .env)
│   ├── chat.py                  # plain model chat (M0 Playground)
│   ├── llm/
│   │   ├── models.py            # "provider:model" → LangChain chat model; list models
│   │   ├── errors.py            # provider exceptions → friendly messages
│   │   └── fake.py              # ScriptedChatModel for tests
│   ├── runtime/
│   │   ├── agent_factory.py     # AgentDef → create_agent(...) with middleware
│   │   ├── run_service.py       # start/stream/cancel/resume runs; run records
│   │   └── budgets.py           # limits → LangChain middleware
│   ├── tools/
│   │   ├── registry.py          # all tools as LangChain BaseTools, namespaced
│   │   ├── builtin/             # python tools: http_get, read_file, calculator, ...
│   │   └── agent_tool.py        # wraps an agent graph as a tool
│   ├── mcp/
│   │   ├── manager.py           # MultiServerMCPClient lifecycle, status, discovery
│   │   └── registry_client.py   # public registry search
│   ├── skills/loader.py
│   ├── orchestration/
│   │   ├── builder.py           # workflow YAML/DB → LangGraph StateGraph
│   │   ├── patterns.py          # sequential, parallel, router, supervisor, critic templates
│   │   ├── state.py             # WorkflowState + reducers
│   │   └── checkpoints.py       # AsyncSqliteSaver setup
│   ├── a2a/
│   │   ├── bus.py               # in-proc message bus
│   │   └── server.py            # (phase 4) A2A protocol endpoint via FastAPI
│   ├── workspace/
│   │   ├── repo_manager.py      # register / init / clone repos, branches, worktrees, local merge, keep, discard
│   │   ├── repo_tools.py        # sandboxed file tools scoped to the run's worktree
│   │   ├── languages.py         # load profiles, detect repo language, toolchain checks, scaffolding
│   │   ├── test_parsers.py      # pytest / vitest / jest / junit-xml / go-json → test_report.json
│   │   └── runner.py            # runs install/test/lint commands → test_report.json
│   └── tracing/
│       ├── tracer.py            # spans → SQLite + live event queue
│       └── callbacks.py         # LangChain callback handler → tracer
├── config/
│   ├── agents/*.yaml            # incl. requirements, architect, coder, test_writer, reviewer
│   ├── workflows/*.yaml         # incl. dev_team.yaml
│   ├── mcp_servers.yaml
│   └── languages/               # python.yaml, javascript.yaml, typescript.yaml, java.yaml, csharp.yaml, go.yaml, rust.yaml
├── scaffolds/                   # starter files per language for new repos
├── skills/                      # SKILL.md folders, incl. lang-python, lang-javascript, lang-typescript, ...
├── tests/
├── .env.example
├── pyproject.toml
└── docs/                        # PLAN.md, IMPLEMENTATION_PLAN.md, RULES.md, SETUP.md, ...
```

---

## 9. Build phases

Each phase ends with something demoable.

### Phase 0: Skeleton (½ day)
- `pyproject.toml` (uv), `.env`, SQLite, Streamlit multipage shell with empty pages.
- LangChain chat‑model factory (`ChatOpenAI`, Responses API) + scripted fake model for tests; one "hello" call from the Playground using `OPENAI_API_KEY`. ✅ Done.

### Phase 1: Single agent + tools + tracing (1–2 days)
- Agent factory: `AgentDef` → `create_agent` with Python tools, parallel tool calls, error results, and limit middleware.
- Tracer that writes spans. Runs page with a basic trace tree.
- Agents page (CRUD + YAML import/export). Tools page (catalog + "Try it").
- ✅ Demo: a custom agent uses `http_get` + `calculator`; inspect the trace.

### Phase 2: MCP + Settings + Skills (2 days)
- `MCPManager` on `langchain-mcp-adapters`: stdio + Streamable HTTP, persistent sessions in a background loop, tool discovery, and tools registered as `<server>__<tool>`.
- Settings: manual add, import of `mcp.json`, public registry browse/search, connect/test.
- `SkillLoader`: scan `skills/`, inject skill name+description list into the system prompt, provide a `load_skill(name)` tool that returns the SKILL.md body (and `read_skill_file`).
- **Repositories page + `RepoManager`**: add local/new/cloned repos, per‑repo commands, branch + worktree per run, sandboxed repo tools, code runner.
- **Language profiles**: Python, JavaScript, TypeScript fully wired (scaffold, commands, test parser, coding skill); Java, C#, Go, Rust as experimental profiles. Language dropdowns in Repositories and Playground; Languages tab in Settings with toolchain checks.
- ✅ Demo: add the filesystem + fetch MCP servers from the registry, give them to an agent, and have it use a "report‑writing" skill. Then have a single coder agent write a small module + tests into a new repo on an agent branch, and see the diff in the UI.

### Phase 3: Multi‑agent orchestration (3 days)
- Agent‑as‑tool, message bus, and nested runs/traces.
- Workflow builder (YAML → LangGraph `StateGraph`); patterns 2–7 from §4 as YAML templates.
- Workflows page with templates and a Graphviz view; Playground can target workflows.
- A2A message log (sequence diagram).
- **Dev‑team workflow v1** (§5.4) as a sequential pipeline: Requirements → Architect → Test writer ∥ Coder → Runner → Reviewer, with artifacts stored per run.
- ✅ Demo: Supervisor + 3 workers, and a Writer↔Critic loop, with the full nested trace. The dev team builds a small module end to end in a target repo.

### Phase 4: Graph engine, HITL, A2A protocol (3 days)
- Full graph features on LangGraph: conditional edges, cycles with max‑iterations, join nodes, `AsyncSqliteSaver` checkpoints, resume after approval via `interrupt()` / `Command(resume=...)`.
- Approval gates in the Playground.
- Expose selected agents over the **A2A protocol** (FastAPI sidecar serving `/.well-known/agent.json` Agent Card + task endpoints); add a "remote agent" tool type that calls an A2A URL.
- **Dev‑team workflow v2**: full graph with fix and review loops, iteration limits, spec approval + final approval gates, and the finish step (merge locally / keep branch / discard).
- ✅ Demo: two engine instances; agent on instance A delegates to agent on instance B. The dev team takes a request through to a locally merged branch, with one human approval of the spec and one of the final diff.

### Phase 5: Hardening and evaluation (ongoing)
- Budgets (max turns, tokens, $ per run), timeouts, retries, cancellation.
- Memory: per‑agent long‑term notes, **key/value only** (decided; no vector store in the POC).
- Replay and compare runs; a small eval set per workflow (expected properties, LLM‑as‑judge).
- Optional OpenTelemetry export.

---

## 10. Tech choices

| Area | Choice | Why |
|---|---|---|
| Language/env | Python 3.14, `uv` | Fast, simple |
| UI | Streamlit (multipage, `st.chat_message`, `st.status`, `st.graphviz_chart`) | Fastest to POC |
| LLM | LangChain chat models: `langchain-openai` `ChatOpenAI` (Responses API, `store=False`), streaming; `OPENAI_API_KEY` in env or `.env` | One interface for every provider; tool calling, structured output, streaming |
| Agents & orchestration | **LangGraph** (`langchain.agents.create_agent`, `StateGraph`, `Send`, `Command`, `interrupt`) + `langgraph-checkpoint-sqlite` | Graphs, parallelism, cycles, checkpoints, human‑in‑the‑loop without writing our own executor |
| Default models | A strong model for supervisors/planners/critics, a small cheap model for routers, extractors, and high‑volume workers. Set per agent; pick the actual names from what your key can access (`client.models.list()`), since model names change often | Per‑agent model is a core feature to demo |
| Later providers | `langchain-anthropic` (`anthropic:<model>` refs) | Compare models in one workflow |
| MCP | `langchain-mcp-adapters` (`MultiServerMCPClient`) on the official `mcp` SDK, pinned `<2` (ADR‑016) | MCP tools become LangChain tools; stdio + HTTP |
| Public MCP discovery | Official MCP Registry REST API; Smithery optional | "Add MCP from public things" |
| Persistence | SQLite + SQLModel | Zero setup |
| Config | YAML + Pydantic validation | Human‑editable, versionable |
| Graph render | Graphviz / Mermaid (LangGraph can export Mermaid: `graph.get_graph().draw_mermaid()`) | Start simple |
| A2A (phase 4) | FastAPI + A2A protocol (Agent Card JSON, tasks) | Interop with other agent frameworks |
| Tracing | Own LangChain callback handler → SQLite; LangSmith optional | Works offline; no account needed |
| REST API | FastAPI + uvicorn, Swagger UI at `/docs` | Scriptable access to agents, tools, runs (ADR‑017) |
| Secrets | `.env` + `keyring` | Keep them out of the DB |

**Model and LangChain notes for the runtime:**

- `ChatOpenAI(use_responses_api=True, store=False)`: Responses API, with the transcript kept in LangGraph state rather than on OpenAI's servers (no `previous_response_id`). That keeps tracing, replay, handoffs, and provider switching possible.
- Tool calls arrive as `AIMessage.tool_calls`; `create_agent` runs them (in parallel when the model asks for several) and appends `ToolMessage`s. Tool errors become error `ToolMessage`s the model can react to (`ToolErrorMiddleware` / `handle_tool_error`), never crashes.
- Routers, planners, extractors, and reviewers use **structured output** (`response_format=` on `create_agent`, or `model.with_structured_output(Schema)`), never free‑text parsing.
- Reasoning models: `reasoning={"effort": ...}` is a per‑agent setting (low for routers and workers, higher for supervisors and critics).
- Limits are middleware: `ModelCallLimitMiddleware` and `ToolCallLimitMiddleware` per agent; `HumanInTheLoopMiddleware` for `requires_approval` tools.
- Token usage comes from `AIMessage.usage_metadata`; the tracer records it on every model span. Keep the price table in Settings, since prices change.
- Use `AIMessage.text` for display; with the Responses API, `content` can be a list of blocks.
- OpenAI's hosted tools (web search, file search, code interpreter, remote MCP) bypass our approvals and tracing, so they're an optional per‑agent toggle only.

---

## 11. Later: compare against frameworks

The engine is built on LangChain + LangGraph (ADR‑015). Once it works, wrap one or two patterns in each of these to compare:
- **OpenAI Agents SDK**: agents, handoffs, guardrails, and tracing out of the box
- **Claude Agent SDK / Claude Managed Agents** (once you have an Anthropic key): batteries‑included agent harness, or a hosted loop + sandbox
- **CrewAI / AutoGen**: role‑based crews, conversational multi‑agent

Your registry and trace UI should be able to display runs from any of them (adapter → spans).

---

## 12. Risks & gotchas

- **Streamlit reruns the script on every interaction.** Keep the engine, MCP sessions, and event loop in `st.cache_resource` singletons. Stream with `st.write_stream` or by polling a run's event queue.
- **stdio MCP servers on Windows:** use `npx.cmd` / full paths; Node and `uv` must be on PATH. Surface stderr in the UI.
- **Public MCP servers run code on your machine.** Show the exact command before connecting, require confirmation, and default new servers' write tools to `requires_approval`.
- **Runaway agent loops / cost:** hard caps on turns, depth of agent‑to‑agent nesting (e.g. 3), and $ per run.
- **Tool‑name collisions** across MCP servers: namespace as `server__tool`.
- **Agents writing outside the target repo or touching secrets:** all file access goes through the sandboxed repo tools (path resolution + protected paths). Coding agents get no general filesystem MCP. The runner gets no secrets in its environment.
- **Generated code runs on your machine:** timeouts now, Docker in phase 5. Never run in your real checkout; always in the run's worktree.
- **Windows + git worktrees:** long paths and file locks (an open editor, a running process) can block worktree removal. Enable `core.longpaths` and retry cleanup.
- **Context bloat in supervisors:** have workers return summaries and artifacts by reference (`artifacts["findings"]`), not full transcripts. `SummarizationMiddleware` can trim long agent histories.
- **LangChain / LangGraph / MCP version churn:** these move fast. Pin versions in `uv.lock`, keep framework calls inside `core/runtime`, `core/orchestration`, `core/llm`, and `core/mcp`, and upgrade deliberately. Example: `langchain-mcp-adapters` 0.3.1 breaks with `mcp` 2.x, so `mcp` is pinned `<2` (ADR‑016).
- **Python 3.14 is new:** some LangChain dependencies emit deprecation warnings on 3.14. Harmless today; watch for breakage on upgrades.

---

## 13. Definition of done for the POC

- [ ] Add a public MCP server from Settings (registry search → connect) and see its tools in the Tools page
- [ ] Create 4+ agents in the UI with different models, tools, and skills
- [ ] Run each orchestration pattern 1–9 from a template
- [ ] Every run has a navigable trace tree + A2A sequence diagram + token/cost totals
- [ ] An approval gate pauses a workflow and resumes it from the UI
- [ ] One agent is reachable over the A2A protocol from a second instance
- [ ] Agents/workflows export to YAML and re‑import cleanly
- [ ] Register a repo from the UI (local, new, or cloned) with its test/lint commands
- [ ] Choose the language in the UI; the dev team produces passing code + tests in Python, JavaScript, and TypeScript repos
- [ ] The dev team turns a request into code + passing tests on an agent branch in that repo, with nothing written outside it
- [ ] Per‑step diffs, test report, and review are visible in the UI; the run ends in local merge, kept branch, or discard

---

## 14. Open questions to decide

1. **LLM providers:** decided. OpenAI now, behind a provider interface; add Anthropic when a key is available.
2. **Single‑user local tool**, or eventually multi‑user/hosted? This affects auth, secrets, and whether MCP stdio is acceptable.
3. **Graph editor depth:** decided. Table + rendered diagram; no drag‑and‑drop in the POC.
4. **Memory:** decided. Key/value only.
5. **Target domain for demos:** decided. The flagship is the AI software team writing into a target repo (§5.4). Pick one smaller second demo (e.g. research report) to show non‑coding orchestration.
6. **Git hosting:** decided. Local only: merge / keep / discard, no push or PRs in the POC.
7. **Languages for generated code:** decided. Selectable in the UI via language profiles: Python, JavaScript, TypeScript supported; Java, C#, Go, Rust experimental (§5.4).
