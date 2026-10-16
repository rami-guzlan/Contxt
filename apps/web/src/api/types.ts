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
  action: "approve" | "reject" | "unschedule" | "archive" | "edit" | "restore" | "unarchive" | "update" | "verify" | "mark";
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

// A project's other names are set on its entry, comma separated. A must-hold's domains
// (applies_to) and the words that bring it in (triggers) are comma separated too.
export type EntryField =
  | "owner"
  | "review_days"
  | "review_by"
  | "classification"
  | "area"
  | "topic"
  | "aliases"
  | "load"
  | "applies_to"
  | "triggers"
  | "must_text"
  | "critical"
  | "baseline"
  | "as_of"
  | "valid_until";

// ---- the context supply chain

export interface EntryOrigin {
  kind:
    | "conversation"
    | "workspace"
    | "work"
    | "file"
    | "meeting"
    | "output"
    | "doc"
    | "you"
    | "import"
    | "capture"
    | "library"
    | "project"
    | "skill"
    | "run"
    | "movein"
    | "upload"
    | "chat"
    | "folder"
    | "unknown";
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
  load?: string; // standing | domain (a must-hold) | on-demand | manual
  applies_to?: string[]; // a must-hold's domains: areas, area/topic pairs, project ids
  triggers?: string[]; // words that bring a must-hold's domain into play
  must_text?: string; // a must-hold's one line
  critical?: boolean; // its line also goes in every session's startup context
  /** Why a change to it waits for a reason (a rule, a must-hold, confirmed, much used), or "". */
  baseline?: string;
  baseline_marked?: boolean; // you marked it a baseline
  as_of?: string | null; // the day a changing value was true
  valid_until?: string | null; // the last day it holds
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

export type Preset = "personal" | "careful" | "regulated";
export type CaptureType = "file" | "fact" | "decision" | "progress" | "preference" | "rule" | "convention" | "change";
export type CaptureOrigin = "app" | "chat" | "folder";

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
  /** The starting point for what goes straight in (a Brain without one is careful). */
  preset?: Preset;
  presets?: Preset[];
  /** What each kind of capture does, by where it came from: in at once, or wait for you. */
  capture?: Record<CaptureType, Record<CaptureOrigin, "apply" | "wait">>;
  capture_types?: CaptureType[];
  capture_origins?: CaptureOrigin[];
  /** A day to think before a rule, a standing note or a must-hold changes. */
  revision_delay?: boolean;
  /** Your own AI reads possible disagreements side by side, when one is connected. */
  model_checks?: boolean;
  /** Once a week, your most used notes and oldest baselines are read against the rest. */
  cross_check?: boolean;
  /** The external challenger argues against a few beliefs each week; off until you turn it on. */
  challenger?: boolean;
  /** Private details hidden from a cloud model that reads what you bring in (decision 13). */
  redact_cloud?: boolean;
}

