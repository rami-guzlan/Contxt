// Data for the v4 screens: the Release 1 endpoints (docs/dev/plans/release1-plan.md). Screens may
// also use the older hooks in ../api/hooks.ts where they already cover an endpoint. Every
// mutation refreshes the areas it changes, so each view stays current.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { del, get, post, put, query } from "../api/client";

/** Refresh these areas after a change ("brain", "captures", ...). */
export function useRefresh() {
  const client = useQueryClient();
  return (...areas: string[]) => Promise.all(areas.map((area) => client.invalidateQueries({ queryKey: [area] })));
}

// ------------------------------------------------------------------ sources (captures)

export interface SourceStatus {
  item_id: string;
  status:
    | "captured"
    | "analysis_pending"
    | "retrying"
    | "awaiting_review"
    | "indexing"
    | "partial"
    | "searchable"
    | "nothing_kept"
    | "excluded"
    | "failed";
  label: string;
  stage: "captured" | "analysis" | "review" | "accepted" | "indexing" | "searchable";
  detail: string;
  can_retry: boolean;
  waiting: number;
  kept: number;
  skipped: number;
  searchable: number;
  task_id: string | null;
  proposal_ids: string[];
}

export const useSourceStatus = (ids: string[]) =>
  useQuery({
    queryKey: ["captures", "status", ids.join(",")],
    queryFn: () => get<Record<string, SourceStatus>>(`/api/captures/status${query({ ids: ids.join(",") })}`),
    enabled: ids.length > 0,
  });

function captureAction(path: (id: string) => string, body?: (id: string, extra?: string) => unknown) {
  return () => {
    const refresh = useRefresh();
    return useMutation({
      mutationFn: ({ id, extra }: { id: string; extra?: string }) => post<SourceStatus>(path(id), body ? body(id, extra) : {}),
      onSuccess: () => refresh("captures", "notes", "brain"),
    });
  };
}

export const useReadAgain = captureAction((id) => `/api/captures/${encodeURIComponent(id)}/read-again`);
export const useExclude = captureAction(
  (id) => `/api/captures/${encodeURIComponent(id)}/exclude`,
  (_id, reason) => ({ reason }),
);
export const useInclude = captureAction((id) => `/api/captures/${encodeURIComponent(id)}/include`);

// ------------------------------------------------------------------ Scout

export interface ScoutDifference {
  id: string;
  kind: "new" | "changed";
  path: string;
  size?: number;
  project?: string | null;
  at: string;
  status: "waiting" | "captured" | "dismissed";
  capture_id?: string;
}

export interface ScoutOverview {
  folders: { path: string; project: string | null }[];
  formats: Record<string, boolean>;
  last_inspection: string | null;
  last_error: { at: string; why: string } | null;
  files_seen: number;
  differences: ScoutDifference[];
  later: string[];
  found?: { kind: string; path: string; from?: string; quiet?: boolean }[];
  unreadable?: string[];
}

export const useScout = () => useQuery({ queryKey: ["scout"], queryFn: () => get<ScoutOverview>("/api/scout") });

export function useScoutSettings() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (body: { folders?: { path: string; project?: string | null }[]; formats?: Record<string, boolean> }) =>
      put<ScoutOverview>("/api/scout", body),
    onSuccess: () => refresh("scout"),
  });
}

export function useScan() {
  const refresh = useRefresh();
  return useMutation({ mutationFn: () => post<ScoutOverview>("/api/scout/scan"), onSuccess: () => refresh("scout") });
}

export function useScoutDifference() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ id, act }: { id: string; act: "bring-in" | "dismiss" }) =>
      post<{ capture_id?: string }>(`/api/scout/differences/${encodeURIComponent(id)}/${act}`),
    onSuccess: () => refresh("scout", "captures", "notes"),
  });
}

// ------------------------------------------------------------------ proposals (Capture and Catch up)

export interface SourceRef {
  id: string;
  version: string;
  locator: string;
  speaker: string;
  excerpt: string;
}

