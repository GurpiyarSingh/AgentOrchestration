// Types mirroring the FastAPI response models.

export interface KeyStatus { configured: boolean; source: "saved" | "missing"; hint: string | null; location: string }
export interface UserPrefs {
  default_model: string | null; cheap_model: string | null; show_all_models: boolean;
  git_author_name: string | null; git_author_email: string | null;
}
export interface SettingsView {
  key: KeyStatus; prefs: UserPrefs; default_model: string; cheap_model: string;
  git_author_name: string; git_author_email: string; github_token_set: boolean;
  data_dir: string; workspaces_dir: string; runner_timeout_s: number;
}
export interface KeyCheck { ok: boolean; message: string; models: number }
export interface ModelPrice { input_per_1m: number; output_per_1m: number; cached_input_per_1m?: number | null }

export interface UsageSummary { runs: number; model_calls: number; tool_calls: number; input_tokens: number; output_tokens: number; cost_usd: number }
export interface UsageReport { today: UsageSummary; all_time: UsageSummary }

export interface LanguageInfo { id: string; name: string; available: boolean; toolchain: string }
export interface Project { id: string; name: string; path: string; language: string; base_branch: string; kind: string; created_at: string }
export interface FileEntry { path: string; size: number }

export interface AgentDef {
  name: string; description: string; kind: "llm" | "step"; role: string; system_prompt: string;
  model: string; reasoning_effort: string | null; tools: string[]; skills: string[];
  max_model_calls: number; max_tool_calls: number;
}

export interface ToolInfo {
  name: string; source: string; description: string; enabled: boolean; requires_approval: boolean;
  invokable: boolean; used_by: string[]; args_schema: JsonSchema;
}
export interface JsonSchema { type?: string; properties?: Record<string, JsonSchema & { description?: string; default?: unknown; enum?: string[] }>; required?: string[]; description?: string }
export interface ToolInvocation { ok: boolean; output: string; duration_ms: number }

export type StageKind = "requirements" | "architecture" | "tests" | "code" | "run" | "fix" | "review";
export interface StageRun {
  id: string; stage: StageKind; agent: string; title: string; status: "pending" | "running" | "done" | "failed" | "skipped";
  attempt: number; started_at: string | null; ended_at: string | null; summary: string; model: string | null;
  model_calls: number; tool_calls: number; input_tokens: number; output_tokens: number;
}
export interface Spec { title: string; summary: string; acceptance_criteria: string[]; assumptions: string[]; out_of_scope: string[] }
export interface Plan { approach: string; files: { path: string; kind: "source" | "test"; purpose: string }[]; interfaces: string }
export interface ReviewIssue { severity: "high" | "medium" | "low"; file: string; message: string }
export interface Review { approved: boolean; summary: string; issues: ReviewIssue[] }
export interface TestCase { name: string; status: "passed" | "failed" | "error" | "skipped"; message: string }
export interface TestReport {
  ok: boolean; total: number; passed: number; failed: number; errors: number; skipped: number;
  exit_code: number | null; timed_out: boolean; duration_s: number; command: string; output: string; cases: TestCase[];
}
export type BuildStatus = "running" | "done" | "needs_attention" | "failed" | "cancelled";
export interface BuildSnapshot {
  run_id: string; project_id: string; project_name: string; language: string; requirement: string;
  status: BuildStatus; started_at: string; ended_at: string | null; stages: StageRun[];
  spec: Spec | null; plan: Plan | null; test_report: TestReport | null; review: Review | null; files: string[];
  branch: string; base_branch: string; worktree: string; repo_path: string; fix_attempts: number; review_rounds: number;
  final_action: "merged" | "kept" | "discarded" | null; message: string; error: string | null;
  totals: { model_calls: number; tool_calls: number; input_tokens: number; output_tokens: number; cost_usd: number };
}
export interface BuildSummary {
  run_id: string; project_id: string; project_name: string; title: string; status: BuildStatus;
  final_action: string | null; started_at: string; ended_at: string | null; tests: string; total_tokens: number;
}

export interface ChatTurn { role: "user" | "assistant"; content: string }
export interface TimelineItem {
  kind: "text" | "tool"; text: string; tool_call_id: string | null; tool_name: string | null;
  tool_args: Record<string, unknown>; tool_output: string | null; tool_status: "running" | "ok" | "error" | null;
}
export interface RunSnapshot {
  run_id: string; agent: string; status: string; timeline: TimelineItem[]; output: string | null; error: string | null;
  input_tokens: number; output_tokens: number; cost_usd: number; model_calls: number; tool_calls: number;
}
export interface RunSummary {
  run_id: string; kind: string; target: string; status: string; input: string; output: string | null;
  started_at: string; ended_at: string | null; input_tokens: number; output_tokens: number; cost_usd: number;
  model_calls: number; tool_calls: number;
}
export interface SpanNode {
  id: string; type: string; name: string; started_at: string; duration_ms: number | null;
  tokens_in: number; tokens_out: number; meta: Record<string, unknown>; input: unknown; output: unknown; children: SpanNode[];
}

export interface FolderEntry { name: string; path: string; is_git: boolean }
export interface FolderListing { path: string | null; parent: string | null; is_git: boolean; entries: FolderEntry[]; shortcuts: FolderEntry[] }

export interface McpServerConfig {
  name: string; transport: "stdio" | "http"; command: string | null; args: string[];
  env: Record<string, string>; url: string | null; headers: Record<string, string>; enabled: boolean;
}
export interface McpToolInfo { name: string; original_name: string; description: string; read_only: boolean | null; destructive: boolean | null }
export interface McpServerView {
  name: string; transport: "stdio" | "http"; command: string | null; args: string[]; url: string | null;
  env_keys: string[]; header_keys: string[]; enabled: boolean;
  status: "disconnected" | "connecting" | "connected" | "error"; error: string | null; tools: McpToolInfo[]; connected_at: string | null;
}
export interface EnvVarSpec { name: string; description: string; required: boolean; secret: boolean; default: string | null }
export interface RegistryEntry {
  name: string; title: string; description: string; version: string; repository: string | null;
  kind: string; draft: McpServerConfig; env_vars: EnvVarSpec[]; supported: boolean; note: string;
}
export interface Skill { name: string; description: string; body: string; files: string[]; path: string }
