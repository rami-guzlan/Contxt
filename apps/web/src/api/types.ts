// Mirrors of the records the server returns (packages/core domain/records.py).

export type TaskStatus =
  | "draft"
  | "ready"
  | "claimed"
  | "in_progress"
  | "review"
  | "done"
  | "blocked"
  | "failed"
  | "cancelled"
  | "archived";

export interface WorkspaceInfo {
  id: string;
  name: string;
  timezone: string;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  version: number;
}

export interface Actor {
  id: string;
  kind: "human" | "model" | "system";
  name: string;
  provider: string | null;
  description: string | null;
  last_seen_at: string | null;
  disabled_at: string | null;
  created_at: string;
  updated_at: string;
  version: number;
}

export interface Credential {
  id: string;
  actor_id: string;
  token_hint: string;
  label: string | null;
  actions: string[];
  projects: string[] | null;
  created_by: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

interface Tracked {
  created_by: string;
  created_at: string;
  updated_at: string;
  version: number;
  archived_at: string | null;
}

export interface Schedule {
  kind: "manual" | "once" | "daily" | "weekly" | "monthly";
  at?: string;
  time?: string;
  days?: string[];
  day?: number;
}

export interface OutputContract {
  artifacts: { type: string; count?: number; notes?: string }[];
  notes?: string;
}

export interface Task extends Tracked {
  id: string;
  project_id: string | null;
  title: string;
  purpose: string;
  instructions: string;
  prompt_version: number;
  assignee_id: string | null;
  schedule: Schedule;
  timezone: string;
  next_due_at: string | null;
  output_contract: OutputContract;
  review_policy: "required" | "auto";
  brain_request: string | null;
  status: TaskStatus;
  attempts: number;
  depends_on: string | null;
  template: string | null;
  current_run_id: string | null;
  revision: number;
  provenance: Record<string, unknown>;
}

export interface Run {
  id: string;
  task_id: string;
  attempt: number;
  occurrence: string;
  status: string;
  actor_id: string;
  task_revision: number;
  claimed_at: string;
  lease_expires_at: string;
  started_at: string | null;
  finished_at: string | null;
  packet: Record<string, unknown>;
  outcome: { result?: string; summary?: string; blocked?: string };
  version: number;
}

export interface WorkspaceEvent {
  seq: number;
  id: string;
  at: string;
  actor_id: string;
  type: string;
  subject_type: string;
  subject_id: string;
  project_id: string | null;
  reason: string | null;
  data: Record<string, unknown>;
  noise: boolean;
}

export interface BrainHit {
  id: string;
  title: string;
  summary: string;
  scope: string;
  kind: string;
  score: number;
}

export interface BrainEntry {
  id: string;
  title: string;
  text: string;
  scope: string;
  kind: string;
  status: string;
  revision: string | null;
  summary: string;
  confidence: string | null;
  verified: string | null;
  stale: boolean;
  stale_reason: string | null;
  source: string | null;
  path: string | null;
}

export interface BrainProposal {
  id: string;
  kind: string;
  scope: string;
  route_key?: string;
  title?: string;
  summary?: string;
  note_summary?: string;
  body?: string;
  proposer?: string;
  created?: string;
  reason?: string;
  similar?: string;
  purpose?: string | null;
  preview?: string | null;
  files?: { path: string; size: number }[];
  current_body?: string | null;
  sources?: string[];
  task_id?: string;
  session?: string;
  target?: Record<string, unknown>;
}

/** A live (or archived) entry a proposal relates to, with its text to compare. */
export interface RelatedEntry {
  id: string;
  title: string;
  summary: string;
  route_key: string;
  live: boolean;
  body: string;
  score?: number;
  close?: boolean; // near enough that it may say the same thing
  missing?: boolean;
}

/** What approving a proposal would change (brainkit review.py). */
export interface ProposalAnalysis {
  id: string;
  kind: string;
  title: string;
  route_key: string;
  placement: "guessed" | "chosen" | string;
  change: "new" | "update" | "retire" | "file" | "skill";
  replaces: RelatedEntry[];
  conflicts: RelatedEntry[];
  overlaps: RelatedEntry[];
  duplicates: { id: string; title: string; score: number }[];
  related: { id: string; title: string; live: boolean }[];
  new_topic: boolean;
  suggested: { topic: string; score: number }[];
  base_changed: boolean;
  problems: string[];
  /** A skill proposal: the skill it makes or changes. */
  skill?: { name: string; category: string; description: string };
  /** A change to a skill: what the skill is now, to compare. */
  skill_before?: { description: string; when_to_use: string; triggers: string[]; body: string };
}

/** A request that a model reconcile a waiting proposal with an entry, and what it suggested. */
export interface Reconciliation {
  task_id: string;
  status: string;
  entry_id: string;
  current: "proposal" | "entry";
  suggestion_ids: string[];
}

export interface ReviewProposal extends BrainProposal {
  analysis: Partial<ProposalAnalysis>;
  reconciliations?: Reconciliation[];
}

export interface ReviewCounts {
  total: number;
  new: number;
  updates: number;
  replaces: number;
  conflicts: number;
  close: number;
  duplicates: number;
  problems: number;
  files: number;
  skills?: number;
  new_topics: number;
  look: number; // something to settle before approving
  clear: number;
}

export interface ReviewBatch {
  key: string;
  title: string;
  proposer: string;
  created: string;
  proposal_ids: string[];
  counts: ReviewCounts;
  topics: { route_key: string; count: number }[];
  task_id: string | null;
  task_status: string | null;
  documents: { id: string; title: string }[];
  reconciles?: { proposal_id: string; entry_id: string; current: "proposal" | "entry" } | null;
}

export interface BrainReview {
  batches: ReviewBatch[];
  proposals: ReviewProposal[];
}

export interface CheckpointDecision {
  action: "approved" | "edited" | "rejected" | "archived" | "reverted" | "redone";
  proposal?: string;
  note?: string;
  kind?: string;
  title?: string;
  superseded?: string[];
  reverted?: string;
  redone?: string;
}

/** An undo point: one batch of decisions, and whether it can be taken back now. */
export interface BrainCheckpoint {
  id: string;
  at: string;
  by: string;
  kind: "decisions" | "undo" | "redo";
  label: string;
  source: Record<string, string>;
  decisions: CheckpointDecision[];
  files: { path: string; before: string | null; after: string | null }[];
  undoes: string | null;
  undone_by: string | null;
  undone_at: string | null;
  blocked?: { path: string; what: string }[];
  undoable?: boolean;
}

export interface BrainDecision {
  action: "approve" | "reject" | "archive" | "edit" | "restore" | "unarchive" | "update" | "verify" | "mark";
  proposal_id?: string;
  entry_id?: string; // every action but approve and reject acts on an entry
  reason?: string;
  replaces?: string[];
  topic?: string;
  title?: string;
  summary?: string;
  body?: string; // approve: file these words instead; edit: the entry's new text
  minor?: boolean; // edit: a typo or cleanup, not new knowledge
  ref?: string; // restore: the version to put back
  fields?: Partial<Record<EntryField, string | null>>; // update: details to set ("" clears)
  state?: "stale" | "disputed"; // mark, with a reason
  confidence?: string; // verify
}

// A project's other names are set on its entry, comma separated.
export type EntryField = "owner" | "review_days" | "review_by" | "classification" | "area" | "topic" | "aliases";

// ---- the context supply chain

export interface EntryOrigin {
  kind: "conversation" | "workspace" | "work" | "file" | "meeting" | "output" | "doc" | "you" | "import" | "unknown";
  ref: string;
  label: string;
}

export interface EntryUses {
  total: number;
  d7: number;
  d30: number;
  last: string | null;
}

/** One row of the Brain's inventory: an entry (live or archived), a skill or a filed document. */
export interface InventoryItem {
  type: "note" | "skill" | "reference";
  id: string;
  title: string;
  summary: string;
  kind: string;
  area: string;
  area_label: string;
  topic: string;
  topic_label: string;
  scope: string;
  partition: string | null;
  status: string;
  live: boolean;
  tokens: number;
  path: string;
  owner: string;
  owner_set: boolean;
  uses: EntryUses;
  // entries only
  load?: string;
  added?: string;
  updated?: string;
  revised?: string;
  verified?: string;
  /** A person confirmed it since it went live, not only approved it. */
  checked?: boolean;
  confidence?: string | null;
  stale?: string | null;
  review_days?: number;
  /** The entry sets its own cadence (else it follows the policy's). */
  review_days_set?: boolean;
  review_by?: string | null;
  review_due?: string | null;
  origin?: EntryOrigin;
  classification?: string;
  supersedes?: string[];
  superseded_by?: string | null;
  changes?: number;
  hash?: string;
}

/** A governed event about an entry (or the policy), from the Brain's decision journal. */
export interface BrainEvent {
  at: string;
  action: string;
  by?: string;
  proposer?: string;
  reason?: string;
  note?: string;
  title?: string;
  proposal?: string;
  kind?: string;
  session?: string;
  state?: string;
  confidence?: string;
  from?: string;
  from_at?: string;
  fields?: Record<string, string>;
  was?: Record<string, unknown>;
  changes?: Record<string, unknown>;
  superseded?: string[];
  superseded_by?: string;
  moved_from?: string;
  minor?: boolean;
  reverted?: string;
  redone?: string;
  checkpoint?: string;
  target_id?: string;
  /** A procedure the event changed (a skill proposal approved or rejected). */
  skill?: string;
  path?: string;
  target_title?: string;
  has_previous?: boolean;
}

export interface EntryVersion {
  ref: string;
  at: string;
  title: string;
  summary: string;
  status: string;
  hash: string;
  chars: number;
  text_changed: boolean;
  current?: boolean;
  committed: boolean;
  commit?: string;
  author?: string;
  message?: string;
  path?: string;
  changes: BrainEvent[];
  body?: string;
}

export interface EntryHandout {
  session_id: string;
  packet_id: string;
  at: string;
  hash: string;
  reason: string | null;
  tokens: number;
  request: string | null;
  mode: string | null;
  via: "packet" | "opened" | "work";
  work?: { run_id: string; task_id: string; title: string; project_id: string | null; actor: string };
}

export interface EntryUse {
  id: string;
  kind: string;
  daily: { day: string; conversations: number; in_packets: number; opened: number; in_work: number; tokens: number }[];
  recent: EntryHandout[];
  totals: Partial<{ total: number; d7: number; d30: number; last: string | null; tokens: number; in_packets: number; opened: number; in_work: number }>;
}

/** A request the Brain served poorly. */
export interface BrainGap {
  key: string;
  kind: "nothing" | "searched";
  at: string;
  session_id: string;
  request: string;
  entry: string | null;
  entry_title?: string | null;
  entry_summary?: string | null;
  close: { id: string; title: string }[];
}

export interface BrainFlow {
  days: number;
  since: string;
  came_in: number;
  approved: number;
  rejected: number;
  decided: Record<string, number>;
  waiting: number;
  oldest_waiting: string | null;
  delivery: Partial<{
    packets: number;
    conversations: number;
    packet_tokens: number;
    entries: number;
    entry_tokens: number;
    work_runs: number;
    empty: number;
  }>;
  stock: { live: number; due: number; disputed: number; unused_60_days: number; standing_tokens: number };
  /** The first day use was recorded: "unused" means unused since then. */
  usage_since?: string;
}

export interface BrainPolicies {
  review_days: Record<string, number>;
  default_owner: string;
  auto_apply_own_scope: boolean;
  auto_apply_scopes: string[];
  max_proposals_per_session: number;
  retention_days: number;
  approver: string;
  areas: string[];
  kinds: string[];
  scopes: string[];
}

export interface DecisionOutcome {
  results: { id: string; action: string; ok: boolean; message: string; data: Record<string, unknown> }[];
  checkpoint: BrainCheckpoint | null;
}

export interface BrainEntrySummary {
  id: string;
  title: string;
  summary: string;
  area: string;
  topic: string;
  kind: string;
  scope: string;
  partition: string | null;
  added: string | null;
  verified: string | null;
  confidence: string | null;
  stale_reason: string | null;
  standing: boolean;
  file: string | null;
}

export interface BrainTopic {
  key: string;
  label: string;
  description: string;
  entries: number;
}

export interface BrainArea {
  key: string;
  label: string;
  description: string;
  topics: BrainTopic[];
}

export interface BrainCatalog {
  areas: BrainArea[];
  entries: BrainEntrySummary[];
}

export interface BrainFile {
  path: string;
  kind: "reference" | "asset" | "skill";
  title: string;
  size: number;
  mime: string;
  updated: string | null;
  description: string;
  entry_id: string | null;
  original: string | null;
  /** Which copy it is and where it belongs: a work file in a project, or a guide kept whole. */
  project?: string | null;
  project_title?: string | null;
  version?: number | null;
  file_status?: string | null;
  dated?: string | null;
  /** How many parts of it the Brain can quote on their own. */
  sections?: number;
  work?: boolean;
}

/** A piece of work the Brain follows across conversations (a Focus). */
export interface BrainProject {
  id: string;
  title: string;
  summary: string;
  status: string;
  active: boolean;
  current: string;
  next: string;
  blockers: string;
  updated: string | null;
  aliases: string[];
  files: number;
  updates: number;
  /** Where its notes are filed, area/topic. */
  topic: string;
}

/** One progress update on a project, as its journal keeps it. */
export interface ProjectUpdate {
  seq: number;
  at: string;
  summary: string;
  changes: Record<string, string>;
  evidence: string;
  actor: string;
}

/** A file filed in a project, with which copy it is. */
export interface ProjectFile {
  path: string;
  id: string;
  title: string;
  summary: string;
  version: number | null;
  file_status: string | null;
  dated: string | null;
  filename: string | null;
  sections: number;
}

/** A project in full: what it is for, where it stands, its progress, files and notes. */
export interface BrainProjectDetail {
  id: string;
  title: string;
  summary: string;
  aliases: string[];
  status: string;
  active: boolean;
  state: Record<string, string>;
  brief: string;
  route_key: string;
  updates: ProjectUpdate[];
  files: ProjectFile[];
  notes: { id: string; title: string; summary: string; kind: string; type: string | null; added: string | null }[];
}

/** What filing a file did: filed at once (with an undo point) or waiting for review. */
export interface BrainFiled {
  status: "applied" | "pending" | "duplicate" | "refused";
  message: string;
  proposal_id: string | null;
  entry_id: string | null;
  path: string | null;
  version: number | null;
  replaced: string | null;
  sections: number;
  project: string | null;
  checkpoint_id: string | null;
}

/** What an AI would be handed for a request, and why each piece is there. */
export interface BrainPreview {
  request: string;
  mode: string;
  tokens: number;
  text: string;
  project: { id: string; title: string } | null;
  procedure: string | null;
  candidates: string[];
  notes: { id: string; title: string; kind: string; topic: string; score: number; why: string }[];
  sections: { id: string; file: string; title: string; label: string; score: number; why: string }[];
  related: string[];
}

export interface BrainSkill {
  name: string;
  category: string;
  description: string;
  when_to_use: string;
  path: string;
  files: BrainFile[];
  /** What a person says to ask for it. */
  triggers?: string[];
  /** What it makes: post, pdf, pptx. */
  artifacts?: string[];
  depends_on?: string[];
  scope?: string;
}

/** A skill as the Skills place lists it: what it makes and how its last run went. */
export interface SkillCard {
  name: string;
  category: string;
  description: string;
  triggers: string[];
  artifacts: string[];
  /** It makes files on this computer (a PDF, a deck), in a folder of its own. */
  makes_files: boolean;
  files: number;
  last_run: { task_id: string; status: TaskStatus; at: string } | null;
  /** The skills that build on it. */
  used_by: string[];
  /** Run it here; `support`: files other skills use (fonts, logos), kept rather than run;
   * `chat`: the Brain's own housekeeping, called by name in a conversation. */
  use: "run" | "support" | "chat";
}

export interface SkillCards {
  skills: SkillCard[];
  /** New skills a model wrote, waiting in Review. */
  waiting: { proposal_id: string; name: string; description: string | null; task_id: string | null }[];
}

/** One run of a skill, or one draft of a better version of it, and what came of it. */
export interface SkillRun {
  task_id: string;
  skill: string;
  kind: "run" | "improve";
  ask: string;
  status: TaskStatus;
  assignee_id: string | null;
  created_at: string;
  updated_at: string;
  makes_files: boolean;
  folder: string | null;
  files: { name: string; size: number }[];
  capture: { id: string; title: string } | null;
  project: { id: string; title: string } | null;
  /** Files from the Brain it was pointed to. */
  attached: string[];
  result: { artifact_id: string; title: string; text: string; version: number; at: string } | null;
  proposal: { id: string; status: string } | null;
}

/** One version of a skill's procedure, from the Brain's history. */
export interface SkillVersion {
  ref: string;
  at: string;
  current?: boolean;
  committed?: boolean;
  message?: string;
  author?: string;
  text_changed: boolean;
  chars: number;
  body?: string;
  meta?: Record<string, unknown>;
}

export interface BrainFiles {
  references: BrainFile[];
  assets: BrainFile[];
  skills: BrainSkill[];
}

export interface BrainSkillDetail extends BrainSkill {
  text: string;
  loads: string[];
}

export interface BrainHistoryRecord {
  at: string;
  action: string;
  by?: string;
  proposer?: string;
  reason?: string;
  state?: string;
  confidence?: string;
  reverted?: string;
  redone?: string;
}

/** A request to find what to remember in notes, with what it proposed. */
export interface DistillRequest {
  task_id: string;
  title: string;
  status: TaskStatus;
  assignee_id: string | null;
  assignee_name: string | null;
  /** The notes it reads. */
  items: string[];
  created_at: string;
  updated_at: string;
  summary: string;
  proposals: { id: string; title: string; status: "pending" | "approved" | "rejected" | "closed" }[];
  waiting: boolean;
}

/** Which model does the AI work the app starts (none: the only one connected). */
export interface DistillSettings {
  assignee_id: string | null;
}

// A CLI on the machine the workspace runs on (apps/server runners.py).
export interface RunnerStatus {
  id: string;
  label: string;
  provider: string;
  one_click: boolean;
  installed: boolean;
  version: string | null;
  signed_in: boolean | null;
  install: string;
  sign_in: string;
  actor_id: string | null;
  detail: string;
}

export type LocalRunStatus = "starting" | "running" | "succeeded" | "failed" | "cancelled" | "timed_out";

export interface RunEvent {
  seq: number;
  at: string;
  kind: "status" | "text" | "tool" | "tool_result" | "result" | "stderr" | "error" | "log" | "done" | "files";
  text?: string;
  name?: string;
  ok?: boolean;
}

export interface LocalRun {
  id: string;
  runner: string;
  task_id: string;
  task_title: string;
  actor_id: string;
  started_by: string;
  status: LocalRunStatus;
  /** Why a run being stopped will end; it stays running until its end is recorded. */
  stopping?: "cancelled" | "timed_out" | null;
  started_at: string;
  finished_at: string | null;
  exit_code: number | null;
  summary: string;
  events: RunEvent[];
  /** Where a run that makes files worked, and what it left there. */
  folder?: string | null;
  made?: { name: string; size: number }[];
  /** The page the run's work belongs to (the skill, the capture, Review). */
  link?: string | null;
}

export interface Me {
  actor_id: string;
  kind: string;
  name: string;
  actions: string[];
  projects: string[] | null;
  workspace: WorkspaceInfo;
}

/** What every page's navigation shows. */
export interface Home {
  workspace: WorkspaceInfo;
  counts: {
    /** Proposals waiting for the person's review. */
    brain_proposals: number;
    /** The AI work the app started, by status. */
    ai_work: Partial<Record<TaskStatus, number>>;
  };
}

/** How one AI app connects to the Brain: the same text as `uv run contxt connect`. */
export interface BrainClientSetup {
  client: string;
  label: string;
  server: string;
  /** A command to run once (Claude Code), or a block for a settings file. */
  command?: string;
  file?: string;
  config?: string;
  note: string;
}

export interface BrainConnect {
  /** False when no Brain is configured. */
  ready: boolean;
  server: string;
  vault?: string;
  clients: BrainClientSetup[];
}

export interface ProviderSetup {
  provider: string;
  label: string;
  transport: string;
  url: string;
  schedule_hint: string;
  file?: string;
  config: string;
  command?: string;
}

export interface Connection {
  actor: Actor;
  credential: Credential;
  token: string;
  setup: ProviderSetup;
  worker_prompt: string;
}

/** What in the Brain wants a look besides proposals, and how much each entry was used. */
export interface BrainAttention {
  clashes: { proposal_id: string; title: string; entry_id: string; entry_title: string; why: string }[];
  twins: { a: string; a_title: string; b: string; b_title: string; score: number }[];
  flagged: { id: string; title: string; why: string }[];
  recheck: { id: string; title: string; why: string }[];
  /** Entry id: how many conversations it went to in the last `days`. */
  usage: Record<string, number>;
  days: number;
}

export type SetupStep = "you" | "ai" | "brain" | "project" | "file";

/** First-time setup: each step is done when its thing exists in the Brain. */
export interface Onboarding {
  steps: { id: SetupStep; done: boolean; count: number | null }[];
  done: number;
  total: number;
  owner_name: string;
  brain: { available: boolean; own_entries: number; waiting: number; projects: number; files: number };
  local_model: boolean;
  completed_at: string | null;
  dismissed_at: string | null;
  tour_seen_at: string | null;
}

// ---------------------------------------------------------------- notes

/** A note in the person's scratchpad: private until they add it to the Brain. */
export interface Note {
  id: string;
  title: string;
  /** Left out of lists. */
  body: string | null;
  revision: number;
  version: number;
  created_by: string;
  created_at: string;
  updated_at: string;
  edited_by: string | null;
  archived_at: string | null;
  /** What it is: typed here, spoken, recorded, a transcript made elsewhere, or a document. */
  capture?: CaptureKind;
  /** What was brought in, kept beside the text. */
  original?: { filename: string; mime: string; size: number } | null;
  /** How far a spoken or recorded capture's text is. */
  transcription?: Transcription | null;
  /** Its summary and key points, or how far asking for them is. */
  digest?: Digest | null;
}

/** How a key point fits what the Brain holds now. */
export type Fit = "new" | "repeats" | "updates" | "clashes";

export interface DigestPoint {
  text: string;
  fit: Fit;
  /** The entry it repeats, updates or clashes with. */
  entry?: string;
  why?: string;
}

export interface Digest {
  /** queued: asked for once its text is in; waiting: a model has it; ready: written. */
  state: "queued" | "waiting" | "ready";
  task_id?: string;
  summary?: string;
  points?: DigestPoint[];
  decisions?: string[];
  actions?: string[];
  questions?: string[];
  people?: string[];
  at?: string;
  by?: string;
}

/** An entry in the Brain a capture touches, found by meaning. */
export interface RelatedInBrain {
  id: string;
  title: string;
  summary: string;
  topic: string;
  score: number;
}

export type CaptureKind = "note" | "talk" | "recording" | "transcript" | "document";

export interface Transcription {
  state: "pending" | "working" | "ready" | "failed";
  progress: number;
  /** Seconds of audio, once heard. */
  duration: number | null;
  error: string | null;
}

/** Speech to text on this computer: the library, the model, a download under way. */
export interface SpeechStatus {
  installed: boolean;
  model: string;
  present: boolean;
  ready: boolean;
  downloading: boolean;
  about_mb: number;
  error: string | null;
}

export interface NoteVersion {
  revision: number;
  title: string;
  body: string | null;
  size: number;
  by: string;
  at: string;
  label: string | null;
  sealed: boolean;
  current: boolean;
}

// ---------------------------------------------------------------- search

export interface SearchResults {
  query: string;
  brain: BrainHit[];
  projects: BrainProject[];
  notes: Note[];
}

// ---------------------------------------------------------------- the earlier workspace

export interface LegacySummary {
  counts: {
    goals: number;
    todos_open: number;
    todos_done: number;
    meetings: number;
    transcripts: number;
    memories: number;
    documents: number;
    sheets: number;
    canvases: number;
    ai_work: number;
    projects: number;
    projects_without_brain: number;
  };
  has_any: boolean;
  exported_at: string | null;
  export_dir: string | null;
  moved_at: string | null;
  moved: Record<string, string[]>;
}

export interface LegacyReport {
  projects_started: string[];
  projects_matched: number;
  projects_left: { title: string; why: string }[];
  notes_proposed: number;
  files_filed: number;
  next_steps: number;
  /** Every open to-do, in one private note. */
  todos_noted: number;
  todo_note: string | null;
  refused: { title: string; why: string }[];
  skipped: number;
}