/** One waiting proposal: the same record in Capture, Catch up and a project. */
export interface Proposal {
  id: string;
  kind: string;
  scope: string;
  route_key: string;
  title: string;
  note_summary: string;
  summary: string;
  body: string;
  current_body: string | null;
  created: string;
  proposer: string;
  reason: string;
  similar: string;
  conflicts: string;
  sources?: string[];
  task_id?: string;
  source: SourceRef | null;
  operation: string;
  statement_status: string;
  effective: string;
  destination?: string;
  op_id: string;
  /** What it is and where it came from, as the capture policy names them ("fact:chat"). */
  capture?: string;
  origin?: string;
  target: Record<string, unknown>;
}

export const useProposals = () => useQuery({ queryKey: ["brain", "proposals"], queryFn: () => get<Proposal[]>("/api/brain/proposals") });

export interface Decision {
  action: "approve" | "reject";
  proposal_id: string;
  reason?: string;
  body?: string;
  title?: string;
  destination?: Record<string, string>;
}

export function useDecide() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (decisions: Decision[]) =>
      post<{ results: { id: string; ok: boolean; message: string }[]; checkpoint?: { id: string } }>("/api/brain/decisions", {
        decisions,
      }),
    onSuccess: () => refresh("brain", "captures", "home"),
  });
}

export function useUndo() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (checkpointId: string) => post<Record<string, unknown>>(`/api/brain/checkpoints/${encodeURIComponent(checkpointId)}/undo`),
    onSuccess: () => refresh("brain", "captures", "home"),
  });
}

// ------------------------------------------------------------------ receipts and Ask

export interface ReceiptItem {
  id: string;
  title: string;
  form?: string;
  tokens?: number;
  why?: string;
  at?: string;
}

export interface Receipt {
  id: string;
  session_id: string;
  at: string;
  request: string;
  scope: string[];
  partition: string | null;
  sent: ReceiptItem[];
  opened: ReceiptItem[];
  did_not_fit: ReceiptItem[];
  already_delivered: ReceiptItem[];
  unknown: string[];
  conflicts: string[];
  older: string[];
  tokens: { packet: number; map: number; opened: number; total: number; budget: number | null; counted: string };
  text: string;
  complete: false;
  note: string;
}

export const useReceipt = (id: string | null | undefined) =>
  useQuery({
    queryKey: ["brain", "receipt", id],
    queryFn: () => get<Receipt>(`/api/brain/receipts/${encodeURIComponent(id ?? "")}`),
    enabled: Boolean(id),
  });

export const CORRECTIONS: [string, string][] = [
  ["wrong_information", "Wrong information"],
  ["wrong_interpretation", "Wrong interpretation"],
  ["outdated", "Out of date"],
  ["not_relevant", "Not relevant"],
  ["missing", "Missing something"],
  ["cut_for_budget", "Cut for budget"],
  ["answer_ignored_context", "The answer ignored it"],
];

export function useCorrect() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ id, kind, item, note }: { id: string; kind: string; item?: string; note?: string }) =>
      post<Record<string, unknown>>(`/api/brain/receipts/${encodeURIComponent(id)}/corrections`, { kind, item: item ?? "", note: note ?? "" }),
    onSuccess: () => refresh("brain"),
  });
}

export interface ProviderCard {
  id: string;
  label: string;
  vendor: string;
  model: string | null;
  model_from: string;
  available: boolean;
  health: string;
  data: string;
  switches: string;
}

export interface AskAnswer {
  question: string;
  answer: string;
  session_id: string;
  receipts: string[];
  cited: string[];
  asked_brain: boolean;
  provider: ProviderCard;
}

export function useAsk() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (question: string) => post<AskAnswer>("/api/brain/agent/ask", { question }),
    onSuccess: () => refresh("brain"),
  });
}

// ------------------------------------------------------------------ Brain

export interface TasteEntry {
  id: string;
  text: string;
  kind: "principle" | "pair" | "use" | "avoid";
  strength: "usually" | "always";
  not_that: string;
  domains: string[];
}

