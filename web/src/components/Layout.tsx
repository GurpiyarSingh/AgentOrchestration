import { NavLink, Outlet, useLocation, Link } from "react-router-dom";
import {
  Activity, ArrowRight, Bot, BookMarked, BookOpen, Plug, Moon, Sun, Coins, Cpu, FolderGit2, Hammer, KeyRound, MessageSquare, Settings, Wrench, Zap,
} from "lucide-react";
import { api } from "../api";
import { fmt, useData } from "../lib";
import { useApp } from "./AppContext";
import { Wordmark } from "./Brand";
import { NetworkBackground } from "./NetworkBackground";
import { ErrorBoundary } from "./ErrorBoundary";
import { useTheme } from "../theme";

const NAV = [
  { section: "Build", items: [
    { to: "/", label: "Build", icon: Hammer, end: true },
    { to: "/projects", label: "Projects", icon: FolderGit2 },
  ] },
  { section: "Agents", items: [
    { to: "/agents", label: "Agents", icon: Bot },
    { to: "/skills", label: "Skills", icon: BookMarked },
    { to: "/mcp", label: "MCP servers", icon: Plug },
    { to: "/tools", label: "Tools", icon: Wrench },
    { to: "/chat", label: "Chat", icon: MessageSquare },
  ] },
  { section: "Observe", items: [
    { to: "/runs", label: "Runs & traces", icon: Activity },
    { to: "/settings", label: "Settings", icon: Settings },
  ] },
];

const TITLES: Record<string, [string, string]> = {
  "": ["Build", "Your AI software team turns requirements into tested, reviewed code"],
  builds: ["Build", "Turn a requirement into tested, reviewed code"],
  projects: ["Projects", "Folders your agent team writes code into"],
  agents: ["Agents", "The build team and your own agents"],
  tools: ["Tools", "Everything agents can call"],
  mcp: ["MCP servers", "Connect external tools via the Model Context Protocol"],
  skills: ["Skills", "Reusable know-how your agents load on demand"],
  chat: ["Chat", "Talk to an agent or a model directly"],
  runs: ["Runs & traces", "Every model call and tool call, with tokens and cost"],
  settings: ["Settings", "API key, models, pricing and integrations"],
};

function UsageStrip() {
  const { data } = useData(api.usage, [], 4000);
  const t = data?.today;
  const all = data?.all_time;
  const title = all
    ? `All time: ${fmt.int(all.runs)} runs · ${fmt.int(all.model_calls)} model calls · ${fmt.int(all.tool_calls)} tool calls · ` +
      `${fmt.int(all.input_tokens)} in + ${fmt.int(all.output_tokens)} out tokens · ${fmt.cost(all.cost_usd)}`
    : "";
  return (
    <div className="usage" title={title}>
      <span className="usage-scope">Today</span>
      <div className="usage-item"><Cpu size={14} /><span className="k">Model calls</span><span className="v">{fmt.int(t?.model_calls)}</span></div>
      <div className="usage-item opt"><Wrench size={14} /><span className="k">Tool calls</span><span className="v">{fmt.int(t?.tool_calls)}</span></div>
      <div className="usage-item"><Zap size={14} /><span className="k">Tokens</span>
        <span className="v">{fmt.compact(t?.input_tokens ?? 0)} <span className="muted">in</span> · {fmt.compact(t?.output_tokens ?? 0)} <span className="muted">out</span></span>
      </div>
      <div className="usage-item opt"><span className="k">Total</span><span className="v">{fmt.compact((t?.input_tokens ?? 0) + (t?.output_tokens ?? 0))}</span></div>
      <div className="usage-item"><Coins size={14} /><span className="k">Cost</span><span className="v">{fmt.cost(t?.cost_usd ?? 0)}</span></div>
    </div>
  );
}

function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button className="btn icon-btn" onClick={toggle} title={`Switch to ${next} theme`} aria-label={`Switch to ${next} theme`}>
      {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}

export function Layout() {
  const loc = useLocation();
  const { settings, keyReady } = useApp();
  const seg = loc.pathname.split("/")[1] ?? "";
  const [title, sub] = TITLES[seg] ?? TITLES[""];
  return (
    <div className="shell">
      <aside className="sidebar">
        <Wordmark />
        {NAV.map((g) => (
          <div key={g.section}>
            <div className="nav-label">{g.section}</div>
            {g.items.map(({ to, label, icon: Icon, end }) => (
              <NavLink key={to} to={to} end={end} className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
                <Icon size={16} />{label}
              </NavLink>
            ))}
          </div>
        ))}
        <div className="sidebar-foot">
          <a className="nav-item" href="/docs" target="_blank" rel="noreferrer"><BookOpen size={16} />API docs</a>
          {settings && (keyReady ? (
            <div className="chip" title={`Key stored in ${settings.key.location}`}>
              <span className="dot" style={{ color: "var(--ok)" }} /> OpenAI connected <span className="faint">{settings.key.hint}</span>
            </div>
          ) : (
            <Link to="/settings" className="chip" style={{ borderColor: "rgba(251,191,36,.35)", color: "#fcd34d" }}>
              <KeyRound size={13} /> Add your OpenAI key
            </Link>
          ))}
          {settings && keyReady && (
            <div className="xs faint ellipsis" title="Default model">Model: <span className="mono">{settings.default_model || "not set"}</span></div>
          )}
        </div>
      </aside>
      <div className="main">
        <NetworkBackground />
        <header className="topbar">
          <div className="topbar-title">
            <h1>{title}</h1>
            <span className="crumb">{sub}</span>
          </div>
          <div className="row" style={{ gap: 8 }}>
            <UsageStrip />
            <ThemeToggle />
          </div>
        </header>
        <div className="content">
          {settings && !keyReady && seg !== "settings" && (
            <div className="page" style={{ marginBottom: 20 }}>
              <div className="callout warn">
                <KeyRound size={18} style={{ color: "var(--warn)", marginTop: 2 }} />
                <div className="grow">
                  <div className="strong">Connect your OpenAI account to start</div>
                  <div className="small muted">Paste an API key in Settings. It is verified and stored in your OS credential store, never in the database.</div>
                </div>
                <Link to="/settings" className="btn primary sm">Open settings <ArrowRight size={14} /></Link>
              </div>
            </div>
          )}
          <ErrorBoundary resetKey={loc.pathname}><Outlet /></ErrorBoundary>
        </div>
      </div>
    </div>
  );
}
