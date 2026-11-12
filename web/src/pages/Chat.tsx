import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Bot, Cpu, Loader2, MessageSquare, RotateCcw, Send, Square, Wrench } from "lucide-react";
import { api } from "../api";
import { fmt, useData } from "../lib";
import type { ChatTurn, RunSnapshot, TimelineItem } from "../types";
import { useApp } from "../components/AppContext";
import { Badge, Card, Empty, Pre, useToast } from "../components/ui";

type Msg = { role: "user" | "assistant"; content: string; timeline?: TimelineItem[]; meta?: string; runId?: string; error?: boolean };

export default function ChatPage() {
  const toast = useToast();
  const { keyReady, settings } = useApp();
  const { data: agents } = useData(api.agents, []);
  const { data: models } = useData(() => (keyReady ? api.models() : Promise.resolve([])), [keyReady]);
  const [mode, setMode] = useState<"agent" | "model">("agent");
  const [agent, setAgent] = useState("assistant");
  const [model, setModel] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [live, setLive] = useState<RunSnapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const chatAgents = (agents ?? []).filter((a) => a.kind === "llm");

  // Block body on purpose: newer browsers return a Promise from scrollIntoView, and an effect must
  // return nothing or a cleanup function, otherwise React crashes on unmount.
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, live]);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    const history: ChatTurn[] = [...msgs.filter((m) => !m.error).map((m) => ({ role: m.role, content: m.content })), { role: "user", content: text }];
    setMsgs((m) => [...m, { role: "user", content: text }]);
    setInput("");
    setBusy(true);
    try {
      if (mode === "model") {
        const r = await api.chat(history, model || null);
        setMsgs((m) => [...m, { role: "assistant", content: r.text, runId: r.run_id, meta: `${(r.model || model || settings?.default_model || "model").replace("openai:", "")} · ${fmt.int(r.input_tokens)} in / ${fmt.int(r.output_tokens)} out` }]);
      } else {
        let snap = await api.startRun(agent, history, model || null);
        setLive(snap);
        while (snap.status === "running") {
          await new Promise((r) => setTimeout(r, 400));
          snap = (await api.run(snap.run_id)) as RunSnapshot;
          setLive(snap);
        }
        setLive(null);
        setMsgs((m) => [...m, {
          role: "assistant", content: snap.output ?? snap.error ?? `(${snap.status})`, timeline: snap.timeline, runId: snap.run_id,
          error: snap.status !== "done",
          meta: `${snap.agent} · ${snap.model_calls} model calls · ${snap.tool_calls} tool calls · ${fmt.int(snap.input_tokens)} in / ${fmt.int(snap.output_tokens)} out`,
        }]);
      }
    } catch (e) {
      setLive(null);
      toast("err", e instanceof Error ? e.message : String(e));
      setMsgs((m) => [...m, { role: "assistant", content: e instanceof Error ? e.message : String(e), error: true }]);
    } finally { setBusy(false); }
  };

  return (
    <div className="page" style={{ maxWidth: 1100 }}>
      <Card title="Chat" icon={<MessageSquare size={16} />}
        actions={<>
          <div className="segmented">
            <button className={mode === "agent" ? "on" : ""} onClick={() => setMode("agent")}><Bot size={13} />Agent</button>
            <button className={mode === "model" ? "on" : ""} onClick={() => setMode("model")}><Cpu size={13} />Model</button>
          </div>
          {mode === "agent" && (
            <select className="select" style={{ width: 200 }} value={agent} onChange={(e) => setAgent(e.target.value)}>
              {chatAgents.map((a) => <option key={a.name} value={a.name}>{a.name}</option>)}
            </select>
          )}
          <select className="select" style={{ width: 220 }} value={model} onChange={(e) => setModel(e.target.value)}>
            <option value="">{mode === "agent" ? "Agent's model" : `Default · ${(settings?.default_model || "not set").replace("openai:", "")}`}</option>
            {(models ?? []).map((m) => <option key={m} value={`openai:${m}`}>{m}</option>)}
          </select>
          <button className="btn ghost icon-btn" title="New conversation" onClick={() => setMsgs([])}><RotateCcw size={15} /></button>
        </>}>
        <div className="col" style={{ gap: 16, minHeight: 420, maxHeight: "calc(100vh - 330px)", overflow: "auto", paddingRight: 4 }}>
          {!msgs.length && !live && (
            <Empty icon={<MessageSquare size={20} />} title="Start a conversation">
              Chat with an agent (it can call its tools, e.g. the calculator or web fetch) or directly with a model.
              Every message is traced in <Link to="/runs">Runs</Link>.
            </Empty>
          )}
          {msgs.map((m, i) => <Message key={i} m={m} />)}
          {live && (
            <div className="msg">
              <Timeline items={live.timeline} />
              <div className="row xs muted"><Loader2 size={13} className="spin" />Working… {live.model_calls} model calls · {live.tool_calls} tool calls
                <button className="btn sm ghost" onClick={() => api.cancelRun(live.run_id)}><Square size={12} />Stop</button></div>
            </div>
          )}
          <div ref={endRef} />
        </div>
        <div className="row" style={{ marginTop: 16, alignItems: "flex-end" }}>
          <textarea className="textarea grow" rows={2} style={{ minHeight: 48 }} placeholder={keyReady ? "Message… (Enter to send, Shift+Enter for a new line)" : "Add your OpenAI key in Settings first"}
            disabled={!keyReady} value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
          <button className="btn primary lg" disabled={!keyReady || busy || !input.trim()} onClick={send}>{busy ? <Loader2 size={16} className="spin" /> : <Send size={16} />}Send</button>
        </div>
      </Card>
    </div>
  );
}

function Timeline({ items }: { items: TimelineItem[] }) {
  return (
    <div className="col" style={{ gap: 8 }}>
      {items.map((it, i) => it.kind === "text" ? (it.text ? <div key={i} className="bubble">{it.text}</div> : null) : (
        <div key={i} className="tool-call">
          <div className="row"><Wrench size={13} className="muted" /><span className="mono strong">{it.tool_name}</span>
            <Badge tone={it.tool_status === "ok" ? "ok" : it.tool_status === "error" ? "err" : "accent"}>{it.tool_status ?? "…"}</Badge></div>
          <div className="mono xs muted">{JSON.stringify(it.tool_args)}</div>
          {it.tool_output && <Pre text={it.tool_output.slice(0, 2000)} maxHeight={140} />}
        </div>
      ))}
    </div>
  );
}

function Message({ m }: { m: Msg }) {
  if (m.role === "user") return <div className="msg user"><div className="bubble">{m.content}</div></div>;
  const tools = m.timeline?.filter((t) => t.kind === "tool") ?? [];
  return (
    <div className="msg">
      {tools.length > 0 && <Timeline items={tools} />}
      <div className="bubble" style={m.error ? { borderColor: "rgba(248,113,113,.4)" } : undefined}>{m.content}</div>
      {m.meta && <div className="xs faint">{m.meta}{m.runId && <> · <Link to={`/runs/${m.runId}`}>trace</Link></>}</div>}
    </div>
  );
}
