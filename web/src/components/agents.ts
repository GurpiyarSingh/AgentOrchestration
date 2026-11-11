import type { CSSProperties } from "react";
import { Bot, Brain, Code2, FlaskConical, Layers, ShieldCheck, Terminal, Wrench, type LucideIcon } from "lucide-react";
import type { StageKind } from "../types";

/** Visual identity of each agent role (colour, icon, labels), shared across the app. */
export interface AgentLook { key: string; name: string; role: string; color: string; icon: LucideIcon; desc: string }

export const TEAM: AgentLook[] = [
  { key: "requirements", name: "Requirements Analyst", role: "Understand", color: "#a3e635", icon: Brain, desc: "Turns your request into a spec with testable acceptance criteria." },
  { key: "architecture", name: "Architect", role: "Design", color: "#2dd4bf", icon: Layers, desc: "Plans the files and the exact public interface." },
  { key: "tests", name: "Unit Test Writer", role: "Test", color: "#facc15", icon: FlaskConical, desc: "Writes tests from the spec, without seeing the code." },
  { key: "code", name: "Code Generator", role: "Build", color: "#34d399", icon: Code2, desc: "Implements the plan and fixes failures." },
  { key: "run", name: "Code Runner", role: "Run", color: "#38bdf8", icon: Terminal, desc: "Executes the tests in an isolated sandbox." },
  { key: "review", name: "Code Reviewer", role: "Verify", color: "#f0abfc", icon: ShieldCheck, desc: "Checks the code against the spec and approves." },
];

const BY_STAGE: Record<StageKind, string> = {
  requirements: "requirements", architecture: "architecture", tests: "tests", code: "code", fix: "code", run: "run", review: "review",
};
const BY_ROLE: Record<string, string> = {
  requirements: "requirements", architect: "architecture", tests: "tests", coder: "code", runner: "run", reviewer: "review",
};

export const lookForStage = (s: StageKind): AgentLook => TEAM.find((t) => t.key === BY_STAGE[s]) ?? TEAM[0];
export const lookForRole = (role: string): AgentLook | null => TEAM.find((t) => t.key === BY_ROLE[role]) ?? null;
export const GENERAL_AGENT: AgentLook = { key: "general", name: "Agent", role: "General", color: "#94a3b8", icon: Bot, desc: "" };
export const FIX_ICON = Wrench;

/** Round avatar with the agent's colour and icon. */
export function avatarStyle(color: string): CSSProperties {
  return {
    background: `radial-gradient(circle at 30% 25%, ${color}55, ${color}1f 60%, transparent 75%), #11131b`,
    borderColor: `${color}66`, color, boxShadow: `0 0 18px ${color}2e`,
  };
}
