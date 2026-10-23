// Data for Agents, Settings and the States page that ../api.ts and ../../api/hooks.ts do not
// cover yet: the knowledge agent's provider card, Test the Brain, a CLI's sign-in, and agent
// profiles. Built like ../api.ts (react-query over ../../api/client).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { get, post, query } from "../../api/client";
import type { AgentJob, AgentOverview } from "../../api/types";
import type { ProviderCard } from "../api";

/** Refresh these areas after a change. */
function useRefresh() {
  const client = useQueryClient();
  return (...areas: unknown[][]) => Promise.all(areas.map((key) => client.invalidateQueries({ queryKey: key })));
}

// ------------------------------------------------------------------ the knowledge agent

/** The agent's page, with the card of what it runs on (routes/agent.py adds `provider`). */
export type AgentPage = AgentOverview & { provider?: ProviderCard };

export const useAgentPage = () =>
  useQuery({
    queryKey: ["brain", "agent"],
    queryFn: () => get<AgentPage>("/api/brain/agent"),
    refetchInterval: (q) => (q.state.data?.working?.length ? 4000 : false),
  });

/** The agent's work since the app started, newest first; looked at again while one runs. */
export const useAgentJobs = () =>
  useQuery({
    queryKey: ["brain", "agent", "jobs"],
    queryFn: () => get<AgentJob[]>("/api/brain/agent/jobs"),
    refetchInterval: (q) => ((q.state.data ?? []).some((j) => j.status === "waiting" || j.status === "running") ? 2000 : false),
  });

/** Start one upkeep action by hand; it runs in the background through the chosen model. */
export function useStartAction() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (action: string) => post<AgentJob>(`/api/brain/agent/actions/${encodeURIComponent(action)}`, {}),
    onSuccess: () => refresh(["brain", "agent"]),
  });
}

/** The knowledge agent's skills and the release each belongs to (the v4 skill list). An
 * action run by hand is named by the skill's own name. */
export const AGENT_SKILL_RELEASE: Record<string, string> = {
  "knowledge-agent": "Release 1",
  teach: "Release 1",
  "wrap-up": "Release 1",
  "distill-capture": "Release 1",
  "judge-clash": "Release 1",
  "sort-notes": "Release 1",
  "check-drift": "Release 1 · run by hand",
  "tidy-repeats": "Release 1 · run by hand",
  "freshen-up": "Release 1 · run by hand",
  "check-goal-fit": "Release 1 · run by hand",
  "fill-gaps": "Release 1 · run by hand",
  "tidy-projects": "Release 1 · run by hand",
  "tidy-skills": "Release 1 · run by hand",
  "tend-sheets": "Release 1 · run by hand",
  "check-alignment": "Release 1 · run by hand",
  "goals-interview": "Release 1 · optional",
  "scheduled-run": "Later · Release 2",
  "pull-from-tools": "Later · Release 2",
  "verify-sources": "Later · Release 2",
  "distill-taste": "Later · Release 2",
  "learn-from-decisions": "Later · Release 2",
  "measure-goals": "Later · Release 2",
  "build-component": "Later · Release 3",
};

export const isLater = (name: string) => (AGENT_SKILL_RELEASE[name] ?? "").startsWith("Later");

// ------------------------------------------------------------------ CLIs on this computer

/** Open a terminal where the person signs in to a CLI; the CLI keeps the login. */
export function useRunnerSignIn() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (id: string) => post<{ opened: boolean; command: string }>(`/api/runners/${encodeURIComponent(id)}/sign-in`),
    onSuccess: () => refresh(["runners"], ["brain", "agent"]),
  });
}

// ------------------------------------------------------------------ agent profiles

export function useCreateProfile() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (body: { name: string; role: string; prompt: string; runner?: string }) => post<Record<string, unknown>>("/api/agents", body),
    onSuccess: () => refresh(["work-agents"]),
  });
}

export function useAskProfile() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ name, ask }: { name: string; ask: string }) =>
      post<{ id: string; title?: string }>(`/api/agents/${encodeURIComponent(name)}/run`, { ask }),
    onSuccess: () => refresh(["work-agents"], ["tasks"]),
  });
}

