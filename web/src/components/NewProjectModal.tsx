import { useState } from "react";
import { FolderGit2 } from "lucide-react";
import { api } from "../api";
import { useData } from "../lib";
import type { Project } from "../types";
import { FolderField } from "./FolderPicker";
import { Field, Modal, Spinner, useToast } from "./ui";

const NAME_RE = /^[a-zA-Z][a-zA-Z0-9_-]{1,48}$/;

/** "Test Repo!" -> "test-repo" (valid project name), or "" if nothing usable. */
export function slugName(raw: string): string {
  const s = raw.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/-+/g, "-").replace(/^[-_0-9]+|-+$/g, "").slice(0, 49);
  return NAME_RE.test(s) ? s : "";
}

const lastSegment = (p: string) => p.split(/[\\/]/).filter(Boolean).pop() ?? "";
const joinPath = (dir: string, name: string) => {
  const sep = dir.includes("\\") || /^[a-zA-Z]:/.test(dir) ? "\\" : "/";
  return dir.replace(/[\\/]+$/, "") + sep + name;
};

export function NewProjectModal({ onClose, onCreated }: { onClose: () => void; onCreated: (p: Project) => void }) {
  const toast = useToast();
  const { data: langs } = useData(api.languages, []);
  const { data: settings } = useData(api.settings, []);
  const [mode, setMode] = useState<"new" | "existing">("new");
  const [name, setName] = useState("");
  const [nameTouched, setNameTouched] = useState(false);
  const [language, setLanguage] = useState("python");
  const [location, setLocation] = useState("");      // new: parent folder (optional)
  const [repoPath, setRepoPath] = useState("");      // existing: the repository folder
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const nameOk = NAME_RE.test(name.trim());
  const suggestion = slugName(name);
  const target = mode === "new" && nameOk
    ? joinPath(location.trim() || settings?.workspaces_dir || "workspaces", name.trim())
    : "";
  const canSubmit = !busy && nameOk && (mode === "new" || (!!repoPath.trim()));

  const pickRepo = (p: string) => {
    setRepoPath(p);
    if (!nameTouched || !name.trim()) setName(slugName(lastSegment(p)));
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const p = await api.createProject({
        name: name.trim(), language, mode,
        path: mode === "existing" ? repoPath.trim() : (location.trim() ? target : undefined),
      });
      toast("ok", `Project "${p.name}" ${mode === "new" ? "created" : "added"}`);
      onCreated(p);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="New project" width={620} onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn primary" disabled={!canSubmit} onClick={submit}>
        {busy ? <Spinner size={14} /> : <FolderGit2 size={15} />} {mode === "new" ? "Create project" : "Add folder"}
      </button>
    </>}>
      <div className="segmented" style={{ justifySelf: "start" }}>
        <button className={mode === "new" ? "on" : ""} onClick={() => { setMode("new"); setError(null); }}>New folder</button>
        <button className={mode === "existing" ? "on" : ""} onClick={() => { setMode("existing"); setError(null); }}>Existing folder</button>
      </div>

      {mode === "existing" && (
        <Field label="Project folder">
          <FolderField value={repoPath} dialogTitle="Choose a project folder" placeholder="Choose a folder…"
            onChange={pickRepo} />
          <div className="xs muted">Any folder. Agents write files straight into it; Codeloom never runs git.</div>
        </Field>
      )}

      <Field label="Name" hint={name && !nameOk
        ? <span style={{ color: "var(--err)" }}>Use 2-49 letters, digits, - or _, starting with a letter (no spaces).{" "}
            {suggestion && <button type="button" className="btn ghost sm" onClick={() => setName(suggestion)}>Use "{suggestion}"</button>}</span>
        : mode === "new" ? "Letters, digits, - and _. Also the folder name." : "Shown in Codeloom; the folder keeps its name."}>
        <input className="input" autoFocus={mode === "new"} value={name} placeholder="text-utils"
          onChange={(e) => { setName(e.target.value); setNameTouched(true); }} />
      </Field>

      <Field label="Language">
        <div className="row wrap">
          {(langs ?? []).map((l) => (
            <button key={l.id} type="button" disabled={!l.available}
              className={`chip click ${language === l.id ? "on" : ""}`} onClick={() => setLanguage(l.id)} title={l.toolchain}>
              {l.name}{!l.available && " (not installed)"}
            </button>
          ))}
        </div>
      </Field>

      {mode === "new" && (
        <Field label="Location (optional)">
          <FolderField value={location} dialogTitle="Choose where to create the project" placeholder={settings?.workspaces_dir ?? "Default workspaces folder"}
            onChange={(p) => setLocation(p)} />
          {target && <div className="hint">Will create <span className="mono" style={{ color: "var(--text-2)" }}>{target}</span></div>}
        </Field>
      )}

      {error && <div className="callout err small">{error}</div>}
    </Modal>
  );
}
