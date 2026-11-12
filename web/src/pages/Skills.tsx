import { useEffect, useState } from "react";
import { BookMarked, Bot, FileText, Plus, Save, Trash2 } from "lucide-react";
import { api } from "../api";
import { useData } from "../lib";
import type { Skill } from "../types";
import { Badge, Card, Confirm, Empty, Field, Spinner, useToast } from "../components/ui";

const NEW_BODY = `# Instructions

Explain, step by step, how the agent should do this kind of task.

- Rules and conventions to follow
- What a good result looks like
- Common mistakes to avoid
`;

export default function SkillsPage() {
  const toast = useToast();
  const { data: skills, reload } = useData(api.skills, []);
  const { data: agents } = useData(api.agents, []);
  const [sel, setSel] = useState<string | null>(null);
  const [draft, setDraft] = useState<{ name: string; description: string; body: string } | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => { if (!sel && !isNew && skills?.length) setSel(skills[0].name); }, [skills, sel, isNew]);
  useEffect(() => {
    if (isNew) return;
    const s = skills?.find((x) => x.name === sel);
    setDraft(s ? { name: s.name, description: s.description, body: s.body } : null);
  }, [sel, skills, isNew]);

  const current: Skill | undefined = skills?.find((x) => x.name === sel);
  const usedBy = (agents ?? []).filter((a) => draft && a.skills.includes(draft.name));
  const nameOk = !!draft && /^[a-z][a-z0-9-]{1,48}$/.test(draft.name);

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    try {
      const s = await api.saveSkill(draft);
      toast("ok", `Saved skill ${s.name}`);
      setIsNew(false);
      await reload();
      setSel(s.name);
    } catch (e) { toast("err", e instanceof Error ? e.message : String(e)); } finally { setSaving(false); }
  };

  return (
    <div className="page">
      <div className="split-wide">
        <Card title="Skills" sub="Knowledge packs agents load on demand" icon={<BookMarked size={16} />} tight
          actions={<button className="btn sm primary" onClick={() => { setIsNew(true); setSel(null); setDraft({ name: "", description: "", body: NEW_BODY }); }}><Plus size={14} />New</button>}>
          {!skills?.length ? <div className="empty small" style={{ padding: 24 }}>No skills yet.</div> : (
            <div className="list">
              {skills.map((s) => (
                <div key={s.name} className={`list-item ${!isNew && s.name === sel ? "sel" : ""}`} onClick={() => { setIsNew(false); setSel(s.name); }}>
                  <div className="avatar sm" style={{ color: "var(--accent)", borderColor: "var(--border-strong)" }}><BookMarked size={13} /></div>
                  <div className="grow" style={{ minWidth: 0 }}>
                    <div className="strong small mono">{s.name}</div>
                    <div className="xs muted ellipsis">{s.description}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {!draft ? <Card><Empty icon={<BookMarked size={20} />} title="Select or create a skill" /></Card> : (
          <Card title={isNew ? "New skill" : draft.name} icon={<BookMarked size={16} />}
            sub="Agents see the name and description, and load the instructions when a task matches."
            actions={<>
              {!isNew && <button className="btn sm danger" onClick={() => setDeleting(true)}><Trash2 size={13} />Delete</button>}
              <button className="btn sm primary" disabled={saving || !nameOk || !draft.description.trim()} onClick={save}>
                {saving ? <Spinner size={13} /> : <Save size={13} />}Save
              </button>
            </>}>
            <div className="col" style={{ gap: 16 }}>
              <div className="grid-2">
                <Field label="Name" hint={draft.name && !nameOk ? <span style={{ color: "var(--err)" }}>lowercase letters, digits and -</span> : "lowercase-with-dashes"}>
                  <input className="input mono" value={draft.name} disabled={!isNew} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="api-design" />
                </Field>
                <Field label="Used by">
                  <div className="row wrap" style={{ minHeight: 36 }}>
                    {usedBy.length ? usedBy.map((a) => <Badge key={a.name} tone="accent"><Bot size={11} />{a.name}</Badge>)
                      : <span className="small muted">No agents yet. Assign it on the Agents page.</span>}
                  </div>
                </Field>
              </div>
              <Field label="Description" hint="When should an agent use this skill? Be specific; this is all the agent sees until it loads the skill.">
                <input className="input" value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                  placeholder="REST API design conventions. Use when creating or reviewing HTTP endpoints." />
              </Field>
              <Field label="Instructions (Markdown)">
                <textarea className="textarea mono" rows={18} value={draft.body} onChange={(e) => setDraft({ ...draft, body: e.target.value })} />
              </Field>
              {current && current.files.length > 0 && !isNew && (
                <Field label="Reference files" hint={<>Agents read these with <span className="mono">skill__read_file</span>. Add files in <span className="mono">{current.path}</span>.</>}>
                  <div className="row wrap">{current.files.map((f) => <span key={f} className="chip"><FileText size={12} />{f}</span>)}</div>
                </Field>
              )}
            </div>
          </Card>
        )}
      </div>
      {deleting && draft && (
        <Confirm title={`Delete ${draft.name}?`} danger confirmLabel="Delete" body="The skill folder is deleted and removed from all agents."
          onConfirm={async () => { await api.deleteSkill(draft.name); toast("ok", "Skill deleted"); setSel(null); reload(); }}
          onClose={() => setDeleting(false)} />
      )}
    </div>
  );
}
