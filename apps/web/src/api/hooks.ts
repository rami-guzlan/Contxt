// Data hooks over the REST API. Mutations invalidate by area, so every view stays current.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, get, post, put, query } from "./client";
import type {
  BackupFile,
  BackupMade,
  LocalModels,
  AiApp,
  AiRequestFull,
  AiRequests,
  BuiltinSkills,
  CatchUpPlan,
  Comparison,
  DifferenceExample,
  Dictation,
  Goals,
  MadeFrom,
  MoveInKept,
  MoveInKind,
  MoveInPreview,
  Outputs,
  WeekOfUse,
  RelatedInBrain,
  SpeechStatus,
  Actor,
  BrainAttention,
  BrainCatalog,
  BrainCheckpoint,
  BrainConnect,
  BrainDecision,
  BrainEntry,
  BrainEvent,
  BrainFiled,
  BrainFiles,
  BrainFlow,
  BrainGap,
  BrainHistoryRecord,
  BrainHit,
  BrainPolicies,
  BrainPreview,
  BrainProject,
  BrainProjectDetail,
  BrainProposal,
  BrainReview,
  BrainSkillDetail,
  Connection,
  DecisionOutcome,
  DistillRequest,
  DistillSettings,
  EntryUse,
  EntryVersion,
  Home,
  InventoryItem,
  LegacyReport,
  LegacySummary,
  LocalRun,
  Me,
  Note,
  NoteVersion,
  Onboarding,
  Run,
  RunnerStatus,
  SearchResults,
  SetupStep,
  SkillCards,
  SkillRun,
  SkillVersion,
  Task,
  WorkspaceEvent,
} from "./types";

export const keys = {
  me: ["me"] as const,
  home: ["home"] as const,
  catchUp: ["brain", "catch-up"] as const,
  outputs: ["outputs"] as const,
  tasks: ["tasks"] as const,
  events: ["events"] as const,
  actors: ["actors"] as const,
  brain: ["brain"] as const,
  notes: ["notes"] as const,
  onboarding: ["onboarding"] as const,
  legacy: ["legacy"] as const,
  skills: ["skills"] as const,
};

export function useInvalidate() {
  const client = useQueryClient();
  return (...areas: (readonly string[])[]) =>
    Promise.all(areas.map((area) => client.invalidateQueries({ queryKey: area })));
}

export const useMe = () => useQuery({ queryKey: keys.me, queryFn: () => get<Me>("/api/me"), retry: false });
/** The workspace and what waits for the person: what the navigation shows on every page. */
export const useHome = () => useQuery({ queryKey: keys.home, queryFn: () => get<Home>("/api/home") });
export const useSearch = (q: string) =>
  useQuery({
    queryKey: ["search", q],
    queryFn: () => get<SearchResults>(`/api/search${query({ q })}`),
    enabled: q.trim().length > 1,
  });

// ---- AI work the app started

export const useTask = (id: string | undefined) =>
  useQuery({ queryKey: [...keys.tasks, id], queryFn: () => get<Task>(`/api/tasks/${id}`), enabled: !!id });
export const useTaskRuns = (id: string | undefined) =>
  useQuery({ queryKey: [...keys.tasks, id, "runs"], queryFn: () => get<Run[]>(`/api/tasks/${id}/runs`), enabled: !!id });

/** Stop AI work that has not finished: a request still waiting, or one a model holds. */
export function useCancelTask() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: string) => post<Task>(`/api/tasks/${encodeURIComponent(id)}/cancel`, { reason: "" }),
    onSettled: () => invalidate(keys.tasks, keys.notes, keys.brain, keys.home),
  });
}

export const useEvents = (params: { subject_id?: string; include_noise?: boolean; limit?: number } = {}) =>
  useQuery({
    queryKey: [...keys.events, params],
    queryFn: () => get<WorkspaceEvent[]>(`/api/events${query(params)}`),
  });
export const useActors = () => useQuery({ queryKey: keys.actors, queryFn: () => get<Actor[]>("/api/actors") });
/** How each AI app connects to the Brain (a local command beside its folder; no token). */
export const useBrainConnect = () =>
  useQuery({ queryKey: [...keys.brain, "connect"], queryFn: () => get<BrainConnect>("/api/brain/connect") });
