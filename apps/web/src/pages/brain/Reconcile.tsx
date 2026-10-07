// Reconciling two pieces of context that step on each other: the person says which one is
// current, a model (Claude Code on this computer, or any connected one) rewrites the other so
// both can stand, and its suggestion is reviewed right here, beside the pair, before anything
// changes.

import { useState } from "react";
import { Link } from "react-router";

import { post } from "../../api/client";
import { keys, useActors, useInvalidate, useRunners, useTaskRuns } from "../../api/hooks";
import type { BrainDecision, LocalRun, Reconciliation, RelatedEntry, ReviewProposal, Task } from "../../api/types";
import { Compare } from "../../components/Diff";
import { CopyPrompt, RunConsole } from "../../components/RunNow";
import { ErrorNote } from "../../components/ui";

const WORKING = ["draft", "ready", "claimed", "in_progress"];

type Current = "proposal" | "entry";

export function Reconcile({
  proposal,
  entry,
  name,
  reconciliation,
  suggestion,
  onRun,
  busy,
}: {
  proposal: ReviewProposal;
  entry: RelatedEntry;
  name: string;
  reconciliation?: Reconciliation;
  suggestion?: ReviewProposal;
  onRun: (decisions: BrainDecision[]) => void;
  busy: boolean;
}) {
  const [runId, setRunId] = useState<string | null>(null);
  if (reconciliation && suggestion) {
    return (
      <Suggested
        proposal={proposal}
        entry={entry}
        name={name}
        reconciliation={reconciliation}
        suggestion={suggestion}
        onRun={onRun}
        busy={busy}
      />
    );
  }
  if (reconciliation && WORKING.includes(reconciliation.status)) {
    return (
      <div className="reconcile">
        <p className="muted small">
          {reconciliation.status === "draft"
            ? "The reconcile request is waiting for a model to take it."
            : "A model is reconciling these two. Its suggestion appears here when it is done."}
        </p>
        {runId ? <RunConsole runId={runId} /> : null}
      </div>
    );
  }
  return (
    <Chooser
      proposal={proposal}
      entry={entry}
      finishedEmpty={!!reconciliation}
      lastTask={reconciliation?.task_id}
      runId={runId}
      onStarted={setRunId}
    />
  );
}

