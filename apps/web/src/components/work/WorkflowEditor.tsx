// The workflow builder: a name, when it runs, its steps as boxes in order, where it runs and
// where what it makes goes. Straight lines for now: each step reads what the step before made.

import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import {
  useAgent,
  useBrainFiles,
  useBrainProjects,
  useConnectors,
  useNotes,
  useSavedPrompts,
  useSaveWorkflow,
  useSkills,
  useWorkAgents,
} from "../../api/hooks";
import type { StepKind, Workflow, WorkflowForm, WorkflowSchedule, WorkflowStep } from "../../api/types";
import { CAPTURE_NAMES } from "../CaptureParts";
import { ErrorNote, Field } from "../ui";
import { linesOf, PickMany, textOf } from "./PickMany";
import { WorkflowCanvas } from "./WorkflowCanvas";

export const STEP_NAMES: Record<StepKind, string> = {
  skill: "Skill",
  agent: "Agent",
  prompt: "Prompt",
  connector: "Connector",
  upkeep: "Brain upkeep",
  ingest: "Bring in",
  distill: "Find what to remember",
  state: "Update a sheet",
  task: "Open a task",
  handoff: "Hand off",
  check: "Your check",
};
export const STEP_HINTS: Record<StepKind, string> = {
  skill: "Follows one of your skills.",
  agent: "One of your agents does it, with its role and what it points to.",
  prompt: "A saved prompt, or one written here, with its picks.",
  connector: "Reads from a tool you connected to Claude Code (HubSpot, Gmail), with the tools you name.",
  upkeep: "One of the knowledge agent's upkeep jobs; what it suggests waits in Catch up.",
  ingest: "Refreshes a Library item, fetches a page into the Library, or sweeps your watched folders.",
  distill: "Reads what the step before made and suggests what should last in the Brain; it waits in Catch up.",
  state: "Writes what the step before made into one cell of a State sheet, under the column's rule.",
  task: "Opens a task in the Tasks sheet, for you or an AI.",
  handoff: "Hands the task the step before opened to an AI or a person, with when it is done.",
  check: "The run waits for you: go on, edit what came before, or stop.",
};
const DAYS = [
  ["mon", "Mon"],
  ["tue", "Tue"],
  ["wed", "Wed"],
  ["thu", "Thu"],
  ["fri", "Fri"],
  ["sat", "Sat"],
  ["sun", "Sun"],
] as const;

export const EMPTY_FORM: WorkflowForm = {
  name: "",
  description: "",
  project: null,
  schedule: { kind: "manual" },
  ai: false,
  steps: [],
  runner: "claude",
  output: { kind: "outputs" },
  enabled: true,
};

const short = (text: string | undefined, limit = 30) => {
  const flat = (text ?? "").replace(/\s+/g, " ").trim();
  return flat.length > limit ? `${flat.slice(0, limit - 1).trimEnd()}…` : flat;
};

/** A step's box, in a few words. */
export function stepWords(step: WorkflowStep, actions?: Map<string, string>): string {
  switch (step.kind) {
    case "skill":
      return step.skill ? `/${step.skill}` : "A skill";
    case "agent":
      return step.agent ? `Agent ${step.agent}` : "An agent";
    case "prompt":
      return step.prompt_id ? "Saved prompt" : short(step.text) || "Prompt";
    case "connector":
      return `Connector${step.tools?.length ? `: ${step.tools.length} tool${step.tools.length === 1 ? "" : "s"}` : ""}`;
    case "upkeep":
      return actions?.get(step.action ?? "") ?? step.action ?? "Brain upkeep";
    case "ingest":
      return step.source === "folder" ? "Sweep the folders" : step.source === "url" ? `Fetch ${short(step.target, 24) || "a page"}` : `Refresh ${short(step.target, 24) || "an item"}`;
    case "distill":
      return "Find what to remember";
    case "state":
      return step.sheet ? `${step.sheet}: ${step.row || "a row"}, ${step.column || "a column"}` : "Update a sheet";
    case "task":
      return short(step.ask) || "Open a task";
    case "handoff":
      return step.to ? `Hand to ${step.to}` : "Hand off";
    case "check":
      return short(step.ask) || "Your check";
  }
}

