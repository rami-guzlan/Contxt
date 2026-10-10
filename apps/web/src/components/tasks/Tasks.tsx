// Activity > Tasks and handoffs (goals plan 6.9 and 6.13): who has what (Now, the Tasks sheet
// as lanes) and who did what (Timeline, one lane per owner). A task's drawer shows its card and
// its log, and the hand-off composer calls the same function as the `hand_off` tool, so nothing
// reaches Done without evidence and nothing changes owner without a card.

import { type FormEvent, useState } from "react";
import { Link } from "react-router";

import { useHandOff, useHandoffTask, useHandoffs, useTakeBack, useTimeline } from "../../api/hooks";
import type { TaskItem, TimelineEvent } from "../../api/types";
import { ErrorNote, Field, Loading } from "../ui";
import { onDay, plural, when } from "../../lib/format";

const LANES: { id: keyof ReturnType<typeof emptyLanes>; label: string }[] = [
  { id: "waiting_for_you", label: "Waiting for you" },
  { id: "handed_off", label: "Handed off" },
  { id: "working", label: "Working" },
  { id: "blocked", label: "Blocked" },
  { id: "open", label: "Open" },
];
function emptyLanes() {
  return { waiting_for_you: 0, handed_off: 0, working: 0, blocked: 0, open: 0 };
}
const TARGETS = ["you", "Knowledge agent", "Claude Code", "Codex", "Cursor", "Claude app", "ChatGPT"];

export function TasksTab() {
  const [view, setView] = useState<"now" | "timeline">("now");
  const [open, setOpen] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  return (
    <div className="tasks-tab">
      <div className="row" role="tablist" aria-label="Tasks view">
        <button type="button" role="tab" aria-selected={view === "now"} className={view === "now" ? "primary" : ""} onClick={() => setView("now")}>
          Now
        </button>
        <button type="button" role="tab" aria-selected={view === "timeline"} className={view === "timeline" ? "primary" : ""} onClick={() => setView("timeline")}>
          Timeline
        </button>
        <button type="button" onClick={() => setAdding(!adding)}>
          + Task
        </button>
      </div>
      {adding ? <NewTask onDone={(id) => (setAdding(false), setOpen(id))} /> : null}
      {view === "now" ? <Now onOpen={setOpen} /> : <Timeline onOpen={setOpen} />}
      {open ? <TaskDrawer id={open} onClose={() => setOpen(null)} /> : null}
    </div>
  );
}

function NewTask({ onDone }: { onDone: (id: string) => void }) {
  const hand = useHandOff();
  const [title, setTitle] = useState("");
  return (
    <form
      className="row"
      onSubmit={(event: FormEvent) => {
        event.preventDefault();
        hand.mutate({ new_task: { title: title.trim() } }, { onSuccess: (made) => onDone(made.task.id) });
      }}
    >
      <input aria-label="New task" placeholder="What to do, in a line" maxLength={300} value={title} onChange={(event) => setTitle(event.target.value)} />
      <button type="submit" className="primary" disabled={!title.trim() || hand.isPending}>
        Open it
      </button>
      <ErrorNote error={hand.error} />
    </form>
  );
}

