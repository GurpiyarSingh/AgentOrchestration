import { useEffect, useState } from "react";
import { Check, Coins, Cpu, Eye, EyeOff, GitBranch, KeyRound, Plug, Plus, RefreshCw, Save, ShieldCheck, Trash2 } from "lucide-react";
import { api } from "../api";
import { useData } from "../lib";
import type { ModelPrice } from "../types";
import { useApp } from "../components/AppContext";
import { Badge, Card, Confirm, Field, Spinner, Toggle, useToast } from "../components/ui";

export default function SettingsPage() {
  return (
    <div className="page" style={{ maxWidth: 1100 }}>
      <ApiKeyCard />
      <ModelsCard />
      <PricingCard />
      <div className="grid-2">
        <GitCard />
        <IntegrationsCard />
      </div>
      <SystemCard />
    </div>
  );
}

function ApiKeyCard() {
  const toast = useToast();
  const { settings, reloadSettings } = useApp();
  const [key, setKey] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState<"verify" | "save" | null>(null);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [removing, setRemoving] = useState(false);
  const status = settings?.key;

  const submit = async (save: boolean) => {
    setBusy(save ? "save" : "verify");
    setResult(null);
    try {
      const r = await api.saveKey(key.trim(), save);
      setResult(r);
      if (r.ok && save) {
        setKey("");
        toast("ok", "OpenAI key saved and verified");
        await reloadSettings();
      }
    } catch (e) {
      setResult({ ok: false, message: e instanceof Error ? e.message : String(e) });
    } finally { setBusy(null); }
  };

  return (
    <Card title="OpenAI connection" icon={<KeyRound size={16} />} sub="Your key is verified with OpenAI, then stored in your operating system's credential store, never in the app database or logs.">
      <div className="col" style={{ gap: 16 }}>
        {status && (status.configured ? (
          <div className="callout ok">
            <ShieldCheck size={18} style={{ color: "var(--ok)" }} />
            <div className="grow"><div className="strong">Connected</div>
              <div className="small" style={{ color: "var(--text-2)" }}>Key <span className="mono">{status.hint}</span> stored in {status.location}.</div></div>
            <button className="btn sm danger" onClick={() => setRemoving(true)}><Trash2 size={13} />Remove</button>
          </div>
        ) : (
          <div className="callout warn"><KeyRound size={18} style={{ color: "var(--warn)" }} />
            <div><div className="strong">Not connected</div><div className="small" style={{ color: "var(--text-2)" }}>Paste an API key from platform.openai.com → API keys.</div></div></div>
        ))}
        <Field label={status?.configured ? "Replace key" : "API key"}>
          <div className="row">
            <div className="grow" style={{ position: "relative" }}>
              <input className="input mono" type={show ? "text" : "password"} autoComplete="off" spellCheck={false} placeholder="sk-…" value={key}
                onChange={(e) => setKey(e.target.value)} onKeyDown={(e) => e.key === "Enter" && key.trim() && submit(true)} />
              <button className="btn ghost icon-btn sm" style={{ position: "absolute", right: 4, top: 4 }} onClick={() => setShow(!show)}>{show ? <EyeOff size={14} /> : <Eye size={14} />}</button>
            </div>
            <button className="btn" disabled={!key.trim() || !!busy} onClick={() => submit(false)}>{busy === "verify" ? <Spinner size={14} /> : <Check size={15} />}Verify</button>
            <button className="btn primary" disabled={!key.trim() || !!busy} onClick={() => submit(true)}>{busy === "save" ? <Spinner size={14} /> : <Save size={15} />}Verify & save</button>
          </div>
        </Field>
        {result && <div className={`callout small ${result.ok ? "ok" : "err"}`}>{result.message}</div>}
      </div>
      {removing && <Confirm title="Remove API key?" danger confirmLabel="Remove" body="Agents and builds will stop working until you add a key again."
        onConfirm={async () => { await api.removeKey(); toast("ok", "Key removed"); reloadSettings(); }} onClose={() => setRemoving(false)} />}
    </Card>
  );
}

