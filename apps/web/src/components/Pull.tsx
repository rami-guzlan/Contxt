// Pull what matters: the knowledge agent on something you brought in or a document filed in the
// Brain. It reads it against your goals and active projects, suggests what serves them (each
// with its goal and project), and lists what it left out so nothing is lost. "Anything in
// particular?" is your guidance, and it wins over the goals.

import { Sparkles } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { useRequestPull, useRunSkill } from "../api/hooks";
import type { Task } from "../api/types";
import { Working } from "./RunNow";
import { ErrorNote } from "./ui";

export function PullWhatMatters({ paths, itemIds, label = "Pull what matters" }: { paths?: string[]; itemIds?: string[]; label?: string }) {
  const pull = useRequestPull();
  const [open, setOpen] = useState(false);
  const [guidance, setGuidance] = useState("");
  const [task, setTask] = useState<Task | null>(null);
  if (task) {
    return (
      <div className="pull">
        <p className="small" role="status">
          Pulling what matters. What it suggests waits in Catch up, with the goal and project each one serves, and what it left out.
        </p>
        <Working task={task} waiting="It waits for the first AI that can do it." />
      </div>
    );
  }
  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)}>
        <Sparkles className="button-icon" aria-hidden="true" />
        {label}
      </button>
    );
  }
  return (
    <form
      className="pull stack-tight"
      onSubmit={(event) => {
        event.preventDefault();
        pull.mutate({ paths: paths ?? [], item_ids: itemIds ?? [], guidance: guidance.trim() }, { onSuccess: setTask });
      }}
    >
      <label className="field">
        <span className="field-label">Anything in particular? (optional)</span>
        <input value={guidance} placeholder="Say “the pricing discussion”, or leave it to your goals" onChange={(event) => setGuidance(event.target.value)} />
      </label>
      <p className="muted small">It weighs every piece against your goals and active projects, and lists what it leaves out.</p>
      <div className="row">
        <button type="submit" className="primary" disabled={pull.isPending}>
          {pull.isPending ? "Asking…" : label}
        </button>
        <button type="button" className="link" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
      <ErrorNote error={pull.error} />
    </form>
  );
}

/** The built-in knowledge check on one capture or file: what the Brain already knows, what is
 * new, what disagrees with it and what is off its goals. Its answer shows on the skill's page. */
export function KnowledgeCheck({ title, captureId, path }: { title: string; captureId?: string; path?: string }) {
  const run = useRunSkill();
  const [task, setTask] = useState<Task | null>(null);
  if (task) {
    return (
      <div className="pull">
        <Working task={task} waiting="It waits for the first AI that can do it." />
        <Link className="small" to="/skills/knowledge-check">
          See the answer
        </Link>
      </div>
    );
  }
  return (
    <>
      <button
        type="button"
        disabled={run.isPending}
        onClick={() =>
          run.mutate(
            { name: "knowledge-check", ask: `Check “${title}” against my Brain and what it is for.`, capture_id: captureId, files: path ? [path] : undefined },
            { onSuccess: setTask },
          )
        }
      >
        Knowledge check
      </button>
      <ErrorNote error={run.error} />
    </>
  );
}

