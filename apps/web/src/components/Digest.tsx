// What a capture says, in a minute: its summary, its key points each marked by how it fits what
// the Brain holds now (new, repeats, updates, clashes, with the entry it touches), and the
// decisions, actions, open questions and people in it. Then what in the Brain it touches, found
// by meaning at once. Nothing here changes the Brain: pulling something in is the next step.

import { useState } from "react";
import { Link } from "react-router";

import { useBrainProjects, useCaptureRelated, useCreateBrainProject, useSummarize, useTask } from "../api/hooks";
import type { Digest, DigestPoint, Fit, Note } from "../api/types";
import { when } from "../lib/format";
import { entryUrl } from "../pages/brain/shared";
import { RunButtons, RunConsole, RunnerNote, canRun } from "./RunNow";
import { ErrorNote, Loading } from "./ui";

const FIT: Record<Fit, string> = { new: "New", repeats: "Repeats", updates: "Updates", clashes: "Clashes" };

export function DigestPanel({ note, hasText }: { note: Note; hasText: boolean }) {
  const digest = note.digest;
  return (
    <div className="stack">
      <section className="side-part" aria-label="What it says">
        <h3>What it says</h3>
        {digest?.state === "ready" ? (
          <Written digest={digest} note={note} />
        ) : digest?.state === "waiting" && digest.task_id ? (
          <Waiting taskId={digest.task_id} />
        ) : digest?.state === "queued" ? (
          <p className="muted small" role="status">
            {hasText ? "Its summary is on its way." : "It is summarized once its text is in."}
          </p>
        ) : (
          <Ask note={note} hasText={hasText} />
        )}
      </section>
      {hasText ? <Related note={note} /> : null}
    </div>
  );
}

function Written({ digest, note }: { digest: Digest; note: Note }) {
  const points = digest.points ?? [];
  return (
    <>
      {digest.about ? (
        <p className="about">
          <strong>Mostly about:</strong> {digest.about}
        </p>
      ) : null}
      {digest.summary ? <p>{digest.summary}</p> : null}
      {points.length ? (
        <>
          <h4>Key points</h4>
          <ul className="digest-points">
            {points.map((point, index) => (
              <Point key={`${index}-${point.text}`} point={point} />
            ))}
          </ul>
        </>
      ) : null}
      <List title="Decided" items={digest.decisions} />
      <List title="To do" items={digest.actions} />
      <List title="Still open" items={digest.questions} />
      {digest.people?.length ? <p className="small muted">People: {digest.people.join(", ")}</p> : null}
      {digest.new_project ? <StartProject name={digest.new_project} from={note.title} /> : null}
      <p className="small muted">
        Summarized by {digest.by ?? "your AI"}
        {digest.at ? ` ${when(digest.at)}` : ""}. <Again note={note} />
      </p>
    </>
  );
}

function Point({ point }: { point: DigestPoint }) {
  return (
    <li className={`digest-point fit-${point.fit}`}>
      <span className={`chip fit fit-${point.fit}`}>{FIT[point.fit] ?? "New"}</span>{" "}
      <span>{point.text}</span>
      {point.entry ? (
        <>
          {" "}
          <Link className="small" to={entryUrl(point.entry)}>
            {point.fit === "repeats" ? "already in the Brain" : point.fit === "clashes" ? "the note it clashes with" : "the note it changes"}
          </Link>
        </>
      ) : null}
      {point.why ? <span className="muted small"> · {point.why}</span> : null}
      {point.serves ? <span className="chip small serves-chip">For {point.serves === "goals" ? "your goals" : point.serves}</span> : null}
    </li>
  );
}

/** Work it is mostly about that is not a project yet: start one, and your AI knows where it
 * stands from then on. */
function StartProject({ name, from }: { name: string; from: string }) {
  const { data: projects } = useBrainProjects();
  const start = useCreateBrainProject();
  const exists = (projects ?? []).some((p) => [p.title, ...p.aliases].some((n) => n.toLowerCase() === name.toLowerCase()));
  if (exists) return null;
  if (start.isSuccess) {
    return (
      <p className="small" role="status">
        Started the project {name}.
      </p>
    );
  }
  return (
    <div className="nudge">
      <p className="small">
        This is about <strong>{name}</strong>, which is not a project yet. Start one?
      </p>
      <button
        type="button"
        className="small"
        disabled={start.isPending}
        onClick={() => start.mutate({ name, summary: `${name}, started from “${from}”.`, aliases: [] })}
      >
        Start “{name}”
      </button>
      <ErrorNote error={start.error} />
    </div>
  );
}

function List({ title, items }: { title: string; items: string[] | undefined }) {
  if (!items?.length) return null;
  return (
    <>
      <h4>{title}</h4>
      <ul className="compact-list">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </>
  );
}

/** A summary request still going: who has it, and a way to run it here now. */
function Waiting({ taskId }: { taskId: string }) {
  const { data: task } = useTask(taskId);
  const [runId, setRunId] = useState<string | null>(null);
  if (!task) return <Loading />;
  const failed = task.status === "failed" || task.status === "cancelled";
  return (
    <div className="stack">
      <p className="small" role="status">
        {failed
          ? "The summary didn't finish."
          : task.assignee_id
            ? "Your AI is summarizing it."
            : "Waiting for a model to summarize it."}
      </p>
      {canRun(task) ? (
        <>
          <RunButtons task={task} onStarted={setRunId} />
          <RunnerNote />
        </>
      ) : null}
      {runId ? <RunConsole runId={runId} /> : null}
    </div>
  );
}

function Ask({ note, hasText }: { note: Note; hasText: boolean }) {
  const summarize = useSummarize();
  const [guidance, setGuidance] = useState("");
  if (!hasText) return <p className="muted small">It can be summarized once it has text.</p>;
  return (
    <div className="stack">
      <p className="muted small">Your AI writes its summary and key points, and marks how each fits what your Brain holds now.</p>
      <input
        aria-label="Anything to look for (optional)"
        placeholder="Anything to look for, like who owns each action"
        value={guidance}
        onChange={(event) => setGuidance(event.target.value)}
      />
      <button type="button" disabled={summarize.isPending} onClick={() => summarize.mutate({ id: note.id, guidance })}>
        Summarize
      </button>
      <ErrorNote error={summarize.error} />
    </div>
  );
}

function Again({ note }: { note: Note }) {
  const summarize = useSummarize();
  return (
    <button type="button" className="link small" disabled={summarize.isPending} onClick={() => summarize.mutate({ id: note.id })}>
      Summarize again
    </button>
  );
}

/** What the Brain already holds that this touches: found by meaning, part by part. */
function Related({ note }: { note: Note }) {
  const { data: related, isLoading } = useCaptureRelated(note.id);
  return (
    <section className="side-part" aria-label="In your Brain already">
      <h3>In your Brain already</h3>
      {isLoading ? (
        <Loading />
      ) : related?.length ? (
        <ul className="compact-list">
          {related.map((entry) => (
            <li key={entry.id}>
              <Link to={entryUrl(entry.id)}>{entry.title}</Link>
              {entry.summary ? <span className="muted small"> · {entry.summary}</span> : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted small">Nothing in your Brain touches this yet: what you pull in from it will be new.</p>
      )}
    </section>
  );
}
