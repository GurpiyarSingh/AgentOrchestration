import { useEffect, useState } from "react";
import { Bot, Brain, Code2, Download, FlaskConical, Layers, Plus, RotateCcw, Save, ShieldCheck, Terminal, Trash2 } from "lucide-react";
import { api } from "../api";
import { download, useData } from "../lib";
import type { AgentDef } from "../types";
import { useApp } from "../components/AppContext";
import { GENERAL_AGENT, avatarStyle, lookForRole } from "../components/agents";
import { Badge, Card, Confirm, Empty, Field, Spinner, useToast } from "../components/ui";

const TEAM_ORDER = ["requirements", "architect", "tests", "coder", "runner", "reviewer"];
const ROLE_META: Record<string, { label: string; icon: typeof Bot }> = {
  requirements: { label: "Requirements", icon: Brain },
  architect: { label: "Design", icon: Layers },
  tests: { label: "Unit tests", icon: FlaskConical },
  coder: { label: "Code generation", icon: Code2 },
  runner: { label: "Test execution", icon: Terminal },
  reviewer: { label: "Code review", icon: ShieldCheck },
};
const EFFORTS = ["", "minimal", "low", "medium", "high"];
const blank = (): AgentDef => ({
  name: "", description: "", kind: "llm", role: "", system_prompt: "You are a helpful assistant.", model: "",
  reasoning_effort: null, tools: [], skills: [], max_model_calls: 20, max_tool_calls: 50,
});