function ModelsCard() {
  const toast = useToast();
  const { settings, keyReady, reloadSettings } = useApp();
  const [showAll, setShowAll] = useState(false);
  const { data: models, error, loading, reload } = useData(() => (keyReady ? api.models(showAll) : Promise.resolve([])), [keyReady, showAll]);
  const [def, setDef] = useState("");
  const [cheap, setCheap] = useState("");
  // Depend on the saved values (not the settings object, which is re-fetched every 30s) so edits in progress are kept.
  useEffect(() => { setDef(settings?.default_model ?? ""); setCheap(settings?.cheap_model ?? ""); setShowAll(!!settings?.prefs.show_all_models); },
    [settings?.default_model, settings?.cheap_model, settings?.prefs.show_all_models]);

  const save = async () => {
    try {
      await api.savePrefs({ default_model: def || null, cheap_model: cheap || null, show_all_models: showAll });
      toast("ok", "Model defaults saved");
      reloadSettings();
    } catch (e) { toast("err", e instanceof Error ? e.message : String(e)); }
  };
  const options = (models ?? []).map((m) => `openai:${m}`);
  const withCurrent = (v: string) => (v && !options.includes(v) ? [v, ...options] : options);

  return (
    <Card title="Models" icon={<Cpu size={16} />} sub="Every model your key can access. The default is used by all agents that don't pick their own."
      actions={<button className="btn sm ghost" onClick={reload} disabled={!keyReady}><RefreshCw size={13} />Refresh</button>}>
      {!keyReady ? <div className="small muted">Connect your OpenAI key to list models.</div> : (
        <div className="col" style={{ gap: 16 }}>
          <div className="grid-2">
            <Field label="Default model" hint="Recommended: a fast, capable model such as gpt-5.4-mini.">
              <select className="select" value={def} onChange={(e) => setDef(e.target.value)}>
                <option value="">Not set</option>{withCurrent(def).map((m) => <option key={m} value={m}>{m.replace("openai:", "")}</option>)}
              </select>
            </Field>
            <Field label="Cheap model" hint="For lightweight helper steps (optional).">
              <select className="select" value={cheap} onChange={(e) => setCheap(e.target.value)}>
                <option value="">Not set</option>{withCurrent(cheap).map((m) => <option key={m} value={m}>{m.replace("openai:", "")}</option>)}
              </select>
            </Field>
          </div>
          <div className="row between">
            <label className="row small"><Toggle checked={showAll} onChange={setShowAll} />Show all model types (audio, image, embeddings, snapshots, fine-tunes)</label>
            <button className="btn primary" onClick={save}><Save size={15} />Save</button>
          </div>
          {error ? <div className="callout err small">{error}</div> : (
            <div className="col" style={{ gap: 8 }}>
              <div className="xs muted">{loading ? "Loading…" : `${models?.length ?? 0} models available`}</div>
              <div className="row wrap" style={{ maxHeight: 180, overflow: "auto" }}>
                {(models ?? []).map((m) => (
                  <button key={m} className={`chip click ${def === `openai:${m}` ? "on" : ""}`} onClick={() => setDef(`openai:${m}`)}><span className="mono">{m}</span></button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function PricingCard() {
  const toast = useToast();
  const { data, reload } = useData(api.prices, []);
  const [rows, setRows] = useState<{ model: string; input: string; output: string; cached: string }[]>([]);
  useEffect(() => {
    if (data) setRows(Object.entries(data).map(([model, p]) => ({ model, input: String(p.input_per_1m), output: String(p.output_per_1m), cached: p.cached_input_per_1m == null ? "" : String(p.cached_input_per_1m) })));
  }, [data]);
  const save = async () => {
    const models: Record<string, ModelPrice> = {};
    for (const r of rows) {
      if (!r.model.trim()) continue;
      models[r.model.trim()] = { input_per_1m: Number(r.input) || 0, output_per_1m: Number(r.output) || 0, cached_input_per_1m: r.cached === "" ? null : Number(r.cached) };
    }
    try { await api.savePrices(models); toast("ok", "Prices saved"); reload(); }
    catch (e) { toast("err", e instanceof Error ? e.message : String(e)); }
  };
  const upd = (i: number, k: "model" | "input" | "output" | "cached", v: string) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  return (
    <Card title="Pricing" icon={<Coins size={16} />} sub="USD per 1M tokens, used to show cost. Copy current prices from your provider's pricing page."
      actions={<><button className="btn sm" onClick={() => setRows([...rows, { model: "", input: "", output: "", cached: "" }])}><Plus size={13} />Add model</button>
        <button className="btn sm primary" onClick={save}><Save size={13} />Save</button></>}>
      {!rows.length ? <div className="small muted">No prices yet. Costs show as "—" until you add the models you use.</div> : (
        <table className="table">
          <thead><tr><th>Model</th><th>Input $/1M</th><th>Output $/1M</th><th>Cached input $/1M</th><th /></tr></thead>
          <tbody>{rows.map((r, i) => (
            <tr key={i}>
              <td><input className="input mono" value={r.model} placeholder="gpt-5.4-mini" onChange={(e) => upd(i, "model", e.target.value)} /></td>
              <td><input className="input num" value={r.input} onChange={(e) => upd(i, "input", e.target.value)} /></td>
              <td><input className="input num" value={r.output} onChange={(e) => upd(i, "output", e.target.value)} /></td>
              <td><input className="input num" value={r.cached} placeholder="same as input" onChange={(e) => upd(i, "cached", e.target.value)} /></td>
              <td><button className="btn ghost icon-btn" onClick={() => setRows(rows.filter((_, j) => j !== i))}><Trash2 size={14} /></button></td>
            </tr>
          ))}</tbody>
        </table>
      )}
    </Card>
  );
}

function GitCard() {
  const toast = useToast();
  const { settings, reloadSettings } = useApp();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  useEffect(() => { setName(settings?.git_author_name ?? ""); setEmail(settings?.git_author_email ?? ""); },
    [settings?.git_author_name, settings?.git_author_email]);
  return (
    <Card title="Git identity" icon={<GitBranch size={16} />} sub="Author of commits the agents make. Git stays local: nothing is ever pushed.">
      <div className="col" style={{ gap: 12 }}>
        <Field label="Author name"><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Author email"><input className="input" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
        <button className="btn primary" style={{ alignSelf: "flex-start" }} onClick={async () => {
          await api.savePrefs({ git_author_name: name.trim() || null, git_author_email: email.trim() || null }); toast("ok", "Saved"); reloadSettings();
        }}><Save size={15} />Save</button>
      </div>
    </Card>
  );
}

function IntegrationsCard() {
  const toast = useToast();
  const { settings, reloadSettings } = useApp();
  const [token, setToken] = useState("");
  return (
    <Card title="Integrations" icon={<Plug size={16} />} sub="External services and MCP servers.">
      <div className="col" style={{ gap: 14 }}>
        <div className="row between">
          <div><div className="strong small">GitHub token</div><div className="xs muted">Read-only, for adding private repositories.</div></div>
          {settings?.github_token_set ? <Badge tone="ok">Saved</Badge> : <Badge>Not set</Badge>}
        </div>
        <div className="row">
          <input className="input mono grow" type="password" placeholder="github_pat_…" value={token} onChange={(e) => setToken(e.target.value)} />
          <button className="btn" disabled={!token.trim()} onClick={async () => { await api.saveGithubToken(token.trim()); setToken(""); toast("ok", "Token saved"); reloadSettings(); }}><Save size={14} />Save</button>
          {settings?.github_token_set && <button className="btn danger icon-btn" onClick={async () => { await api.removeGithubToken(); reloadSettings(); }}><Trash2 size={14} /></button>}
        </div>
        <div className="divider" />
        <div className="row between">
          <div><div className="strong small">MCP servers</div><div className="xs muted">Connect public MCP servers (filesystem, fetch, GitHub…) and give their tools to agents.</div></div>
          <Badge tone="info">Next release</Badge>
        </div>
      </div>
    </Card>
  );
}

function SystemCard() {
  const { settings } = useApp();
  const { data: langs } = useData(api.languages, []);
  if (!settings) return null;
  return (
    <Card title="System" icon={<ShieldCheck size={16} />}>
      <dl className="kv">
        <dt>Data folder</dt><dd className="mono small">{settings.data_dir}</dd>
        <dt>Workspaces</dt><dd className="mono small">{settings.workspaces_dir}</dd>
        <dt>Secrets</dt><dd className="small">{settings.key.location}</dd>
        <dt>Test timeout</dt><dd className="small">{settings.runner_timeout_s}s per test run</dd>
        <dt>Languages</dt><dd className="row wrap">{(langs ?? []).map((l) => <Badge key={l.id} tone={l.available ? "ok" : "err"}>{l.name} · {l.toolchain}</Badge>)}</dd>
        <dt>API</dt><dd className="small"><a href="/docs" target="_blank" rel="noreferrer">Swagger UI</a> · <a href="/redoc" target="_blank" rel="noreferrer">ReDoc</a></dd>
      </dl>
    </Card>
  );
}
