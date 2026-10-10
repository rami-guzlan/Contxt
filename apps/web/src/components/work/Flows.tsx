// Workflows as his sketches draw them: a strip of boxes and arrows (when it runs, each step,
// where what it makes goes), colored by the last run; and a workflow's card with Run now. Shared
// by Work's overview and the Workflows tab.

import { ArrowRight } from "lucide-react";
import { Link, useNavigate } from "react-router";

import { useAgent, useRunWorkflow } from "../../api/hooks";
import type { Workflow, WorkflowRunSummary, WorkflowStep } from "../../api/types";
import { when } from "../../lib/format";
import { ErrorNote, Pill } from "../ui";
import { STEP_NAMES, stepWords } from "./WorkflowEditor";
import { ScopeChip } from "./Scope";

export const workflowUrl = (id: string, run?: string) => `/work/workflows/${encodeURIComponent(id)}${run ? `?run=${encodeURIComponent(run)}` : ""}`;

export function FlowCard({ workflow }: { workflow: Workflow }) {
  const run = useRunWorkflow();
  const navigate = useNavigate();
  const last = workflow.last_run;
  return (
    <article className="flow-card">
      <header className="row flow-card-head">
        <h3>
          <Link to={workflowUrl(workflow.id)}>{workflow.name}</Link>
        </h3>
        <ScopeChip />
        {workflow.enabled ? null : <span className="muted small">Off</span>}
        {last ? <Pill status={last.status} /> : null}
        {workflow.running && last ? (
          <Link className="small" to={workflowUrl(workflow.id, last.id)}>
            See the run
          </Link>
        ) : (
          <button
            type="button"
            className="small"
            disabled={run.isPending || !!workflow.archived_at}
            onClick={() => run.mutate({ id: workflow.id }, { onSuccess: (made) => navigate(workflowUrl(workflow.id, made.id)) })}
          >
            Run now
          </button>
        )}
      </header>
      <FlowStrip steps={workflow.steps} whenWords={workflow.when} output={workflow.output.kind} last={last} />
      <p className="muted small">
        {workflow.next_due_at ? `Next ${when(workflow.next_due_at)}` : "Runs when you run it"}
        {last ? ` · last ran ${when(last.started_at)}${last.note ? `: ${last.note}` : ""}` : " · not run yet"}
      </p>
      <ErrorNote error={run.error} />
    </article>
  );
}

/** The workflow as boxes and arrows: when it runs, each step, where what it makes goes. */
export function FlowStrip({
  steps,
  whenWords,
  output,
  last,
}: {
  steps: WorkflowStep[];
  whenWords: string;
  output: "outputs" | "workspace";
  last?: WorkflowRunSummary | null;
}) {
  const { data: agent } = useAgent();
  const actions = new Map((agent?.actions ?? []).map((a) => [a.id, a.label]));
  return (
    <ol className="flow-strip" aria-label="Its steps">
      <li className="flow-box flow-trigger">{whenWords}</li>
      {steps.map((step, index) => (
        <li key={index} className={`flow-box flow-${last?.steps[index] ?? "idle"}`} title={STEP_NAMES[step.kind]}>
          <ArrowRight className="flow-arrow" aria-hidden="true" />
          <span className="flow-kind">{STEP_NAMES[step.kind]}</span>
          <span>{stepWords(step, actions)}</span>
        </li>
      ))}
      <li className="flow-box flow-output">
        <ArrowRight className="flow-arrow" aria-hidden="true" />
        {output === "workspace" ? "A Workspace doc" : "Outputs"}
      </li>
    </ol>
  );
}
