// Work, Workflows: steps that run as one thing, on a schedule, with a button, or from any AI you
// connect. Each is drawn as a strip of boxes (when, each step, where it goes), colored by its
// last run; a run that reaches a check waits here for your yes, your edit, or a stop.

import { Upload } from "lucide-react";
import { useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router";

import {
  useArchiveWorkflow,
  useDecideCheck,
  useImportWorkflow,
  useRunWorkflow,
  useStepResult,
  useStopRun,
  useWaitingRuns,
  useWorkflow,
  useWorkflowRuns,
  useWorkflows,
  useWorkflowTemplates,
  workflowExportUrl,
} from "../../api/hooks";
import type { Workflow, WorkflowForm, WorkflowRun, WorkflowStep, WorkflowTemplate } from "../../api/types";
import { Empty, ErrorNote, Field, Loading, Pill, Section, Tabs } from "../../components/ui";
import { FlowCard, FlowStrip, workflowUrl } from "../../components/work/Flows";
import { STEP_NAMES, WorkflowEditor, stepWords } from "../../components/work/WorkflowEditor";
import { when } from "../../lib/format";


const TRIGGER_WORDS: Record<string, string> = { now: "Run now", schedule: "On schedule", ai: "From an AI" };
const TASK_WORDS: Record<string, string> = {
  draft: "waiting for a model",
  ready: "waiting for a model",
  claimed: "a model took it",
  in_progress: "a model is working on it",
  review: "in review",
  blocked: "blocked: a person must act",
};

// ---------------------------------------------------------------- the list

export function WorkflowsPage() {
  const { data, isLoading, error } = useWorkflows();
  const { data: templates } = useWorkflowTemplates();
  const { data: waiting } = useWaitingRuns();
  const navigate = useNavigate();
  const bring = useImportWorkflow();
  const file = useRef<HTMLInputElement>(null);
  if (isLoading) return <Loading />;
  if (!data) return <ErrorNote error={error} />;
  return (
    <div className="work-tab workflows">
      <div className="work-intro">
        <p>
          Steps that run as one thing: on a schedule, with a button, or from any AI you connect. Each step reads what the step before made,
          and nothing is published or sent: what matters waits for your yes.
        </p>
        <div className="row">
          <Link className="button primary" to="/work/workflows/new">
            New workflow
          </Link>
          <button type="button" disabled={bring.isPending} onClick={() => file.current?.click()}>
            <Upload className="button-icon" aria-hidden="true" /> Bring one in
          </button>
          <input
            ref={file}
            type="file"
            hidden
            accept=".json,application/json"
            aria-label="A workflow file"
            onChange={(event) => {
              const picked = event.target.files?.[0];
              if (picked) bring.mutate(picked, { onSuccess: (made) => navigate(workflowUrl(made.id)) });
              event.target.value = "";
            }}
          />
        </div>
      </div>
      <ErrorNote error={bring.error} />
      {waiting?.length ? (
        <Section title="Waiting for you">
          <ul className="list" aria-label="Runs waiting for you">
            {waiting.map((run) => (
              <li key={run.id}>
                <Link to={workflowUrl(run.workflow_id, run.id)}>{run.workflow}</Link>
                <span className="muted small">
                  {" · "}
                  {run.waiting ? run.waiting.ask : run.steps[run.step]?.note || "A step waits for a person."} · started {when(run.started_at)}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
      {data.length ? (
        <ul className="flow-list" aria-label="Your workflows">
          {data.map((workflow) => (
            <li key={workflow.id}>
              <FlowCard workflow={workflow} />
            </li>
          ))}
        </ul>
      ) : (
        <Empty why="No workflows yet. Start from one below, or make one: a skill or an agent on a schedule, with a check before anything matters." />
      )}
      {templates?.length ? (
        <Section title="Start from one">
          <ul className="template-list" aria-label="Templates">
            {templates.map((t) => (
              <li key={t.id} className="template-card">
                <h3>{t.name}</h3>
                <p className="small">{t.description}</p>
                <FlowStrip steps={t.steps} whenWords={t.schedule.kind === "manual" ? "Run now" : "On a schedule"} output={t.output.kind} />
                <Link className="button" to={`/work/workflows/new?template=${encodeURIComponent(t.id)}`}>
                  Start from this
                </Link>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------- one workflow

export function WorkflowPage() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const { data: workflow, isLoading, error } = useWorkflow(id);
  const [tab, setTab] = useState<"runs" | "steps">(params.get("tab") === "steps" ? "steps" : "runs");
  const run = useRunWorkflow();
  const archive = useArchiveWorkflow();
  const navigate = useNavigate();
  const [request, setRequest] = useState("");
  if (isLoading) return <Loading />;
  if (!workflow) return <ErrorNote error={error} />;
  return (
    <div className="work-tab workflow-page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/work/workflows">Workflows</Link>
      </nav>
      <header className="stack-tight">
        <h2 className="workflow-title">{workflow.name}</h2>
        {workflow.description ? <p className="muted">{workflow.description}</p> : null}
        <p className="small muted">
          {workflow.enabled ? (workflow.next_due_at ? `Next ${when(workflow.next_due_at)}` : "Runs when you run it") : "Off: it runs only when you run it"}
          {` · revision ${workflow.revision}`}
          {workflow.ai ? " · any AI you connect may start it" : ""}
        </p>
      </header>
      <FlowStrip steps={workflow.steps} whenWords={workflow.when} output={workflow.output.kind} last={workflow.last_run} />
      <div className="row workflow-actions">
        <input
          aria-label="What this run is about (optional)"
          placeholder="What this run is about (optional)"
          value={request}
          onChange={(event) => setRequest(event.target.value)}
        />
        <button
          type="button"
          className="primary"
          disabled={workflow.running || run.isPending || !!workflow.archived_at}
          onClick={() =>
            run.mutate(
              { id: workflow.id, request },
              {
                onSuccess: (made) => {
                  setRequest("");
                  setTab("runs");
                  setParams({ run: made.id });
                },
              },
            )
          }
        >
          {workflow.running ? "Running" : "Run now"}
        </button>
        <a className="button" href={workflowExportUrl(workflow.id)} download>
          Take it as a file
        </a>
        {workflow.archived_at ? (
          <button type="button" onClick={() => archive.mutate({ id: workflow.id, back: true })}>
            Bring it back
          </button>
        ) : (
          <button type="button" onClick={() => archive.mutate({ id: workflow.id }, { onSuccess: () => navigate("/work/workflows") })}>
            Archive
          </button>
        )}
      </div>
      <ErrorNote error={run.error ?? archive.error} />
      <Tabs
        tabs={[
          { id: "runs", label: "Runs" },
          { id: "steps", label: "Its steps" },
        ]}
        active={tab}
        onChange={setTab}
      />
      {tab === "runs" ? (
        <Runs workflow={workflow} open={params.get("run")} />
      ) : (
        <WorkflowEditor key={workflow.version} workflow={workflow} onSaved={() => setTab("runs")} />
      )}
    </div>
  );
}

function Runs({ workflow, open }: { workflow: Workflow; open: string | null }) {
  const { data: runs, isLoading, error } = useWorkflowRuns(workflow.id);
  if (isLoading) return <Loading />;
  if (!runs) return <ErrorNote error={error} />;
  if (!runs.length) return <Empty why="Not run yet. Run it now, or wait for its time." />;
  return (
    <ol className="workflow-runs" aria-label="Runs">
      {runs.map((run, index) => (
        <li key={run.id}>
          <RunCard run={run} workflow={workflow} first={open ? run.id === open : index === 0} />
        </li>
      ))}
    </ol>
  );
}

function RunCard({ run, workflow, first }: { run: WorkflowRun; workflow: Workflow; first: boolean }) {
  const [open, setOpen] = useState(first);
  const stop = useStopRun();
  const going = run.status === "running" || run.status === "waiting";
  return (
    <article className="workflow-run" aria-label={`Run of ${when(run.started_at)}`}>
      <header className="row">
        <Pill status={run.status} />
        <span>{TRIGGER_WORDS[run.trigger] ?? run.trigger}</span>
        <span className="muted small">{when(run.started_at)}</span>
        {run.note ? <span className="muted small">{run.note}</span> : null}
        <button type="button" className="link small" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? "Hide the steps" : "Its steps"}
        </button>
        {going ? (
          <button type="button" className="small" disabled={stop.isPending} onClick={() => stop.mutate(run.id)}>
            Stop it
          </button>
        ) : null}
      </header>
      {run.request ? <p className="small">This run: {run.request}</p> : null}
      {run.waiting ? <CheckPanel run={run} /> : null}
      {open ? (
        <ol className="workflow-run-steps">
          {run.steps.map((step) => (
            <li key={step.index} className={`flow-${step.status}`}>
              <span className="workflow-step-number">{step.index + 1}</span>
              <span>{workflow.steps[step.index] ? stepWords(workflow.steps[step.index] as WorkflowStep) : STEP_NAMES[step.kind]}</span>
              <Pill status={step.status} />
              {step.task_status ? <span className="muted small">{TASK_WORDS[step.task_status] ?? step.task_status.replace(/_/g, " ")}</span> : null}
              {step.result?.title ? <span className="small">“{step.result.title}”</span> : null}
              {step.result?.text ? <span className="small">{step.result.text}</span> : null}
              {step.result?.edited ? <span className="muted small">(you edited it)</span> : null}
              {step.note ? <span className="muted small">{step.note}</span> : null}
              {step.result?.artifact_id ? <StepText run={run} index={step.index} /> : null}
            </li>
          ))}
        </ol>
      ) : null}
      <ErrorNote error={stop.error} />
    </article>
  );
}

/** What a step made, in full, on demand. */
function StepText({ run, index }: { run: WorkflowRun; index: number }) {
  const [open, setOpen] = useState(false);
  const { data } = useStepResult(run.id, open ? index : null);
  return (
    <>
      <button type="button" className="link small" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "Hide it" : "Read it"}
      </button>
      {open && data ? <pre className="workflow-result">{data.text}</pre> : null}
    </>
  );
}

/** A check: what the step before made, and go on, edit it first, or stop. */
function CheckPanel({ run }: { run: WorkflowRun }) {
  const before = run.waiting?.result ?? null;
  const index = run.steps.slice(0, run.step).reduce((found, step) => (step.result ? step.index : found), -1);
  const { data: full } = useStepResult(run.id, index >= 0 ? index : null);
  const decide = useDecideCheck();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const body = text ?? full?.text ?? before?.excerpt ?? before?.text ?? "";
  return (
    <section className="workflow-check" aria-label="Your check">
      <h3>Your check: {run.waiting?.ask}</h3>
      {before?.title ? <p className="small">The step before made “{before.title}”.</p> : null}
      {editing ? (
        <Field label="Edit it before it goes on">
          <textarea rows={10} value={body} onChange={(event) => setText(event.target.value)} />
        </Field>
      ) : (
        <pre className="workflow-result">{body || "It made no text."}</pre>
      )}
      <Field label="A note (optional)">
        <input value={note} onChange={(event) => setNote(event.target.value)} />
      </Field>
      <div className="row">
        <button
          type="button"
          className="primary"
          disabled={decide.isPending}
          onClick={() => decide.mutate({ runId: run.id, go: true, edit: editing && text !== null ? text : undefined, note })}
        >
          {editing ? "Go on with my edit" : "Looks good, go on"}
        </button>
        {before?.artifact_id && !editing ? (
          <button type="button" onClick={() => setEditing(true)}>
            Edit it first
          </button>
        ) : null}
        <button type="button" disabled={decide.isPending} onClick={() => decide.mutate({ runId: run.id, go: false, note })}>
          Stop here
        </button>
      </div>
      <ErrorNote error={decide.error} />
    </section>
  );
}

// ---------------------------------------------------------------- a new one

/** What a new workflow starts with: a template, an agent to schedule, or a step from Compose. */
function startingPoint(params: URLSearchParams, templates: WorkflowTemplate[] | undefined, step: WorkflowStep | null): Partial<WorkflowForm> | null {
  const template = params.get("template");
  if (template) {
    const found = templates?.find((t) => t.id === template);
    if (!found) return null;
    return { name: found.name, description: found.description, schedule: found.schedule, steps: found.steps, output: found.output };
  }
  const agent = params.get("agent");
  if (agent) {
    return {
      name: `${agent}, every week`,
      schedule: { kind: "weekly", days: ["mon"], time: "09:00" },
      steps: [{ kind: "agent", agent, ask: params.get("ask") ?? "", docs: [], library: [] }, { kind: "check", ask: "Read what it made." }],
      project: params.get("project"),
    };
  }
  if (step) {
    return { name: params.get("name") ?? "", schedule: { kind: "weekly", days: ["mon"], time: "09:00" }, steps: [step] };
  }
  return {};
}

export function NewWorkflowPage() {
  const [params] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { data: templates, isLoading } = useWorkflowTemplates();
  const step = ((location.state as { step?: WorkflowStep } | null)?.step ?? null) as WorkflowStep | null;
  const start = startingPoint(params, templates, step);
  if (isLoading && params.get("template")) return <Loading />;
  return (
    <div className="work-tab workflow-page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/work/workflows">Workflows</Link>
      </nav>
      <h2 className="workflow-title">New workflow</h2>
      {start ? (
        <WorkflowEditor initial={start} onSaved={(saved) => navigate(workflowUrl(saved.id))} />
      ) : (
        <ErrorNote error={new Error("That template is not here.")} />
      )}
    </div>
  );
}