export const useProviders = () =>
  useQuery({
    queryKey: ["providers"],
    queryFn: () => get<{ id: string; label: string; transport: string; schedule_hint: string }[]>("/api/providers"),
  });

// ---- the Brain

export const useBrainStatus = () =>
  useQuery({ queryKey: [...keys.brain, "status"], queryFn: () => get<Record<string, unknown>>("/api/brain/status") });
export const useBrainProposals = () =>
  useQuery({ queryKey: [...keys.brain, "proposals"], queryFn: () => get<BrainProposal[]>("/api/brain/proposals") });
export const useBrainSearch = (q: string) =>
  useQuery({
    queryKey: [...keys.brain, "search", q],
    queryFn: () => get<BrainHit[]>(`/api/brain/search${query({ q })}`),
    enabled: q.trim().length > 1,
  });
export const useBrainCatalog = () =>
  useQuery({ queryKey: [...keys.brain, "catalog"], queryFn: () => get<BrainCatalog>("/api/brain/catalog") });
export const useBrainEntry = (id: string) =>
  useQuery({
    queryKey: [...keys.brain, "entry", id],
    queryFn: () => get<BrainEntry>(`/api/brain/entries/${encodeURIComponent(id)}`),
    enabled: !!id,
  });
export const useBrainHistory = (id: string) =>
  useQuery({
    queryKey: [...keys.brain, "entry", id, "history"],
    queryFn: () => get<BrainHistoryRecord[]>(`/api/brain/entries/${encodeURIComponent(id)}/history`),
    enabled: !!id,
  });
export const useBrainFiles = () =>
  useQuery({ queryKey: [...keys.brain, "files"], queryFn: () => get<BrainFiles>("/api/brain/files") });

// ---- projects: the work the Brain follows across conversations

/** Every project the Brain follows, active first. */
export const useBrainProjects = () =>
  useQuery({ queryKey: [...keys.brain, "projects"], queryFn: () => get<BrainProject[]>("/api/brain/projects") });

/** One project in full: its brief, where it stands, its progress, its files and notes. */
export const useBrainProject = (id: string) =>
  useQuery({
    queryKey: [...keys.brain, "projects", id],
    queryFn: () => get<BrainProjectDetail>(`/api/brain/projects/${encodeURIComponent(id)}`),
    enabled: !!id,
  });

/** Start a project in the Brain: its name, what it is for, the names you will call it by. */
export function useCreateBrainProject() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { name: string; summary: string; aliases: string[] }) =>
      post<BrainProject>("/api/brain/projects", body),
    onSuccess: () => invalidate(keys.brain, keys.events, keys.onboarding),
  });
}

/** Record progress on a project: one line on what happened, and what changed in where it stands. */
export function useUpdateProject(id: string) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { summary: string; state: Record<string, string> }) =>
      post<Record<string, unknown>>(`/api/brain/projects/${encodeURIComponent(id)}/updates`, body),
    onSuccess: () => invalidate(keys.brain, keys.events),
  });
}

export interface FileInput {
  file: File;
  title?: string;
  description?: string;
  topic?: string;
  project?: string;
  status?: string;
}

/** File a document or asset in the Brain, in a project when one is named. */
export function useFileInBrain() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (input: FileInput) => {
      const form = new FormData();
      form.set("file", input.file);
      for (const key of ["title", "description", "topic", "project", "status"] as const) {
        const value = input[key];
        if (value) form.set(key, value);
      }
      return api<BrainFiled>("/api/brain/files", { method: "POST", form });
    },
    onSuccess: () => invalidate(keys.brain, keys.home, keys.events, keys.onboarding),
  });
}

/** What an AI would be handed for a request, recording nothing. */
export const useBrainPreview = (request: string, project = "") =>
  useQuery({
    queryKey: [...keys.brain, "preview", request, project],
    queryFn: () =>
      get<BrainPreview>(
        `/api/brain/preview?request=${encodeURIComponent(request)}` +
          (project ? `&project=${encodeURIComponent(project)}` : ""),
      ),
    enabled: request.trim().length > 0,
    staleTime: 30_000,
  });
export const useBrainSkill = (name: string) =>
  useQuery({
    queryKey: [...keys.brain, "skill", name],
    queryFn: () => get<BrainSkillDetail>(`/api/brain/skills/${encodeURIComponent(name)}`),
    enabled: !!name,
  });
