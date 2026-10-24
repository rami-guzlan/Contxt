// Agent orchestrators (AGENTS.md 8b): a project's orchestrators, their runs, the auto sheets,
// Outputs grouped by run, the activity timeline and the owner's yes to a gate. They mirror
// /api/projects/{id}/orchestrators on the server (routes/orchestrators.py).

import { useMutation, useQuery } from "@tanstack/react-query";

import { get, post, put } from "../../api/client";
import { useRefresh } from "../api";

export type WorksBy = "computer" | "mcp" | "files";
export type RunStatus = "running" | "waiting" | "done" | "stopped";
export type AgentState = "queued" | "working" | "waiting" | "reported" | "stopped";

export interface OrchestratorAgent {
  id: string;
  profile: string;
  role: string;
  short: string;
  works_by: WorksBy;
  cli: string;
  model: string;
  tools: string[];
}

export interface RunAgentState {
  state: AgentState;
  shown: AgentState;
  task_id: string | null;
  act_task_id: string | null;
  task_status: string | null;
  note: string | null;
  brief: string | null;
}

export interface TrailItem {
  at: string;
  agent_id: string;
  profile: string;
  short: string;
  output_id: string;
  title: string;
  summary: string;
  sources: string[];
  act: boolean;
}

export interface Gate {
  id: string;
  kind: "spend" | "post" | "customer_facing";
  what: string;
  tools: string[];
  agent_id: string | null;
  profile: string;
  status: "pending" | "approved" | "rejected";
  asked_at: string;
  approve_label: string;
  quote?: string;
}

export interface OrchestratorRun {
  id: string;
  orchestrator_id: string;
  status: RunStatus;
  shown: RunStatus;
  trigger: "gnomon" | "ai";
  asked_by: string;
  steer: string;
  task_id: string | null;
  spec: { name: string; slug: string; goal: string; cli: string; model: string; sheet: string; agents: OrchestratorAgent[] };
  agents: Record<string, RunAgentState>;
  trail: TrailItem[];
  gates: Gate[];
  final: { output_id: string; title: string; summary: string; sources: string[]; at: string } | null;
  note: string;
  started_at: string;
  finished_at: string | null;
}

export interface Orchestrator {
  id: string;
  slug: string;
  name: string;
  goal: string;
  cli: string;
  model: string;
  trigger: "gnomon" | "ai";
  sheet: string;
  agents: OrchestratorAgent[];
  version: number;
  latest_run: OrchestratorRun | null;
}

export interface AgentTask {
  kind: "agent" | "orchestrator";
  title: string;
  profile: string;
  agent_id: string;
  orchestrator_id: string;
  orchestrator: string;
  run_id: string;
  works_by: WorksBy | "";
  cli: string;
  model: string;
  state: AgentState | RunStatus;
  task_id: string | null;
  note: string;
}

export interface CliChoice {
  id: string;
  label: string;
  models: { id: string; label: string }[];
  one_click: boolean;
}

export interface OrchestratorsOverview {
  orchestrators: Orchestrator[];
  agent_tasks: AgentTask[];
  clis: CliChoice[];
  works_by: { id: WorksBy; label: string; line: string }[];
}

export interface TimelineEvent {
  id: string;
  seq: number;
  at: string;
  kind: string;
  who: string;
  text: string;
  meta: string;
  go: string;
  run_id: string;
  orchestrator_id: string;
}

export interface OrchestratorSheet {
  orchestrator_id: string;
  orchestrator: string;
  name: string;
  agents: number;
  columns: string[];
  cells: { what: string; value: string; source: string; agent: string; at: string; run_id: string }[];
}

export interface AgentSpecIn {
  id?: string;
  profile: string;
  new_profile?: boolean;
  role: string;
  works_by: WorksBy;
  cli: string;
  model: string;
  tools: string[];
}

export interface OrchestratorIn {
  name: string;
  goal: string;
  cli: string;
  model: string;
  trigger: "gnomon" | "ai";
  agents: AgentSpecIn[];
  expected_version?: number;
}

const base = (project: string) => `/api/projects/${encodeURIComponent(project)}/orchestrators`;
const KEY = "orchestrators";

const LIVE = 4000; // while a run is going, the page reads it again this often (ms)

/** Whether any of the project's runs is still going (running, or waiting for the owner). */
export const isLive = (data: OrchestratorsOverview | undefined) =>
  (data?.orchestrators ?? []).some((o) => o.latest_run?.shown === "running" || o.latest_run?.shown === "waiting");

export const useOrchestrators = (project: string) =>
  useQuery({
    queryKey: [KEY, project],
    queryFn: () => get<OrchestratorsOverview>(base(project)),
    enabled: !!project,
    refetchInterval: (q) => (isLive(q.state.data) ? LIVE : false),
  });

export const useOrchestratorTimeline = (project: string, live = false) =>
  useQuery({
    queryKey: [KEY, project, "timeline"],
    queryFn: () => get<TimelineEvent[]>(`${base(project)}/timeline`),
    enabled: !!project,
    refetchInterval: live ? LIVE : false,
  });

export const useOrchestratorOutputs = (project: string) =>
  useQuery({ queryKey: [KEY, project, "outputs"], queryFn: () => get<OrchestratorRun[]>(`${base(project)}/outputs`), enabled: !!project });

export const useOrchestratorSheets = (project: string) =>
  useQuery({ queryKey: [KEY, project, "sheets"], queryFn: () => get<OrchestratorSheet[]>(`${base(project)}/sheets`), enabled: !!project });

/** Make an orchestrator, or change one. New agent profiles land in Agents too. */
export function useSaveOrchestrator(project: string) {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ id, spec }: { id?: string; spec: OrchestratorIn }) =>
      id ? put<Orchestrator>(`${base(project)}/${encodeURIComponent(id)}`, spec) : post<Orchestrator>(base(project), spec),
    onSuccess: () => refresh(KEY, "agents"),
  });
}

/** Run now, with an optional steer: the orchestrator's CLI starts on this computer. */
export function useRunOrchestrator(project: string) {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ id, steer }: { id: string; steer: string }) => post<OrchestratorRun>(`${base(project)}/${encodeURIComponent(id)}/run`, { steer }),
    onSuccess: () => refresh(KEY),
  });
}

/** The owner's yes (or no) to what a run waits for. */
export function useDecideGate(project: string) {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ run, gate, approve, quote }: { run: string; gate: string; approve: boolean; quote: string }) =>
      post<{ run: OrchestratorRun; gate: Gate }>(`${base(project)}/runs/${encodeURIComponent(run)}/gates/${encodeURIComponent(gate)}`, {
        decision: approve ? "approve" : "decline",
        quote,
      }),
    onSuccess: () => refresh(KEY),
  });
}
