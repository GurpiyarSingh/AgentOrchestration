import { useEffect, useMemo, useState } from "react";
import {
  ChevronRight, CircleAlert, Download, ExternalLink, FileJson, Globe, Lock, Pencil, Plug, PlugZap, Plus, RefreshCw,
  Search, Server, Terminal, Trash2, Unplug, Wrench,
} from "lucide-react";
import { api } from "../api";
import { useData } from "../lib";
import type { McpServerConfig, McpServerView, RegistryEntry } from "../types";
import { Badge, Card, Confirm, Field, Modal, Spinner, useToast } from "../components/ui";

const PRESETS: { label: string; desc: string; cfg: Partial<McpServerConfig>; needs?: string }[] = [
  { label: "Fetch", desc: "Fetch web pages as markdown", cfg: { name: "fetch", transport: "stdio", command: "uvx", args: ["mcp-server-fetch"] }, needs: "uv" },
  { label: "Filesystem", desc: "Read/write files in a folder you choose", cfg: { name: "filesystem", transport: "stdio", command: "npx", args: ["-y", "@modelcontextprotocol/server-filesystem", "C:\\path\\to\\folder"] }, needs: "Node.js" },
  { label: "Memory", desc: "A knowledge-graph memory", cfg: { name: "memory", transport: "stdio", command: "npx", args: ["-y", "@modelcontextprotocol/server-memory"] }, needs: "Node.js" },
  { label: "Time", desc: "Current time and timezone conversion", cfg: { name: "time", transport: "stdio", command: "uvx", args: ["mcp-server-time"] }, needs: "uv" },
];

const blank = (): McpServerConfig => ({ name: "", transport: "stdio", command: "", args: [], env: {}, url: "", headers: {}, enabled: true });

const STATUS_TONE: Record<string, string> = { connected: "ok", connecting: "accent", error: "err", disconnected: "" };