export interface DecisionOutcome {
  results: { id: string; action: string; ok: boolean; message: string; data: Record<string, unknown> }[];
  checkpoint: BrainCheckpoint | null;
  /** Live, but saving it to the Brain's git history failed: why. */
  commit_error?: string;
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
  /** Its kind in the Library (guide, reference, influence, asset), when its card says. */
  library?: string | null;
  /** Where it came from, as its card says (capture:recording, library, run:<id>), or inferred
   * from its card for a file filed before origins were kept; null when nobody knows. */
  origin?: string | null;
  origin_inferred?: boolean;
  scope?: string | null;
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
  /** The output it is chasing: it opens every brief in the project. */
  objective?: string;
  /** The goals it serves. */
  goals?: string[];
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
  /** The output it is chasing; it opens every brief in the project. */
  objective?: string;
  /** The goals it serves. */
  goals?: string[];
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

/** A skill by its purpose (UX C): when it was last used, whether it may be out of date (what
 * it loads changed since its last edit), what uses it, its version, its Claude Code copy. */
export interface SkillOverview {
  name: string;
  category: string;
  last_used: string | null;
  last_edited: string | null;
  changed: { key: string; title: string; at: string | null }[];
  version: number;
  used_by: { skills: string[]; agents: string[]; workflows: { id: string; name: string }[] };
  copy: { behind: number | null; pushed_at: string | null } | null;
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
  /** Every skill it followed: several when chosen on the Skills page; none when the Brain
   * picked the one that fit. */
  skills?: string[];
  kind: "run" | "improve";
  /** The agent asked, when an agent was. */
  agent?: string | null;
  /** A Workspace doc's own runs: a critic's questions (push-back), or more of it (continue). */
  doc_action?: "push-back" | "continue" | null;
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
  proposals: {
    id: string;
    title: string;
    status: "pending" | "approved" | "rejected" | "closed";
    /** The goal it serves and the project it belongs to, as the knowledge agent said. */
    goal?: string | null;
    project_id?: string | null;
  }[];
  waiting: boolean;
  /** Documents filed in the Brain it reads. */
  files?: string[];
  /** What it considered and did not pull, each with why: one tap from pulled anyway. */
  left_out?: { statement: string; why: string }[];
}

/** Which model does the AI work the app starts (none: the only one connected). */
export interface DistillSettings {
  assignee_id: string | null;
  /** The model that triages first: claude, local:<model>, ollama:<model>, or off. */
  triage?: string | null;
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
  /** The standing instruction that makes the app's model ask the Brain first. */
  instruction?: string;
  /** Where the app keeps the instructions it follows in every conversation. */
  instruction_where?: string;
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

export type SetupStep = "you" | "goals" | "ai" | "brain" | "project" | "file";

/** First-time setup: each step is done when its thing exists in the Brain. */
export interface Onboarding {
  steps: { id: SetupStep; done: boolean; count: number | null }[];
  done: number;
  total: number;
  owner_name: string;
  brain: { available: boolean; own_entries: number; waiting: number; projects: number; files: number; goals?: boolean };
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
  /** The projects it is linked to (a link, never a copy; it stays private). */
  projects?: string[];
  /** Where a link points. */
  url?: string | null;
}

/** How a key point fits what the Brain holds now. */
export type Fit = "new" | "repeats" | "updates" | "clashes";

export interface DigestPoint {
  text: string;
  fit: Fit;
  /** The entry it repeats, updates or clashes with. */
  entry?: string;
  why?: string;
  /** The project it moves forward, or "goals". */
  serves?: string;
}

export interface Digest {
  /** queued: asked for once its text is in; waiting: a model has it; ready: written. */
  state: "queued" | "waiting" | "ready";
  task_id?: string;
  /** What it is mostly about, and which goal or project that serves. */
  about?: string;
  /** Work it is about that is not a project yet. */
  new_project?: string;
  /** A subject none of the goals covers. */
  off_goal?: string;
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

export type CaptureKind = "note" | "talk" | "recording" | "transcript" | "document" | "link";

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
  /** In the Brain at once. */
  files_filed: number;
  /** Waiting in Review (Careful and Regulated), with their names. */
  files_waiting?: number;
  waiting_files?: string[];
  next_steps: number;
  /** Every open to-do, in one private note. */
  todos_noted: number;
  todo_note: string | null;
  refused: { title: string; why: string }[];
  skipped: number;
}

// ---------------------------------------------------------------- catch up

export interface Advice {
  action: string;
  reason: string;
}

/** The goal and the project the knowledge agent tagged a suggestion with. */
export interface Serves {
  goal: string | null;
  project: { id: string; title: string } | null;
}

export type CardType =
  | "challenge"
  | "baseline"
  | "went_in"
  | "conflict"
  | "close"
  | "duplicate"
  | "private"
  | "change"
  | "retire"
  | "replace"
  | "skill"
  | "problem";
export type CardAction =
  | "keep_mine"
  | "use_this"
  | "keep_both"
  | "edit"
  | "later"
  | "keep_one"
  | "not_this"
  | "keep"
  | "review"
  | "compare"
  | "revise"
  | "both_hold"
  | "undo"
  | "dispute"
  | "keep_note"
  | "revise_note";

/** What your own AI said after reading two notes side by side (check 3). */
export interface ModelVerdict {
  relation: "contradicts" | "narrows" | "extends" | "agrees" | "unrelated";
  proposed: string;
  existing: string;
  settle: string;
  at: string | null;
}

/** A note a change must not quietly overturn, as a "Changes a baseline" card shows it. */
export interface CardBaseline {
  id: string;
  title: string;
  body: string;
  kind: string;
  load: string;
  /** Why it is a baseline, in plain words. */
  why: string;
  /** A new version of it, its retirement, or a suggestion that disagrees with it. */
  change: "revise" | "retire" | "disagree";
  tension: string;
  approved_by: string;
  approved_at: string;
  added: string;
  revised: string;
  verified: string;
  uses: number;
  /** A rule, a standing note or a must-hold: its impact comes first. */
  weighty: boolean;
  impact: { conversations: number; recent: { request: string; at: string; client: string }[]; domains: string[] } | null;
  previous_reason: string;
  min_words: number;
}

/** One decision that needs the person, in plain words, with a recommendation. */
export interface JudgmentCard extends Serves {
  key: string;
  /** None for something that already went in (`went_in`): it names its entry instead. */
  proposal_id: string | null;
  entry_id?: string;
  /** The undo point that takes a change that went in on its own back. */
  checkpoint?: string | null;
  type: CardType;
  kind: string;
  tag: string;
  /** It changes how every AI works (a rule, who you are, a skill). */
  shapes: boolean;
  title: string;
  summary: string;
  body: string;
  source: string;
  at: string | null;
  topic: string;
  /** The note it disagrees with, repeats, changes or retires. */
  with: { id: string; title: string; body: string; score: number | null } | null;
  duplicates: string[];
  why: string;
  recommend: Advice;
  actions: CardAction[];
  baseline?: CardBaseline | null;
  /** Whether your own AI read the pair yet, and what it said. */
  check?: { model: "done" | "waiting" | "none"; verdict: ModelVerdict | null };
  /** It would have gone in on its own, but waits: what it may disagree with. */
  held?: { id: string; why: string } | null;
}

/** A revision you decided, going in a day later unless you cancel it. */
export interface ScheduledRevision {
  proposal_id: string;
  title: string;
  at: string;
  reason: string;
  baseline: string | null;
}

/** Suggestions nothing disagrees with, kept with one tap. */
export interface QuickGroup {
  key: string;
  kind: string;
  area: string;
  title: string;
  detail: string;
  count: number;
  proposal_ids: string[];
  shapes: boolean;
  items: ({ id: string; title: string; summary: string; source: string } & Serves)[];
  sources: string[];
}

export interface UpkeepSide {
  id: string;
  title: string;
  summary: string;
  uses: number;
  added: string | null;
}

export type UpkeepCard =
  | { key: string; type: "recheck"; id: string; title: string; summary: string; why: string; uses: number; last_used: string | null }
  | { key: string; type: "duplicate"; score: number | null; a: UpkeepSide; b: UpkeepSide; recommend: Advice }
  | { key: string; type: "tidy"; id: string; title: string; why: string }
  | { key: string; type: "unused"; count: number; days: number; items: { id: string; title: string; last_used: string | null; topic: string }[] }
  | { key: string; type: "musthold"; id: string; title: string; summary: string; area: string; area_label: string; triggers: string[]; recommend: Advice }
  | { key: string; type: "spot"; id: string; title: string; summary: string; why: string; uses: number; last_used: string | null }
  | { key: string; type: "older"; older: UpkeepSide; newer: UpkeepSide; older_as_of: string | null; newer_as_of: string | null }
  | {
      key: string;
      type: "belief";
      id: string;
      title: string;
      summary: string;
      why: string;
      found_by: string;
      baseline: string;
      evidence: { kind: "note" | "file" | "proposal" | "rejected"; id: string; title: string; text: string };
    }
  | { key: string; type: "challenger"; baselines: number; stale: boolean };

/** After a run of the same yes: let this kind go straight in? */
export interface Offer {
  key: string;
  type: CaptureType;
  origin: CaptureOrigin;
  kept: number;
  title: string;
  detail: string;
  shapes: boolean;
}

export type Nudge =
  | { key: string; type: "start_project"; name: string; capture: { id: string; title: string }; title: string }
  | { key: string; type: "add_goal"; subject: string; count: number; captures: { id: string; title: string }[]; title: string }
  /** An agent's "Goals it serves" line that names no goal. */
  | { key: string; type: "agent_goal"; agent: string; line: string; title: string };

/** Offered once: what the earlier workspace holds that the Brain does not. */
export interface LegacyOffer {
  key: string;
  title: string;
  detail: string;
  counts: LegacySummary["counts"];
  seconds: number;
  minutes: number;
}

export interface HealthFactor {
  key: "fresh" | "tidy" | "used";
  label: string;
  score: number;
  detail: string;
  fix: { label: string; to: string } | null;
}

export interface BrainHealth {
  score: number | null;
  label: "good" | "fair" | "low" | "new";
  factors: HealthFactor[];
  /** Governed files live but not saved to git (a commit failed). */
  unsaved: string[];
  /** Approvals taken back within `days`: the sign that approvals drift. */
  drift?: { approvals: number; undone: number; share: number | null; days: number };
}

/** Something that went in on its own (the capture policy, your own scope). */
export interface WentIn {
  at: string;
  kind: string;
  id: string;
  title: string;
  source: string;
  capture: string;
  path: string | null;
  live: boolean;
  checkpoint: string | null;
}

export interface Recap {
  since: string;
  went_in: WentIn[];
  went_in_total: number;
  decided: Record<string, number>;
  came_in: { total: number; by_source: Record<string, number>; waiting: number };
  projects: { id: string; title: string; updates: number; last: { at: string; summary: string } | null }[];
  gaps: number;
}

/** Everything the catch-up shows: a plan, never a pile. */
export interface CatchUpPlan {
  seen_at: string | null;
  since: string;
  away_days: number | null;
  recap_first: boolean;
  seconds: number;
  minutes: number;
  caught_up: boolean;
  counts: {
    judgment: number;
    quick: number;
    quick_items: number;
    upkeep: number;
    offers: number;
    legacy: number;
    handled: number;
    snoozed: number;
    /** Workflow runs waiting for you at a check (Work). */
    checks?: number;
  };
  /** Work's checks: workflow runs waiting for you. */
  work?: { run_id: string; workflow_id: string; workflow: string; ask: string; started_at: string }[];
  health: BrainHealth;
  recap: Recap;
  handled: WentIn[];
  judgment: JudgmentCard[];
  quick: QuickGroup[];
  upkeep: UpkeepCard[];
  scheduled?: ScheduledRevision[];
  /** This many judgment cards kept this fast each earns a plain word on the next card. */
  pace?: { cards: number; seconds: number };
  offers: Offer[];
  legacy: LegacyOffer | null;
  nudges: Nudge[];
  preset: Preset | null;
  /** Agent goals that slipped (one card per slip). */
  goals?: GoalCard[];
  /** Tasks handed to you, and handoffs nobody claimed for a day. */
  handed?: TaskItem[];
  unclaimed?: TaskItem[];
  /** AI values in State that wait for your tap. */
  state_waiting?: StateWaiting[];
  /** Suggested next steps for your goals, a quick yes grouped by goal. */
  goal_steps?: { goal: string; title: string; steps: GoalSuggestion[] }[];
  /** What the updating loop asks of you (BL 9). */
  loop?: LoopCard[];
}

/** One ask of the updating loop in Catch up. */
export interface LoopCard {
  key: string;
  type: "still_true" | "bent_rule" | "approval_health" | "corroborate" | "quarterly_review" | "lesson" | "hand_up";
  ask: string;
  note?: string;
  title?: string;
  text?: string;
  correction?: number;
  salience?: boolean;
  count?: number;
  uses?: number;
  source?: string;
  action?: string;
  area?: string;
  cases?: number;
  why?: string;
  at?: string;
}

/** A step of a knowledge agent run: what it answered, the tool it called and what came back. */
export interface LoopRunStep {
  answer: string;
  tool: string | null;
  args: Record<string, unknown> | null;
  result: string | null;
  problems: string[];
}

/** A knowledge agent run as the Brain keeps it (BL 17.8). */
export interface LoopRun {
  id: string;
  at: string;
  action: string;
  ending: string;
  record: { why?: string; model?: string; seconds?: number | null; prompt_version?: string; steps?: LoopRunStep[] };
}

// ---------------------------------------------------------------- goals and built-in skills

export interface GoalQuestion {
  id: string;
  question: string;
  why: string;
  required: boolean;
  example: string;
}

export interface Goals {
  questions: GoalQuestion[];
  answers: Record<string, string>;
  exists: boolean;
  id: string;
  starter: string | null;
  updated: string | null;
  purpose: string;
  /** "What is in motion", one per line: each can start a project. */
  projects: string[];
  text: string;
  status?: "saved" | "unchanged";
  checkpoint?: BrainCheckpoint | null;
}

export interface BuiltinSkill {
  name: string;
  category: string;
  description: string;
  installed: boolean;
}

export interface BuiltinSkills {
  skills: BuiltinSkill[];
  missing: string[];
  added?: string[];
}

// ---------------------------------------------------------------- moving in

export type MoveInKind = "chatgpt" | "claude" | "cursor" | "instructions" | "paste";

export interface MoveInIdea {
  id: string;
  source: string;
  source_kind: MoveInKind;
  text: string;
  original: string;
  group: string;
  kind: "identity" | "rule" | "state" | "fact";
  personal: boolean;
  topic: string;
  topic_label: string;
  match: { id: string; title: string; score: number } | null;
  why: string;
  status: "new" | "known" | "waiting" | "disagree" | "private";
  private?: string;
  secret?: boolean;
  /** It serves a goal, an active project, or says who you are or how you work. */
  fits: boolean;
  serves: { goal: string | null; project: { id: string; title: string } | null; about_you: boolean };
  /** Why the sift left it out (it can still be kept). */
  left_out?: string;
}

export interface MoveInStages {
  sources: number;
  chars: number;
  ideas: number;
  kinds: Record<string, number>;
  new: number;
  known: number;
  waiting: number;
  disagree: number;
  private: number;
  sifted?: boolean;
  fits?: number;
  for_goals?: number;
  for_projects?: Record<string, number>;
  about_you?: number;
  left_out?: number;
  to_keep: number;
}

export interface MoveInPreview {
  sources: { id: string; kind: MoveInKind; label: string; chars: number; ideas: number }[];
  ideas: MoveInIdea[];
  stages: MoveInStages;
  /** One idea to open at each stage of the pipeline. */
  examples: Record<string, string>;
}

export interface MoveInKept {
  stages: MoveInStages;
  proposed: { idea: string; proposal_id: string | null; status: string }[];
  already: { idea: string; proposal_id: string | null; status: string }[];
  refused: { idea: string; message: string }[];
  secrets_left_out: number;
}

// ---------------------------------------------------------------- activity: what each AI got

export interface RequestPiece {
  kind: "note" | "section" | "focus" | "skill" | "reference" | "kernel" | "system" | string;
  id: string;
  tokens: number;
  why: string;
  title?: string;
  note_kind?: string;
  topic?: string;
  topic_label?: string;
  live?: boolean;
  path?: string;
}

export interface AiRequest {
  id: string;
  session_id: string;
  at: string;
  request: string;
  mode: string;
  /** The app that asked, as a person names it. */
  app: string;
  client: string | null;
  tokens: number;
  /** Its share of the whole Brain. */
  share: number | null;
  project: { id: string; title: string } | null;
  skill: string | null;
  got: RequestPiece[];
  /** It got the startup context too. */
  kernel: boolean;
  opened: RequestPiece[];
  nothing: boolean;
  saved: { id: string; title: string; status: string; source?: string }[];
  engine: string | null;
  /** Its app runs older engine code: restart it to pick up the new version. */
  old_engine: boolean;
}

/** One request in full: the exact text it was handed, and the startup context when that went
 * with it (its text null when it was sent before the Brain kept it). Text null: it got notes
 * you do not see. */
export interface AiRequestFull extends AiRequest {
  text: string | null;
  startup: { fingerprint: string; text: string | null } | null;
  /** Its place in your private eval set, with your labels, when you labeled it. */
  eval?: EvalCase | null;
  /** Why each candidate went in or stayed out, as the ledger kept it. */
  why?: RequestWhy | null;
}

/** One candidate a brief's retrieval looked at: its scores, what became of it and why. */
export interface WhyRow {
  kind: "note" | "section";
  item: string;
  title: string;
  path?: string | null;
  /** The keyword part of its match, 0 to 1. */
  keyword: number | null;
  /** Its meaning score, 0 to 1 (none without the local meaning model). */
  meaning: number | null;
  /** The local reranker's relevance score, 0 to 1 (none without the local engine). */
  rerank: number | null;
  /** The decision model's answers: question to probability, or option probabilities. */
  kev: Record<string, unknown>;
  outcome: "body" | "pointer" | "listed" | "held" | "out";
  reason: string;
  found_by: string;
  round: number;
}

/** Why each candidate went in or stayed out of one brief: the local engine's record, or what
 * retrieval scored without it (fallback). */
export interface RequestWhy {
  mode: "on" | "fallback" | null;
  reason: string;
  lock: string;
  /** The gate: the decision model's yes against its cut, or, where that model has not
   * qualified on this computer, the reranker's best score against the relevance cut. */
  gate: { yes: number; cut: number; passed: boolean; by?: "reranker" } | null;
  cuts: Record<string, number>;
  fitted: { date?: string | null; eval_run?: string | null };
  timings: Record<string, number>;
  rounds: number;
  ceiling_hit: boolean;
  /** What this computer's setup ran instead of a step, in words. */
  notes?: string[];
  /** The cuts were fitted for other models: the defaults stood in. */
  refit?: boolean;
  in: WhyRow[];
  out: WhyRow[];
  out_count: number;
}

/** One of your real requests in the private eval set: the notes it needed, the ones that
 * helped, the ones that were noise, and the ones it should have had. */
export interface EvalCase {
  /** You marked it as a request that should get nothing from the Brain. */
  nothing?: boolean;
  id: string;
  packet_id: string | null;
  request: string;
  labeled: boolean;
  holdout?: boolean;
  must: string[][];
  useful: string[];
  noise: string[];
  missing?: string[];
}

export interface CostLine {
  tokens: number;
  usd: number;
}

export type CostLineName = "fixed" | "briefs" | "rereads" | "rewrites" | "jobs";

export interface CostDay {
  day: string;
  lines: Record<CostLineName, CostLine>;
  total_usd: number;
  total_tokens: number;
  sources: Record<string, string>;
  packets: number;
  brief_tokens: number;
  median_brief_by_type: Record<string, number>;
  claude_code?: { calls: number; sessions: number; all_usd: number };
  jobs?: { job: string; model: string; calls: number; tokens_in: number; tokens_out: number; cost: number }[];
}

export interface EvalScores {
  cases: number;
  must_recall: number;
  precision: number;
  noise_share: number;
  avg_tokens: number;
}

/** What context cost by day and line, how big briefs are by request type, and how well they
 * carry what a task needs. */
export interface ReportCard {
  days: number;
  per_day_usd: number;
  spend: {
    days: CostDay[];
    factor: { factor: number; measured: boolean; samples?: number; method?: string; at?: string };
    overhead: { per_call_claude_code: number; per_call_other: number; kernel: number; tools: number };
    model: string;
    later_calls: number;
    later_calls_source: string;
    transcripts: boolean;
    sessions_read: number;
  };
  brief_tokens_by_type: Record<string, number>;
  eval_set: { cases: number; labeled: number; held_out: number };
  eval?: Record<"tuning" | "holdout" | "all", EvalScores>;
  private_eval?: Record<"tuning" | "holdout" | "all", EvalScores>;
  text: string;
}

export interface AiRequests {
  requests: AiRequest[];
  brain_tokens: number;
  apps: string[];
  engine: string;
}

export interface WeekOfUse {
  start: string;
  end: string;
  conversations: number;
  packets: number;
}

export interface AiApp {
  client: string;
  label: string;
  found: boolean;
  connected: boolean;
  last_request: { at: string; request: string } | null;
  setup: BrainClientSetup | null;
}

// ---------------------------------------------------------------- see the difference

export interface DifferenceItem {
  what: string;
  item: string;
}

export interface DifferencePiece {
  kind: string;
  id: string;
  title: string;
}

export interface Comparison {
  id: string;
  request: string;
  project: string | null;
  started_at: string;
  status: "running" | "done" | "failed";
  step: "without" | "with" | "differences" | "done";
  without: string;
  with_context: string;
  differences: DifferenceItem[];
  pieces: DifferencePiece[];
  tokens: number;
  kernel_tokens: number;
  brain_tokens: number;
  share: number | null;
  finished_at: string | null;
  error: string | null;
}

/** A before and after a demo Brain keeps, made earlier. */
export interface DifferenceExample {
  id: string;
  request: string;
  illustrative: boolean;
  note: string;
  without: string;
  with_context: string;
  differences: DifferenceItem[];
  pieces: DifferencePiece[];
  tokens: number;
  kernel_tokens: number;
  brain_tokens: number;
}

// ---------------------------------------------------------------- outputs

export type OutputKind = "document" | "pdf" | "slides" | "spreadsheet" | "image" | "page" | "data" | "audio" | "video" | "file";

export interface OutputFile {
  path: string;
  name: string;
  folder: string;
  size: number;
  modified: string;
  kind: OutputKind | string;
  from: "skill" | "chat" | null;
  /** A skill run is still working in its folder. */
  working: boolean;
  /** What it is for (BL 16.5): the project, the State row (sheet/row), who made it. */
  project?: string | null;
  for?: string | null;
  maker?: string | null;
  title?: string | null;
}

export interface Outputs {
  root: string;
  folders: string[];
  files: OutputFile[];
}

export interface MadeFrom {
  path: string;
  how: "skill" | "export" | "chat" | "unknown";
  skill_run?: {
    task_id: string;
    skill: string;
    ask: string;
    project: string | null;
    attached: string[];
    capture: { id: string; title: string } | null;
    status: string;
    created_at: string;
    runs: { id: string; at: string | null; status: string; by: string }[];
  };
  export?: {
    artifact_id: string;
    version: number;
    title: string;
    type: string;
    task_id: string | null;
    run_id: string | null;
    exported_at: string;
  };
  chat?: { title: string; at: string | null; app: string; session_id: string | null; requests: AiRequest[] };
  /** What each run was handed from the Brain. */
  given?: { id: string; pieces: RequestPiece[] }[];
}

/** Dictation into a field: the words, and how long the person spoke. */
export interface Dictation {
  text: string;
  seconds: number;
}

// ---------------------------------------------------------------- this computer

/** The local model that matches by meaning: here, being fetched, or not yet. */
export interface LocalModels {
  matching: {
    enabled: boolean;
    model?: string | null;
    present: boolean;
    downloading: boolean;
    error?: string | null;
    about_mb?: number;
  };
}

/** One pinned option for a role on this computer (Settings, On this computer, Local models). */
export interface LocalModelOption {
  name: string;
  repository: string;
  revision: string | null;
  pinned: boolean;
  size_gb: number | null;
  ram_gb: number | null;
  license: string | null;
  downloaded: boolean;
  why_not: string;
  fits: boolean;
  fit_reason: string;
  measured: { speed_ms?: number; quality?: number; at?: string } | null;
  slow: string;
  in_use: boolean;
  setup_default: boolean;
  /** The meaning index's model: kept with the Brain, downloaded under Matching by meaning. */
  with_brain?: boolean;
}

export interface LocalModelRole {
  role: "embed" | "rerank" | "decide" | "agent";
  label: string;
  model: string | null;
  options: LocalModelOption[];
}

/** This computer's local models: the machine, its setup, each role, and the engine's mode. */
export interface LocalModelsOverview {
  enabled: boolean;
  machine?: { ram_gb: number; gpu: string; gpu_gb: number; apple_silicon: boolean; system: string };
  setup?: "laptop" | "workstation" | "large" | "small";
  setup_label?: string;
  checked_at?: string | null;
  roles?: LocalModelRole[];
  ram_in_use_gb?: number;
  budget_ms?: Record<string, number>;
  fallbacks?: string[];
  engine?: { ready: boolean; reason: string; lock: string; agent: string };
  /** Claude Code for the knowledge agent, as it stands (the person's choice, or on until a
   * local agent model is here). */
  agent_claude_code?: boolean;
  agent_claude_code_set?: boolean;
  lock?: string;
  downloading?: string[];
  errors?: Record<string, string>;
  /** A warning that did not refuse the change (a model slower than this machine's budget). */
  notice?: string;
}

export interface BackupFile {
  name: string;
  size: number;
  at: string;
}

export interface BackupMade {
  name: string;
  size: number;
  records: number;
  files: number;
  brain_files: number;
  originals: number;
}

// ---- the knowledge agent

/** A model the agent can work through: Claude Code on this computer, or a local one. */
export interface AgentModel {
  id: string;
  label: string;
  /** cli: Claude Code; local: through Ollama; pinned: the app's own model service. */
  kind: "cli" | "local" | "pinned";
  available: boolean;
  detail: string;
  /** A small model: it gets the short map and fewer candidates. */
  brief: boolean;
}

export interface AgentAction {
  id: string;
  label: string;
  blurb: string;
  /** The goal it works toward ("Why I'm doing this"), when that goal is on. */
  serves?: { id: string; title: string; words: string } | null;
}

/** Something the agent asks the owner, with the one-tap answers its kind allows. */
export interface AgentQuestion {
  key: string;
  action: string;
  verdict: string;
  ask: string;
  why: string;
  text: string;
  target: { type: "note" | "project" | "skill" | "gap" | "goals"; id: string; title: string };
  triggers?: string[];
  at: string;
  status: "open" | "done" | "dismissed";
  /** The run that asked it. */
  run?: string;
}

/** What one run of an action did. */
export interface AgentRun {
  id: string;
  action: string;
  label: string;
  model: string;
  at: string;
  summary: string;
  checked: number;
  found: number;
  proposed: number;
  questions: number;
  fine: number;
  skipped: number;
  proposals: string[];
  notes: string[];
  seconds?: number;
}

export interface AgentOverview {
  model: string;
  suggestions: boolean;
  /** The goals it keeps (on once you turn them on in Settings > Alignment). */
  goals?: GoalView[];
  actions: AgentAction[];
  questions: AgentQuestion[];
  runs: AgentRun[];
  models: AgentModel[];
  working: AgentJob[];
}

/** A suggestion made by code as the Brain changes: the action that deals with it, or where. */
export interface AgentSuggestion {
  key: string;
  kind: string;
  title: string;
  detail: string;
  count: number;
  action: string | null;
  link: string | null;
}

export interface AgentChatResult {
  reply: string;
  run: string[];
  notes: { title: string; text: string; kind: string }[];
}

/** The agent at work in the background: an action, or one turn of the conversation. */
export interface AgentJob {
  id: string;
  kind: "action" | "chat";
  action: string | null;
  model: string;
  model_label: string;
  message: string;
  status: "waiting" | "running" | "done" | "failed";
  result: Partial<AgentRun> & Partial<AgentChatResult>;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface AgentSkill {
  name: string;
  description: string;
  when_to_use: string;
  triggers: string[];
  text: string;
  /** The Brain holds its own skill of this name, used instead. */
  own: boolean;
}

// ------------------------------------------------------------------ Work: the Library

/** What an item is for; a prompt has its own tab (Prompts) and never routes on its own. */
export type LibraryKind = "guide" | "reference" | "influence" | "prompt" | "asset";
export type LibraryRefresh = "never" | "weekly" | "monthly";

/** An item kept whole, by what it is for: a guide to follow, a reference to read whole, an
 * influence whose taste to borrow, or an asset kept byte for byte; with where it came from,
 * where it was fetched from and what uses it. */
export interface LibraryItem {
  path: string;
  title: string;
  kind: LibraryKind;
  /** The file it is: a document kept as text, or an asset kept byte for byte. */
  file_kind: "reference" | "asset";
  mime: string;
  origin: string | null;
  origin_inferred: boolean;
  scope: string | null;
  summary: string;
  entry_id: string | null;
  source_url: string | null;
  source_repo: string | null;
  source_paths: string[];
  fetched_at: string | null;
  refresh: LibraryRefresh;
  updated: string | null;
  dated: string | null;
  version: number | null;
  size: number;
  original: string | null;
  project: string | null;
  project_title: string | null;
  used_by: { skills: string[]; agents?: string[]; workflows?: string[] };
}

export interface LibraryItemFull extends LibraryItem {
  /** The document's text; null for an asset, which the page shows or offers as a file. */
  text: string | null;
  checked_at: string | null;
}

/** What filing in the Library did: as the Brain files any document, or "unchanged" when the
 * text was already there. */
export interface LibraryFiled extends Omit<BrainFiled, "status"> {
  status: BrainFiled["status"] | "unchanged";
}

export interface LibraryRefreshed {
  status: "applied" | "pending" | "unchanged" | "refused";
  message: string;
  path: string;
  proposal_id: string | null;
}

// ------------------------------------------------------------------ Work: agents

export type AgentOutput = "outputs" | "workspace" | "proposals";

/** A role written like a job description, kept in the Brain (agents/<name>/AGENT.md). */
export interface WorkAgent {
  name: string;
  role: string;
  responsibilities: string[];
  goals: string[];
  projects: string[];
  skills: string[];
  library: string[];
  context: string[];
  meetings_days: number;
  boundaries: string[];
  output: AgentOutput;
  output_shape: string;
  runner: string;
  review: boolean;
  scope: string;
  status: "active" | "archived";
  prompt: string;
  path: string;
  last_run?: { task_id: string; status: string; at: string } | null;
}

/** What each of an agent's pointers is now, and which no longer resolve. */
export interface WorkAgentResolved {
  skills: { name: string; missing: boolean; description: string }[];
  library: { path: string; title: string; missing: boolean }[];
  context: { key: string; missing: boolean }[];
  projects: { id: string; title: string; missing: boolean; status?: string; current?: string; next?: string }[];
  broken: string[];
}

export interface WorkAgentFull {
  agent: WorkAgent;
  resolved: WorkAgentResolved;
  /** The role as a model gets it, before the brief of a task. */
  prompt: string;
  checkpoint?: BrainCheckpoint | null;
}

/** The form an agent is written with; the Brain checks what each field means. */
export interface WorkAgentForm {
  name: string;
  role: string;
  responsibilities: string[];
  goals: string[];
  projects: string[];
  skills: string[];
  library: string[];
  context: string[];
  meetings_days: number;
  boundaries: string[];
  output: AgentOutput;
  output_shape: string;
  runner: string;
  review: boolean;
  prompt: string;
}

/** A model's draft for Work: an agent's operating prompt, or an improved prompt in Compose. */
export interface WorkDraft {
  prompt: string;
  questions: string[];
  changes?: string[];
  used?: string[];
}

/** A Work job in the background (the same queue as the knowledge agent's). */
export interface WorkJob<R = WorkDraft> {
  id: string;
  kind: string;
  model: string;
  model_label: string;
  message: string;
  status: "waiting" | "running" | "done" | "failed";
  result: Partial<R>;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

// ------------------------------------------------------------------ Work: the Workspace

export type DocTemplate = "blank" | "outline" | "plan" | "decision" | "progress";

/** One thing in the Workspace: a doc, a link, or anything linked to a project. */
export interface WorkspaceItem {
  id: string;
  title: string;
  kind: "doc" | "link" | CaptureKind;
  url: string | null;
  excerpt: string;
  projects: { id: string; title: string; missing: boolean }[];
  updated_at: string;
  original: { filename: string; mime: string; size: number } | null;
}

export interface WorkspaceView {
  items: WorkspaceItem[];
  projects: { id: string; title: string; active: boolean }[];
  /** For one project: the agents that work on it. */
  agents?: { name: string; role: string; last_run?: { task_id: string; status: string; at: string } | null }[];
  /** For one project: the workflows that name it. */
  workflows?: { id: string; name: string; when: string; enabled: boolean; running: boolean; last_run: WorkflowRunSummary | null }[];
}

// ------------------------------------------------------------------ Work: Compose

/** What goes with a request: skills in order, one agent, notes, documents, a project. */
export interface ComposePicks {
  skills: string[];
  agent: string | null;
  docs: string[];
  library: string[];
  project: string | null;
}

export interface ComposeSpec extends ComposePicks {
  request: string;
}

/** The whole prompt a model gets, its size in tokens, and the short request for any AI. */
export interface ComposeAssembly {
  title: string;
  prompt: string;
  tokens: number;
  /** Counted exactly (a tokenizer), or estimated from the characters. */
  exact: boolean;
  parts: { label: string; tokens: number }[];
  brief: { available: boolean; entries: number; note: string | null };
  short: string;
  short_tokens: number;
  skills: string[];
  agent: string | null;
  makes_files: boolean;
}

/** A prompt kept word for word in the Brain's Library, in your own scope: its words with every
 * version, its tags and project, what it is used with, the files that came with it, and how
 * often it ran. Any AI connected to the Brain finds it by name; none gets it unasked. */
export interface SavedPrompt {
  /** Its card in the Brain. */
  id: string;
  /** Its file, under references/prompts/. */
  path: string;
  title: string;
  body: string;
  picks: ComposePicks;
  tags: string[];
  project: string | null;
  project_title: string | null;
  /** Where it came from: chat (saved by an AI in a conversation), upload (saved here). */
  origin: string | null;
  scope: string | null;
  revision: number;
  version: number;
  created_at: string | null;
  updated_at: string | null;
  archived_at: string | null;
  uses: number;
  last_used: string | null;
  /** Newest first; only on one prompt's page. */
  versions: { revision: number; title: string; body: string; at: string | null }[];
  attachments: { path: string; title: string; kind: "asset" | "reference" }[];
}

// ------------------------------------------------------------------ Work: Workflows

export type StepKind =
  | "skill"
  | "agent"
  | "prompt"
  | "connector"
  | "upkeep"
  | "ingest"
  | "distill"
  | "state"
  | "task"
  | "handoff"
  | "check";

/** The canvas's node library: each kind of step, what it takes and gives (BL 16.6). */
export interface NodeLibrary {
  kinds: { kind: StepKind; group: string; label: string; takes: string[]; gives: string[] }[];
  actions: { id: string; label: string; blurb?: string }[];
  ingest_sources: string[];
  triggers: { id: string; label: string; later?: boolean }[];
}

/** One box of a workflow: what it runs, and what it is given. */
export interface WorkflowStep {
  kind: StepKind;
  title?: string;
  ask?: string;
  skill?: string;
  agent?: string | null;
  prompt_id?: string | null;
  text?: string;
  skills?: string[];
  docs?: string[];
  library?: string[];
  meetings?: number;
  tools?: string[];
  writes?: boolean;
  action?: string;
  /** An ingestion step: library, url or folder, and the item or address. */
  source?: string;
  target?: string;
  /** A State step: the sheet, row and column it writes. */
  sheet?: string;
  row?: string;
  column?: string;
  /** A task or hand-off step. */
  to?: string;
  goal?: string | null;
  done_when?: string;
  next_step?: string;
}

/** When a workflow runs by itself, in the workspace's time zone. */
export interface WorkflowSchedule {
  kind: "manual" | "once" | "daily" | "weekly" | "monthly";
  at?: string;
  time?: string;
  days?: string[];
  day?: number;
}

export type WorkflowOutput = { kind: "outputs" } | { kind: "workspace"; doc_id: string | null };

export interface WorkflowRunSummary {
  id: string;
  status: WorkflowRunStatus;
  trigger: string;
  started_at: string;
  finished_at: string | null;
  note: string;
  step: number;
  steps: WorkflowStepStatus[];
}

export type WorkflowRunStatus = "running" | "waiting" | "done" | "failed" | "stopped";
export type WorkflowStepStatus = "pending" | "running" | "waiting" | "done" | "failed";

export interface Workflow {
  id: string;
  name: string;
  description: string;
  project: string | null;
  schedule: WorkflowSchedule;
  /** The schedule in words. */
  when: string;
  /** Any connected AI may start it (run_workflow). */
  ai: boolean;
  steps: WorkflowStep[];
  runner: "claude" | "any";
  output: WorkflowOutput;
  enabled: boolean;
  timezone: string;
  next_due_at: string | null;
  revision: number;
  version: number;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  last_run: WorkflowRunSummary | null;
  running: boolean;
}

export interface WorkflowStepResult {
  artifact_id?: string;
  version?: number;
  title?: string;
  excerpt?: string;
  text?: string;
  edited?: boolean;
}

export interface WorkflowRunStep {
  index: number;
  kind: StepKind;
  title: string;
  status: WorkflowStepStatus;
  task_id?: string;
  job_id?: string;
  started_at?: string;
  finished_at?: string;
  result?: WorkflowStepResult | null;
  read?: { ref: string; version: number }[];
  note?: string;
  ask?: string;
  /** For a step under way: where its task is (draft and ready: waiting for a model). */
  task_status?: string;
}

export interface WorkflowRun {
  id: string;
  workflow_id: string;
  workflow: string;
  status: WorkflowRunStatus;
  trigger: "now" | "schedule" | "ai";
  due_at: string | null;
  started_at: string;
  finished_at: string | null;
  step: number;
  steps: WorkflowRunStep[];
  revision: number;
  request: string;
  note: string;
  version: number;
  /** A check waiting for the owner: what to look at, and what the step before made. */
  waiting: { step: number; ask: string; result: WorkflowStepResult | null } | null;
}

export interface WorkflowTemplate {
  id: string;
  name: string;
  description: string;
  schedule: WorkflowSchedule;
  steps: WorkflowStep[];
  output: WorkflowOutput;
}

export interface WorkflowForm {
  name: string;
  description: string;
  project: string | null;
  schedule: WorkflowSchedule;
  ai: boolean;
  steps: WorkflowStep[];
  runner: "claude" | "any";
  output: WorkflowOutput;
  enabled: boolean;
}

/** The MCP servers Claude Code here connects to, to name a connector step's tools from. */
export interface Connectors {
  available: boolean;
  servers: { name: string; detail: string; connected: boolean; state: string }[];
  note: string;
}

// ------------------------------------------------------------------ Work: Skills, upgraded

/** What uses a skill, when it was edited and used, and its copies in Claude Code. */
export interface SkillAbout {
  used_by: { skills: string[]; agents: string[]; workflows: { id: string; name: string }[] };
  freshness: {
    last_edited: string | null;
    last_used: string | null;
    last_run_here: string | null;
    last_asked: string | null;
    /** What it loads that changed after its last edit. */
    changed: { key: string; title: string; at: string }[];
  };
  pushed: SkillCopy[];
}

/** A copy of a skill in Claude Code, and how many versions behind the Brain's it is. */
export interface SkillCopy {
  place: string;
  user: boolean;
  pushed_at: string | null;
  /** 0: current. null: older than the history kept. */
  behind: number | null;
}

/** A skill worth writing down: asks repeated with no skill, or a prompt run often. */
export interface SkillSuggestion {
  kind: "asks" | "prompt";
  key: string;
  title: string;
  count: number;
  examples: string[];
  apps: string[];
  last: string | null;
  prompt_id: string | null;
  /** What New skill starts from when it is accepted. */
  ask: string;
}

export interface SkillBroughtIn {
  name: string;
  replaced: boolean;
  files: number;
  /** What the Brain does not keep in a skill, with why. */
  skipped: string[];
}

// ---------------------------------------------------------------- the goal ladder (goals plan G1)

export type GoalCall = "on_track" | "at_risk" | "off_track";
export type GoalStatus =
  | GoalCall
  | "needs_attention"
  | "no_data"
  | "not_checked_in"
  | "paused"
  | "met"
  | "missed"
  | "dropped"
  | "retired";

export interface GoalMeasure {
  kind: "enter" | "at_most" | "at_least" | "reach_by" | "every_period" | "trend" | "judgment";
  signal?: string;
  params?: Record<string, number>;
  target?: number;
  unit?: string;
}

/** One goal as the app shows it: yours, or an agent's. */
export interface GoalView {
  id: string;
  title: string;
  level: "yours" | "agent";
  kept_by: string | null;
  why: string;
  serves: string[];
  measure: GoalMeasure | null;
  measure_words: string;
  due: string | null;
  cadence: "daily" | "weekly" | "monthly";
  lifecycle: "active" | "paused" | "met" | "missed" | "dropped" | "retired";
  started: string | null;
  status: GoalStatus;
  words: string;
  /** Your latest call, when it still stands. */
  call: GoalCall | null;
  /** A computed measure that disagrees with your call; your call stands. */
  flag: string;
  stale: boolean;
  now: number | null;
  target: number | null;
  unit: string | null;
  trend: number[];
  checked_at: string | null;
  checked_in_at: string | null;
  check_in_due: boolean;
  projects: { id: string; title: string; status: string }[];
  shared_plan: boolean;
  /** Suggested next steps waiting (your goals, on the ladder). */
  suggestions?: number;
}

export interface GoalSignal {
  name: string;
  label: string;
  params: Record<string, number>;
  available: boolean;
  waits_for: string | null;
  now: number | null;
}

export interface Ladder {
  purpose: { id: string; exists: boolean; text: string; signals: string[] };
  yours: GoalView[];
  agents: GoalView[];
  has_goals: boolean;
  check_ins_due: number;
  starters: { id: string; title: string; on: boolean }[];
  signals: GoalSignal[];
}

export interface GoalBlock {
  id: string;
  type: "note" | "checklist" | "doc" | "projects" | "links" | "decisions" | "sheet";
  title: string;
  shared: boolean;
  collapsed: boolean;
  column: 0 | 1;
  text?: string;
  items?: { text: string; done: boolean }[];
  doc_id?: string;
  doc_title?: string;
  links?: { title: string; url: string }[];
  sheet_id?: string;
  drives?: string;
  agg?: "latest" | "sum" | "average" | "count";
}

export interface GoalBoard {
  columns: 1 | 2;
  template: string;
  blocks: GoalBlock[];
  version: number;
}

export interface GoalSuggestion {
  id: string;
  text: string;
  source: string;
  at: string;
  status: "waiting" | "accepted" | "dismissed";
}

export interface GoalJournalEntry {
  at: string;
  kind: "check_in" | "decision" | "progress";
  by: string;
  call?: GoalCall;
  value?: number | null;
  line?: string;
  text?: string;
}

/** A goal with no per-page extras: what the shared pieces read. */
export type GoalBase = Omit<GoalView, "suggestions">;

export interface GoalPage extends GoalBase {
  /** The goal's tasks: what AI is doing for it. */
  tasks?: TaskItem[];
  journal: GoalJournalEntry[];
  checks: { at: string; value: number | null; status: string; source: "you" | "code"; note: string }[];
  plan: string;
  context: string;
  board: GoalBoard;
  suggestions: GoalSuggestion[];
  templates: { id: string; label: string }[];
}

export interface GoalDraft {
  title: string;
  why: string;
  due: string;
  cadence: "daily" | "weekly" | "monthly";
  measure: GoalMeasure | null;
  board: { wish?: string; outcome?: string; obstacle?: string; plan?: string };
  first_steps: string[];
  project: string;
}

export interface GoalCoachResult {
  questions?: string[];
  draft?: GoalDraft;
  error?: string;
}

export interface GoalsHome {
  has_goals: boolean;
  purpose: string;
  check_ins: GoalView[];
  agent_goals: GoalView[];
  review: {
    goals: { id: string; title: string; words: string; flag: string | null }[];
    agent_goals: { id: string; title: string; words: string }[];
    notes: { goal: string; at: string; line: string }[];
    next_steps: { goal: string; text: string }[];
  } | null;
}

/** An agent goal that slipped, waiting in Catch up (one card per slip). */
export interface GoalCard {
  key: string;
  goal: GoalView;
  why: string;
  at: string;
}

// ---------------------------------------------------------------- State and tasks (step 6)

export type ColumnType = "text" | "number" | "money" | "date" | "date_range" | "status" | "person" | "link" | "reference";
export type Friction = "free" | "confirm" | "locked";

export interface StateColumn {
  name: string;
  type: ColumnType;
  friction: Friction;
  age_days: number | null;
  source: string;
  sensitivity: string;
  options: string[];
  ref: string;
  formula: string;
  formula_words?: string;
}

export interface StateSheet {
  id: string;
  title: string;
  key: string;
  columns: StateColumn[];
  partition_by: string;
  scope: string;
  template: string;
  builtin: boolean;
  description: string;
}

export interface StateCell {
  value: string | number | null;
  at: string;
  by: string;
  said_by: string;
  as_of: string;
  source: string;
  ai: boolean;
  stale: boolean;
}

export interface StateEvent {
  kind: string;
  id?: string;
  at: string;
  column?: string;
  value?: string | number | null;
  by?: string;
  said_by?: string;
  source?: string;
  ai?: boolean;
  pending?: boolean;
  event?: string;
  key?: string;
}

export interface StateRow {
  id: string;
  key: string;
  aliases: string[];
  partition: string;
  created: string;
  updated: string;
  cells: Record<string, StateCell>;
  computed: Record<string, string | number | boolean | null>;
  pending: StateEvent[];
}

export interface StateSummary {
  rows: number;
  columns: Record<string, { filled: number; by_status?: Record<string, number>; sum?: number; average?: number | null }>;
}

export interface SheetView {
  sheet: StateSheet;
  rows: StateRow[];
  summary: StateSummary;
}

export interface StateWaiting {
  sheet: string;
  sheet_title: string;
  row: string;
  column: string;
  value: string | number | null;
  event: string;
  at: string;
  source: string;
}

export interface LiveOverview {
  sheets: StateSheet[];
  templates: { id: string; title: string; builtin: boolean; columns: string[] }[];
  waiting: StateWaiting[];
}

export type HandoffStatus = "open" | "handed_off" | "working" | "waiting_for_you" | "blocked" | "done" | "dropped";

export interface TaskCard {
  done_when?: string;
  done_so_far?: string;
  next_step?: string;
  decisions?: string;
  open_questions?: string;
  load?: string;
  reason?: string;
  by?: string;
  at?: string;
}

export interface TaskItem {
  id: string;
  row: string;
  task: string;
  goal: string | null;
  project: string | null;
  for: string | null;
  milestone: boolean;
  owner: string;
  owner_label: string;
  tool: string | null;
  status: HandoffStatus;
  status_words: string;
  due: string | null;
  evidence: string[];
  card: TaskCard;
  created: string;
  updated: string;
  days_open: number | null;
  since_update: number | null;
  unclaimed?: boolean;
  key?: string;
}

export interface TaskDetail extends TaskItem {
  log: StateEvent[];
  rendered: string;
}

export interface HandoffsNow {
  lanes: Record<"waiting_for_you" | "handed_off" | "working" | "blocked" | "open", TaskItem[]>;
  done_this_week: TaskItem[];
  count: number;
}

export interface TimelineEvent {
  at: string;
  task: string;
  title: string;
  owner: string;
  kind: "open" | "handoff" | "claim" | "save" | "finish" | "blocked" | "dropped";
  from?: string;
  to?: string;
}
