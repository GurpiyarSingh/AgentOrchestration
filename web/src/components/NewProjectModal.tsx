import { useState } from "react";
import { CircleAlert, FolderGit2 } from "lucide-react";
import { api } from "../api";
import { useData } from "../lib";
import type { Project } from "../types";
import { FolderField } from "./FolderPicker";
import { Badge, Field, Modal, Spinner, useToast } from "./ui";

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
  const [repoIsGit, setRepoIsGit] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const nameOk = NAME_RE.test(name.trim());
  const suggestion = slugName(name);
  const target = mode === "new" && nameOk
    ? joinPath(location.trim() || settings?.workspaces_dir || "workspaces", name.trim())
    : "";
  const canSubmit = !busy && nameOk && (mode === "new" || (!!repoPath.trim() && repoIsGit !== false));

  const pickRepo = (p: string, isGit: boolean | null) => {
    setRepoPath(p);
    setRepoIsGit(p ? isGit : null); // null = typed by hand, validated by the server
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
        {busy ? <Spinner size={14} /> : <FolderGit2 size={15} />} {mode === "new" ? "Create project" : "Add repository"}
      </button>
    </>}>
      <div className="segmented" style={{ justifySelf: "start" }}>
        <button className={mode === "new" ? "on" : ""} onClick={() => { setMode("new"); setError(null); }}>New repository</button>
        <button className={mode === "existing" ? "on" : ""} onClick={() => { setMode("existing"); setError(null); }}>Existing local repo</button>
      </div>

      {mode === "existing" && (
        <Field label="Repository folder">
          <FolderField value={repoPath} dialogTitle="Choose a git repository" requireGit placeholder="Choose a folder…"
            onChange={pickRepo} />
          {repoPath && repoIsGit === true && <div><Badge tone="ok"><FolderGit2 size={11} />git repository</Badge></div>}
          {repoPath && repoIsGit === false && (
            <div className="callout warn small"><CircleAlert size={15} />This folder is not a git repository. Pick a folder that contains a <span className="mono">.git</span> folder, or create a new repository instead.</div>
          )}
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