// ------------------------------------------------------------------ Test the Brain

const TTB = "/api/test-the-brain";
const ttbKey = ["test-the-brain"];

export interface TtbBar {
  op: string;
  value: number;
}

export interface TtbRunKind {
  id: string;
  name: string;
  covers: string;
  paid: boolean;
  estimate?: { usd?: number | null; seconds?: number | null; calls?: number | null } | null;
  last?: { run?: string; at?: string } | null;
}

export interface TtbActive {
  run: string | null;
  kind: string | null;
  state: string;
  message: string;
  started_at?: string;
}

export interface TtbReady {
  suite: string;
  state: string;
  note?: string;
}

export interface TtbState {
  source: "lab" | "builtin";
  lab: { name: string | null; folder: string } | null;
  error: string | null;
  status: { run_kinds?: TtbRunKind[]; ready?: TtbReady[] } | null;
  running: TtbActive | null;
  builtin?: { name: string; reads_brain: string; waits: TtbReady[] };
}

export interface TtbPillar {
  id: string;
  name: string;
  total: number;
  measured: number;
  met: number;
  confident: number;
  headline: { id: string; name: string; value: number; ci: number[] | null; bar: TtbBar | null } | null;
}

export interface TtbOverview {
  source: string;
  pillars: TtbPillar[];
  last: { run: string; kind: string; ended?: string | null; valid: boolean } | null;
}

export interface TtbGate {
  id: string;
  name: string;
  bar: TtbBar | null;
  kind: string;
  value: number | null;
  n: number | null;
  met: boolean | null;
  run: string | null;
}

export interface TtbRun {
  run: string;
  kind: string;
  valid: boolean;
  metrics: number;
  failing: number;
  started?: string | null;
  ended?: string | null;
  note?: string | null;
}

export interface TtbCases {
  total: number;
  cases: { id: string; suite: string; title: string; sensitive: boolean; pass: boolean | null }[];
}

export interface TtbStage {
  id: string;
  name: string;
  state: string;
  in: number | null;
  out: number | null;
  note: string;
}

export interface TtbWatch {
  request: string | null;
  read_only: boolean;
  tokens?: number | null;
  stages: TtbStage[];
  notes: { id: string; title: string; outcome: string; why: string }[];
}

export const useTtbState = () =>
  useQuery({
    queryKey: [...ttbKey, "state"],
    queryFn: () => get<TtbState>(TTB),
    refetchInterval: (q) => (q.state.data?.running ? 1500 : false),
  });

export const useTtbOverview = () => useQuery({ queryKey: [...ttbKey, "overview"], queryFn: () => get<TtbOverview>(`${TTB}/overview`) });

export const useTtbGates = () =>
  useQuery({ queryKey: [...ttbKey, "gates"], queryFn: () => get<{ gates: TtbGate[]; run: string | null }>(`${TTB}/gates`) });

export const useTtbRuns = () => useQuery({ queryKey: [...ttbKey, "runs"], queryFn: () => get<{ runs: TtbRun[] }>(`${TTB}/runs`) });

export const useTtbCases = (run: string | null | undefined) =>
  useQuery({
    queryKey: [...ttbKey, "cases", run],
    queryFn: () => get<TtbCases>(`${TTB}/runs/${encodeURIComponent(run ?? "")}/cases${query({ limit: 100 })}`),
    enabled: Boolean(run),
  });

export function useStartTtb() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (body: { kind: string; confirm?: boolean }) => post<TtbActive>(`${TTB}/runs`, body),
    onSuccess: () => refresh(ttbKey),
  });
}

export function useCancelTtb() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (run: string) => post<TtbActive>(`${TTB}/runs/${encodeURIComponent(run)}/cancel`),
    onSuccess: () => refresh(ttbKey),
  });
}

/** Read only: one request routed on this app's Brain, stage by stage; nothing is recorded. */
export function useTtbWatch() {
  return useMutation({ mutationFn: (request: string) => post<TtbWatch>(`${TTB}/watch`, { request }) });
}