/** Clashes, near twins, misplaced text, entries to re-check, and use this week. */
export const useBrainAttention = () =>
  useQuery({ queryKey: [...keys.brain, "attention"], queryFn: () => get<BrainAttention>("/api/brain/attention") });

/** Everything waiting, in batches, each proposal with what approving it would change. */
export const useBrainReview = () =>
  useQuery({ queryKey: [...keys.brain, "review"], queryFn: () => get<BrainReview>("/api/brain/review") });
export const useBrainCheckpoints = () =>
  useQuery({ queryKey: [...keys.brain, "checkpoints"], queryFn: () => get<BrainCheckpoint[]>("/api/brain/checkpoints") });

// ---- the context supply chain

/** Every entry (live and archived), skill and filed document, with details, changes and use. */
export const useBrainInventory = () =>
  useQuery({ queryKey: [...keys.brain, "inventory"], queryFn: () => get<InventoryItem[]>("/api/brain/inventory") });
export const useEntryDetails = (id: string) =>
  useQuery({
    queryKey: [...keys.brain, "entry", id, "details"],
    queryFn: () => get<InventoryItem>(`/api/brain/entries/${encodeURIComponent(id)}/details`),
    enabled: !!id,
  });
/** Every version of an entry, newest first; with `text`, each with its full text. */
export const useEntryVersions = (id: string, text = false) =>
  useQuery({
    queryKey: [...keys.brain, "entry", id, "versions", text],
    queryFn: () => get<EntryVersion[]>(`/api/brain/entries/${encodeURIComponent(id)}/versions${query({ text: text || undefined })}`),
    enabled: !!id,
  });
export const useEntryUse = (id: string) =>
  useQuery({
    queryKey: [...keys.brain, "entry", id, "use"],
    queryFn: () => get<EntryUse>(`/api/brain/entries/${encodeURIComponent(id)}/use`),
    enabled: !!id,
  });

export interface ActivityFilters {
  entry?: string;
  since?: string;
  until?: string;
  action?: string[];
  by?: string;
  limit?: number;
}
export const useBrainActivity = (filters: ActivityFilters = {}) =>
  useQuery({
    queryKey: [...keys.brain, "activity", filters],
    queryFn: () => get<BrainEvent[]>(`/api/brain/activity${query({ ...filters })}`),
  });
export const useBrainFlow = (days = 7) =>
  useQuery({ queryKey: [...keys.brain, "flow", days], queryFn: () => get<BrainFlow>(`/api/brain/flow${query({ days })}`) });
export const useBrainGaps = (days = 30) =>
  useQuery({ queryKey: [...keys.brain, "gaps", days], queryFn: () => get<BrainGap[]>(`/api/brain/gaps${query({ days })}`) });
export const useBrainPolicies = () =>
  useQuery({ queryKey: [...keys.brain, "policies"], queryFn: () => get<BrainPolicies>("/api/brain/policies") });

export function useSetBrainPolicies() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (changes: Partial<BrainPolicies>) =>
      put<{ status: string; policy: BrainPolicies; checkpoint: BrainCheckpoint | null }>("/api/brain/policies", changes),
    onSettled: () => invalidate(keys.brain, keys.events),
  });
}

export function useDismissGap() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (key: string) => post<null>("/api/brain/gaps/dismiss", { key }),
    onSettled: () => invalidate(keys.brain),
  });
}

/** Propose a new entry in a person's own words; it waits in Review like every proposal. */
export function useProposeEntry() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { title: string; statement: string; kind?: string; evidence?: string; topic?: string; origin?: string }) =>
      post<{ status: string; message: string; proposal_id: string | null }>("/api/brain/proposals", body),
    onSettled: () => invalidate(keys.brain, keys.home),
  });
}

/** Decide many proposals (and change entries) at once; the answer names the undo point. */
export function useBrainDecisions() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { decisions: BrainDecision[]; label?: string; source?: Record<string, string | number> }) =>
      post<DecisionOutcome>("/api/brain/decisions", body),
    onSettled: () => invalidate(keys.brain, keys.home, keys.events, keys.tasks, keys.notes),
  });
}

/** Take one batch of decisions back (an undo point's own undo redoes it). */
export function useBrainUndo() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (checkpointId: string) =>
      post<{ undone: string; checkpoint: BrainCheckpoint | null }>(
        `/api/brain/checkpoints/${encodeURIComponent(checkpointId)}/undo`,
      ),
    onSettled: () => invalidate(keys.brain, keys.home, keys.events, keys.tasks, keys.notes, keys.onboarding),
  });
}