export default function AgentsPage() {
  const toast = useToast();
  const { keyReady } = useApp();
  const { data: agents, reload } = useData(api.agents, []);
  const { data: tools } = useData(api.tools, []);
  const { data: allSkills } = useData(api.skills, []);
  const { data: models } = useData(() => (keyReady ? api.models() : Promise.resolve([])), [keyReady]);
  const [selName, setSelName] = useState<string | null>(null);
  const [draft, setDraft] = useState<AgentDef | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const team = (agents ?? []).filter((a) => a.role).sort((a, b) => TEAM_ORDER.indexOf(a.role) - TEAM_ORDER.indexOf(b.role));
  const others = (agents ?? []).filter((a) => !a.role);

  useEffect(() => {
    if (!selName && team.length) setSelName(team[0].name);
  }, [team, selName]);
  useEffect(() => {
    if (isNew) return;
    const a = agents?.find((x) => x.name === selName);
    setDraft(a ? { ...a } : null);
  }, [selName, agents, isNew]);

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    try {
      const saved = await api.saveAgent({ ...draft, name: draft.name.trim(), reasoning_effort: draft.reasoning_effort || null });
      toast("ok", `Saved ${saved.name}`);
      setIsNew(false);
      await reload();
      setSelName(saved.name);
    } catch (e) {
      toast("err", e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const registryTools = (tools ?? []).filter((t) => t.invokable);
  const set = (patch: Partial<AgentDef>) => draft && setDraft({ ...draft, ...patch });

  const AgentRow = ({ a }: { a: AgentDef }) => {
    const meta = ROLE_META[a.role];
    const look = lookForRole(a.role) ?? GENERAL_AGENT;
    const Icon = look.icon;
    const sel = !isNew && a.name === selName;
    return (
      <div className={`list-item ${sel ? "sel" : ""}`} style={sel ? { boxShadow: `inset 3px 0 0 ${look.color}` } : undefined}
        onClick={() => { setIsNew(false); setSelName(a.name); }}>
        <div className="avatar sm" style={avatarStyle(look.color)}><Icon size={14} /></div>
        <div className="grow">
          <div className="strong small">{a.name}</div>
          <div className="xs muted ellipsis">{meta?.label ?? "General agent"}{a.kind === "step" ? " · deterministic" : a.model ? ` · ${a.model.replace("openai:", "")}` : " · default model"}</div>
        </div>
      </div>
    );
  };

  return (
    <div className="page">
      <div className="split-wide">
        <div className="col" style={{ gap: 20 }}>
          <Card title="Build team" sub="Used by every build, in this order" icon={<Bot size={16} />} tight
            actions={<button className="btn sm ghost" title="Re-create missing default agents" onClick={async () => {
              const r = await api.restoreAgents(false); toast("ok", r.length ? `Restored: ${r.join(", ")}` : "All defaults present"); reload();
            }}><RotateCcw size={13} />Restore</button>}>
            <div className="list">{team.map((a) => <AgentRow key={a.name} a={a} />)}</div>
          </Card>
          <Card title="Other agents" sub="Use them in Chat" icon={<Bot size={16} />} tight
            actions={<button className="btn sm primary" onClick={() => { setIsNew(true); setDraft(blank()); }}><Plus size={14} />New</button>}>
            {others.length ? <div className="list">{others.map((a) => <AgentRow key={a.name} a={a} />)}</div>
              : <div className="empty small" style={{ padding: 20 }}>No custom agents.</div>}
          </Card>
        </div>

        {!draft ? <Card><Empty icon={<Bot size={20} />} title="Select an agent" /></Card> : (
          <Card
            title={isNew ? "New agent" : draft.name}
            sub={draft.role ? `${ROLE_META[draft.role]?.label ?? draft.role} · part of the build team` : "General agent"}
            icon={<Bot size={16} />}
            actions={<>
              {!isNew && <button className="btn sm ghost" onClick={async () => download(`${draft.name}.yaml`, await api.agentYaml(draft.name))}><Download size={13} />YAML</button>}
              {!isNew && !draft.role && <button className="btn sm danger" onClick={() => setDeleting(true)}><Trash2 size={13} />Delete</button>}
              <button className="btn sm primary" disabled={saving || !draft.name.trim() || draft.kind === "step"} onClick={save}>
                {saving ? <Spinner size={13} /> : <Save size={13} />}Save
              </button>
            </>}>
            {draft.kind === "step" ? (
              <div className="col" style={{ gap: 14 }}>
                <div className="callout info small"><Terminal size={16} /><div>
                  <div className="strong">Deterministic step, no AI model</div>
                  The Code Runner executes the project's tests (pytest or <span className="mono">node --test</span>) inside the isolated build
                  workspace, with a timeout and without your secrets, and reports pass/fail per test.
                </div></div>
                <p className="muted small">{draft.description}</p>
              </div>
            ) : (
              <div className="col" style={{ gap: 16 }}>
                <div className="grid-2">
                  <Field label="Name" hint={isNew ? "lowercase, digits, - and _" : undefined}>
                    <input className="input mono" value={draft.name} disabled={!isNew} onChange={(e) => set({ name: e.target.value })} />
                  </Field>
                  <Field label="Description"><input className="input" value={draft.description} onChange={(e) => set({ description: e.target.value })} /></Field>
                </div>
                <div className="grid-3">
                  <Field label="Model">
                    <select className="select" value={draft.model} onChange={(e) => set({ model: e.target.value })}>
                      <option value="">Default model</option>
                      {draft.model && !(models ?? []).includes(draft.model.replace("openai:", "")) && <option value={draft.model}>{draft.model}</option>}
                      {(models ?? []).map((m) => <option key={m} value={`openai:${m}`}>{m}</option>)}
                    </select>
                  </Field>
                  <Field label="Reasoning effort" hint="Reasoning models only">
                    <select className="select" value={draft.reasoning_effort ?? ""} onChange={(e) => set({ reasoning_effort: e.target.value || null })}>
                      {EFFORTS.map((x) => <option key={x} value={x}>{x || "Model default"}</option>)}
                    </select>
                  </Field>
                  <div className="grid-2">
                    <Field label="Max model calls"><input className="input num" type="number" min={1} max={200} value={draft.max_model_calls} onChange={(e) => set({ max_model_calls: Number(e.target.value) })} /></Field>
                    <Field label="Max tool calls"><input className="input num" type="number" min={1} max={500} value={draft.max_tool_calls} onChange={(e) => set({ max_tool_calls: Number(e.target.value) })} /></Field>
                  </div>
                </div>
                <Field label="System prompt" hint={draft.role ? "Edits apply to the next build." : undefined}>
                  <textarea className="textarea mono" rows={16} value={draft.system_prompt} onChange={(e) => set({ system_prompt: e.target.value })} />
                </Field>
                <Field label="Tools" hint={draft.role === "tests" || draft.role === "coder"
                  ? "Build agents automatically get sandboxed workspace tools (list/read/write files) during a build."
                  : "Tools this agent may call in Chat."}>
                  <div className="row wrap">
                    {registryTools.map((t) => {
                      const on = draft.tools.includes(t.name);
                      return (
                        <button key={t.name} className={`chip click ${on ? "on" : ""}`} title={t.description}
                          onClick={() => set({ tools: on ? draft.tools.filter((x) => x !== t.name) : [...draft.tools, t.name] })}>
                          <span className="mono">{t.name}</span>
                        </button>
                      );
                    })}
                    {(draft.role === "tests" || draft.role === "coder") && <Badge tone="info">+ workspace file tools</Badge>}
                  </div>
                </Field>
                <Field label="Skills" hint="The agent sees each skill's name and description and loads the full instructions when relevant.">
                  <div className="row wrap">
                    {(allSkills ?? []).map((sk) => {
                      const on = draft.skills.includes(sk.name);
                      return (
                        <button key={sk.name} className={`chip click ${on ? "on" : ""}`} title={sk.description}
                          onClick={() => set({ skills: on ? draft.skills.filter((x) => x !== sk.name) : [...draft.skills, sk.name] })}>
                          <span className="mono">{sk.name}</span>
                        </button>
                      );
                    })}
                    {!allSkills?.length && <span className="small muted">No skills yet. Create one on the Skills page.</span>}
                  </div>
                </Field>
              </div>
            )}
          </Card>
        )}
      </div>
      {deleting && draft && (
        <Confirm title={`Delete ${draft.name}?`} danger confirmLabel="Delete" body="This agent will be removed."
          onConfirm={async () => { await api.deleteAgent(draft.name); toast("ok", "Deleted"); setSelName(null); reload(); }}
          onClose={() => setDeleting(false)} />
      )}
    </div>
  );
}
