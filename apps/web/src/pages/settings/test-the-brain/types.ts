// What Settings > Test the Brain reads from /api/test-the-brain. One results contract, whether it
// comes from a connected Lab or from the checks this app runs on its own Brain.

export type RunState = "running" | "done" | "failed" | "cancelled";

export interface ActiveRun {
  ticket?: string;
  run: string | null;
  kind: string | null;
  suite?: string | null;
  state: RunState;
  message: string;
  exit_code?: number | null;
  started_at?: string;
  ended_at?: string | null;
  /** False for a run someone else started (the Lab's own pane). */
  ours?: boolean;
}

export interface ProgressEvent {
  event: string;
  at?: string;
  run?: string;
  kind?: string;
  suite?: string;
  case?: string;
  done?: number;
  total?: number;
  failures?: number;
  message?: string;
}

export interface LiveReply {
  active: ActiveRun | null;
  events: ProgressEvent[];
  next: number;
}

export interface RunKind {
  id: string;
  name: string;
  covers: string;
  paid: boolean;
  last?: { run?: string; at?: string; seconds?: number | null; usd?: number | null } | null;
  estimate?: { usd?: number | null; seconds?: number | null; calls?: number | null } | null;
  suites: string[];
}

export interface ReadyRow {
  suite: string;
  setup?: string;
  state: string; // ready | waiting_step | waiting_labels | pc_only
  note?: string;
}

export interface Bar {
  op: string;
  value: number;
}

export interface Status {
  updated?: string | null;
  engine_ref?: string | null;
  machine_setup?: string | null;
  brain?: string | null;
  run_kinds: RunKind[];
  ready: ReadyRow[];
  labels: Record<string, unknown> & {
    labeled?: number;
    total?: number;
    held_out?: number;
    sitting?: { state?: string; minutes?: number };
  };
  qualification: Qualification[];
  lock_holder: string | null;
}

export interface Qualification {
  step: string;
  model?: string;
  state: string; // on | fallback
  fallback?: string;
  speed_ms?: number | null;
  budget_ms?: number | null;
  peak_ram_mb?: number | null;
}

export interface BuiltinInfo {
  name: string;
  reads_brain: string;
  waits: ReadyRow[];
  computer: {
    system: string;
    cpus: number | null;
    python: string;
    engine: boolean;
    matching: { enabled?: boolean; present?: boolean; model?: string; about_mb?: number };
  };
}

export interface State {
  source: "lab" | "builtin";
  lab: { name: string | null; folder: string; contract: number | null } | null;
  error: string | null;
  status: Status | null;
  running: ActiveRun | null;
  builtin?: BuiltinInfo;
}

export interface Pillar {
  id: string;
  name: string;
  total: number;
  measured: number;
  met: number;
  confident: number;
  headline: { id: string; name: string; value: number; ci: number[] | null; bar: Bar | null } | null;
  trend: number[];
}

export interface ReportCardLines {
  days?: number;
  per_day_usd?: number;
  brief_tokens_by_type?: Record<string, number>;
  by_day?: { day: string; total_usd: number; lines: Record<string, number | null> }[];
  text?: string;
}

export interface Overview {
  source: "lab" | "builtin";
  pillars: Pillar[];
  effect: { id: string; value?: number; ci?: number[]; n?: number; run?: string } | null;
  ready: ReadyRow[];
  labels: Status["labels"];
  card: ReportCardLines | null;
  last: { run: string; kind: string; ended?: string | null; valid: boolean } | null;
  lock_holder: string | null;
}

export interface GateRow {
  id: string;
  name: string;
  bar: Bar | null;
  kind: "hard" | "watch";
  source: string;
  pillar: string | null;
  value: number | null;
  ci: number[] | null;
  n: number | null;
  met: boolean | null;
  met_confident: boolean | null;
  run: string | null;
  trend: number[];
}

export interface RunRow {
  run: string;
  kind: string;
  valid: boolean;
  config: Record<string, unknown>;
  cost: { usd_estimate?: number; tokens?: number; seconds?: number };
  metrics: number;
  failing: number;
  started?: string | null;
  ended?: string | null;
  note?: string | null;
}

export interface Metric {
  id: string;
  split?: string | null;
  n?: number | null;
  value?: number | null;
  ci?: number[] | null;
  gate?: string | null;
  met?: boolean | null;
  met_confident?: boolean | null;
}

export interface Summary {
  run: string;
  kind: string;
  config: Record<string, unknown>;
  valid: boolean;
  metrics: Metric[];
  cost: { usd_estimate?: number; tokens?: number; seconds?: number };
  failing_cases: { id: string; title: string; why: string }[];
  started?: string;
  ended?: string;
  note?: string;
}

export type CaseKind = "retrieval" | "outcome" | "world" | "session" | "table";

export interface CaseRow {
  id: string;
  suite: string;
  kind: CaseKind;
  title: string;
  sensitive: boolean;
  pass: boolean | null;
  measures: Record<string, unknown>;
}

export interface CasePage {
  total: number;
  skipped: number;
  kinds: string[];
  cases: CaseRow[];
}

export interface NoteView {
  id: string;
  title?: string;
  label?: string;
  form?: string;
  scores?: Record<string, number>;
  why?: string;
  tokens?: number;
}

export interface CaseFull extends CaseRow {
  request: string | null;
  view: {
    request?: string;
    brief?: string;
    notes?: NoteView[];
    standards?: { id: string; name: string; pass: boolean }[];
    waits?: string;
    with?: { text: string };
    without?: { text: string };
    key_points?: { text: string; with: boolean; without: boolean; item?: string }[];
    violations?: { rule: string; arm: string; text: string }[];
    plants?: { id: string; what: string; found: boolean }[];
    false_alarms?: { what: string }[];
    suggestions?: { text: string; impact?: string[] }[];
    turns?: { role: string; text: string }[];
    checks?: { name: string; pass: boolean }[];
    columns?: string[];
    rows?: { label: string; expected?: string; got?: string; pass?: boolean | null }[];
    [key: string]: unknown;
  };
}

export interface Compare {
  a: string;
  b: string;
  config: { a: Record<string, unknown>; b: Record<string, unknown> };
  metrics: {
    id: string;
    gate: string | null;
    from: number | null;
    to: number | null;
    delta: number | null;
    met_from: boolean | null;
    met_to: boolean | null;
  }[];
  flipped: { id: string; title: string; from: boolean; to: boolean }[];
}

export interface StageDrawn {
  id: string;
  name: string;
  state: string; // done | waiting | skipped
  in: number | null;
  out: number | null;
  ms: number | null;
  note: string;
  dropped: { id: string; title: string; why: string }[];
  added: { id: string; title: string; why: string }[];
}

export interface WatchReply {
  test: boolean;
  client: string;
  read_only: boolean;
  from_record?: boolean;
  engine?: boolean;
  mode?: string | null;
  tokens?: number | null;
  ms?: number;
  request: string | null;
  case?: string | null;
  labels?: Record<string, string>;
  stages: StageDrawn[];
  notes: { id: string; title: string; outcome: string; why: string; label?: string }[];
}