/** Where the Brain serves a file from; `original` asks for a reference's source document. */
export function brainFileUrl(path: string, original = false): string {
  return `/api/brain/files/content${query({ path, original: original || undefined })}`;
}

// ---- AI work: finding what to remember, and which model does it

export const useDistillRequests = (itemId?: string) =>
  useQuery({
    queryKey: [...keys.brain, "distill", "requests", itemId ?? "all"],
    queryFn: () => get<DistillRequest[]>(`/api/brain/distill/requests${query({ item_id: itemId })}`),
    // Follow a request while a model works on it.
    refetchInterval: (q) =>
      (q.state.data ?? []).some((r) => ["ready", "claimed", "in_progress"].includes(r.status)) ? 4_000 : false,
  });
export const useDistillSettings = () =>
  useQuery({
    queryKey: [...keys.brain, "distill", "settings"],
    queryFn: () => get<DistillSettings>("/api/brain/distill/settings"),
  });
export function useSetDistillSettings() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: DistillSettings) => put<DistillSettings>("/api/brain/distill/settings", body),
    onSettled: () => invalidate(keys.brain),
  });
}

export const runnerKeys = ["runners"] as const;

/** The CLIs on the computer the workspace runs on: installed, signed in, ready to run. */
export const useRunners = () =>
  useQuery({ queryKey: runnerKeys, queryFn: () => get<RunnerStatus[]>("/api/runners"), staleTime: 15_000 });

/** Ask again, skipping the server's short cache (after installing or signing in). */
export function useCheckRunners() {
  const client = useQueryClient();
  return async () => {
    const fresh = await get<RunnerStatus[]>("/api/runners?refresh=true");
    client.setQueryData(runnerKeys, fresh);
    return fresh;
  };
}

/** What runs here now and what finished lately, for the AI work tray: looked at often while
 * something runs, now and then otherwise. */
export const useRecentRuns = () =>
  useQuery({
    queryKey: [...runnerKeys, "recent"],
    queryFn: () => get<LocalRun[]>("/api/runners/runs"),
    refetchInterval: (q) => ((q.state.data ?? []).some((r) => ["starting", "running"].includes(r.status)) ? 2000 : 10_000),
  });

/** One run started from the workspace, polled while it is going. */
export const useLocalRun = (id: string | null) =>
  useQuery({
    queryKey: [...runnerKeys, "run", id],
    queryFn: () => get<LocalRun>(`/api/runners/runs/${id}`),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data && !["starting", "running"].includes(q.state.data.status) ? false : 800),
  });

export function useConnect() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { name: string; provider: string; projects?: string[] }) =>
      post<Connection>("/api/connections", body),
    onSuccess: () => invalidate(keys.actors, keys.home, keys.onboarding),
  });
}

// ---- skills: run one, improve one, write a new one

const skillPath = (name: string) => `/api/skills/${encodeURIComponent(name)}`;

export const useSkills = () => useQuery({ queryKey: keys.skills, queryFn: () => get<SkillCards>("/api/skills") });

/** A skill's runs and drafts; looked at again while one is still going. */
export const useSkillRuns = (name: string) =>
  useQuery({
    queryKey: [...keys.skills, name, "runs"],
    queryFn: () => get<SkillRun[]>(`${skillPath(name)}/runs`),
    enabled: !!name,
    refetchInterval: (q) =>
      (q.state.data ?? []).some((r) => ["ready", "claimed", "in_progress"].includes(r.status)) ? 4000 : false,
  });

export const useSkillVersions = (name: string, text = false) =>
  useQuery({
    queryKey: [...keys.skills, name, "versions", text],
    queryFn: () => get<SkillVersion[]>(`${skillPath(name)}/versions${query({ text: text || undefined })}`),
    enabled: !!name,
  });

export function useRunSkill() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ name, ...body }: { name: string; ask: string; capture_id?: string; project?: string; files?: string[] }) =>
      post<Task>(`${skillPath(name)}/runs`, body),
    onSettled: () => invalidate(keys.skills, keys.tasks),
  });
}

