import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { CircleAlert, CircleCheck, Info, Loader2, X } from "lucide-react";

/* ---------- Status badge ---------- */
const STATUS: Record<string, { cls: string; label: string }> = {
  running: { cls: "accent", label: "Running" },
  done: { cls: "ok", label: "Done" },
  needs_attention: { cls: "warn", label: "Needs attention" },
  failed: { cls: "err", label: "Failed" },
  cancelled: { cls: "", label: "Cancelled" },
  merged: { cls: "ok", label: "Merged" },
  kept: { cls: "info", label: "Branch kept" },
  discarded: { cls: "", label: "Discarded" },
  pending: { cls: "", label: "Pending" },
  skipped: { cls: "", label: "Skipped" },
};

export function StatusBadge({ status }: { status: string }) {
  const s = STATUS[status] ?? { cls: "", label: status };
  return (
    <span className={`badge ${s.cls}`}>
      <span className={`dot ${status === "running" ? "pulse" : ""}`} />
      {s.label}
    </span>
  );
}

export function Badge({ children, tone = "" }: { children: ReactNode; tone?: string }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

/* ---------- Layout primitives ---------- */
export function Card({ title, sub, icon, actions, children, tight, className = "" }: {
  title?: ReactNode; sub?: ReactNode; icon?: ReactNode; actions?: ReactNode; children?: ReactNode; tight?: boolean; className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <div className="card-head">
          <div className="col" style={{ gap: 2 }}>
            <div className="section-title">{icon}<h2>{title}</h2></div>
            {sub && <div className="sub">{sub}</div>}
          </div>
          {actions && <div className="row">{actions}</div>}
        </div>
      )}
      <div className={`card-body ${tight ? "tight" : ""}`}>{children}</div>
    </section>
  );
}

export function Spinner({ size = 16 }: { size?: number }) {
  return <Loader2 size={size} className="spin" />;
}

export function Empty({ icon, title, children, action }: { icon: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      <div className="ic">{icon}</div>
      <h3>{title}</h3>
      {children && <div className="small" style={{ maxWidth: 440 }}>{children}</div>}
      {action}
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
      {hint && <div className="hint">{hint}</div>}
    </div>
  );
}

export function Toggle({ checked, onChange, disabled }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span />
    </label>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: {
  tabs: { id: T; label: string; icon?: ReactNode; count?: number | string | null }[]; value: T; onChange: (v: T) => void;
}) {
  return (
    <div className="tabs">
      {tabs.map((t) => (
        <button key={t.id} className={`tab ${value === t.id ? "on" : ""}`} onClick={() => onChange(t.id)}>
          {t.icon}{t.label}{t.count !== undefined && t.count !== null && <span className="count">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Modal({ title, onClose, children, footer, width }: {
  title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; width?: number;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Rendered into <body> via a portal: ancestors with backdrop-filter/transform would otherwise
  // become the containing block for this fixed overlay and clip it inside a card.
  return createPortal(
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}
        style={width ? { width: `min(${width}px, calc(100vw - 32px))` } : undefined}>
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="btn ghost icon-btn" onClick={onClose} aria-label="Close"><X size={16} /></button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}

/* ---------- Code & diff ---------- */
export function CodeView({ text, maxHeight }: { text: string; maxHeight?: number }) {
  const lines = text.replace(/\n$/, "").split("\n");
  return (
    <div className="code" style={maxHeight ? { maxHeight } : undefined}>
      <table>
        <tbody>
          {lines.map((l, i) => (
            <tr key={i}><td className="ln">{i + 1}</td><td className="src">{l || " "}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DiffView({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <div className="code" style={{ maxHeight: 640 }}>
      <table>
        <tbody>
          {lines.map((l, i) => {
            const cls = l.startsWith("diff --git") ? "diff-file" : l.startsWith("@@") ? "diff-hunk"
              : l.startsWith("+") && !l.startsWith("+++") ? "diff-add" : l.startsWith("-") && !l.startsWith("---") ? "diff-del" : "";
            return <tr key={i}><td className={`src ${cls}`} style={{ paddingLeft: 14 }}>{l || " "}</td></tr>;
          })}
        </tbody>
      </table>
    </div>
  );
}

export function Pre({ text, maxHeight = 420 }: { text: string; maxHeight?: number }) {
  return <div className="code" style={{ maxHeight }}><pre>{text}</pre></div>;
}

/* ---------- Toasts ---------- */
type Toast = { id: number; tone: "ok" | "err" | "info"; text: string };
const ToastCtx = createContext<(tone: Toast["tone"], text: string) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((tone: Toast["tone"], text: string) => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs, { id, tone, text }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), tone === "err" ? 7000 : 3500);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.tone}`}>
            {t.tone === "ok" ? <CircleCheck size={18} /> : t.tone === "err" ? <CircleAlert size={18} /> : <Info size={18} />}
            <div className="grow small">{t.text}</div>
            <button className="btn ghost icon-btn sm" onClick={() => setItems((xs) => xs.filter((x) => x.id !== t.id))}><X size={14} /></button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);

export function Confirm({ title, body, confirmLabel, danger, onConfirm, onClose }: {
  title: string; body: ReactNode; confirmLabel: string; danger?: boolean; onConfirm: () => void; onClose: () => void;
}) {
  return (
    <Modal title={title} onClose={onClose} footer={<>
      <button className="btn" onClick={onClose}>Cancel</button>
      <button className={`btn ${danger ? "danger" : "primary"}`} onClick={() => { onConfirm(); onClose(); }}>{confirmLabel}</button>
    </>}>
      <div className="small" style={{ color: "var(--text-2)" }}>{body}</div>
    </Modal>
  );
}