function Now({ onOpen }: { onOpen: (id: string) => void }) {
  const { data, isLoading, error } = useHandoffs();
  const takeBack = useTakeBack();
  if (isLoading) return <Loading />;
  if (!data) return <ErrorNote error={error} />;
  if (!data.count) return <p className="muted">No tasks yet. Open one here, from a goal, or ask any AI to "make this a task".</p>;
  return (
    <div className="stack">
      {LANES.map((lane) => {
        const tasks = data.lanes[lane.id];
        return (
          <section key={lane.id} aria-label={lane.label}>
            <h3 className="small-head">
              {lane.label} ({tasks.length})
            </h3>
            <ul className="list compact-list">
              {tasks.map((t) => (
                <li key={t.id} className="row wrap">
                  <button type="button" className="link" onClick={() => onOpen(t.id)}>
                    {t.id} {t.task}
                  </button>
                  <span className="muted small">
                    {t.owner_label}
                    {t.tool && t.owner_label !== t.tool ? `, ${t.tool}` : ""}
                    {t.card.at ? ` · last saved ${when(t.card.at)}` : ""}
                    {t.card.next_step ? `: “${t.card.next_step}”` : ""}
                  </span>
                  {t.unclaimed ? (
                    <span className="small">
                      not claimed for a day{" "}
                      <button type="button" className="link small" onClick={() => takeBack.mutate(t.id)}>
                        Take back
                      </button>
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        );
      })}
      <details>
        <summary className="small">Done this week ({data.done_this_week.length})</summary>
        <ul className="list compact-list small">
          {data.done_this_week.map((t) => (
            <li key={t.id}>
              <button type="button" className="link small" onClick={() => onOpen(t.id)}>
                {t.id} {t.task}
              </button>{" "}
              <span className="muted">{t.owner_label}</span>
            </li>
          ))}
        </ul>
      </details>
      <ErrorNote error={takeBack.error} />
    </div>
  );
}

const MARKS: Record<TimelineEvent["kind"], string> = {
  open: "opened",
  handoff: "handed off",
  claim: "claimed",
  save: "saved",
  finish: "finished",
  blocked: "blocked",
  dropped: "dropped",
};

function Timeline({ onOpen }: { onOpen: (id: string) => void }) {
  const { data, isLoading, error } = useTimeline(7);
  if (isLoading) return <Loading />;
  if (!data) return <ErrorNote error={error} />;
  if (!data.events.length) return <p className="muted">Nothing happened on a task in the last week.</p>;
  const days = [...new Set(data.events.map((e) => e.at.slice(0, 10)))];
  return (
    <div className="timeline" aria-label="Timeline">
      <table className="timeline-lanes">
        <thead>
          <tr>
            <th scope="col">Owner</th>
            {days.map((d) => (
              <th key={d} scope="col">
                {onDay(d)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.owners.map((owner) => (
            <tr key={owner}>
              <th scope="row">{owner === "you" ? "You" : owner.replace("agent:", "")}</th>
              {days.map((d) => (
                <td key={d}>
                  {data.events
                    .filter((e) => e.owner === owner && e.at.startsWith(d))
                    .map((e, i) => (
                      <button key={i} type="button" className={`mark mark-${e.kind}`} title={`${e.task} ${MARKS[e.kind]}`} onClick={() => onOpen(e.task)}>
                        {e.kind === "handoff" ? `→ ${e.to === "you" ? "You" : e.to}` : e.kind === "save" ? "•" : MARKS[e.kind]} {e.task}
                      </button>
                    ))}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** A task's drawer: its card, its log, and the moves: save, hand off, finish, block, drop. */
export function TaskDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const { data: task, isLoading, error } = useHandoffTask(id);
  return (
    <aside className="card side-panel" aria-label={`Task ${id}`}>
      <header className="row">
        <h2>{task ? `${task.id} ${task.task}` : id}</h2>
        <button type="button" className="link small" onClick={onClose}>
          Close
        </button>
      </header>
      {isLoading ? <Loading /> : null}
      {task ? (
        <div className="stack small">
          <p>
            {task.status_words} · {task.owner_label}
            {task.goal ? (
              <>
                {" "}
                · goal <Link to={`/goals/${encodeURIComponent(task.goal)}`}>{task.goal}</Link>
              </>
            ) : null}
            {task.project ? (
              <>
                {" "}
                · project <Link to={`/projects/${encodeURIComponent(task.project)}`}>{task.project}</Link>
              </>
            ) : null}
          </p>
          <pre className="card-text">{task.rendered}</pre>
          <Composer task={task} />
          <h3 className="small-head">Log</h3>
          <ul className="updates">
            {task.log.slice(0, 30).map((e, i) => (
              <li key={e.id ?? i}>
                <span className="muted">{when(e.at)}</span> {e.kind === "row" ? "opened" : `${e.column}: ${e.column === "Card" ? "saved" : String(e.value ?? "")}`}{" "}
                <span className="muted">({e.by})</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <ErrorNote error={error} />
      )}
    </aside>
  );
}

function Composer({ task }: { task: TaskItem }) {
  const hand = useHandOff();
  const [to, setTo] = useState("");
  const [fields, setFields] = useState({
    done_when: task.card.done_when ?? "",
    next_step: task.card.next_step ?? "",
    done_so_far: task.card.done_so_far ?? "",
    decisions: task.card.decisions ?? "",
    open_questions: task.card.open_questions ?? "",
    load: task.card.load ?? "",
  });
  const [evidence, setEvidence] = useState("");
  const [reason, setReason] = useState("");
  const set = (k: keyof typeof fields, v: string) => setFields({ ...fields, [k]: v });
  const send = (extra: Record<string, unknown>) =>
    hand.mutate({ task: task.id, ...Object.fromEntries(Object.entries(fields).filter(([, v]) => v.trim())), ...extra });
  const closed = task.status === "done" || task.status === "dropped";
  if (closed) return <p className="muted">This task is {task.status_words.toLowerCase()}.</p>;
  return (
    <form
      className="stack composer"
      aria-label={`Hand off ${task.id}`}
      onSubmit={(event: FormEvent) => {
        event.preventDefault();
        send(to ? { to } : {});
      }}
    >
      <fieldset className="row wrap">
        <legend>To</legend>
        {TARGETS.map((t) => (
          <label key={t}>
            <input type="radio" name={`to-${task.id}`} checked={to === t} onChange={() => setTo(t)} /> {t === "you" ? "You" : t}
          </label>
        ))}
        <label>
          <input type="radio" name={`to-${task.id}`} checked={to === ""} onChange={() => setTo("")} /> Keep it (save progress)
        </label>
      </fieldset>
      <Field label="Done when">
        <input value={fields.done_when} onChange={(event) => set("done_when", event.target.value)} />
      </Field>
      <Field label="Next step">
        <input value={fields.next_step} onChange={(event) => set("next_step", event.target.value)} />
      </Field>
      <details>
        <summary>Done so far, decisions, open questions, what to load</summary>
        <Field label="Done so far">
          <textarea rows={2} value={fields.done_so_far} onChange={(event) => set("done_so_far", event.target.value)} />
        </Field>
        <Field label="Decisions">
          <textarea rows={2} value={fields.decisions} onChange={(event) => set("decisions", event.target.value)} />
        </Field>
        <Field label="Open questions">
          <textarea rows={2} value={fields.open_questions} onChange={(event) => set("open_questions", event.target.value)} />
        </Field>
        <Field label="What to load" hint="Notes, rows, skills: their ids.">
          <input value={fields.load} onChange={(event) => set("load", event.target.value)} />
        </Field>
      </details>
      <div className="row wrap">
        <button type="submit" className="primary" disabled={hand.isPending}>
          {to ? `Hand off to ${to === "you" ? "you" : to}` : "Save progress"}
        </button>
        {task.status !== "working" ? (
          <button type="button" onClick={() => hand.mutate({ task: task.id, claim: true })}>
            Start it
          </button>
        ) : null}
      </div>
      <div className="row wrap">
        <input aria-label="Evidence" placeholder="An output's path, or a decided proposal's id" value={evidence} onChange={(event) => setEvidence(event.target.value)} />
        <button type="button" disabled={!evidence.trim()} onClick={() => send({ status: "done", evidence: [evidence.trim()] })}>
          Done
        </button>
      </div>
      <div className="row wrap">
        <input aria-label="Reason" placeholder="Why it is blocked or dropped" value={reason} onChange={(event) => setReason(event.target.value)} />
        <button type="button" disabled={!reason.trim()} onClick={() => send({ status: "blocked", reason: reason.trim() })}>
          Blocked
        </button>
        <button type="button" disabled={!reason.trim()} onClick={() => send({ status: "dropped", reason: reason.trim() })}>
          Drop it
        </button>
      </div>
      <p className="muted small">{plural(Object.values(fields).filter((v) => v.trim()).length, "card field")} filled. The card stays near 250 tokens; longer text stays in the log.</p>
      <ErrorNote error={hand.error} />
    </form>
  );
}

/** A project's tasks, execution first (goals plan 6.5): counts by lane, and what AI is on. */
export function ProjectTasks({ project }: { project: string }) {
  const { data } = useHandoffs({ project });
  if (!data || !data.count) return null;
  const ai = Object.values(data.lanes)
    .flat()
    .filter((t) => t.owner !== "you");
  return (
    <section className="project-tasks" aria-label="Tasks">
      <p className="small">
        <strong>Tasks</strong> · open {data.lanes.open.length} · working {data.lanes.working.length} · waiting for you {data.lanes.waiting_for_you.length} ·
        handed off {data.lanes.handed_off.length} · done this week {data.done_this_week.length} ·{" "}
        <Link to="/activity?tab=tasks">Board</Link>
      </p>
      {ai.length ? (
        <p className="small">
          <strong>AI on this</strong>{" "}
          {ai.map((t, i) => (
            <span key={t.id}>
              {i ? "; " : ""}
              {t.owner_label}: {t.id}
              {t.card.at ? `, saved ${when(t.card.at)}` : ""}
            </span>
          ))}
        </p>
      ) : null}
    </section>
  );
}
