import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Activity, Bot, Brain, ChevronRight, Cpu, Hammer, MessageSquare, Wrench } from "lucide-react";
import { api } from "../api";
import { fmt, useData } from "../lib";
import type { SpanNode } from "../types";
import { Badge, Card, Empty, Pre, StatusBadge } from "../components/ui";

const KIND: Record<string, { label: string; icon: typeof Bot; tone: string }> = {
  pipeline: { label: "Build", icon: Hammer, tone: "accent" },
  agent: { label: "Agent", icon: Bot, tone: "info" },
  chat: { label: "Chat", icon: MessageSquare, tone: "" },
};

export default function RunsPage() {
  const { runId } = useParams();
  const nav = useNavigate();
  const { data: runs } = useData(() => api.runs(200), [], 5000);
  const [kind, setKind] = useState("all");
  const shown = (runs ?? []).filter((r) => kind === "all" || r.kind === kind);
  const sel = runs?.find((r) => r.run_id === runId);

  return (
    <div className="page">
      <div className="segmented" style={{ justifySelf: "start" }}>
        {["all", "pipeline", "agent", "chat"].map((k) => (
          <button key={k} className={kind === k ? "on" : ""} onClick={() => setKind(k)}>{k === "all" ? "All" : KIND[k].label + "s"}</button>
        ))}
      </div>
      <Card tight>
        {!shown.length ? <Empty icon={<Activity size={20} />} title="No runs yet">Builds, agent chats and model chats appear here with full traces.</Empty> : (
          <div style={{ maxHeight: 380, overflow: "auto" }}>
            <table className="table">
              <thead><tr><th>Kind</th><th>Target</th><th>Input</th><th>Status</th><th>Model calls</th><th>Tool calls</th><th>Tokens in / out</th><th>Cost</th><th>Started</th><th>Duration</th></tr></thead>
              <tbody>{shown.map((r) => {
                const k = KIND[r.kind] ?? { label: r.kind, icon: Activity, tone: "" };
                return (
                  <tr key={r.run_id} className={`click ${r.run_id === runId ? "sel" : ""}`} onClick={() => nav(`/runs/${r.run_id}`)}>
                    <td><Badge tone={k.tone}><k.icon size={11} />{k.label}</Badge></td>
                    <td className="small strong">{r.target.replace("openai:", "")}</td>
                    <td className="small muted ellipsis" style={{ maxWidth: 280 }}>{r.input}</td>
                    <td><StatusBadge status={r.status} /></td>
                    <td className="num small">{r.model_calls}</td>
                    <td className="num small">{r.tool_calls}</td>
                    <td className="num small">{fmt.int(r.input_tokens)} / {fmt.int(r.output_tokens)}</td>
                    <td className="num small">{fmt.cost(r.cost_usd)}</td>
                    <td className="small muted">{fmt.ago(r.started_at)}</td>
                    <td className="small muted num">{fmt.duration(r.started_at, r.ended_at)}</td>
                  </tr>
                );
              })}</tbody>
            </table>
          </div>
        )}
      </Card>
      {sel && <Trace runId={sel.run_id} title={sel.target} kind={sel.kind} />}
    </div>
  );
}

function Trace({ runId, title, kind }: { runId: string; title: string; kind: string }) {
  const { data: spans } = useData(() => api.spans(runId), [runId], 4000);
  const [open, setOpen] = useState<SpanNode | null>(null);
  const flat: { n: SpanNode; depth: number }[] = [];
  const walk = (ns: SpanNode[], d: number) => ns.forEach((n) => { flat.push({ n, depth: d }); walk(n.children, d + 1); });
  walk(spans ?? [], 0);
  const maxDur = Math.max(1, ...flat.map((f) => f.n.duration_ms ?? 0));
  return (
    <div className="grid-2" style={{ gridTemplateColumns: "1.2fr 1fr", alignItems: "start" }}>
      <Card title="Trace" sub={<span className="mono">{runId} · {title}</span>} icon={<Activity size={16} />} tight
        actions={kind === "pipeline" ? <Link className="btn sm" to={`/builds/${runId}`}><Hammer size={13} />Open build</Link> : undefined}>
        {!flat.length ? <div className="empty small" style={{ padding: 24 }}>No spans.</div> : flat.map(({ n, depth }) => {
          const Icon = n.type === "llm" ? Cpu : n.type === "tool" ? Wrench : n.type === "agent" ? Brain : Activity;
          const err = n.meta.error as string | undefined;
          return (
            <div key={n.id} className="span-row" style={{ background: open?.id === n.id ? "var(--accent-soft)" : undefined }} onClick={() => setOpen(n)}>
              <div className="row" style={{ paddingLeft: depth * 18, minWidth: 0 }}>
                {n.children.length ? <ChevronRight size={12} className="faint" /> : <span style={{ width: 12 }} />}
                <Icon size={14} className={err ? "" : "muted"} style={err ? { color: "var(--err)" } : undefined} />
                <span className="small strong ellipsis">{n.name.replace("openai:", "")}</span>
                <span className="xs faint">{n.type}</span>
              </div>
              <div className="row xs muted num" style={{ gap: 12 }}>
                {(n.tokens_in > 0 || n.tokens_out > 0) && <span>{fmt.int(n.tokens_in)}→{fmt.int(n.tokens_out)}</span>}
                <div style={{ width: 90 }}><div className="span-bar" style={{ width: `${Math.max(3, ((n.duration_ms ?? 0) / maxDur) * 100)}%` }} /></div>
                <span style={{ width: 64, textAlign: "right" }}>{n.duration_ms === null ? "…" : `${(n.duration_ms / 1000).toFixed(2)}s`}</span>
              </div>
            </div>
          );
        })}
      </Card>
      <Card title={open ? open.name : "Span details"} sub={open ? `${open.type} · ${open.duration_ms ?? "…"} ms` : "Select a span"} className="sticky">
        {!open ? <div className="small muted">Click a span to see its full input and output.</div> : (
          <div className="col" style={{ gap: 12 }}>
            {typeof open.meta.error === "string" && <div className="callout err small">{open.meta.error}</div>}
            <div className="row wrap">{Object.entries(open.meta).filter(([k]) => k !== "error").map(([k, v]) => <span key={k} className="chip"><span className="muted">{k}</span> {String(v)}</span>)}</div>
            <div className="label">Input</div><Pre text={typeof open.input === "string" ? open.input : JSON.stringify(open.input, null, 2)} maxHeight={280} />
            <div className="label">Output</div><Pre text={typeof open.output === "string" ? open.output : JSON.stringify(open.output, null, 2)} maxHeight={280} />
          </div>
        )}
      </Card>
    </div>
  );
}