function newStep(kind: StepKind): WorkflowStep {
  switch (kind) {
    case "skill":
      return { kind, skill: "", ask: "", docs: [], library: [], meetings: 0 };
    case "agent":
      return { kind, agent: "", ask: "", docs: [], library: [] };
    case "prompt":
      return { kind, prompt_id: null, text: "", skills: [], docs: [], library: [], meetings: 0 };
    case "connector":
      return { kind, ask: "", tools: [], writes: false };
    case "upkeep":
      return { kind, action: "tidy-repeats" };
    case "ingest":
      return { kind, source: "folder", target: "" };
    case "distill":
      return { kind, ask: "" };
    case "state":
      return { kind, sheet: "", row: "", column: "" };
    case "task":
      return { kind, ask: "", to: "you" };
    case "handoff":
      return { kind, to: "Claude Code", done_when: "", next_step: "" };
    case "check":
      return { kind, ask: "Read what the step before made." };
  }
}

export function WorkflowEditor({
  workflow,
  initial,
  onSaved,
}: {
  workflow?: Workflow;
  initial?: Partial<WorkflowForm>;
  onSaved: (saved: Workflow) => void;
}) {
  const save = useSaveWorkflow();
  const { data: projects } = useBrainProjects();
  const { data: docs } = useNotes();
  const [form, setForm] = useState<WorkflowForm>(() =>
    workflow
      ? {
          name: workflow.name,
          description: workflow.description,
          project: workflow.project,
          schedule: workflow.schedule,
          ai: workflow.ai,
          steps: workflow.steps,
          runner: workflow.runner,
          output: workflow.output,
          enabled: workflow.enabled,
        }
      : { ...EMPTY_FORM, ...initial },
  );
  const set = (changes: Partial<WorkflowForm>) => setForm((f) => ({ ...f, ...changes }));
  const setStep = (index: number, step: WorkflowStep) => set({ steps: form.steps.map((s, n) => (n === index ? step : s)) });
  const move = (index: number, by: number) => {
    const next = [...form.steps];
    const [taken] = next.splice(index, 1);
    if (taken) next.splice(index + by, 0, taken);
    set({ steps: next });
  };
  const written = (docs ?? []).filter((n) => (n.capture ?? "note") === "note");
  const [view, setView] = useState<"canvas" | "list">("canvas");
  const [picked, setPicked] = useState<number | null>(null);
  const add = (kind: StepKind) => {
    set({ steps: [...form.steps, newStep(kind)] });
    setPicked(form.steps.length);
  };
  const pickedStep = picked != null ? form.steps[picked] : undefined;
  const outputWords =
    form.output.kind === "outputs"
      ? "Outputs"
      : form.output.doc_id
        ? `The next version of ${written.find((d) => d.id === (form.output as { doc_id: string | null }).doc_id)?.title ?? "a doc"}`
        : "A new Workspace doc";
  return (
    <form
      className="stack workflow-editor"
      aria-label="The workflow"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate({ ...form, id: workflow?.id, expected_version: workflow?.version }, { onSuccess: onSaved });
      }}
    >
      <div className="grid-2">
        <Field label="Its name">
          <input required maxLength={120} value={form.name} placeholder="For example: Weekly LinkedIn plan" onChange={(event) => set({ name: event.target.value })} />
        </Field>
        <Field label="For a project (optional)" hint="It shows on the project's page.">
          <select value={form.project ?? ""} onChange={(event) => set({ project: event.target.value || null })}>
            <option value="">None</option>
            {(projects ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <Field label="What it is for (optional)">
        <textarea rows={2} maxLength={2000} value={form.description} onChange={(event) => set({ description: event.target.value })} />
      </Field>
      <fieldset className="workflow-when">
        <legend>When it runs</legend>
        <ScheduleField value={form.schedule} onChange={(schedule) => set({ schedule })} />
        <label className="check">
          <input type="checkbox" checked={form.ai} onChange={(event) => set({ ai: event.target.checked })} />
          Any AI you connect may start it too (run_workflow)
        </label>
        <label className="check">
          <input type="checkbox" checked={form.enabled} onChange={(event) => set({ enabled: event.target.checked })} />
          On: it runs by itself when its time comes
        </label>
      </fieldset>
      <section aria-label="Steps" className="stack">
        <div className="row">
          <h3>Steps, in order</h3>
          <span className="row small" role="group" aria-label="How to show the steps">
            <button type="button" className={view === "canvas" ? "pill active" : "link small"} aria-pressed={view === "canvas"} onClick={() => setView("canvas")}>
              Canvas
            </button>
            <button type="button" className={view === "list" ? "pill active" : "link small"} aria-pressed={view === "list"} onClick={() => setView("list")}>
              List
            </button>
          </span>
        </div>
        {view === "canvas" ? (
          <>
            <WorkflowCanvas
              steps={form.steps}
              when={workflow?.when ?? (form.schedule.kind === "manual" ? "When you run it" : "On its schedule")}
              output={outputWords}
              picked={picked}
              statuses={workflow?.last_run?.steps}
              onPick={setPicked}
              onAdd={add}
            />
            {pickedStep && picked != null ? (
              <div className="workflow-step-box" aria-label="The picked step">
                <StepEditor
                  step={pickedStep}
                  index={picked}
                  count={form.steps.length}
                  onChange={(next) => setStep(picked, next)}
                  onMove={(by) => {
                    move(picked, by);
                    setPicked(picked + by);
                  }}
                  onRemove={() => {
                    set({ steps: form.steps.filter((_, n) => n !== picked) });
                    setPicked(null);
                  }}
                />
                {workflow?.last_run?.steps[picked] ? (
                  <p className="muted small">
                    Last run: {workflow.last_run.steps[picked]}
                    {workflow.last_run.note ? ` (${workflow.last_run.note})` : ""}
                  </p>
                ) : null}
              </div>
            ) : (
              <p className="muted small">{form.steps.length ? "Pick a box to set it up." : "Add the first step from the library."}</p>
            )}
          </>
        ) : form.steps.length ? (
          <ol className="workflow-steps">
            {form.steps.map((step, index) => (
              <li key={index} className="workflow-step-box">
                <StepEditor
                  step={step}
                  index={index}
                  count={form.steps.length}
                  onChange={(next) => setStep(index, next)}
                  onMove={(by) => move(index, by)}
                  onRemove={() => set({ steps: form.steps.filter((_, n) => n !== index) })}
                />
              </li>
            ))}
          </ol>
        ) : (
          <p className="muted small">No steps yet. Add the first: a skill, an agent or a prompt.</p>
        )}
        {view === "list" ? (
          <div className="row workflow-add" role="group" aria-label="Add a step">
            {(Object.keys(STEP_NAMES) as StepKind[]).map((kind) => (
              <button key={kind} type="button" title={STEP_HINTS[kind]} onClick={() => set({ steps: [...form.steps, newStep(kind)] })}>
                <Plus className="button-icon" aria-hidden="true" /> {STEP_NAMES[kind]}
              </button>
            ))}
          </div>
        ) : null}
      </section>
      <div className="grid-2">
        <Field label="Where it runs">
          <select value={form.runner} onChange={(event) => set({ runner: event.target.value as WorkflowForm["runner"] })}>
            <option value="claude">Claude Code on this computer</option>
            <option value="any">Any AI you connect (it picks up each step)</option>
          </select>
        </Field>
        <Field label="What it makes goes to">
          <select
            value={form.output.kind === "workspace" ? form.output.doc_id ?? "new" : "outputs"}
            onChange={(event) => {
              const value = event.target.value;
              set({ output: value === "outputs" ? { kind: "outputs" } : { kind: "workspace", doc_id: value === "new" ? null : value } });
            }}
          >
            <option value="outputs">Outputs</option>
            <option value="new">A new Workspace doc</option>
            {written.map((d) => (
              <option key={d.id} value={d.id}>
                The next version of {d.title}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <p className="muted small">Nothing a workflow runs publishes or sends: each step's work is a draft or a suggestion for you.</p>
      <div className="row">
        <button type="submit" className="primary" disabled={!form.name.trim() || !form.steps.length || save.isPending}>
          {workflow ? "Save the changes" : "Save the workflow"}
        </button>
      </div>
      <ErrorNote error={save.error} />
    </form>
  );
}

function ScheduleField({ value, onChange }: { value: WorkflowSchedule; onChange: (schedule: WorkflowSchedule) => void }) {
  const time = value.time ?? "09:00";
  return (
    <div className="row workflow-schedule">
      <Field label="How often">
        <select
          value={value.kind}
          onChange={(event) => {
            const kind = event.target.value as WorkflowSchedule["kind"];
            if (kind === "manual") onChange({ kind });
            else if (kind === "once") onChange({ kind, at: value.at ?? "" });
            else if (kind === "weekly") onChange({ kind, time, days: value.days?.length ? value.days : ["mon"] });
            else if (kind === "monthly") onChange({ kind, time, day: value.day ?? 1 });
            else onChange({ kind, time });
          }}
        >
          <option value="manual">Only when I run it</option>
          <option value="once">Once</option>
          <option value="daily">Every day</option>
          <option value="weekly">Every week</option>
          <option value="monthly">Every month</option>
        </select>
      </Field>
      {value.kind === "once" ? (
        <Field label="On">
          <input type="datetime-local" value={value.at ?? ""} onChange={(event) => onChange({ kind: "once", at: event.target.value })} />
        </Field>
      ) : null}
      {value.kind === "weekly" ? (
        <div className="field">
          <span className="field-label">On</span>
          <div className="row workflow-days" role="group" aria-label="Days">
            {DAYS.map(([id, name]) => (
              <label key={id} className="check">
                <input
                  type="checkbox"
                  checked={(value.days ?? []).includes(id)}
                  onChange={(event) =>
                    onChange({ ...value, days: event.target.checked ? [...(value.days ?? []), id] : (value.days ?? []).filter((d) => d !== id) })
                  }
                />
                {name}
              </label>
            ))}
          </div>
        </div>
      ) : null}
      {value.kind === "monthly" ? (
        <Field label="On day">
          <input type="number" min={1} max={31} value={value.day ?? 1} onChange={(event) => onChange({ ...value, day: Number(event.target.value) || 1 })} />
        </Field>
      ) : null}
      {value.kind === "daily" || value.kind === "weekly" || value.kind === "monthly" ? (
        <Field label="At">
          <input type="time" value={time} onChange={(event) => onChange({ ...value, time: event.target.value })} />
        </Field>
      ) : null}
    </div>
  );
}

function StepEditor({
  step,
  index,
  count,
  onChange,
  onMove,
  onRemove,
}: {
  step: WorkflowStep;
  index: number;
  count: number;
  onChange: (step: WorkflowStep) => void;
  onMove: (by: number) => void;
  onRemove: () => void;
}) {
  const set = (changes: Partial<WorkflowStep>) => onChange({ ...step, ...changes });
  return (
    <div className="stack-tight">
      <header className="row workflow-step-head">
        <span className="workflow-step-number">{index + 1}</span>
        <strong>{STEP_NAMES[step.kind]}</strong>
        <span className="muted small">{STEP_HINTS[step.kind]}</span>
        <span className="row workflow-step-tools">
          <button type="button" className="icon-button" aria-label={`Move step ${index + 1} up`} disabled={index === 0} onClick={() => onMove(-1)}>
            <ArrowUp className="button-icon" aria-hidden="true" />
          </button>
          <button type="button" className="icon-button" aria-label={`Move step ${index + 1} down`} disabled={index === count - 1} onClick={() => onMove(1)}>
            <ArrowDown className="button-icon" aria-hidden="true" />
          </button>
          <button type="button" className="icon-button" aria-label={`Take out step ${index + 1}`} onClick={onRemove}>
            <Trash2 className="button-icon" aria-hidden="true" />
          </button>
        </span>
      </header>
      {step.kind === "skill" ? <SkillStep step={step} set={set} /> : null}
      {step.kind === "agent" ? <AgentStep step={step} set={set} /> : null}
      {step.kind === "prompt" ? <PromptStep step={step} set={set} /> : null}
      {step.kind === "connector" ? <ConnectorStep step={step} set={set} /> : null}
      {step.kind === "upkeep" ? <UpkeepStep step={step} set={set} /> : null}
      {step.kind === "ingest" ? <IngestStep step={step} set={set} /> : null}
      {step.kind === "state" ? <StateStep step={step} set={set} /> : null}
      {step.kind === "task" ? <TaskStep step={step} set={set} /> : null}
      {step.kind === "handoff" ? <HandoffStep step={step} set={set} /> : null}
      {step.kind === "check" ? (
        <Field label="What to look at">
          <input value={step.ask ?? ""} onChange={(event) => set({ ask: event.target.value })} />
        </Field>
      ) : null}
    </div>
  );
}

type StepProps = { step: WorkflowStep; set: (changes: Partial<WorkflowStep>) => void };

function Ask({ step, set, label = "What it should do" }: StepProps & { label?: string }) {
  return (
    <Field label={label}>
      <textarea rows={2} maxLength={4000} value={step.ask ?? ""} onChange={(event) => set({ ask: event.target.value })} />
    </Field>
  );
}

/** Notes and documents a step reads, and recent meetings. */
function Inputs({ step, set, meetings = true }: StepProps & { meetings?: boolean }) {
  const { data: notes } = useNotes();
  const { data: files } = useBrainFiles();
  return (
    <div className="compose-pickers">
      <PickMany
        label="Notes and docs it reads"
        empty="None"
        options={(notes ?? []).map((n) => ({ value: n.id, label: n.title, hint: CAPTURE_NAMES[n.capture ?? "note"] }))}
        value={step.docs ?? []}
        onChange={(docs) => set({ docs })}
        max={5}
      />
      <PickMany
        label="Documents it reads whole"
        empty="None"
        options={(files?.references ?? []).map((f) => ({ value: f.path, label: f.title, hint: f.project_title ?? f.path }))}
        value={step.library ?? []}
        onChange={(library) => set({ library })}
        max={5}
      />
      {meetings ? (
        <Field label="Recent meetings (days)" hint="The latest recordings and transcripts, up to three. 0 for none.">
          <input type="number" min={0} max={30} value={step.meetings ?? 0} onChange={(event) => set({ meetings: Math.max(0, Math.min(30, Number(event.target.value) || 0)) })} />
        </Field>
      ) : null}
    </div>
  );
}

function SkillStep({ step, set }: StepProps) {
  const { data: skills } = useSkills();
  const runnable = (skills?.skills ?? []).filter((s) => s.use === "run");
  return (
    <>
      <Field label="The skill">
        <select value={step.skill ?? ""} onChange={(event) => set({ skill: event.target.value })}>
          <option value="">Choose a skill</option>
          {runnable.map((s) => (
            <option key={s.name} value={s.name}>
              /{s.name}
            </option>
          ))}
        </select>
      </Field>
      <Ask step={step} set={set} />
      <Inputs step={step} set={set} />
    </>
  );
}

function AgentStep({ step, set }: StepProps) {
  const { data: agents } = useWorkAgents();
  return (
    <>
      <Field label="The agent">
        <select value={step.agent ?? ""} onChange={(event) => set({ agent: event.target.value })}>
          <option value="">Choose an agent</option>
          {(agents ?? [])
            .filter((a) => a.status !== "archived")
            .map((a) => (
              <option key={a.name} value={a.name}>
                {a.name}: {a.role}
              </option>
            ))}
        </select>
      </Field>
      <Ask step={step} set={set} label="What it should do this time" />
      <Inputs step={step} set={set} meetings={false} />
    </>
  );
}

function PromptStep({ step, set }: StepProps) {
  const { data: prompts } = useSavedPrompts();
  const { data: skills } = useSkills();
  const saved = !!step.prompt_id;
  return (
    <>
      <Field label="The prompt">
        <select value={step.prompt_id ?? ""} onChange={(event) => set({ prompt_id: event.target.value || null })}>
          <option value="">Write it here</option>
          {(prompts ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              Saved: {p.title}
            </option>
          ))}
        </select>
      </Field>
      {saved ? (
        <p className="muted small">It runs the saved prompt as it is when the step starts, with its picks.</p>
      ) : (
        <>
          <Field label="What it asks">
            <textarea rows={3} maxLength={4000} value={step.text ?? ""} onChange={(event) => set({ text: event.target.value })} />
          </Field>
          <PickMany
            label="Skills to follow"
            empty="None: the Brain picks what fits"
            options={(skills?.skills ?? []).filter((s) => s.use === "run").map((s) => ({ value: s.name, label: `/${s.name}` }))}
            value={step.skills ?? []}
            onChange={(next) => set({ skills: next })}
            max={6}
            ordered
          />
        </>
      )}
      <Inputs step={step} set={set} />
    </>
  );
}

function ConnectorStep({ step, set }: StepProps) {
  const [looking, setLooking] = useState(false);
  // The box keeps what is typed (a new line included); the step keeps the tools in it.
  const [raw, setRaw] = useState(() => textOf(step.tools ?? []));
  const { data: found, isFetching, error } = useConnectors(looking);
  return (
    <>
      <Ask step={step} set={set} label="What to find" />
      <Field label="The tools it may use, one per line" hint="Each in full, like mcp__hubspot__search_crm_objects. Name tools that read.">
        <textarea
          rows={3}
          className="mono"
          value={raw}
          onChange={(event) => {
            setRaw(event.target.value);
            set({ tools: linesOf(event.target.value) });
          }}
        />
      </Field>
      <div className="row small">
        <button type="button" className="link" disabled={isFetching} onClick={() => setLooking(true)}>
          {isFetching ? "Asking Claude Code…" : "Which connectors does Claude Code have?"}
        </button>
      </div>
      {found ? (
        <p className="muted small">
          {found.servers.length
            ? `Connected: ${found.servers.map((s) => `${s.name}${s.connected ? "" : " (not answering)"}`).join(", ")}. ${found.note}`
            : found.note}
        </p>
      ) : null}
      <ErrorNote error={error} />
      <label className="check">
        <input type="checkbox" checked={!!step.writes} onChange={(event) => set({ writes: event.target.checked })} />
        Some of these tools write (it may change things in that tool)
      </label>
      {step.writes ? (
        <p className="warning small">Only for tools you trust to write: it may change what the request asks for in that tool, and says what it changed.</p>
      ) : (
        <p className="muted small">It runs on Claude Code here with your own connectors, using only these tools. Contxt never sees their sign-ins.</p>
      )}
    </>
  );
}

function IngestStep({ step, set }: StepProps) {
  return (
    <div className="grid-2">
      <Field label="What it brings in">
        <select value={step.source ?? "folder"} onChange={(event) => set({ source: event.target.value })}>
          <option value="folder">Sweep my watched folders</option>
          <option value="library">Refresh a Library item</option>
          <option value="url">Fetch a page into the Library</option>
        </select>
      </Field>
      {step.source && step.source !== "folder" ? (
        <Field label={step.source === "url" ? "The address" : "The Library item"}>
          <input value={step.target ?? ""} onChange={(event) => set({ target: event.target.value })} />
        </Field>
      ) : null}
    </div>
  );
}

function StateStep({ step, set }: StepProps) {
  return (
    <div className="grid-2">
      <Field label="The sheet">
        <input value={step.sheet ?? ""} placeholder="accounts" onChange={(event) => set({ sheet: event.target.value })} />
      </Field>
      <Field label="The row">
        <input value={step.row ?? ""} placeholder="Northwind" onChange={(event) => set({ row: event.target.value })} />
      </Field>
      <Field label="The column">
        <input value={step.column ?? ""} placeholder="Next step" onChange={(event) => set({ column: event.target.value })} />
      </Field>
    </div>
  );
}

function TaskStep({ step, set }: StepProps) {
  return (
    <div className="grid-2">
      <Ask step={step} set={set} label="The task" />
      <Field label="For" hint="you, or an AI or person to hand it to at once">
        <input value={step.to ?? "you"} onChange={(event) => set({ to: event.target.value })} />
      </Field>
    </div>
  );
}

function HandoffStep({ step, set }: StepProps) {
  return (
    <div className="grid-2">
      <Field label="To">
        <input value={step.to ?? ""} onChange={(event) => set({ to: event.target.value })} />
      </Field>
      <Field label="Done when">
        <input value={step.done_when ?? ""} onChange={(event) => set({ done_when: event.target.value })} />
      </Field>
      <Field label="The next step">
        <input value={step.next_step ?? ""} onChange={(event) => set({ next_step: event.target.value })} />
      </Field>
    </div>
  );
}

function UpkeepStep({ step, set }: StepProps) {
  const { data: agent } = useAgent();
  return (
    <Field label="The upkeep job">
      <select value={step.action ?? ""} onChange={(event) => set({ action: event.target.value })}>
        {(agent?.actions ?? []).map((a) => (
          <option key={a.id} value={a.id}>
            {a.label}: {a.blurb}
          </option>
        ))}
        {!agent ? <option value={step.action ?? ""}>{step.action}</option> : null}
      </select>
    </Field>
  );
}
