import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Ban, Bot, Check, CircleAlert, CircleX, Clock, Cpu, FileCode2, FileText, FlaskConical,
  FolderGit2, FolderOpen, Hammer, Layers, ListChecks, Loader2, Play, Plus, Rocket, ScrollText, ShieldCheck,
  Sparkles, Wrench, Zap,
} from "lucide-react";
import { api } from "../api";
import { fmt, LANG_LABEL, useData } from "../lib";
import type { BuildSnapshot, StageKind, StageRun } from "../types";
import { useApp } from "../components/AppContext";
import { AgentConstellation } from "../components/AgentConstellation";
import { TEAM, avatarStyle, lookForStage } from "../components/agents";
import { PRODUCT } from "../components/Brand";
import { NewProjectModal } from "../components/NewProjectModal";
import {
  Badge, Card, CodeView, DiffView, Empty, Field, Pre, Spinner, StatusBadge, Tabs, useToast,
} from "../components/ui";

const EXAMPLES = [
  "A function that converts any text into a URL-friendly slug: lowercase, ASCII only, words separated by single hyphens, max 80 characters.",
  "An in-memory shopping cart: add/remove items with quantity, apply percentage discount codes, and compute subtotal, tax (configurable rate) and total, rounded to cents.",
  "A password strength checker that scores a password 0-4 and returns the list of unmet rules (length >= 12, upper, lower, digit, symbol, not a common password).",
];

const STAGES_FOR: Record<string, StageKind[]> = {
  requirements: ["requirements"], architecture: ["architecture"], tests: ["tests"], code: ["code", "fix"], run: ["run"], review: ["review"],
};

export default function BuildPage() {
  const { runId } = useParams();
  return (
    <div className="page">
      <div className="split">
        <div className="col" style={{ gap: 20 }}>
          <NewBuild />
          <RecentBuilds activeId={runId} />
        </div>
        {runId ? <BuildView runId={runId} key={runId} /> : <Welcome />}
      </div>
    </div>
  );
}

/* ====================================================================== new build */

