import type { CSSProperties } from "react";
import { Bot, Brain, Code2, FlaskConical, Layers, ShieldCheck, Terminal, Wrench, type LucideIcon } from "lucide-react";
import type { StageKind } from "../types";

/**
 * Visual identity of each agent role (colour, icon, labels), shared across the app.
 * Colours are CSS variables (defined per theme in styles.css / theme-light.css), so every
 * agent stays readable on both dark and light backgrounds.
 */
export interface AgentLook { key: string; name: string; role: string; color: string; icon: LucideIcon; desc: string }

export const TEAM: AgentLook[] = [
  { key: "requirements", name: "Requirements Analyst", role: "Understand", color: "var(--agent-requirements)", icon: Brain, desc: "Turns your request into a spec with testable acceptance criteria." },
  { key: "architecture", name: "Architect", role: "Design", color: "var(--agent-architecture)", icon: Layers, desc: "Plans the files and the exact public interface." },
  { key: "tests", name: "Unit Test Writer", role: "Test", color: "var(--agent-tests)", icon: FlaskConical, desc: "Writes tests from the spec, without seeing the code." },
  { key: "code", name: "Code Generator", role: "Build", color: "var(--agent-code)", icon: Code2, desc: "Implements the plan and fixes failures." },
  { key: "run", name: "Code Runner", role: "Run", color: "var(--agent-run)", icon: Terminal, desc: "Executes the tests in an isolated sandbox." },
  { key: "review", name: "Code Reviewer", role: "Verify", color: "var(--agent-review)", icon: ShieldCheck, desc: "Checks the code against the spec and approves." },
];

const BY_STAGE: Record<StageKind, string> = {
  requirements: "requirements", architecture: "architecture", tests: "tests", code: "code", fix: "code", run: "run", review: "review",
};
const BY_ROLE: Record<string, string> = {
  requirements: "requirements", architect: "architecture", tests: "tests", coder: "code", runner: "run", reviewer: "review",
};

export const lookForStage = (s: StageKind): AgentLook => TEAM.find((t) => t.key === BY_STAGE[s]) ?? TEAM[0];
export const lookForRole = (role: string): AgentLook | null => TEAM.find((t) => t.key === BY_ROLE[role]) ?? null;
export const GENERAL_AGENT: AgentLook = { key: "general", name: "Agent", role: "General", color: "var(--agent-general)", icon: Bot, desc: "" };
export const FIX_ICON = Wrench;

const mix = (color: string, pct: number) => `color-mix(in srgb, ${color} ${pct}%, transparent)`;

/** Rounded avatar tinted with the agent's colour (works with CSS variables). */
export function avatarStyle(color: string): CSSProperties {
  return {
    background: `radial-gradient(circle at 30% 25%, ${mix(color, 33)}, ${mix(color, 12)} 60%, transparent 75%), var(--avatar-bg)`,
    borderColor: mix(color, 40),
    color,
    boxShadow: `0 0 18px ${mix(color, 18)}`,
  };
}
