// History: every batch of decisions is an undo point. Undo takes the Brain back to how it was
// before that batch; an undo is itself a point, so it can be redone.

import { useState } from "react";
import { Link } from "react-router";

import { useBrainCheckpoints, useBrainUndo } from "../../api/hooks";
import type { BrainCheckpoint, CheckpointDecision } from "../../api/types";
import { Empty, ErrorNote, Loading } from "../../components/ui";
import { when } from "../../lib/format";

const VERBS: Record<string, string> = {
  approved: "Approved",
  rejected: "Rejected",
  archived: "Archived",
  reverted: "Undone",
  redone: "Redone",
};

export function HistoryPage() {
  const { data: points, isLoading, error } = useBrainCheckpoints();
  if (isLoading) return <Loading />;
  if (!points) return <ErrorNote error={error} />;
  return (
    <div className="history-page">
      <p className="section-lede">
        Every batch of decisions is saved as an undo point. Undo takes the Brain back to how it was before that batch: entries
        it added leave, entries it replaced or archived come back, and its proposals return to{" "}
        <Link to="/review">Review</Link>. Nothing is lost; an undo can be redone.
      </p>
      {points.length ? (
        <ol className="timeline">
          {points.map((point) => (
            <Point key={point.id} point={point} />
          ))}
        </ol>
      ) : (
        <Empty why="No decisions yet. Approving, rejecting or archiving in Review saves an undo point here." />
      )}
    </div>
  );
}

function Point({ point }: { point: BrainCheckpoint }) {
  const undo = useBrainUndo();
  const [done, setDone] = useState<string | null>(null);
  const redo = point.kind === "undo";
  const verb = redo ? "Redo" : "Undo";
  const source = point.source?.title;
  return (
    <li className={point.undone_by ? "point undone" : "point"}>
      <div className="point-head">
        <div>
          <p className="point-label">
            <strong>{point.label}</strong>
            {point.kind !== "decisions" ? <span className="chip">{point.kind === "undo" ? "Undo" : "Redo"}</span> : null}
            {point.undone_by ? <span className="chip">Undone {point.undone_at ? when(point.undone_at) : ""}</span> : null}
          </p>
          <p className="muted small">
            <time dateTime={point.at}>{when(point.at)}</time> · by {point.by}
            {source ? ` · from ${source}` : ""}
          </p>
        </div>
        {!point.undone_by ? (
          <button
            type="button"
            disabled={!point.undoable || undo.isPending}
            title={point.undoable ? undefined : "Something changed since; see below"}
            onClick={() => undo.mutate(point.id, { onSuccess: () => setDone(`${verb} done.`) })}
          >
            {verb}
          </button>
        ) : null}
      </div>
      {point.blocked?.length && !point.undone_by ? (
        <p className="warning small">
          Cannot {verb.toLowerCase()} yet: {point.blocked.map((b) => b.what).join(", ")} changed since. Undo the later change
          first.
        </p>
      ) : null}
      {done ? <p className="muted small">{done}</p> : null}
      <ErrorNote error={undo.error} />
      {point.decisions.length ? (
        <details>
          <summary>
            {point.decisions.length} decision{point.decisions.length === 1 ? "" : "s"}
          </summary>
          <ul className="point-decisions">
            {point.decisions.map((decision, index) => (
              <li key={`${decision.proposal ?? decision.note}-${index}`}>
                <span className={`chip chip-${decision.action}`}>{VERBS[decision.action] ?? decision.action}</span>{" "}
                {describe(decision)}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </li>
  );
}

function describe(decision: CheckpointDecision): string {
  const what = decision.title || decision.note || decision.proposal || "an item";
  const original = decision.reverted ?? decision.redone;
  const parts = [original ? `${what} (was ${original})` : what];
  if (decision.superseded?.length) parts.push(`replacing ${decision.superseded.join(", ")}`);
  return parts.join(", ");
}