function NewBuild() {
  const nav = useNavigate();
  const toast = useToast();
  const { keyReady, settings } = useApp();
  const { data: projects, reload: reloadProjects } = useData(api.projects, []);
  const { data: models } = useData(() => (keyReady ? api.models() : Promise.resolve([])), [keyReady]);
  const [projectId, setProjectId] = useState<string>("");
  const [requirement, setRequirement] = useState("");
  const [model, setModel] = useState("");
  const [fixes, setFixes] = useState(3);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!projectId && projects?.length) setProjectId(projects[0].id);
  }, [projects, projectId]);

  const project = projects?.find((p) => p.id === projectId);
  const noModel = keyReady && !model && !settings?.default_model;
  const canStart = keyReady && !!projectId && requirement.trim().length >= 10 && !busy && !noModel;

  const start = async () => {
    setBusy(true);
    try {
      const snap = await api.startBuild({ project_id: projectId, requirement: requirement.trim(), model: model || null, max_fix_attempts: fixes });
      toast("info", "Build started: the agent team is on it");
      setRequirement("");
      nav(`/builds/${snap.run_id}`);
    } catch (e) {
      toast("err", e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="New build" icon={<Hammer size={16} />} sub="Describe what you need; the agent team does the rest">
      <div className="col" style={{ gap: 14 }}>
        <Field label="Project">
          <div className="row">
            <select className="select grow" value={projectId} onChange={(e) => setProjectId(e.target.value)} disabled={!projects?.length}>
              {!projects?.length && <option value="">No projects yet</option>}
              {projects?.map((p) => <option key={p.id} value={p.id}>{p.name} · {LANG_LABEL[p.language] ?? p.language}</option>)}
            </select>
            <button className="btn icon-btn" title="New project" onClick={() => setCreating(true)}><Plus size={16} /></button>
          </div>
          {project && <div className="hint mono ellipsis" title={project.path}>{project.path}</div>}
        </Field>

        <Field label="Requirement" hint="Plain language. Be specific about inputs, outputs and edge cases.">
          <textarea className="textarea" rows={7} value={requirement} onChange={(e) => setRequirement(e.target.value)}
            placeholder="e.g. A function that validates IBAN numbers and returns the normalized form or a clear error…" />
        </Field>
        <div className="col" style={{ gap: 6 }}>
          <span className="xs muted">Try an example</span>
          <div className="row wrap">
            {["Slugify", "Shopping cart", "Password checker"].map((t, i) => (
              <button key={t} className="chip click" onClick={() => setRequirement(EXAMPLES[i])}><Sparkles size={12} />{t}</button>
            ))}
          </div>
        </div>

        <div className="grid-2" style={{ gridTemplateColumns: "1fr 120px" }}>
          <Field label="Model">
            <select className="select" value={model} onChange={(e) => setModel(e.target.value)} disabled={!keyReady}>
              <option value="">{settings?.default_model ? `Default · ${settings.default_model.replace("openai:", "")}` : "Agent defaults"}</option>
              {(models ?? []).map((m) => <option key={m} value={`openai:${m}`}>{m}</option>)}
            </select>
          </Field>
          <Field label="Fix attempts">
            <select className="select" value={fixes} onChange={(e) => setFixes(Number(e.target.value))}>
              {[0, 1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </Field>
        </div>
        {noModel && <div className="callout warn small"><CircleAlert size={16} />Pick a model here or set a default model in Settings.</div>}

        <button className="btn primary lg block" disabled={!canStart} onClick={start}>
          {busy ? <Spinner /> : <Rocket size={16} />} Start build
        </button>
        {!projects?.length && (
          <button className="btn block" onClick={() => setCreating(true)}><FolderGit2 size={15} />Create your first project</button>
        )}
      </div>
      {creating && <NewProjectModal onClose={() => setCreating(false)} onCreated={(p) => { reloadProjects(); setProjectId(p.id); }} />}
    </Card>
  );
}

function RecentBuilds({ activeId }: { activeId?: string }) {
  const nav = useNavigate();
  const { data } = useData(() => api.builds(), [], 3000);
  return (
    <Card title="Recent builds" icon={<Clock size={16} />} tight>
      {!data?.length ? (
        <div className="empty small" style={{ padding: 28 }}>No builds yet.</div>
      ) : (
        <div className="list" style={{ maxHeight: 420, overflow: "auto" }}>
          {data.map((b) => (
            <div key={b.run_id} className={`list-item ${b.run_id === activeId ? "sel" : ""}`} onClick={() => nav(`/builds/${b.run_id}`)}>
              <div className="grow">
                <div className="strong ellipsis small">{b.title}</div>
                <div className="xs muted ellipsis">{b.project_name} · {fmt.ago(b.started_at)} · tests {b.tests}</div>
              </div>
              <StatusBadge status={b.final_action ?? b.status} />
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function Welcome() {
  return (
    <div className="col" style={{ gap: 20, minWidth: 0 }}>
      <section className="hero-agentic">
        <div className="hero-grid">
          <div className="col" style={{ gap: 14 }}>
            <span className="eyebrow"><Sparkles size={12} style={{ verticalAlign: -1 }} /> {PRODUCT.name} · agentic software delivery</span>
            <h2 className="hero-title">Describe it.<br /><span className="grad-text">Your AI team builds it.</span></h2>
            <p className="hero-lead">
              Six specialised agents work together like a real engineering team. They analyse your requirement, design the
              solution, write tests and code in parallel, run the tests, fix what fails and review the result, writing
              straight into your project folder. Codeloom never runs git: committing is up to you.
            </p>
            <div className="row wrap" style={{ gap: 8 }}>
              <Badge tone="accent"><Bot size={12} />6 agents</Badge>
              <Badge tone="info"><FolderOpen size={12} />Writes into your folder</Badge>
              <Badge tone="ok"><ShieldCheck size={12} />Tested &amp; reviewed</Badge>
            </div>
          </div>
          <AgentConstellation />
        </div>
        <div className="hero-steps">
          {[
            ["1", "Pick or create a project", "Any folder, for Python, JavaScript or TypeScript."],
            ["2", "Describe the requirement", "Inputs, outputs, edge cases. The analyst fills in sensible assumptions."],
            ["3", "Watch and review", "Follow every agent live; the code lands in your folder as it is written."],
          ].map(([n, t, d]) => (
            <div key={n} className="hero-step">
              <span className="n">{n}</span>
              <div><div className="strong small">{t}</div><div className="xs muted">{d}</div></div>
            </div>
          ))}
        </div>
      </section>
      <div className="flow">
        {TEAM.map((a) => (
          <div key={a.key} className="flow-item" style={{ ["--c" as string]: a.color, borderTop: `2px solid ${a.color}` }}>
            <div className="avatar" style={avatarStyle(a.color)}><a.icon size={16} /></div>
            <div className="xs" style={{ color: a.color, textTransform: "uppercase", letterSpacing: ".08em", fontWeight: 700 }}>{a.role}</div>
            <div className="t">{a.name}</div>
            <div className="d">{a.desc}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ====================================================================== build view */

type TabId = "activity" | "spec" | "plan" | "files" | "tests" | "review" | "diff";

function BuildView({ runId }: { runId: string }) {
  const toast = useToast();
  const [poll, setPoll] = useState<number | null>(1500);
  const { data: snap, error, reload } = useData(() => api.build(runId), [runId], poll);
  const [tab, setTab] = useState<TabId>("activity");

  useEffect(() => {
    setPoll(snap && snap.status !== "running" ? null : 1500);
  }, [snap?.status]);

  if (error && !snap) return <Card><Empty icon={<CircleX size={20} />} title="Build not found">{error}</Empty></Card>;
  if (!snap) return <Card><div className="col" style={{ gap: 12 }}><div className="skeleton" style={{ height: 28, width: "40%" }} /><div className="skeleton" style={{ height: 120 }} /><div className="skeleton" style={{ height: 240 }} /></div></Card>;

  const running = snap.status === "running";
  const cancel = async () => {
    try { await api.cancelBuild(runId); toast("info", "Build cancelled"); await reload(); }
    catch (e) { toast("err", e instanceof Error ? e.message : String(e)); }
  };

  const tr = snap.test_report;
  return (
    <div className="col" style={{ gap: 20, minWidth: 0 }}>
      {/* Header */}
      <section className={`card build-head ${running ? "live" : ""}`}>
        <div className="card-body col" style={{ gap: 16 }}>
          <div className="row between" style={{ alignItems: "flex-start" }}>
            <div className="col" style={{ gap: 6, minWidth: 0 }}>
              <div className="row wrap">
                <StatusBadge status={snap.status} />
                {snap.final_action && <StatusBadge status={snap.final_action} />}
                <Badge>{LANG_LABEL[snap.language] ?? snap.language}</Badge>
              </div>
              <h2 style={{ fontSize: 19 }}>{snap.spec?.title ?? "Analysing requirement…"}</h2>
              <div className="small muted" style={{ maxWidth: 900 }}>{snap.requirement}</div>
              <div className="row wrap xs muted" style={{ gap: 14 }}>
                <span className="row" style={{ gap: 5 }}><FolderGit2 size={13} /><Link to={`/projects/${snap.project_id}`}>{snap.project_name}</Link></span>
                <span className="row mono" style={{ gap: 5 }} title="Files are written directly into this folder"><FolderOpen size={13} />{snap.repo_path}</span>
                <span className="row" style={{ gap: 5 }}><Clock size={13} />{fmt.time(snap.started_at)} · {fmt.duration(snap.started_at, snap.ended_at)}</span>
              </div>
            </div>
            <div className="row">
              {running && <button className="btn danger" onClick={cancel}><Ban size={15} />Cancel</button>}
            </div>
          </div>

          <div className="row wrap" style={{ gap: 28 }}>
            <div className="stat"><span className="k">Model calls</span><span className="v">{fmt.int(snap.totals.model_calls)}</span></div>
            <div className="stat"><span className="k">Tool calls</span><span className="v">{fmt.int(snap.totals.tool_calls)}</span></div>
            <div className="stat"><span className="k">Input tokens</span><span className="v">{fmt.int(snap.totals.input_tokens)}</span></div>
            <div className="stat"><span className="k">Output tokens</span><span className="v">{fmt.int(snap.totals.output_tokens)}</span></div>
            <div className="stat"><span className="k">Cost</span><span className="v">{fmt.cost(snap.totals.cost_usd)}</span></div>
            <div className="stat"><span className="k">Tests</span><span className="v" style={{ color: tr ? (tr.ok ? "var(--ok)" : "var(--err)") : undefined }}>{tr ? `${tr.passed}/${tr.total}` : "—"}</span></div>
          </div>

          {snap.error && <div className="callout err small"><CircleX size={16} /><div>{snap.error}</div></div>}
          {!snap.error && snap.message && !running && (
            <div className={`callout small ${snap.status === "done" ? "ok" : snap.final_action ? "info" : "warn"}`}>
              {snap.status === "done" ? <Check size={16} /> : <CircleAlert size={16} />}<div>{snap.message}</div>
            </div>
          )}
        </div>
      </section>

      <Pipeline snap={snap} />

      {/* Details */}
      <section className="card">
        <Tabs<TabId> value={tab} onChange={setTab} tabs={[
          { id: "activity", label: "Activity", icon: <ScrollText size={14} />, count: snap.stages.length },
          { id: "spec", label: "Requirements", icon: <ListChecks size={14} /> },
          { id: "plan", label: "Design", icon: <Layers size={14} /> },
          { id: "files", label: "Files", icon: <FileCode2 size={14} />, count: snap.files.length },
          { id: "tests", label: "Tests", icon: <FlaskConical size={14} />, count: tr ? `${tr.passed}/${tr.total}` : null },
          { id: "review", label: "Review", icon: <ShieldCheck size={14} /> },
          { id: "diff", label: "Diff", icon: <FileText size={14} /> },
        ]} />
        <div className="card-body">
          {tab === "activity" && <Activity stages={snap.stages} running={running} />}
          {tab === "spec" && <SpecView snap={snap} />}
          {tab === "plan" && <PlanView snap={snap} />}
          {tab === "files" && <FilesView snap={snap} />}
          {tab === "tests" && <TestsView snap={snap} />}
          {tab === "review" && <ReviewView snap={snap} />}
          {tab === "diff" && <DiffTab runId={runId} status={snap.status} finalAction={snap.final_action} />}
        </div>
      </section>

    </div>
  );
}

function stageState(snap: BuildSnapshot, stages: StageKind[]): { cls: string; runs: StageRun[] } {
  const runs = snap.stages.filter((s) => stages.includes(s.stage));
  const last = runs[runs.length - 1];
  if (!last) return { cls: snap.status === "running" ? "" : "", runs };
  if (last.status === "running") return { cls: "running", runs };
  if (last.status === "failed") return { cls: snap.status === "running" ? "attention" : "failed", runs };
  return { cls: "done", runs };
}

function Pipeline({ snap }: { snap: BuildSnapshot }) {
  return (
    <div className={`pipeline ${snap.status === "running" ? "live" : ""}`}>
      {TEAM.map(({ key, role, name, icon: Icon, color }) => {
        const { cls, runs } = stageState(snap, STAGES_FOR[key]);
        const last = runs[runs.length - 1];
        const tokens = runs.reduce((a, r) => a + r.input_tokens + r.output_tokens, 0);
        let meta: ReactNode = last ? (last.status === "running" ? "Working" : last.status === "failed" ? "Needs fixes" : "Done") : "Waiting";
        if (key === "code" && runs.length > 1 && last?.status !== "running") meta = `${runs.length - 1} fix${runs.length > 2 ? "es" : ""} applied`;
        if (key === "run" && snap.test_report && last?.status !== "running") meta = `${snap.test_report.passed}/${snap.test_report.total} passed`;
        if (key === "review" && snap.review && last?.status !== "running") meta = snap.review.approved ? "Approved" : "Changes requested";
        if (cls === "running") meta = <span className="row" style={{ gap: 6, color }}>{last?.stage === "fix" ? "Fixing" : "Working"}<span className="thinking"><i /><i /><i /></span></span>;
        const statusIcon = cls === "done" ? <Check size={12} /> : cls === "failed" || cls === "attention" ? <CircleAlert size={12} /> : null;
        return (
          <div key={key} className={`step ${cls}`} style={{ ["--c" as string]: color }}>
            <div className="row between">
              <div className="avatar sm" style={avatarStyle(color)}>{cls === "running" ? <Loader2 size={14} className="spin" /> : <Icon size={14} />}</div>
              <div className="row" style={{ gap: 6 }}>
                {tokens > 0 && <span className="xs faint num">{fmt.compact(tokens)} tok</span>}
                {statusIcon && <span style={{ color: cls === "done" ? "var(--ok)" : cls === "attention" ? "var(--warn)" : "var(--err)" }}>{statusIcon}</span>}
              </div>
            </div>
            <div className="agent-tag">{role}</div>
            <div className="name" style={{ lineHeight: 1.25 }}>{name}</div>
            <div className="meta ellipsis">{meta}</div>
          </div>
        );
      })}
    </div>
  );
}

function Activity({ stages, running }: { stages: StageRun[]; running: boolean }) {
  if (!stages.length) return <Empty icon={<Loader2 size={20} className="spin" />} title="Starting…">Preparing the build workspace.</Empty>;
  return (
    <div className="timeline" style={{ margin: -18 }}>
      {stages.map((s) => {
        const look = lookForStage(s.stage);
        const Icon = s.stage === "fix" ? Wrench : look.icon;
        return (
          <div key={s.id} className="tl-item">
            <div className="avatar sm" style={avatarStyle(s.status === "failed" ? "var(--err)" : look.color)}>
              {s.status === "running" ? <Loader2 size={14} className="spin" /> : <Icon size={14} />}
            </div>
            <div className="col" style={{ gap: 4, minWidth: 0 }}>
              <div className="row wrap" style={{ gap: 8 }}>
                <span className="strong small">{s.title}{s.attempt > 1 ? ` #${s.attempt}` : ""}</span>
                <span className="xs muted mono">{s.agent}</span>
                {s.model && <span className="xs faint mono">{s.model.replace("openai:", "")}</span>}
              </div>
              <div className="tl-summary">{s.status === "running" ? "Working…" : s.summary}</div>
            </div>
            <div className="col xs muted num" style={{ gap: 2, alignItems: "flex-end", whiteSpace: "nowrap" }}>
              <span>{fmt.duration(s.started_at, s.ended_at)}</span>
              {(s.model_calls > 0) && <span><Cpu size={11} /> {s.model_calls} · <Zap size={11} /> {fmt.compact(s.input_tokens + s.output_tokens)}</span>}
              {s.tool_calls > 0 && <span><Wrench size={11} /> {s.tool_calls} tools</span>}
            </div>
          </div>
        );
      })}
      {running && <div className="tl-item"><div className="tl-ic running"><Play size={13} /></div><div className="small muted">The team is working…</div><div /></div>}
    </div>
  );
}

function Waiting({ what }: { what: string }) {
  return <Empty icon={<Clock size={20} />} title={`No ${what} yet`}>It will appear here as soon as the agent finishes.</Empty>;
}

function SpecView({ snap }: { snap: BuildSnapshot }) {
  const s = snap.spec;
  if (!s) return <Waiting what="specification" />;
  return (
    <div className="col" style={{ gap: 18 }}>
      <div><h3 style={{ fontSize: 16 }}>{s.title}</h3><p className="muted" style={{ marginTop: 6 }}>{s.summary}</p></div>
      <div className="col"><h3>Acceptance criteria</h3>
        <ol className="criteria">{s.acceptance_criteria.map((c, i) => <li key={i}><span className="n">{i + 1}</span><span>{c}</span></li>)}</ol>
      </div>
      <div className="grid-2">
        <div className="col"><h3>Assumptions</h3>{s.assumptions.length ? <ul className="small" style={{ margin: 0, paddingLeft: 18, color: "var(--text-2)" }}>{s.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul> : <span className="small muted">None</span>}</div>
        <div className="col"><h3>Out of scope</h3>{s.out_of_scope.length ? <ul className="small" style={{ margin: 0, paddingLeft: 18, color: "var(--text-2)" }}>{s.out_of_scope.map((a, i) => <li key={i}>{a}</li>)}</ul> : <span className="small muted">None</span>}</div>
      </div>
    </div>
  );
}

function PlanView({ snap }: { snap: BuildSnapshot }) {
  const p = snap.plan;
  if (!p) return <Waiting what="design" />;
  return (
    <div className="col" style={{ gap: 18 }}>
      <div><h3>Approach</h3><p className="muted" style={{ marginTop: 6 }}>{p.approach}</p></div>
      <div className="col"><h3>Files</h3>
        <table className="table"><thead><tr><th>Path</th><th>Kind</th><th>Purpose</th></tr></thead>
          <tbody>{p.files.map((f) => <tr key={f.path}><td className="mono">{f.path}</td><td><Badge tone={f.kind === "test" ? "info" : "accent"}>{f.kind}</Badge></td><td className="small">{f.purpose}</td></tr>)}</tbody>
        </table>
      </div>
      <div className="col"><h3>Public interface</h3><CodeView text={p.interfaces} maxHeight={420} /></div>
    </div>
  );
}

function FilesView({ snap }: { snap: BuildSnapshot }) {
  const [sel, setSel] = useState<string | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const files = useMemo(() => [...snap.files].sort(), [snap.files]);
  useEffect(() => { if (!sel && files.length) setSel(files.find((f) => !f.startsWith("tests/")) ?? files[0]); }, [files, sel]);
  useEffect(() => {
    if (!sel) return;
    setContent(null); setErr(null);
    api.buildFile(snap.run_id, sel).then(setContent).catch((e) => setErr(e.message));
  }, [sel, snap.run_id, snap.status, snap.stages.length, snap.final_action]);
  if (!files.length) return <Waiting what="files" />;
  return (
    <div className="split-wide" style={{ margin: -18 }}>
      <div className="file-tree" style={{ borderRight: "1px solid var(--border)", paddingTop: 8, paddingBottom: 8 }}>
        {files.map((f) => (
          <div key={f} className={`file-item ${f === sel ? "sel" : ""}`} onClick={() => setSel(f)}>
            {f.startsWith("tests/") ? <FlaskConical size={13} /> : <FileCode2 size={13} />}<span className="ellipsis">{f}</span>
          </div>
        ))}
      </div>
      <div style={{ padding: 16, minWidth: 0 }}>
        {sel && <div className="row between" style={{ marginBottom: 10 }}><span className="mono small">{sel}</span></div>}
        {err ? <div className="callout err small">{err}</div> : content === null ? <div className="skeleton" style={{ height: 300 }} /> : <CodeView text={content} />}
      </div>
    </div>
  );
}

function TestsView({ snap }: { snap: BuildSnapshot }) {
  const r = snap.test_report;
  if (!r) return <Waiting what="test results" />;
  return (
    <div className="col" style={{ gap: 16 }}>
      <div className="row wrap" style={{ gap: 28 }}>
        <div className="stat"><span className="k">Result</span><span className="v" style={{ color: r.ok ? "var(--ok)" : "var(--err)" }}>{r.ok ? "Passing" : r.timed_out ? "Timed out" : "Failing"}</span></div>
        <div className="stat"><span className="k">Passed</span><span className="v">{r.passed}</span></div>
        <div className="stat"><span className="k">Failed</span><span className="v">{r.failed + r.errors}</span></div>
        <div className="stat"><span className="k">Skipped</span><span className="v">{r.skipped}</span></div>
        <div className="stat"><span className="k">Duration</span><span className="v">{r.duration_s}s</span></div>
      </div>
      <div className="xs muted mono">$ {r.command}</div>
      {r.cases.length > 0 && (
        <table className="table">
          <thead><tr><th style={{ width: 110 }}>Status</th><th>Test</th></tr></thead>
          <tbody>{r.cases.map((c, i) => (
            <tr key={i}>
              <td><Badge tone={c.status === "passed" ? "ok" : c.status === "skipped" ? "" : "err"}>{c.status}</Badge></td>
              <td><div className="mono small">{c.name}</div>{c.message && <Pre text={c.message} maxHeight={200} />}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
      <details><summary className="small muted" style={{ cursor: "pointer" }}>Runner output</summary><div style={{ marginTop: 10 }}><Pre text={r.output || "(no output)"} /></div></details>
    </div>
  );
}

function ReviewView({ snap }: { snap: BuildSnapshot }) {
  const r = snap.review;
  if (!r) return <Waiting what="review" />;
  return (
    <div className="col" style={{ gap: 16 }}>
      <div className={`callout ${r.approved ? "ok" : "warn"}`}>
        {r.approved ? <ShieldCheck size={18} style={{ color: "var(--ok)" }} /> : <CircleAlert size={18} style={{ color: "var(--warn)" }} />}
        <div><div className="strong">{r.approved ? "Approved" : "Changes requested"}</div><div className="small" style={{ color: "var(--text-2)" }}>{r.summary}</div></div>
      </div>
      {r.issues.length > 0 && (
        <table className="table">
          <thead><tr><th style={{ width: 100 }}>Severity</th><th style={{ width: 220 }}>File</th><th>Finding</th></tr></thead>
          <tbody>{r.issues.map((i, k) => (
            <tr key={k}>
              <td><Badge tone={i.severity === "high" ? "err" : i.severity === "medium" ? "warn" : ""}>{i.severity}</Badge></td>
              <td className="mono small">{i.file}</td><td className="small">{i.message}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
      {snap.review_rounds > 1 && <div className="xs muted">Review rounds: {snap.review_rounds}</div>}
    </div>
  );
}

function DiffTab({ runId, status, finalAction }: { runId: string; status: string; finalAction: string | null }) {
  const [text, setText] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { setText(null); api.buildDiff(runId).then(setText).catch((e) => setErr(e.message)); }, [runId, status, finalAction]);
  if (err) return <div className="callout err small">{err}</div>;
  if (text === null) return <div className="skeleton" style={{ height: 300 }} />;
  if (!text.trim()) return <Waiting what="changes" />;
  return <DiffView text={text} />;
}