export interface Taste {
  lenses: { looks: TasteEntry[]; feels: TasteEntry[]; works: TasteEntry[] };
  words: { use?: string[]; avoid?: string[] };
  count: number;
}

export const useTaste = () => useQuery({ queryKey: ["brain", "taste"], queryFn: () => get<Taste>("/api/brain/taste") });

export function useProposeTaste() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (body: { text: string; lens: string; kind?: string; strength?: string; not_that?: string }) =>
      post<{ status: string; proposal_id?: string; message: string }>("/api/brain/taste", body),
    onSuccess: () => refresh("brain"),
  });
}

export interface LearnedRule {
  id: string;
  type: string;
  origin: string;
  area: string;
  says: string;
  at: string;
}

export const useLearned = () => useQuery({ queryKey: ["brain", "learned"], queryFn: () => get<LearnedRule[]>("/api/brain/learned") });

export function useForgetLearned() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (id: string) => del<Record<string, unknown>>(`/api/brain/learned/${encodeURIComponent(id)}`),
    onSuccess: () => refresh("brain"),
  });
}

export interface BrainMapPage {
  lines: string[];
  page: number;
  pages: number;
  levels: Record<string, number>;
  fingerprint?: string;
}

export const useBrainMap = (area?: string, page = 1) =>
  useQuery({ queryKey: ["brain", "map", area ?? "", page], queryFn: () => get<BrainMapPage>(`/api/brain/map${query({ area, page })}`) });

export interface Policy {
  mode: "governed" | "auto";
  auto_paused: boolean;
  preset: string;
  presets: string[];
  auto_daily_cap: number;
  auto_applied_today: number;
  standing: { type: string; origin: string; area: string; paused: boolean }[];
  retrieval_policy: "relaxed" | "standard" | "careful";
  retrieval_policies: string[];
  learned: LearnedRule[];
  areas: string[];
  capture_types: string[];
  capture_origins: string[];
  [key: string]: unknown;
}

export const usePolicy = () => useQuery({ queryKey: ["brain", "policy"], queryFn: () => get<Policy>("/api/brain/policies") });

export function useSetPolicy() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (changes: Partial<Policy>) => put<{ policy: Policy }>("/api/brain/policies", changes),
    onSuccess: () => refresh("brain"),
  });
}

// ------------------------------------------------------------------ connections

export interface InstructionStatus {
  app: string;
  supported: boolean;
  installed: boolean;
  path: string | null;
}

export const useInstructions = () =>
  useQuery({ queryKey: ["connections", "instructions"], queryFn: () => get<InstructionStatus[]>("/api/connections/instructions") });

export function useInstruction() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ app, install }: { app: string; install: boolean }) =>
      install
        ? post<InstructionStatus>(`/api/connections/instructions/${encodeURIComponent(app)}`, { confirmed: true })
        : del<InstructionStatus>(`/api/connections/instructions/${encodeURIComponent(app)}`),
    onSuccess: () => refresh("connections"),
  });
}

// ------------------------------------------------------------------ Work with AI

export interface WorkJob {
  task_id: string;
  title: string;
  status: string;
  runner: string | null;
  run_id: string | null;
  model: string | null;
  tokens: Record<string, number>;
  cost: number | null;
  started_at: string;
  finished_at: string | null;
  outputs: { id: string; title: string }[];
  proposals: string[];
  why: string;
  asked_by: string | null;
}

export const useWorkTimeline = (projectId: string | undefined) =>
  useQuery({
    queryKey: ["work", "timeline", projectId],
    queryFn: () => get<WorkJob[]>(`/api/work/projects/${encodeURIComponent(projectId ?? "")}/timeline`),
    enabled: Boolean(projectId),
    refetchInterval: 5000,
  });

export function useWorkAsk() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ project, prompt, skill, agent }: { project: string; prompt: string; skill?: string; agent?: string }) =>
      post<{ task: { id: string }; run: { id: string } }>(`/api/work/projects/${encodeURIComponent(project)}/ask`, {
        prompt,
        skill: skill || null,
        agent: agent || null,
      }),
    onSuccess: () => refresh("work", "tasks"),
  });
}
