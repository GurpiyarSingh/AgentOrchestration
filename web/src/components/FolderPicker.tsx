import { useEffect, useState } from "react";
import { ArrowUp, Check, ChevronRight, Folder, FolderGit2, FolderOpen, HardDrive, Home, Loader2, MonitorUp } from "lucide-react";
import { api } from "../api";
import type { FolderListing } from "../types";
import { Badge, Modal, Spinner, useToast } from "./ui";

/**
 * A folder field: "Browse…" opens the native Windows folder dialog (via the local server);
 * "Browse here" opens an in-app folder browser. The path can still be typed.
 */
export function FolderField({ value, onChange, placeholder, dialogTitle, requireGit }: {
  value: string; onChange: (path: string, isGit: boolean | null) => void; placeholder?: string; dialogTitle: string; requireGit?: boolean;
}) {
  const toast = useToast();
  const [opening, setOpening] = useState(false);
  const [inApp, setInApp] = useState(false);

  const native = async () => {
    setOpening(true);
    try {
      const r = await api.pickFolder(dialogTitle, value || undefined);
      if (r.path) onChange(r.path, r.is_git);
    } catch (e) {
      toast("info", `${e instanceof Error ? e.message : String(e)} Opening the in-app browser instead.`);
      setInApp(true);
    } finally {
      setOpening(false);
    }
  };

  return (
    <>
      <div className="row">
        <input className="input mono grow" value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value, null)} />
        <button type="button" className="btn primary" onClick={native} disabled={opening}>
          {opening ? <Spinner size={14} /> : <FolderOpen size={15} />}Browse…
        </button>
      </div>
      <div className="row xs muted" style={{ gap: 6 }}>
        {opening ? <span className="row" style={{ gap: 6 }}><Loader2 size={12} className="spin" />A folder dialog opened on your desktop. Pick a folder there (check the taskbar if you don't see it).</span>
          : <>Prefer to stay in the browser?<button type="button" className="btn ghost sm" onClick={() => setInApp(true)}><MonitorUp size={12} />Browse here</button></>}
      </div>
      {inApp && (
        <FolderBrowserModal title={dialogTitle} initial={value} requireGit={requireGit}
          onClose={() => setInApp(false)} onPick={(p, git) => { onChange(p, git); setInApp(false); }} />
      )}
    </>
  );
}

export function FolderBrowserModal({ title, initial, requireGit, onPick, onClose }: {
  title: string; initial?: string; requireGit?: boolean; onPick: (path: string, isGit: boolean) => void; onClose: () => void;
}) {
  const [path, setPath] = useState<string | null>(initial?.trim() || null);
  const [data, setData] = useState<FolderListing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api.folders(path ?? undefined)
      .then((d) => { if (alive) setData(d); })
      .catch((e) => {
        if (!alive) return;
        setError(e instanceof Error ? e.message : String(e));
        if (path) setPath(null); // fall back to drives
      })
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [path]);

  const crumbs = (data?.path ?? "").split(/[\\/]/).filter(Boolean);
  const sep = (data?.path ?? "").includes("\\") ? "\\" : "/";
  const crumbPath = (i: number) => {
    const parts = crumbs.slice(0, i + 1);
    const joined = parts.join(sep);
    return sep === "\\" ? (i === 0 ? `${parts[0]}\\` : joined) : `/${joined}`;
  };
  const canSelect = !!data?.path && (!requireGit || data.is_git);

  return (
    <Modal title={title} width={760} onClose={onClose} footer={<>
      <span className="grow xs muted mono ellipsis" title={data?.path ?? ""}>{data?.path ?? "Choose a drive"}</span>
      {requireGit && data?.path && !data.is_git && <span className="xs" style={{ color: "var(--warn)" }}>Not a git repository</span>}
      <button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn primary" disabled={!canSelect} onClick={() => data?.path && onPick(data.path, data.is_git)}>
        <Check size={15} />Select this folder
      </button>
    </>}>
      <div style={{ display: "grid", gridTemplateColumns: "170px 1fr", gap: 14, minHeight: 380 }}>
        <div className="col" style={{ gap: 2, borderRight: "1px solid var(--border)", paddingRight: 10 }}>
          <span className="nav-label" style={{ padding: "0 8px 6px" }}>Places</span>
          {(data?.shortcuts ?? []).map((s) => (
            <button key={s.path} className="nav-item" style={{ border: 0, background: "transparent", cursor: "pointer", textAlign: "left" }} onClick={() => setPath(s.path)}>
              {s.name === "Home" ? <Home size={15} /> : <Folder size={15} />}<span className="ellipsis">{s.name}</span>
            </button>
          ))}
          <button className="nav-item" style={{ border: 0, background: "transparent", cursor: "pointer", textAlign: "left" }} onClick={() => setPath(null)}>
            <HardDrive size={15} />This PC
          </button>
        </div>
        <div className="col" style={{ gap: 10, minWidth: 0 }}>
          <div className="row" style={{ gap: 4, flexWrap: "wrap" }}>
            <button className="btn sm" disabled={!data?.parent && !data?.path} onClick={() => setPath(data?.parent ?? null)}><ArrowUp size={13} />Up</button>
            <button className="btn ghost sm" onClick={() => setPath(null)}><HardDrive size={13} /></button>
            {crumbs.map((c, i) => (
              <span key={i} className="row" style={{ gap: 4 }}>
                <ChevronRight size={12} className="faint" />
                <button className="btn ghost sm mono" onClick={() => setPath(crumbPath(i))}>{c}</button>
              </span>
            ))}
            {data?.is_git && <Badge tone="ok"><FolderGit2 size={11} />git repository</Badge>}
          </div>
          {error && <div className="callout err small">{error}</div>}
          <div className="card" style={{ maxHeight: 360, overflow: "auto", background: "var(--bg-elev)" }}>
            {loading && !data ? <div className="empty small"><Spinner /></div> : !data?.entries.length ? (
              <div className="empty small" style={{ padding: 30 }}>No sub-folders.</div>
            ) : data.entries.map((e) => (
              <div key={e.path} className="file-item" style={{ fontFamily: "var(--font)", fontSize: 13 }} onDoubleClick={() => setPath(e.path)} onClick={() => setPath(e.path)}>
                {data.path === null ? <HardDrive size={15} /> : e.is_git ? <FolderGit2 size={15} style={{ color: "var(--ok)" }} /> : <Folder size={15} />}
                <span className="grow ellipsis">{e.name}</span>
                {e.is_git && <Badge tone="ok">git</Badge>}
              </div>
            ))}
          </div>
          <div className="xs muted">Click a folder to open it, then <b>Select this folder</b>.{requireGit ? " Git repositories are marked in green." : ""}</div>
        </div>
      </div>
    </Modal>
  );
}
