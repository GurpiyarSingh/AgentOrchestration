import { useState } from "react";
import { ChevronRight, Lock, Play, Search, Wrench } from "lucide-react";
import { api } from "../api";
import { useData } from "../lib";
import type { JsonSchema, ToolInfo, ToolInvocation } from "../types";
import { Badge, Card, Empty, Field, Pre, Spinner, Toggle, useToast } from "../components/ui";

const SOURCE_LABEL: Record<string, { label: string; tone: string }> = {
  python: { label: "Built-in", tone: "accent" },
  workspace: { label: "Workspace", tone: "info" },
  mcp: { label: "MCP", tone: "ok" },
};

export default function ToolsPage() {
  const { data: tools, reload } = useData(api.tools, []);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const shown = (tools ?? []).filter((t) => !query || (t.name + t.description).toLowerCase().includes(query.toLowerCase()));
  const groups = [
    { id: "python", title: "Built-in tools", sub: "Available to any agent; try them here" },
    { id: "mcp", title: "MCP tools", sub: "From connected MCP servers (manage them on the MCP servers page)" },
    { id: "workspace", title: "Workspace tools", sub: "Sandboxed file tools given to the Test Writer and Code Generator during a build" },
  ];
  return (
    <div className="page">
      <div className="row between">
        <div className="row" style={{ position: "relative", width: 360 }}>
          <Search size={15} className="muted" style={{ position: "absolute", left: 11 }} />
          <input className="input" style={{ paddingLeft: 34 }} placeholder="Search tools" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <span className="small muted">{tools?.length ?? 0} tools · MCP tools come from connected servers</span>
      </div>
      {groups.map((g) => {
        const items = shown.filter((t) => t.source === g.id);
        return (
          <Card key={g.id} title={g.title} sub={g.sub} icon={<Wrench size={16} />} tight>
            {!items.length ? <div className="empty small" style={{ padding: 20 }}>No tools.</div> : items.map((t) => (
              <ToolRow key={t.name} tool={t} open={open === t.name} onToggle={() => setOpen(open === t.name ? null : t.name)} onChanged={reload} />
            ))}
          </Card>
        );
      })}
      {tools && !tools.length && <Empty icon={<Wrench size={20} />} title="No tools" />}
    </div>
  );
}

function ToolRow({ tool, open, onToggle, onChanged }: { tool: ToolInfo; open: boolean; onToggle: () => void; onChanged: () => void }) {
  const toast = useToast();
  const src = SOURCE_LABEL[tool.source] ?? { label: tool.source, tone: "" };
  const setFlag = async (flags: { enabled?: boolean; requires_approval?: boolean }) => {
    try { await api.setToolFlags(tool.name, flags); onChanged(); }
    catch (e) { toast("err", e instanceof Error ? e.message : String(e)); }
  };
  return (
    <div style={{ borderBottom: "1px solid var(--border)" }}>
      <div className="list-item" style={{ borderBottom: 0 }} onClick={onToggle}>
        <ChevronRight size={15} className="muted" style={{ transform: open ? "rotate(90deg)" : undefined, transition: ".15s" }} />
        <div className="grow" style={{ minWidth: 0 }}>
          <div className="row wrap" style={{ gap: 8 }}>
            <span className="mono strong small">{tool.name}</span>
            <Badge tone={src.tone}>{src.label}</Badge>
            {tool.requires_approval && <Badge tone="warn"><Lock size={11} />approval</Badge>}
            {!tool.enabled && <Badge tone="err">disabled</Badge>}
          </div>
          <div className="xs muted ellipsis">{tool.description.split("\n")[0]}</div>
        </div>
        <div className="xs muted ellipsis" style={{ maxWidth: 260 }}>{tool.used_by.length ? `Used by ${tool.used_by.join(", ")}` : "Not assigned"}</div>
      </div>
      {open && (
        <div style={{ padding: "4px 18px 18px 46px" }} className="col">
          <Pre text={tool.description} maxHeight={160} />
          {tool.invokable && (
            <div className="row" style={{ gap: 24 }}>
              <label className="row small"><Toggle checked={tool.enabled} onChange={(v) => setFlag({ enabled: v })} />Enabled</label>
              <label className="row small"><Toggle checked={tool.requires_approval} onChange={(v) => setFlag({ requires_approval: v })} />Requires approval</label>
            </div>
          )}
          {tool.invokable ? <TryIt tool={tool} /> : (
            <div className="callout info small"><Lock size={15} /><div>Bound to the project folder at run time. Paths are checked so agents can never read or write outside it, or touch <span className="mono">.git</span> or <span className="mono">.env</span>.</div></div>
          )}
        </div>
      )}
    </div>
  );
}

function TryIt({ tool }: { tool: ToolInfo }) {
  const props = tool.args_schema.properties ?? {};
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ToolInvocation | null>(null);
  const coerce = (schema: JsonSchema, raw: string): unknown =>
    schema.type === "integer" ? parseInt(raw, 10) : schema.type === "number" ? Number(raw) : schema.type === "boolean" ? raw === "true" : raw;
  const run = async () => {
    setBusy(true);
    try {
      const args = Object.fromEntries(Object.entries(values).filter(([, v]) => v !== "").map(([k, v]) => [k, coerce(props[k], v)]));
      setResult(await api.invokeTool(tool.name, args));
    } catch (e) {
      setResult({ ok: false, output: e instanceof Error ? e.message : String(e), duration_ms: 0 });
    } finally { setBusy(false); }
  };
  return (
    <div className="card" style={{ background: "var(--bg-elev)" }}>
      <div className="card-body col" style={{ gap: 12 }}>
        <div className="strong small">Try it</div>
        <div className="grid-2">
          {Object.entries(props).map(([name, s]) => (
            <Field key={name} label={`${name}${tool.args_schema.required?.includes(name) ? " *" : ""}`} hint={s.description}>
              <input className="input mono" placeholder={s.default !== undefined ? String(s.default) : s.type} value={values[name] ?? ""}
                onChange={(e) => setValues({ ...values, [name]: e.target.value })} onKeyDown={(e) => e.key === "Enter" && run()} />
            </Field>
          ))}
        </div>
        <div className="row"><button className="btn primary sm" disabled={busy} onClick={run}>{busy ? <Spinner size={13} /> : <Play size={13} />}Run</button>
          {result && <Badge tone={result.ok ? "ok" : "err"}>{result.ok ? "OK" : "Error"} · {result.duration_ms} ms</Badge>}</div>
        {result && <Pre text={result.output} maxHeight={260} />}
      </div>
    </div>
  );
}
