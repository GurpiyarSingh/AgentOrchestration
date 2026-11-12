// Typed client for the FastAPI backend (all routes under /api).
import type {
  AgentDef, BuildSnapshot, BuildSummary, ChatTurn, FileEntry, FolderListing, KeyCheck, McpServerConfig, McpServerView, RegistryEntry, Skill, LanguageInfo, ModelPrice, Project,
  RunSnapshot, RunSummary, SettingsView, SpanNode, ToolInfo, ToolInvocation, UsageReport, UserPrefs,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function request<T>(method: string, path: string, body?: unknown, asText = false): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") message = data.detail;
      else if (Array.isArray(data.detail)) message = data.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch { /* not JSON */ }
    throw new ApiError(res.status, message);
  }
  if (res.status === 204) return undefined as T;
  return (asText ? res.text() : res.json()) as Promise<T>;
}

const get = <T>(p: string) => request<T>("GET", p);
const getText = (p: string) => request<string>("GET", p, undefined, true);
const post = <T>(p: string, b?: unknown) => request<T>("POST", p, b ?? {});
const put = <T>(p: string, b: unknown) => request<T>("PUT", p, b);
const del = (p: string) => request<void>("DELETE", p);
const q = (p: Record<string, string>) => "?" + new URLSearchParams(p).toString();

export const api = {
  usage: () => get<UsageReport>("/usage"),
  models: (all?: boolean) => get<string[]>(`/models${all === undefined ? "" : q({ all: String(all) })}`),
  languages: () => get<LanguageInfo[]>("/languages"),
  pickFolder: (title: string, initial?: string) =>
    post<{ path: string | null; cancelled: boolean; is_git: boolean }>("/system/pick-folder", { title, initial: initial ?? null }),
  folders: (path?: string) => get<FolderListing>(`/system/folders${path ? q({ path }) : ""}`),

  settings: () => get<SettingsView>("/settings"),
  saveKey: (key: string, save = true) => post<KeyCheck>("/settings/openai-key", { key, save }),
  removeKey: () => del("/settings/openai-key"),
  savePrefs: (p: Partial<UserPrefs>) => put<UserPrefs>("/settings/preferences", p),
  prices: () => get<Record<string, ModelPrice>>("/settings/prices"),
  savePrices: (models: Record<string, ModelPrice>) => put<Record<string, ModelPrice>>("/settings/prices", { models }),
  saveGithubToken: (token: string) => put<void>("/settings/github-token", { token }),
  removeGithubToken: () => del("/settings/github-token"),

  projects: () => get<Project[]>("/projects"),
  createProject: (b: { name: string; language: string; mode: "new" | "existing"; path?: string }) => post<Project>("/projects", b),
  removeProject: (id: string) => del(`/projects/${id}`),
  projectFiles: (id: string) => get<FileEntry[]>(`/projects/${id}/files`),
  projectFile: (id: string, path: string) => getText(`/projects/${id}/file${q({ path })}`),

  builds: (projectId?: string) => get<BuildSummary[]>(`/builds${projectId ? q({ project_id: projectId }) : ""}`),
  build: (id: string) => get<BuildSnapshot>(`/builds/${id}`),
  startBuild: (b: { project_id: string; requirement: string; model?: string | null; max_fix_attempts?: number; max_review_rounds?: number }) =>
    post<BuildSnapshot>("/builds", b),
  cancelBuild: (id: string) => post<{ cancelled: boolean }>(`/builds/${id}/cancel`),
  buildFile: (id: string, path: string) => getText(`/builds/${id}/file${q({ path })}`),
  buildDiff: (id: string) => getText(`/builds/${id}/diff`),

  mcpServers: () => get<McpServerView[]>("/mcp/servers"),
  saveMcpServer: (cfg: McpServerConfig, connect = true) => put<McpServerView>(`/mcp/servers/${encodeURIComponent(cfg.name)}${q({ connect: String(connect) })}`, cfg),
  deleteMcpServer: (name: string) => del(`/mcp/servers/${encodeURIComponent(name)}`),
  connectMcp: (name: string) => post<McpServerView>(`/mcp/servers/${encodeURIComponent(name)}/connect`),
  disconnectMcp: (name: string) => post<McpServerView>(`/mcp/servers/${encodeURIComponent(name)}/disconnect`),
  importMcp: (json_text: string) => post<McpServerView[]>("/mcp/import", { json_text, connect: true }),
  mcpRegistry: (query: string) => get<RegistryEntry[]>(`/mcp/registry${q({ q: query, limit: "30" })}`),

  skills: () => get<Skill[]>("/skills"),
  saveSkill: (sk: { name: string; description: string; body: string }) => put<Skill>(`/skills/${sk.name}`, sk),
  deleteSkill: (name: string) => del(`/skills/${name}`),

  agents: () => get<AgentDef[]>("/agents"),
  saveAgent: (a: AgentDef) => put<AgentDef>(`/agents/${a.name}`, a),
  deleteAgent: (name: string) => del(`/agents/${name}`),
  agentYaml: (name: string) => getText(`/agents/${name}/yaml`),
  restoreAgents: (overwrite = false) => post<string[]>(`/agents/restore-defaults${q({ overwrite: String(overwrite) })}`),

  tools: () => get<ToolInfo[]>("/tools"),
  setToolFlags: (name: string, flags: { enabled?: boolean; requires_approval?: boolean }) =>
    request<ToolInfo>("PATCH", `/tools/${name}`, flags),
  invokeTool: (name: string, args: Record<string, unknown>) => post<ToolInvocation>(`/tools/${name}/invoke`, { args }),

  chat: (messages: ChatTurn[], model?: string | null) =>
    post<{ run_id: string; text: string; input_tokens: number; output_tokens: number; model: string | null }>("/chat", { messages, model }),
  startRun: (agent: string, messages: ChatTurn[], model?: string | null) => post<RunSnapshot>("/runs", { agent, messages, model }),
  run: (id: string) => get<RunSnapshot | RunSummary>(`/runs/${id}`),
  cancelRun: (id: string) => post<{ cancelled: boolean }>(`/runs/${id}/cancel`),
  runs: (limit = 200) => get<RunSummary[]>(`/runs${q({ limit: String(limit) })}`),
  spans: (id: string) => get<SpanNode[]>(`/runs/${id}/spans`),
};