/** A run from the Skills page: the skills chosen, followed in order (none: the one that fits). */
export function useRunSkills() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { names: string[]; ask: string; capture_id?: string; project?: string; files?: string[] }) =>
      post<Task>("/api/skills/runs", body),
    onSettled: () => invalidate(keys.skills, keys.tasks),
  });
}

/** The latest runs from the Skills page and every skill; looked at again while one goes. */
export const useLatestSkillRuns = (limit = 5) =>
  useQuery({
    queryKey: [...keys.skills, "latest-runs", limit],
    queryFn: () => get<SkillRun[]>(`/api/skills/runs${query({ limit })}`),
    refetchInterval: (q) =>
      (q.state.data ?? []).some((r) => ["ready", "claimed", "in_progress"].includes(r.status)) ? 4000 : false,
  });

export function useImproveSkill() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ name, ...body }: { name: string; ask: string; capture_id?: string; example?: string }) =>
      post<Task>(`${skillPath(name)}/improve`, body),
    onSettled: () => invalidate(keys.skills, keys.tasks),
  });
}

export function useDraftSkill() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { ask: string; capture_id?: string }) => post<Task>("/api/skills/drafts", body),
    onSettled: () => invalidate(keys.skills, keys.tasks),
  });
}

/** The person's own new version of a skill: it applies at once, with an undo point. */
export function useEditSkill() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({
      name,
      ...body
    }: {
      name: string;
      body: string;
      description?: string;
      when_to_use?: string;
      triggers?: string[];
      reason?: string;
    }) => put<{ message?: string; checkpoint: BrainCheckpoint | null }>(skillPath(name), body),
    onSettled: () => invalidate(keys.skills, keys.brain, keys.events),
  });
}

/** One file a skill run made, to download (or open in place). */
export function skillFileUrl(taskId: string, name: string, download = true): string {
  const file = name.split("/").map(encodeURIComponent).join("/");
  return `/api/skills/runs/${encodeURIComponent(taskId)}/files/${file}${download ? "" : "?download=false"}`;
}

// ---- notes: the person's scratchpad

/** Is this note still being turned into text? Lists and pages look again until it is. */
export const transcribing = (note: Note | undefined) =>
  note?.transcription?.state === "pending" || note?.transcription?.state === "working";

export const useNotes = (archived = false) =>
  useQuery({
    queryKey: [...keys.notes, "list", archived],
    queryFn: () => get<Note[]>(`/api/notes${query({ archived: archived || undefined })}`),
    refetchInterval: (q) => ((q.state.data ?? []).some(transcribing) ? 3000 : false),
  });
export const useNote = (id: string) =>
  useQuery({
    queryKey: [...keys.notes, "item", id],
    queryFn: () => get<Note>(`/api/notes/${encodeURIComponent(id)}`),
    enabled: !!id,
    // What is open is the person's; refetching it under them would fight their typing. A
    // capture being transcribed cannot be typed in, so it is looked at until its text is in.
    refetchOnWindowFocus: false,
    refetchInterval: (q) =>
      transcribing(q.state.data) ? 2000 : ["queued", "waiting"].includes(q.state.data?.digest?.state ?? "") ? 5000 : false,
  });
export const useNoteVersions = (id: string) =>
  useQuery({
    queryKey: [...keys.notes, "item", id, "versions"],
    queryFn: () => get<NoteVersion[]>(`/api/notes/${encodeURIComponent(id)}/versions`),
    enabled: !!id,
  });

export function useCreateNote() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { title?: string; body?: string }) => post<Note>("/api/notes", body),
    onSettled: () => invalidate(keys.notes, keys.events),
  });
}

/** Save what is open. The caller keeps the returned version to send with the next save. */
export const saveNote = (id: string, body: { title?: string; body?: string; expected_version?: number }) =>
  put<Note>(`/api/notes/${encodeURIComponent(id)}`, body);

export function useNoteAction() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, action, body }: { id: string; action: "name" | "restore" | "archive" | "unarchive"; body?: unknown }) =>
      post<Note>(`/api/notes/${encodeURIComponent(id)}/${action}`, body ?? {}),
    onSettled: () => invalidate(keys.notes, keys.events),
  });
}

/** Add a note to the Brain as a document, as it reads now, in a project when one is named. */
export function useNoteToBrain() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; project?: string; status?: string }) =>
      post<BrainFiled>(`/api/notes/${encodeURIComponent(id)}/brain`, body),
    onSettled: () => invalidate(keys.brain, keys.events, keys.home, keys.onboarding),
  });
}