export default function McpPage() {
  const toast = useToast();
  const { data: servers, reload, loading } = useData(api.mcpServers, [], 5000);
  const [editing, setEditing] = useState<{ cfg: McpServerConfig; isNew: boolean; hints?: RegistryEntry } | null>(null);
  const [registry, setRegistry] = useState(false);
  const [importing, setImporting] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  const act = async (name: string, fn: () => Promise<McpServerView>, okMsg: string) => {
    setBusy(name);
    try {
      const v = await fn();
      if (v.status === "error") toast("err", `${name}: ${v.error}`); else toast("ok", okMsg);
      await reload();
    } catch (e) { toast("err", e instanceof Error ? e.message : String(e)); } finally { setBusy(null); }
  };

  const edit = async (name: string) => {
    const v = servers?.find((s) => s.name === name);
    if (!v) return;
    setEditing({
      isNew: false,
      cfg: {
        name: v.name, transport: v.transport, command: v.command, args: v.args, url: v.url, enabled: v.enabled,
        env: Object.fromEntries(v.env_keys.map((k) => [k, ""])), headers: Object.fromEntries(v.header_keys.map((k) => [k, ""])),
      },
    });
  };

  const connectedTools = (servers ?? []).reduce((a, s) => a + (s.status === "connected" ? s.tools.length : 0), 0);

  return (
    <div className="page">
      <section className="card">
        <div className="card-body row between wrap" style={{ gap: 16 }}>
          <div className="col" style={{ gap: 4 }}>
            <div className="row"><Plug size={18} style={{ color: "var(--accent)" }} /><h2 style={{ fontSize: 17 }}>MCP servers</h2></div>
            <div className="small muted" style={{ maxWidth: 680 }}>
              Connect Model Context Protocol servers to give your agents new tools: web fetch, files, GitHub, databases and
              more. Connected tools appear on the Tools page and can be assigned to agents.
            </div>
          </div>
          <div className="row wrap">
            <button className="btn" onClick={() => setImporting(true)}><FileJson size={15} />Import JSON</button>
            <button className="btn" onClick={() => setEditing({ cfg: blank(), isNew: true })}><Plus size={15} />Add manually</button>
            <button className="btn primary" onClick={() => setRegistry(true)}><Search size={15} />Browse registry</button>
          </div>
        </div>
        <div className="row wrap" style={{ gap: 24, padding: "0 18px 16px" }}>
          <div className="stat"><span className="k">Servers</span><span className="v">{servers?.length ?? 0}</span></div>
          <div className="stat"><span className="k">Connected</span><span className="v">{(servers ?? []).filter((s) => s.status === "connected").length}</span></div>
          <div className="stat"><span className="k">Tools available</span><span className="v">{connectedTools}</span></div>
        </div>
      </section>

      {!loading && !servers?.length && (
        <Card title="Quick start" sub="Popular reference servers. Click one to review and connect." icon={<PlugZap size={16} />}>
          <div className="grid" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}>
            {PRESETS.map((p) => (
              <button key={p.label} className="agent-card" style={{ ["--c" as string]: "var(--accent)", textAlign: "left", font: "inherit", color: "inherit" }}
                onClick={() => setEditing({ cfg: { ...blank(), ...p.cfg, args: [...(p.cfg.args ?? [])] }, isNew: true })}>
                <div className="row between"><span className="strong">{p.label}</span><Badge>{p.needs}</Badge></div>
                <span className="xs muted">{p.desc}</span>
                <span className="xs mono faint ellipsis">{p.cfg.command} {(p.cfg.args ?? []).join(" ")}</span>
              </button>
            ))}
          </div>
        </Card>
      )}

      {(servers ?? []).map((s) => (
        <section key={s.name} className="card">
          <div className="card-body col" style={{ gap: 12 }}>
            <div className="row between wrap" style={{ gap: 12 }}>
              <div className="row" style={{ gap: 12, minWidth: 0 }}>
                <div className="avatar" style={{ color: s.status === "connected" ? "var(--ok)" : "var(--muted)", borderColor: "var(--border-strong)" }}>
                  {s.transport === "http" ? <Globe size={16} /> : <Terminal size={16} />}
                </div>
                <div className="col" style={{ gap: 2, minWidth: 0 }}>
                  <div className="row wrap" style={{ gap: 8 }}>
                    <span className="strong">{s.name}</span>
                    <Badge tone={STATUS_TONE[s.status]}><span className={`dot ${s.status === "connecting" ? "pulse" : ""}`} />{s.status}</Badge>
                    {s.status === "connected" && <Badge tone="accent"><Wrench size={11} />{s.tools.length} tools</Badge>}
                    {(s.env_keys.length > 0 || s.header_keys.length > 0) && <Badge><Lock size={11} />{s.env_keys.length + s.header_keys.length} secrets</Badge>}
                  </div>
                  <span className="xs mono muted ellipsis" style={{ maxWidth: 760 }}>
                    {s.transport === "http" ? s.url : `${s.command ?? ""} ${s.args.join(" ")}`}
                  </span>
                </div>
              </div>
              <div className="row">
                {s.status === "connected"
                  ? <button className="btn sm" disabled={busy === s.name} onClick={() => act(s.name, () => api.disconnectMcp(s.name), `Disconnected ${s.name}`)}><Unplug size={13} />Disconnect</button>
                  : <button className="btn sm primary" disabled={busy === s.name} onClick={() => act(s.name, () => api.connectMcp(s.name), `Connected ${s.name}`)}>
                      {busy === s.name ? <Spinner size={13} /> : <PlugZap size={13} />}{s.status === "error" ? "Retry" : "Connect"}
                    </button>}
                {s.status === "connected" && <button className="btn sm ghost" title="Reconnect" onClick={() => act(s.name, () => api.connectMcp(s.name), `Reconnected ${s.name}`)}><RefreshCw size={13} /></button>}
                <button className="btn sm ghost" onClick={() => edit(s.name)}><Pencil size={13} />Edit</button>
                <button className="btn sm danger" onClick={() => setDeleting(s.name)}><Trash2 size={13} /></button>
              </div>
            </div>
            {s.error && <div className="callout err small"><CircleAlert size={15} style={{ flex: "0 0 auto", marginTop: 2 }} /><div>{s.error}</div></div>}
            {s.tools.length > 0 && (
              <div>
                <button className="btn ghost sm" onClick={() => setOpen(open === s.name ? null : s.name)}>
                  <ChevronRight size={13} style={{ transform: open === s.name ? "rotate(90deg)" : undefined }} />{open === s.name ? "Hide" : "Show"} tools
                </button>
                {open === s.name && (
                  <div className="list card" style={{ marginTop: 8, background: "var(--bg-elev)" }}>
                    {s.tools.map((t) => (
                      <div key={t.name} className="list-item" style={{ cursor: "default", alignItems: "flex-start" }}>
                        <Wrench size={14} className="muted" style={{ marginTop: 3 }} />
                        <div className="grow" style={{ minWidth: 0 }}>
                          <div className="row wrap" style={{ gap: 8 }}>
                            <span className="mono small strong">{t.name}</span>
                            {t.read_only && <Badge tone="ok">read-only</Badge>}
                            {t.destructive && <Badge tone="warn"><Lock size={10} />needs approval</Badge>}
                          </div>
                          <div className="xs muted">{t.description.split("\n")[0]}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </section>
      ))}

      {editing && (
        <ServerModal initial={editing.cfg} isNew={editing.isNew} hints={editing.hints} onClose={() => setEditing(null)}
          onSaved={async (v) => {
            setEditing(null);
            if (v.status === "error") toast("err", `Saved, but ${v.name} failed to connect: ${v.error}`);
            else toast("ok", v.status === "connected" ? `${v.name} connected with ${v.tools.length} tools` : `Saved ${v.name}`);
            await reload();
          }} />
      )}
      {registry && (
        <RegistryModal onClose={() => setRegistry(false)} onUse={(e) => {
          setRegistry(false);
          setEditing({ cfg: { ...e.draft, args: [...e.draft.args] }, isNew: true, hints: e });
        }} />
      )}
      {importing && <ImportModal onClose={() => setImporting(false)} onDone={async (n) => { setImporting(false); toast("ok", `Imported ${n} server(s)`); await reload(); }} />}
      {deleting && (
        <Confirm title={`Remove ${deleting}?`} danger confirmLabel="Remove" body="The server is disconnected and its saved secrets are deleted. Agents lose its tools."
          onConfirm={async () => { await api.deleteMcpServer(deleting); toast("ok", "Removed"); reload(); }} onClose={() => setDeleting(null)} />
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------------------- add / edit */

type Row = { key: string; value: string };
const toRows = (o: Record<string, string>): Row[] => Object.entries(o).map(([key, value]) => ({ key, value }));
const fromRows = (rows: Row[]) => Object.fromEntries(rows.filter((r) => r.key.trim()).map((r) => [r.key.trim(), r.value]));

function KeyValueRows({ rows, onChange, keyPlaceholder, existing, hints }: {
  rows: Row[]; onChange: (r: Row[]) => void; keyPlaceholder: string; existing?: boolean;
  hints?: Record<string, { description: string; required: boolean; secret: boolean }>;
}) {
  return (
    <div className="col" style={{ gap: 8 }}>
      {rows.map((r, i) => {
        const h = hints?.[r.key];
        return (
          <div key={i} className="col" style={{ gap: 3 }}>
            <div className="row">
              <input className="input mono" style={{ flex: "0 0 38%" }} placeholder={keyPlaceholder} value={r.key}
                onChange={(e) => onChange(rows.map((x, j) => (j === i ? { ...x, key: e.target.value } : x)))} />
              <input className="input mono grow" type="password" autoComplete="off"
                placeholder={existing ? "saved (leave empty to keep)" : h?.required ? "required" : "value"} value={r.value}
                onChange={(e) => onChange(rows.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} />
              <button type="button" className="btn ghost icon-btn" onClick={() => onChange(rows.filter((_, j) => j !== i))}><Trash2 size={14} /></button>
            </div>
            {h?.description && <span className="xs muted">{h.required && <b style={{ color: "var(--warn)" }}>Required. </b>}{h.description}</span>}
          </div>
        );
      })}
      <button type="button" className="btn sm" style={{ alignSelf: "flex-start" }} onClick={() => onChange([...rows, { key: "", value: "" }])}>
        <Plus size={13} />Add
      </button>
    </div>
  );
}

function ServerModal({ initial, isNew, hints, onClose, onSaved }: {
  initial: McpServerConfig; isNew: boolean; hints?: RegistryEntry; onClose: () => void; onSaved: (v: McpServerView) => void;
}) {
  const [cfg, setCfg] = useState<McpServerConfig>(initial);
  const [argsText, setArgsText] = useState(initial.args.join("\n"));
  const [env, setEnv] = useState<Row[]>(toRows(initial.env));
  const [headers, setHeaders] = useState<Row[]>(toRows(initial.headers));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const envHints = useMemo(() => Object.fromEntries((hints?.env_vars ?? []).map((v) => [v.name, v])), [hints]);
  const missingRequired = (hints?.env_vars ?? []).filter((v) => v.required && !env.find((r) => r.key === v.name && r.value.trim()));
  const nameOk = /^[a-zA-Z][a-zA-Z0-9_.-]{1,48}$/.test(cfg.name.trim());

  const save = async () => {
    setBusy(true);
    setError(null);
    const body: McpServerConfig = {
      ...cfg, name: cfg.name.trim(),
      args: cfg.transport === "stdio" ? argsText.split("\n").map((a) => a.trim()).filter(Boolean) : [],
      env: cfg.transport === "stdio" ? fromRows(env) : {},
      headers: cfg.transport === "http" ? fromRows(headers) : {},
      command: cfg.transport === "stdio" ? (cfg.command ?? "").trim() : null,
      url: cfg.transport === "http" ? (cfg.url ?? "").trim() : null,
    };
    try {
      onSaved(await api.saveMcpServer(body, true));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  };

  return (
    <Modal title={isNew ? (hints ? `Add ${hints.title}` : "Add MCP server") : `Edit ${initial.name}`} width={680} onClose={onClose} footer={<>
      {missingRequired.length > 0 && <span className="xs grow" style={{ color: "var(--warn)" }}>Missing required: {missingRequired.map((v) => v.name).join(", ")}</span>}
      <button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn primary" disabled={busy || !nameOk} onClick={save}>{busy ? <Spinner size={14} /> : <PlugZap size={15} />}Save &amp; connect</button>
    </>}>
      {hints && (
        <div className="callout info small">
          <Server size={15} style={{ flex: "0 0 auto", marginTop: 2 }} />
          <div><div className="strong">{hints.name} <span className="faint">{hints.version}</span></div>
            <div style={{ color: "var(--text-2)" }}>{hints.description}</div>
            <div className="muted">{hints.note} {hints.repository && <a href={hints.repository} target="_blank" rel="noreferrer">Repository <ExternalLink size={11} /></a>}</div>
          </div>
        </div>
      )}
      <div className="grid-2">
        <Field label="Name" hint={cfg.name && !nameOk ? <span style={{ color: "var(--err)" }}>Letters, digits, . - _ (no spaces)</span> : "Tools are named <name>__<tool>."}>
          <input className="input mono" value={cfg.name} disabled={!isNew} onChange={(e) => setCfg({ ...cfg, name: e.target.value })} placeholder="github" />
        </Field>
        <Field label="Type">
          <div className="segmented">
            <button type="button" className={cfg.transport === "stdio" ? "on" : ""} onClick={() => setCfg({ ...cfg, transport: "stdio" })}><Terminal size={13} />Local command</button>
            <button type="button" className={cfg.transport === "http" ? "on" : ""} onClick={() => setCfg({ ...cfg, transport: "http" })}><Globe size={13} />Remote URL</button>
          </div>
        </Field>
      </div>
      {cfg.transport === "stdio" ? <>
        <Field label="Command" hint="Usually npx (Node.js), uvx (Python) or docker. The server runs on this computer.">
          <input className="input mono" value={cfg.command ?? ""} onChange={(e) => setCfg({ ...cfg, command: e.target.value })} placeholder="npx" />
        </Field>
        <Field label="Arguments" hint="One per line.">
          <textarea className="textarea mono" rows={4} value={argsText} onChange={(e) => setArgsText(e.target.value)} placeholder={"-y\n@modelcontextprotocol/server-filesystem\nC:\\path\\to\\folder"} />
        </Field>
        <Field label="Environment variables" hint="Values are stored in your OS credential store, never in the database.">
          <KeyValueRows rows={env} onChange={setEnv} keyPlaceholder="API_KEY" existing={!isNew} hints={envHints} />
        </Field>
      </> : <>
        <Field label="Server URL" hint="Streamable HTTP endpoint, e.g. https://example.com/mcp">
          <input className="input mono" value={cfg.url ?? ""} onChange={(e) => setCfg({ ...cfg, url: e.target.value })} placeholder="https://…/mcp" />
        </Field>
        <Field label="Headers" hint="e.g. Authorization: Bearer … Stored in your OS credential store.">
          <KeyValueRows rows={headers} onChange={setHeaders} keyPlaceholder="Authorization" existing={!isNew} hints={envHints} />
        </Field>
      </>}
      {error && <div className="callout err small"><CircleAlert size={15} style={{ flex: "0 0 auto", marginTop: 2 }} /><div>{error}</div></div>}
    </Modal>
  );
}

/* ---------------------------------------------------------------------------------- registry */

function RegistryModal({ onClose, onUse }: { onClose: () => void; onUse: (e: RegistryEntry) => void }) {
  const [query, setQuery] = useState("");
  const [term, setTerm] = useState("");
  const [results, setResults] = useState<RegistryEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { const t = setTimeout(() => setTerm(query), 350); return () => clearTimeout(t); }, [query]);
  useEffect(() => {
    let alive = true;
    setLoading(true); setError(null);
    api.mcpRegistry(term).then((r) => alive && setResults(r)).catch((e) => alive && setError(e.message)).finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [term]);

  return (
    <Modal title="MCP Registry" width={820} onClose={onClose}>
      <div className="row" style={{ position: "relative" }}>
        <Search size={15} className="muted" style={{ position: "absolute", left: 11 }} />
        <input className="input" style={{ paddingLeft: 34 }} autoFocus placeholder="Search servers: github, postgres, slack, filesystem…" value={query} onChange={(e) => setQuery(e.target.value)} />
        {loading && <Spinner />}
      </div>
      <div className="xs muted">From the official public registry (registry.modelcontextprotocol.io). Review a server before connecting: local servers run on your computer.</div>
      {error && <div className="callout err small">{error}</div>}
      <div className="list card" style={{ maxHeight: 460, overflow: "auto", background: "var(--bg-elev)" }}>
        {results && !results.length && <div className="empty small">No servers found.</div>}
        {(results ?? []).map((e) => (
          <div key={e.name} className="list-item" style={{ alignItems: "flex-start", cursor: "default" }}>
            <div className="avatar sm" style={{ color: "var(--accent)", borderColor: "var(--border-strong)" }}>{e.kind === "remote" ? <Globe size={13} /> : <Download size={13} />}</div>
            <div className="grow" style={{ minWidth: 0 }}>
              <div className="row wrap" style={{ gap: 8 }}>
                <span className="strong small">{e.title}</span>
                <Badge tone={e.supported ? "info" : ""}>{e.kind}</Badge>
                {e.env_vars.some((v) => v.required) && <Badge tone="warn">needs config</Badge>}
              </div>
              <div className="xs muted">{e.description || e.name}</div>
              <div className="xs faint mono ellipsis">{e.name}</div>
            </div>
            <button className="btn sm primary" disabled={!e.supported} onClick={() => onUse(e)} title={e.supported ? "Review and connect" : e.note}><Plus size={13} />Use</button>
          </div>
        ))}
      </div>
    </Modal>
  );
}

/* ---------------------------------------------------------------------------------- import */

function ImportModal({ onClose, onDone }: { onClose: () => void; onDone: (n: number) => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async () => {
    setBusy(true); setError(null);
    try {
      const r = await api.importMcp(text);
      const failed = r.filter((v) => v.status === "error");
      if (failed.length) setError(`Imported, but failed to connect: ${failed.map((f) => `${f.name} (${f.error})`).join("; ")}`);
      else onDone(r.length);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };
  return (
    <Modal title="Import MCP servers" width={680} onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>Close</button>
      <button className="btn primary" disabled={busy || !text.trim()} onClick={run}>{busy ? <Spinner size={14} /> : <FileJson size={15} />}Import &amp; connect</button>
    </>}>
      <div className="small muted">Paste the contents of a <span className="mono">claude_desktop_config.json</span>, <span className="mono">.mcp.json</span> or Cursor/VS Code MCP config.</div>
      <textarea className="textarea mono" rows={12} value={text} onChange={(e) => setText(e.target.value)}
        placeholder={'{\n  "mcpServers": {\n    "fetch": { "command": "uvx", "args": ["mcp-server-fetch"] }\n  }\n}'} />
      {error && <div className="callout err small"><CircleAlert size={15} style={{ flex: "0 0 auto", marginTop: 2 }} /><div>{error}</div></div>}
    </Modal>
  );
}

