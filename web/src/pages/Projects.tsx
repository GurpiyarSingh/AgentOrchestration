import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { FileCode2, FolderGit2, GitBranch, Hammer, Plus, Trash2 } from "lucide-react";
import { api } from "../api";
import { fmt, LANG_LABEL, useData } from "../lib";
import { NewProjectModal } from "../components/NewProjectModal";
import { Badge, Card, CodeView, Confirm, Empty, StatusBadge, useToast } from "../components/ui";

export default function ProjectsPage() {
  const { projectId } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const { data: projects, reload } = useData(api.projects, []);
  const [creating, setCreating] = useState(false);
  const [removing, setRemoving] = useState(false);
  const selected = projects?.find((p) => p.id === projectId) ?? null;

  useEffect(() => {
    if (!projectId && projects?.length) nav(`/projects/${projects[0].id}`, { replace: true });
  }, [projectId, projects, nav]);

  return (
    <div className="page">
      <div className="split-wide">
        <Card title="Projects" icon={<FolderGit2 size={16} />} tight
          actions={<button className="btn sm primary" onClick={() => setCreating(true)}><Plus size={14} />New</button>}>
          {!projects?.length ? (
            <Empty icon={<FolderGit2 size={20} />} title="No projects yet"
              action={<button className="btn primary" onClick={() => setCreating(true)}><Plus size={15} />Create project</button>}>
              A project is a git repository the agent team writes code into.
            </Empty>
          ) : (
            <div className="list">
              {projects.map((p) => (
                <div key={p.id} className={`list-item ${p.id === projectId ? "sel" : ""}`} onClick={() => nav(`/projects/${p.id}`)}>
                  <FolderGit2 size={16} className="muted" />
                  <div className="grow">
                    <div className="strong small">{p.name}</div>
                    <div className="xs muted">{LANG_LABEL[p.language] ?? p.language} · {p.kind === "new" ? "created here" : "existing repo"}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {selected ? (
          <div className="col" style={{ gap: 20, minWidth: 0 }}>
            <section className="card">
              <div className="card-body row between" style={{ alignItems: "flex-start" }}>
                <div className="col" style={{ gap: 6 }}>
                  <div className="row"><h2 style={{ fontSize: 18 }}>{selected.name}</h2><Badge tone="accent">{LANG_LABEL[selected.language] ?? selected.language}</Badge></div>
                  <div className="xs muted mono">{selected.path}</div>
                  <div className="row xs muted" style={{ gap: 14 }}>
                    <span className="row" style={{ gap: 5 }}><GitBranch size={13} />{selected.base_branch}</span>
                    <span>Added {fmt.time(selected.created_at)}</span>
                  </div>
                </div>
                <div className="row">
                  <button className="btn danger" onClick={() => setRemoving(true)}><Trash2 size={15} />Remove</button>
                  <button className="btn primary" onClick={() => nav("/")}><Hammer size={15} />New build</button>
                </div>
              </div>
            </section>
            <ProjectBuilds projectId={selected.id} />
            <ProjectFiles projectId={selected.id} />
          </div>
        ) : (
          <Card><Empty icon={<FolderGit2 size={20} />} title="Select a project" /></Card>
        )}
      </div>
      {creating && <NewProjectModal onClose={() => setCreating(false)} onCreated={(p) => { reload(); nav(`/projects/${p.id}`); }} />}
      {removing && selected && (
        <Confirm title="Remove project?" danger confirmLabel="Remove"
          body={<>"{selected.name}" will be removed from the app. Its folder and git history stay on disk at <span className="mono">{selected.path}</span>.</>}
          onConfirm={async () => { await api.removeProject(selected.id); toast("ok", "Project removed"); await reload(); nav("/projects"); }}
          onClose={() => setRemoving(false)} />
      )}
    </div>
  );
}

function ProjectBuilds({ projectId }: { projectId: string }) {
  const nav = useNavigate();
  const { data } = useData(() => api.builds(projectId), [projectId], 5000);
  return (
    <Card title="Builds" icon={<Hammer size={16} />} tight>
      {!data?.length ? <div className="empty small" style={{ padding: 24 }}>No builds for this project yet.</div> : (
        <table className="table">
          <thead><tr><th>Build</th><th>Status</th><th>Tests</th><th>Tokens</th><th>Started</th></tr></thead>
          <tbody>{data.map((b) => (
            <tr key={b.run_id} className="click" onClick={() => nav(`/builds/${b.run_id}`)}>
              <td className="strong small">{b.title}</td>
              <td><StatusBadge status={b.final_action ?? b.status} /></td>
              <td className="num small">{b.tests}</td>
              <td className="num small">{fmt.compact(b.total_tokens)}</td>
              <td className="small muted">{fmt.ago(b.started_at)}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
    </Card>
  );
}

function ProjectFiles({ projectId }: { projectId: string }) {
  const { data: files } = useData(() => api.projectFiles(projectId), [projectId], 8000);
  const [sel, setSel] = useState<string | null>(null);
  const [content, setContent] = useState<string | null>(null);
  useEffect(() => { setSel(null); }, [projectId]);
  useEffect(() => {
    if (!sel && files?.length) setSel(files.find((f) => /\.(py|js|ts)$/.test(f.path) && !f.path.startsWith("tests/"))?.path ?? files[0].path);
  }, [files, sel]);
  useEffect(() => { if (sel) { setContent(null); api.projectFile(projectId, sel).then(setContent).catch((e) => setContent(`Error: ${e.message}`)); } }, [sel, projectId]);
  return (
    <Card title="Files" sub="Main branch (merged work only)" icon={<FileCode2 size={16} />} tight>
      {!files?.length ? <div className="empty small" style={{ padding: 24 }}>Empty project.</div> : (
        <div className="split-wide" style={{ gap: 0 }}>
          <div className="file-tree" style={{ borderRight: "1px solid var(--border)", padding: "8px 0" }}>
            {files.map((f) => (
              <div key={f.path} className={`file-item ${f.path === sel ? "sel" : ""}`} onClick={() => setSel(f.path)}>
                <FileCode2 size={13} /><span className="grow ellipsis">{f.path}</span><span className="xs faint">{fmt.bytes(f.size)}</span>
              </div>
            ))}
          </div>
          <div style={{ padding: 16, minWidth: 0 }}>
            {content === null ? <div className="skeleton" style={{ height: 260 }} /> : <CodeView text={content} />}
          </div>
        </div>
      )}
    </Card>
  );
}