/** Ask a model to find what in a note should last, as proposals for the Brain. */
export function useRememberNote() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; assignee_id?: string | null; guidance?: string }) =>
      post<Task>(`/api/notes/${encodeURIComponent(id)}/remember`, body),
    onSettled: () => invalidate(keys.brain, keys.tasks, keys.events),
  });
}

export const noteDownloadUrl = (id: string) => `/api/notes/${encodeURIComponent(id)}/download`;

// ---- captures: talk, recordings, transcripts and documents brought in

/** Bring in a file: audio (turned into text on this computer), a transcript or a document. */
export function useBringIn() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ file, title }: { file: File; title?: string }) => {
      const form = new FormData();
      form.set("file", file);
      if (title) form.set("title", title);
      return api<Note>("/api/captures", { method: "POST", form });
    },
    onSettled: () => invalidate(keys.notes, keys.events, keys.home),
  });
}

/** What the person just said, recorded in the browser. */
export function useTalkUpload() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (audio: Blob) => {
      const form = new FormData();
      form.set("audio", audio, audio.type.includes("mp4") ? "talk.m4a" : "talk.webm");
      return api<Note>("/api/captures/talk", { method: "POST", form });
    },
    onSettled: () => invalidate(keys.notes, keys.events, keys.home),
  });
}

export function useRetryCapture() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: string) => post<Note>(`/api/captures/${encodeURIComponent(id)}/retry`),
    onSettled: () => invalidate(keys.notes),
  });
}

/** What the Brain already holds that a capture touches, found by meaning. */
export const useCaptureRelated = (id: string, enabled = true) =>
  useQuery({
    queryKey: [...keys.notes, "item", id, "related"],
    queryFn: () => get<RelatedInBrain[]>(`/api/captures/${encodeURIComponent(id)}/related`),
    enabled: !!id && enabled,
  });

/** Ask a model for a capture's summary and key points. */
export function useSummarize() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, guidance }: { id: string; guidance?: string }) =>
      post<Task>(`/api/captures/${encodeURIComponent(id)}/summarize`, { guidance: guidance ?? "" }),
    onSettled: () => invalidate(keys.notes, keys.tasks),
  });
}

export const useCaptureSettings = () =>
  useQuery({ queryKey: [...keys.notes, "settings"], queryFn: () => get<{ summarize: boolean }>("/api/captures/settings") });

export function useSetCaptureSettings() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { summarize: boolean }) => put<{ summarize: boolean }>("/api/captures/settings", body),
    onSettled: () => invalidate(keys.notes),
  });
}

export const captureOriginalUrl = (id: string, download = false) =>
  `/api/captures/${encodeURIComponent(id)}/original${download ? "?download=true" : ""}`;

export const useSpeech = () =>
  useQuery({
    queryKey: ["speech"],
    queryFn: () => get<SpeechStatus>("/api/speech"),
    refetchInterval: (q) => (q.state.data?.downloading ? 3000 : false),
  });

/** Fetch the speech model, once: the person's call, never automatic. */
export function useDownloadSpeech() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: () => post<SpeechStatus>("/api/speech/download"),
    onSettled: () => invalidate(["speech"]),
  });
}

// ---- first-time setup

export const useOnboarding = (enabled = true) =>
  useQuery({ queryKey: keys.onboarding, queryFn: () => get<Onboarding>("/api/onboarding"), enabled });

/** Keep a moment of the setup: finished, put aside (false brings it back), the tour taken, or a
 * step said to be done as it stands. */
export function useMarkOnboarding() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { completed?: boolean; dismissed?: boolean; tour_seen?: boolean; step?: SetupStep }) =>
      post<Record<string, unknown>>("/api/onboarding", body),
    onSettled: () => invalidate(keys.onboarding),
  });
}

/** A person's (or model's) display name: the owner's own name instead of "Owner". */
export function useRenameActor() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => put<Actor>(`/api/actors/${encodeURIComponent(id)}`, { name }),
    onSettled: () => invalidate(keys.actors, keys.me, keys.onboarding, keys.home),
  });
}

// ---- the earlier workspace: copied out as files, its context moved into the Brain

export const useLegacy = () => useQuery({ queryKey: keys.legacy, queryFn: () => get<LegacySummary>("/api/legacy") });

