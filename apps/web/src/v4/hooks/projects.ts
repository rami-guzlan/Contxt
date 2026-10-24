// Projects' data: the Brain's projects (its Focus items), one project's Context, Tasks, Files and
// Outputs. Built like ../api.ts; the older hooks in ../../api/hooks.ts already cover the list,
// one project, progress updates, the packet preview, outputs, skills, agents, live sheets,
// tasks and AI requests, so those are reused as they are.

import { useMutation, useQuery } from "@tanstack/react-query";

import { get, post, put } from "../../api/client";
import type { BrainProjectDetail, HandoffsNow, Note, Task, TaskItem } from "../../api/types";
import { useRefresh } from "../api";

export {
  useAiRequests,
  useBrainPreview,
  useBrainProject,
  useBrainProjects,
  useCreateBrainProject,
  useHandOff,
  useLive,
  useLiveAct,
  useMadeFrom,
  useNotes,
  useOutputs,
  useSkills,
  useUpdateProject,
  useWorkAgents,
} from "../../api/hooks";

/** Every task in a lane list, open ones first, then what was done this week. */
export function flatTasks(now: HandoffsNow | undefined): TaskItem[] {
  if (!now) return [];
  const order = ["waiting_for_you", "working", "blocked", "handed_off", "open"] as const;
  return [...order.flatMap((lane) => now.lanes[lane] ?? []), ...(now.done_this_week ?? [])];
}

/** The Tasks sheet, filtered by project when one is named (the same task IDs everywhere). */
export const useProjectTasks = (project = "") =>
  useQuery({
    queryKey: ["handoffs", "now", { project }],
    queryFn: () => get<HandoffsNow>(`/api/work/handoffs${project ? `?project=${encodeURIComponent(project)}` : ""}`),
  });

/** Change the output a project is chasing. A change says why, and makes an undo point. */
export function useSetObjective(id: string) {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (body: { objective: string; reason: string }) =>
      put<BrainProjectDetail | null>(`/api/brain/projects/${encodeURIComponent(id)}/objective`, body),
    onSuccess: () => refresh("brain", "events"),
  });
}

/** "Tell it about this project": save what was said as a capture linked to the project, then
 * start Distill on it. Proposals wait for review; nothing is kept until the owner keeps it. */
export function useTellProject(project: { id: string; title: string }) {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: async (text: string) => {
      const note = await post<Note>("/api/notes", { title: `About ${project.title}`, body: text });
      await put<Note>(`/api/workspace/${encodeURIComponent(note.id)}/projects`, { projects: [project.id] });
      const task = await post<Task>("/api/brain/distill/requests", {
        item_ids: [note.id],
        guidance: `This capture is about the project ${project.title} (${project.id}). File what lasts with that project.`,
      });
      return { note, task };
    },
    onSuccess: () => refresh("notes", "captures", "brain", "home"),
  });
}

/** Add a task to the project's Tasks sheet, as you. */
export function useAddTask(project: string) {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (title: string) => post<{ task: TaskItem }>("/api/work/handoffs", { new_task: { title, project } }),
    onSuccess: () => refresh("handoffs", "brain", "live"),
  });
}
