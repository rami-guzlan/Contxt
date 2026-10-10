// Small pieces every tab of Test the Brain shares: numbers in plain words, a verdict for a gate,
// a trend line, and what a readiness state means.

import type { Bar, GateRow, ReadyRow } from "./types";

/** A value the way a person reads it: a share as a percent, a count as a count. */
export function shown(value: number | null | undefined, bar?: Bar | null): string {
  if (value === null || value === undefined) return "Not measured";
  const share = bar ? bar.value > 0 && bar.value <= 1 && value <= 1.5 : value >= 0 && value <= 1 && !Number.isInteger(value);
  if (share) return `${Math.round(value * 1000) / 10}%`;
  return Number.isInteger(value) ? String(value) : String(Math.round(value * 100) / 100);
}

export function interval(ci: number[] | null | undefined, bar?: Bar | null): string {
  if (!ci || ci.length < 2) return "";
  return `${shown(ci[0], bar)} to ${shown(ci[1], bar)}`;
}

export function barWords(bar: Bar | null | undefined): string {
  if (!bar) return "No bar set";
  const words: Record<string, string> = { ">=": "at least", "<=": "at most", ">": "above", "<": "below", "==": "exactly" };
  return `${words[bar.op] ?? bar.op} ${shown(bar.value, bar)}`;
}

export type Tone = "done" | "ready" | "active" | "blocked" | "neutral";

export function verdictOf(gate: Pick<GateRow, "value" | "met" | "met_confident" | "kind">): { text: string; tone: Tone } {
  if (gate.value === null) return { text: "Not measured yet", tone: "neutral" };
  if (gate.met === true) return gate.met_confident ? { text: "Met with confidence", tone: "done" } : { text: "Met", tone: "ready" };
  if (gate.met === false) return gate.kind === "watch" ? { text: "Not met (watching)", tone: "active" } : { text: "Not met", tone: "blocked" };
  return { text: "Measured", tone: "neutral" };
}

export function Chip({ tone = "neutral", children }: { tone?: Tone; children: React.ReactNode }) {
  const css = { done: "pill-done", ready: "pill-ready", active: "pill-pending", blocked: "pill-blocked", neutral: "" }[tone];
  return <span className={`pill ${css}`.trim()}>{children}</span>;
}

export function readyWords(row: ReadyRow): { text: string; tone: Tone } {
  switch (row.state) {
    case "ready":
      return { text: "Ready", tone: "done" };
    case "waiting_step":
      return { text: row.note || "Waits for a build step", tone: "active" };
    case "waiting_labels":
      return { text: row.note || "Waits for labels", tone: "active" };
    case "pc_only":
      return { text: "On the PC only", tone: "neutral" };
    default:
      return { text: row.state.replace(/_/g, " "), tone: "neutral" };
  }
}

export function seconds(value: number | null | undefined): string {
  if (value === null || value === undefined) return "";
  if (value < 1) return `${Math.round(value * 1000)} ms`;
  if (value < 90) return `${Math.round(value * 10) / 10} s`;
  return `${Math.round(value / 6) / 10} min`;
}

export function dollars(value: number | null | undefined): string {
  if (value === null || value === undefined) return "";
  if (value === 0) return "free";
  return `$${value >= 1 ? value.toFixed(2) : value.toFixed(4)}`;
}

/** A small line of past values, with the words a screen reader needs. */
export function Sparkline({ values, bar, label = "Trend" }: { values: number[]; bar?: Bar | null; label?: string }) {
  if (values.length < 2) return <span className="muted small">{values.length === 1 ? "One run so far" : ""}</span>;
  const width = 96;
  const height = 24;
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || 1;
  const points = values.map((v, i) => `${(i / (values.length - 1)) * width},${height - 3 - ((v - low) / span) * (height - 6)}`).join(" ");
  const first = values[0] as number;
  const last = values[values.length - 1] as number;
  return (
    <svg className="ttb-spark" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${label}: ${values.length} runs, from ${shown(first, bar)} to ${shown(last, bar)}`}>
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={width} cy={height - 3 - (((last - low) / span) * (height - 6))} r="2.4" fill="currentColor" />
    </svg>
  );
}

export const VIEWS = [
  { id: "overview", label: "Overview" },
  { id: "run", label: "Run" },
  { id: "gates", label: "Gates" },
  { id: "cases", label: "Cases" },
  { id: "watch", label: "Watch it work" },
  { id: "computer", label: "This computer" },
  { id: "history", label: "History" },
] as const;
export type View = (typeof VIEWS)[number]["id"];

/** Moves to another view, carrying what it needs (a run, a case, a gate). */
export type Go = (view: View, extra?: Record<string, string>) => void;