/** Which one is current, and who reconciles them: this computer's CLI, or a connected model. */
function Chooser({
  proposal,
  entry,
  finishedEmpty,
  lastTask,
  runId,
  onStarted,
}: {
  proposal: ReviewProposal;
  entry: RelatedEntry;
  finishedEmpty: boolean;
  lastTask?: string;
  runId: string | null;
  onStarted: (runId: string) => void;
}) {
  const { data: runners } = useRunners();
  const invalidate = useInvalidate();
  const [current, setCurrent] = useState<Current>("proposal");
  const [asking, setAsking] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const runner = runners?.find((r) => r.one_click && r.installed && r.signed_in !== false);
  const group = `current-${proposal.id}-${entry.id}`;

  async function startHere() {
    if (!runner) return;
    setStarting(true);
    setError(null);
    try {
      const task = await post<Task>("/api/brain/reconcile", { proposal_id: proposal.id, entry_id: entry.id, current });
      const run = await post<LocalRun>(`/api/runners/${runner.id}/runs`, { task_id: task.id });
      onStarted(run.id);
      await invalidate(keys.brain, keys.tasks);
    } catch (caught) {
      setError(caught);
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="reconcile">
      <fieldset className="relation-choice">
        <legend>Or keep both, reconciled: which one is current?</legend>
        <label className="checkbox">
          <input type="radio" name={group} checked={current === "proposal"} onChange={() => setCurrent("proposal")} />
          The suggestion
        </label>
        <label className="checkbox">
          <input type="radio" name={group} checked={current === "entry"} onChange={() => setCurrent("entry")} />
          {`“${entry.title}”, in the Brain`}
        </label>
      </fieldset>
      <p className="muted small">
        {current === "proposal"
          ? `A model rewrites “${entry.title}” so it no longer steps on the suggestion.`
          : "A model rewrites the suggestion so it no longer steps on the note."}{" "}
        You review the rewrite here before anything changes.
        {finishedEmpty && lastTask ? (
          <>
            {" "}
            The last request brought no suggestion
            <LastRun taskId={lastTask} />.
          </>
        ) : null}
      </p>
      <div className="row small">
        {runner ? (
          <button type="button" className="primary" disabled={starting || !!runId} onClick={() => void startHere()}>
            Reconcile with {runner.label}
          </button>
        ) : null}
        <button type="button" onClick={() => setAsking((on) => !on)}>
          {runner ? "Or use a connected model" : "Reconcile with a connected model"}
        </button>
      </div>
      {!runner ? (
        <p className="muted small">
          <Link to="/settings?tab=connections#runners">Set up Claude Code on this computer</Link> to do this in one click.
        </p>
      ) : null}
      {asking ? <PromptFor proposal={proposal} entry={entry} current={current} /> : null}
      <ErrorNote error={error} />
      {runId ? <RunConsole runId={runId} /> : null}
    </div>
  );
}

/** The copied-prompt path: a request assigned to the chosen model, and the prompt to paste. */
function PromptFor({ proposal, entry, current }: { proposal: ReviewProposal; entry: RelatedEntry; current: Current }) {
  const { data: actors } = useActors();
  const invalidate = useInvalidate();
  const models = (actors ?? []).filter((a) => a.kind === "model" && !a.disabled_at);
  const [chosen, setChosen] = useState("");
  const [taskId, setTaskId] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const model = chosen || models[0]?.id || "";

  async function create() {
    setError(null);
    try {
      const task = await post<Task>("/api/brain/reconcile", {
        proposal_id: proposal.id,
        entry_id: entry.id,
        current,
        assignee_id: model,
      });
      setTaskId(task.id);
      await invalidate(keys.brain, keys.tasks);
    } catch (caught) {
      setError(caught);
    }
  }

  if (!models.length) {
    return (
      <p className="muted small">
        No model is connected yet. <Link to="/settings?tab=connections">Connect one</Link>, then come back.
      </p>
    );
  }
  return (
    <div className="row small">
      {taskId ? (
        <>
          <CopyPrompt taskId={taskId} />
          <span className="muted">Paste it into that model; its suggestion appears here.</span>
        </>
      ) : (
        <>
          <select aria-label="Model that reconciles them" value={model} onChange={(event) => setChosen(event.target.value)}>
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
          <button type="button" onClick={() => void create()}>
            Ask it
          </button>
        </>
      )}
      <ErrorNote error={error} />
    </div>
  );
}

/** A model's rewrite, beside what it rewrites, approved with the pair in one undo point. */
function Suggested({
  proposal,
  entry,
  name,
  reconciliation,
  suggestion,
  onRun,
  busy,
}: {
  proposal: ReviewProposal;
  entry: RelatedEntry;
  name: string;
  reconciliation: Reconciliation;
  suggestion: ReviewProposal;
  onRun: (decisions: BrainDecision[]) => void;
  busy: boolean;
}) {
  const changesEntry = reconciliation.current === "proposal";
  // Older vaults keep no titles: a rewrite of the entry is still that entry, by its name.
  const fallback = changesEntry ? entry.title : name;
  const rewrite = {
    label: "Suggested",
    title: suggestion.title || suggestion.note_summary || fallback,
    body: suggestion.body ?? "",
  };
  return (
    <div className="reconcile suggested">
      <p className="relation-head">
        {changesEntry
          ? `Suggested change to “${entry.title}” so both can stand:`
          : "A new version of the suggestion, so it no longer steps on the note:"}
      </p>
      <Compare
        before={
          changesEntry
            ? { label: "In the Brain now", title: entry.title, body: entry.body }
            : { label: "Proposed", title: name, body: proposal.body ?? "" }
        }
        after={rewrite}
      />
      <div className="row">
        <button
          type="button"
          className="primary"
          disabled={busy}
          onClick={() =>
            onRun(
              changesEntry
                ? [
                    { action: "approve", proposal_id: proposal.id },
                    { action: "approve", proposal_id: suggestion.id },
                  ]
                : [
                    { action: "approve", proposal_id: suggestion.id },
                    { action: "reject", proposal_id: proposal.id, reason: `Replaced by the reconciled version, ${suggestion.id}` },
                  ],
            )
          }
        >
          {changesEntry ? "Approve both" : "Use this version"}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => onRun([{ action: "reject", proposal_id: suggestion.id, reason: "Not the right reconciliation" }])}
        >
          Discard the suggestion
        </button>
      </div>
    </div>
  );
}

/** Why the last request brought nothing: what its model said when it finished. */
function LastRun({ taskId }: { taskId: string }) {
  const { data: runs } = useTaskRuns(taskId);
  const said = runs?.[0]?.outcome?.summary || runs?.[0]?.outcome?.blocked;
  return said ? <> (the model said: “{said}”)</> : null;
}
