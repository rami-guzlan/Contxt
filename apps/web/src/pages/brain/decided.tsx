// What every page that decides about the Brain shares: the banner after a decision, with its
// undo point, and the list of what in the Brain wants a look.

import { Link } from "react-router";

import { useBrainUndo } from "../../api/hooks";
import type { BrainAttention, BrainCheckpoint, DecisionOutcome } from "../../api/types";
import { ErrorNote } from "../../components/ui";
import { entryUrl } from "./shared";

/** What the page says after a decision, with the undo point to take it back. */
export interface Decided {
  message: string;
  checkpoint: BrainCheckpoint | null;
  undone?: boolean;
  failed?: string[];
}

export function describeOutcome(outcome: DecisionOutcome): Decided {
  const failed = outcome.results.filter((r) => !r.ok).map((r) => r.message);
  const label = outcome.checkpoint?.label;
  return {
    message: label ? `${label}. Undo point saved.` : failed.length ? "Nothing changed." : "Done.",
    checkpoint: outcome.checkpoint,
    failed,
  };
}

export function DecidedBanner({ decided, onChange }: { decided: Decided; onChange: (next: Decided | null) => void }) {
  const undo = useBrainUndo();
  const point = decided.checkpoint;
  return (
    <div className="decided" role="status">
      <div>
        <strong>{decided.message}</strong>
        {decided.undone ? <span> The Brain is back to how it was before; its proposals are waiting again.</span> : null}
        {decided.failed?.length ? (
          <ul className="error">
            {decided.failed.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        ) : null}
        <ErrorNote error={undo.error} />
      </div>
      <div className="row">
        {point ? (
          <button
            type="button"
            disabled={undo.isPending}
            onClick={() =>
              undo.mutate(point.id, {
                onSuccess: (result) =>
                  onChange({
                    message: decided.undone ? `Redone: ${point.label.replace(/^Undo: /, "")}.` : `Undone: ${point.label}.`,
                    checkpoint: result.checkpoint,
                    undone: !decided.undone,
                  }),
              })
            }
          >
            {decided.undone ? "Redo" : "Undo"}
          </button>
        ) : null}
        <Link className="button" to="/brain/history?view=undo">
          History
        </Link>
        <button type="button" className="link" aria-label="Dismiss" onClick={() => onChange(null)}>
          Dismiss
        </button>
      </div>
    </div>
  );
}

/** What in the Brain wants a look: clashes, near twins, misplaced text, entries to re-check. */
export function BrainChecks({ attention }: { attention: BrainAttention }) {
  const entry = (id: string, title: string) => <Link to={entryUrl(id)}>{title}</Link>;
  return (
    <ul className="list checks">
      {attention.clashes.map((c) => (
        <li key={`clash:${c.proposal_id}:${c.entry_id}`}>
          <span className="chip chip-close">May contradict</span> “{c.title}” and {entry(c.entry_id, c.entry_title)}
          {c.why ? <span className="muted"> · {c.why}</span> : null}
        </li>
      ))}
      {attention.twins.map((t) => (
        <li key={`twin:${t.a}:${t.b}`}>
          <span className="chip">May say the same thing</span> {entry(t.a, t.a_title)} and {entry(t.b, t.b_title)}
        </li>
      ))}
      {attention.flagged.map((f) => (
        <li key={`flag:${f.id}:${f.why}`}>
          <span className="chip">Text to move</span> {entry(f.id, f.title)}
          <span className="muted"> · {f.why}</span>
        </li>
      ))}
      {attention.recheck.map((r) => (
        <li key={`recheck:${r.id}`}>
          <span className="chip chip-late">Re-check</span> {entry(r.id, r.title)}
          <span className="muted"> · {r.why}</span>
        </li>
      ))}
    </ul>
  );
}
