// A project's workflows on its Tasks tab (Release 1 plan, section 11): the chains of steps saved
// for this project, each run's steps with what they used, and the owner's yes, stop and retry.

import { useMutation, useQuery } from "@tanstack/react-query";

import { get, post, put } from "../../api/client";
import type { Workflow, WorkflowBudget, WorkflowRun, WorkflowStep } from "../../api/types";
import { useRefresh } from "../api";

export type { Workflow, WorkflowBudget, WorkflowRun, WorkflowStep };

const KEY = "workflows";

/** The workflows saved for this project. */
export const useProjectWorkflows = (project: string) =>
  useQuery({
    queryKey: [KEY, "project", project],
    queryFn: async () => (await get<Workflow[]>("/api/workflows")).filter((w) => w.project === project),
  });

/** A workflow's runs, newest first; polled while one is going. */
export const useWorkflowRuns = (id: string, going: boolean) =>
  useQuery({
    queryKey: [KEY, "runs", id],
    queryFn: () => get<WorkflowRun[]>(`/api/workflows/${encodeURIComponent(id)}/runs`),
    refetchInterval: going ? 4000 : false,
  });

export interface WorkflowDraft {
  name: string;
  project: string;
  steps: WorkflowStep[];
  budget: WorkflowBudget;
}

/** A new workflow, or a change to one (a new revision). */
export function useSaveWorkflow() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ id, draft }: { id?: string; draft: WorkflowDraft }) => {
      const body = { ...draft, schedule: { kind: "manual" }, runner: "claude", output: { kind: "outputs" } };
      return id ? put<Workflow>(`/api/workflows/${encodeURIComponent(id)}`, body) : post<Workflow>("/api/workflows", body);
    },
    onSuccess: () => refresh(KEY),
  });
}

/** Run now, or a run's yes, stop at a gate, stop, or retry of the step that failed. */
export function useWorkflowAct() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ act, id }: { act: "run" | "yes" | "no" | "stop" | "retry"; id: string }) => {
      const run = `/api/workflows/runs/${encodeURIComponent(id)}`;
      if (act === "run") return post<WorkflowRun>(`/api/workflows/${encodeURIComponent(id)}/run`, {});
      if (act === "yes" || act === "no") return post<WorkflowRun>(`${run}/decide`, { go: act === "yes" });
      return post<WorkflowRun>(`${run}/${act}`);
    },
    onSuccess: () => refresh(KEY, "tasks", "work"),
  });
}