export function useExportLegacy() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: () => post<{ dir: string; files: number }>("/api/legacy/export"),
    onSettled: () => invalidate(keys.legacy),
  });
}

export function useBringLegacyIn() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: () => post<LegacyReport>("/api/legacy/bring-into-brain"),
    onSettled: () => invalidate(keys.legacy, keys.brain, keys.home, keys.events, keys.onboarding),
  });
}

// ---- catch up: a plan, never a pile

/** What needs the person, in tiers, with a time estimate; and how the Brain is doing. */
export const useCatchUp = () => useQuery({ queryKey: keys.catchUp, queryFn: () => get<CatchUpPlan>("/api/brain/catch-up") });

/** The person caught up: the next recap starts from now. */
export function useCatchUpSeen() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: () => post<Record<string, unknown>>("/api/brain/catch-up/seen"),
    onSettled: () => invalidate(keys.catchUp),
  });
}

/** Later (a few days), or set aside (for good, or for `days`). */
export function useSetAside() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ key, later, days }: { key: string; later?: boolean; days?: number }) =>
      post<Record<string, unknown>>(`/api/brain/catch-up/${later ? "snooze" : "dismiss"}`, { key, days }),
    onSettled: () => invalidate(keys.catchUp),
  });
}

/** Two notes that say the same: keep one, and a model writes them as one for review. */
export function useMerge() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { keep_id: string; other_id: string }) => post<Task>("/api/brain/merge", body),
    onSettled: () => invalidate(keys.brain, keys.tasks),
  });
}

// ---- what the Brain is for, and the skills every Brain comes with

export const useGoals = () => useQuery({ queryKey: [...keys.brain, "goals"], queryFn: () => get<Goals>("/api/brain/goals") });

/** The owner's own words: they go straight in, as one undo point. */
export function useSetGoals() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (answers: Record<string, string>) => put<Goals>("/api/brain/goals", { answers }),
    onSettled: () => invalidate(keys.brain, keys.onboarding, keys.events),
  });
}

/** One follow-up on an answer, from Claude Code on this computer; none when it is specific. */
export function useGoalFollowup() {
  return useMutation({
    mutationFn: (body: { question: string; answer: string }) =>
      post<{ followup: string | null }>("/api/brain/goals/followup", body),
  });
}

export const useBuiltinSkills = () =>
  useQuery({ queryKey: [...keys.brain, "builtin-skills"], queryFn: () => get<BuiltinSkills>("/api/brain/builtin-skills") });

export function useAddBuiltinSkills() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (names?: string[]) => post<BuiltinSkills>("/api/brain/builtin-skills", { names: names ?? null }),
    onSettled: () => invalidate(keys.brain, keys.skills, keys.events),
  });
}

// ---- moving in: what your AIs already know

export interface MoveInSource {
  kind: MoveInKind;
  text: string;
  label?: string;
}

/** Read the sources into ideas, checked against the Brain and sifted; writes nothing. */
export function useMoveInPreview() {
  return useMutation({
    mutationFn: (sources: MoveInSource[]) => post<MoveInPreview>("/api/brain/move-in/preview", { sources }),
  });
}

/** Suggest the ideas chosen (none named: the ones that fit); they wait in Catch up. */
export function useMoveInKeep() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ sources, ids }: { sources: MoveInSource[]; ids?: string[] }) =>
      post<MoveInKept>("/api/brain/move-in", { sources, ids: ids ?? null }),
    onSettled: () => invalidate(keys.brain, keys.home, keys.events),
  });
}

// ---- activity: what each AI asked and got

export const useAiRequests = (params: { limit?: number; before?: string; app?: string } = {}, watch = false) =>
  useQuery({
    queryKey: [...keys.brain, "requests", params],
    queryFn: () => get<AiRequests>(`/api/brain/requests${query(params)}`),
    // While the first run waits for the handshake, look again every few seconds.
    refetchInterval: watch ? 3000 : false,
  });

/** One request in full, fetched when its row opens. */
export const useAiRequest = (id: string, enabled = true) =>
  useQuery({
    queryKey: [...keys.brain, "request", id],
    queryFn: () => get<AiRequestFull>(`/api/brain/requests/${encodeURIComponent(id)}`),
    enabled,
    staleTime: 60_000,
  });

export const useWeekly = (weeks = 8) =>
  useQuery({ queryKey: [...keys.brain, "weekly", weeks], queryFn: () => get<WeekOfUse[]>(`/api/brain/weekly${query({ weeks })}`) });

/** The AI apps on this computer: found, connected, and their last request. */
export const useAiApps = (watch = false) =>
  useQuery({
    queryKey: [...keys.brain, "apps"],
    queryFn: () => get<AiApp[]>("/api/brain/apps"),
    // While the first run waits for the handshake, look again every few seconds.
    refetchInterval: watch ? 3000 : false,
  });

/** Add the Brain to one app's settings, after the person's yes (a backup is made first). */
export function useConnectApp() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (client: string) =>
      post<{ client: string; connected: boolean; changed: boolean; backup: string | null }>(
        `/api/brain/apps/${encodeURIComponent(client)}/connect`,
        { confirm: true },
      ),
    onSettled: () => invalidate(keys.brain, keys.onboarding),
  });
}

// ---- see the difference

export function useStartDifference() {
  return useMutation({
    mutationFn: (body: { request: string; project?: string }) => post<Comparison>("/api/brain/difference", body),
  });
}

export const useDifference = (id: string | null) =>
  useQuery({
    queryKey: [...keys.brain, "difference", id],
    queryFn: () => get<Comparison>(`/api/brain/difference/${encodeURIComponent(id ?? "")}`),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data && q.state.data.status !== "running" ? false : 2000),
  });

/** The before and after pairs a demo Brain keeps. */
export const useExamples = () =>
  useQuery({ queryKey: [...keys.brain, "examples"], queryFn: () => get<DifferenceExample[]>("/api/brain/examples") });

// ---- the outputs folder

export const useOutputs = () => useQuery({ queryKey: keys.outputs, queryFn: () => get<Outputs>("/api/outputs") });

export const useMadeFrom = (path: string | null) =>
  useQuery({
    queryKey: [...keys.outputs, "made-from", path],
    queryFn: () => get<MadeFrom>(`/api/outputs/made-from${query({ path: path ?? "" })}`),
    enabled: !!path,
  });

export function useMakeOutputFolder() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (path: string) => post<{ path: string }>("/api/outputs/folders", { path }),
    onSettled: () => invalidate(keys.outputs),
  });
}

/** Move or rename one file inside the outputs folder, never over another. */
export function useMoveOutput() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { source: string; target: string }) => post<{ path: string }>("/api/outputs/move", body),
    onSettled: () => invalidate(keys.outputs),
  });
}

export const outputFileUrl = (path: string, download = true) =>
  `/api/outputs/file${query({ path, download: download ? undefined : false })}`;

// ---- the knowledge agent on documents in the Brain, and dictation

/** Pull what matters from captures or from documents filed in the Brain. */
export function useRequestPull() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { item_ids?: string[]; paths?: string[]; guidance?: string }) =>
      post<Task>("/api/brain/distill/requests", { item_ids: [], paths: [], ...body }),
    onSettled: () => invalidate(keys.brain, keys.tasks, keys.notes),
  });
}

/** What the person just said, as text for the field they fill in; nothing is kept. */
export function useDictate() {
  return useMutation({
    mutationFn: (audio: Blob) => {
      const form = new FormData();
      form.set("audio", audio, audio.type.includes("mp4") ? "dictation.m4a" : "dictation.webm");
      return api<Dictation>("/api/speech/transcribe", { method: "POST", form });
    },
  });
}

// ---- this computer: the matching model, and backups

export const useModels = () =>
  useQuery({
    queryKey: [...keys.brain, "models"],
    queryFn: () => get<LocalModels>("/api/brain/models"),
    refetchInterval: (q) => (q.state.data?.matching.downloading ? 3000 : false),
  });

/** Fetch the model that matches by meaning, once: the person's call, never automatic. */
export function useDownloadModels() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: () => post<LocalModels>("/api/brain/models/download"),
    onSettled: () => invalidate([...keys.brain, "models"]),
  });
}

export const useBackups = () => useQuery({ queryKey: ["backups"], queryFn: () => get<BackupFile[]>("/api/backups") });

export function useMakeBackup() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: () => post<BackupMade>("/api/backups"),
    onSettled: () => invalidate(["backups"]),
  });
}

export const backupUrl = (name: string) => `/api/backups/${encodeURIComponent(name)}`;

