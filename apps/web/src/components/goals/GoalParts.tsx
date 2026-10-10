// The pieces every goal surface shares (goals plan 6): the status word with its shape, a small
// trend line, the check-in fill-in (the same everywhere: a goal card, the goal's page, Home),
// a goal's card for Goals and Projects, and "Set a goal": the coach, or the same draft by hand.

import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";

import { useBrainProjects, useCheckIn, useGoalCoach, useSetGoal, useWorkJob } from "../../api/hooks";
import type { GoalBase, GoalCall, GoalCoachResult, GoalDraft, GoalView } from "../../api/types";
import { ErrorNote, Field } from "../ui";
import { plural, when } from "../../lib/format";

export const goalUrl = (id: string) => `/goals/${encodeURIComponent(id)}`;

const SHAPES: Record<string, string> = {
  on_track: "●",
  at_risk: "▲",
  off_track: "■",
  needs_attention: "▲",
  no_data: "○",
  not_checked_in: "○",
  paused: "‖",
  met: "✓",
  missed: "✕",
  dropped: "✕",
  retired: "‖",
};

/** The status word, with a shape so it reads without color. */
export function GoalStatus({ goal }: { goal: Pick<GoalView, "status" | "words" | "call" | "level"> }) {
  return (
    <span className={`goal-status goal-${goal.status}`}>
      <span aria-hidden="true">{SHAPES[goal.status] ?? "○"}</span> {goal.words}
      {goal.level === "yours" && goal.call ? <span className="muted small"> (your call)</span> : null}
    </span>
  );
}

/** A small trend line of the last checks. */
export function Trend({ values, label = "Trend" }: { values: number[]; label?: string }) {
  if (values.length < 2) return null;
  const top = Math.max(...values);
  const bottom = Math.min(...values);
  const span = top - bottom || 1;
  const points = values.map((v, i) => `${(i / (values.length - 1)) * 60},${16 - ((v - bottom) / span) * 14}`).join(" ");
  return (
    <svg className="trend" width="60" height="18" viewBox="0 0 60 18" role="img" aria-label={`${label}: ${values.join(", ")}`}>
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

/** Where the goal stands against its target: "71 of 150 a session". */
export function Progress({ goal }: { goal: GoalBase }) {
  if (goal.now === null && goal.target === null) return null;
  const unit = goal.unit === "%" ? "%" : goal.unit ? ` ${goal.unit}` : "";
  if (goal.level === "agent") {
    return (
      <span className="small">
        {goal.now ?? "no value yet"}
        {goal.now !== null ? unit : ""} / {goal.measure?.kind === "at_least" ? "at least" : "at most"} {goal.target}
        {unit}
      </span>
    );
  }
  if (goal.now === null) {
    return (
      <span className="small muted">
        no number yet, toward {goal.target}
        {unit}
      </span>
    );
  }
  return (
    <span className="small">
      {goal.now}
      {goal.target !== null ? ` of ${goal.target}` : ""}
      {unit}
    </span>
  );
}

const CALLS: { id: GoalCall; label: string }[] = [
  { id: "on_track", label: "On track" },
  { id: "at_risk", label: "At risk" },
  { id: "off_track", label: "Off track" },
];

/** The check-in: the number (when the goal tracks one), your call and one line. Keyboard
 * first, under 20 seconds. */
export function CheckIn({ goal, onDone }: { goal: GoalBase; onDone?: () => void }) {
  const check = useCheckIn(goal.id);
  const [value, setValue] = useState(goal.now !== null ? String(goal.now) : "");
  const [call, setCall] = useState<GoalCall>(goal.call ?? "on_track");
  const [line, setLine] = useState("");
  const tracks = goal.measure?.kind === "enter" || goal.target !== null;
  function submit(event: FormEvent) {
    event.preventDefault();
    check.mutate(
      { call, value: tracks && value.trim() ? Number(value) : null, line: line.trim() },
      { onSuccess: () => onDone?.() },
    );
  }
  return (
    <form className="check-in row wrap" onSubmit={submit} aria-label={`Check in on ${goal.title}`}>
      {tracks ? (
        <label className="small">
          Where are we?{" "}
          <input
            type="number"
            step="any"
            inputMode="decimal"
            className="narrow"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            aria-label="The number now"
          />{" "}
          {goal.unit ?? ""}
        </label>
      ) : null}
      <fieldset className="row calls" aria-label="How is it going?">
        {CALLS.map((c) => (
          <label key={c.id} className="small">
            <input type="radio" name={`call-${goal.id}`} checked={call === c.id} onChange={() => setCall(c.id)} /> {c.label}
          </label>
        ))}
      </fieldset>
      <input
        className="grow"
        maxLength={300}
        placeholder="One line: what moved, or what is in the way"
        value={line}
        onChange={(event) => setLine(event.target.value)}
        aria-label="One line"
      />
      <button type="submit" className="primary" disabled={check.isPending}>
        Save
      </button>
      <ErrorNote error={check.error} />
    </form>
  );
}

/** A goal on Goals and Projects: your call and any flag, progress, the date, one line of
 * activity, and the check-in on the card itself. */
export function GoalCard({ goal }: { goal: GoalView }) {
  const [checking, setChecking] = useState(false);
  const bits = [
    plural(goal.projects.length, "project"),
    goal.suggestions ? `${plural(goal.suggestions, "suggested step")} wait` : "",
    goal.checked_in_at ? `checked in ${when(goal.checked_in_at)}` : "not checked in yet",
  ].filter(Boolean);
  return (
    <li className="card goal-card">
      <header className="row wrap">
        <h3>
          <Link to={goalUrl(goal.id)}>{goal.title}</Link>
        </h3>
        <GoalStatus goal={goal} />
        <Progress goal={goal} />
        <Trend values={goal.trend} />
        <span className="muted small">{goal.due ? `by ${goal.due}` : "ongoing"}</span>
      </header>
      {goal.flag ? <p className="small flag">{goal.flag}</p> : null}
      <div className="row">
        <span className="muted small">{bits.join(" | ")}</span>
        {goal.lifecycle === "active" ? (
          <button type="button" className="link small" aria-expanded={checking} onClick={() => setChecking(!checking)}>
            {checking ? "Close" : "Check in"}
          </button>
        ) : null}
      </div>
      {checking ? <CheckIn goal={goal} onDone={() => setChecking(false)} /> : null}
    </li>
  );
}

// ---------------------------------------------------------------- setting a goal

type Turn = { role: "you" | "coach"; text: string };

const EMPTY: GoalDraft = {
  title: "",
  why: "",
  due: "",
  cadence: "weekly",
  measure: null,
  board: {},
  first_steps: [],
  project: "",
};

/** "Set a goal": talk it through with the coach (at most three questions, then a draft), or
 * fill in the same draft by hand. Every field is yours to change before it is saved. */
export function SetGoal({ onClose, start = "" }: { onClose: () => void; start?: string }) {
  const [mode, setMode] = useState<"coach" | "form">("coach");
  const [draft, setDraft] = useState<GoalDraft | null>(null);
  return (
    <aside className="card side-panel set-goal" aria-label="Set a goal">
      <header className="row">
        <h2>Set a goal</h2>
        <button type="button" className="link small" onClick={onClose}>
          Close
        </button>
      </header>
      {draft ? (
        <DraftForm initial={draft} onBack={() => setDraft(null)} onClose={onClose} />
      ) : (
        <>
          <div className="row" role="tablist">
            <button type="button" role="tab" aria-selected={mode === "coach"} className={mode === "coach" ? "primary" : ""} onClick={() => setMode("coach")}>
              Talk it through
            </button>
            <button type="button" role="tab" aria-selected={mode === "form"} className={mode === "form" ? "primary" : ""} onClick={() => setDraft({ ...EMPTY, title: start })}>
              Fill it in
            </button>
          </div>
          {mode === "coach" ? <Coach start={start} onDraft={setDraft} /> : null}
        </>
      )}
    </aside>
  );
}

function Coach({ start, onDraft }: { start: string; onDraft: (draft: GoalDraft) => void }) {
  const coach = useGoalCoach();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState(start);
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useWorkJob<GoalCoachResult>(jobId);
  const result = job.data?.status === "done" ? job.data.result : null;
  useEffect(() => {
    if (!result) return;
    if (result.draft) onDraft({ ...EMPTY, ...result.draft });
    else if (result.questions?.length) {
      setTurns((was) => (was[was.length - 1]?.role === "coach" ? was : [...was, { role: "coach", text: result.questions!.join("\n") }]));
      setJobId(null);
    }
  }, [result, onDraft]);
  function send(event: FormEvent) {
    event.preventDefault();
    const next = [...turns, { role: "you" as const, text: text.trim() }];
    setTurns(next);
    setText("");
    coach.mutate(next, { onSuccess: (made) => setJobId(made.id) });
  }
  const working = coach.isPending || (!!jobId && !["done", "failed"].includes(job.data?.status ?? ""));
  return (
    <div className="stack">
      <p className="muted small">
        Say what you want to achieve. The coach asks at most three questions (what reaching it gets you, what gets in the way, what you will do
        then), then drafts the goal for you to change.
      </p>
      <ol className="coach-turns">
        {turns.map((turn, i) => (
          <li key={i} className={turn.role}>
            <strong>{turn.role === "you" ? "You" : "Coach"}</strong> <span className="pre">{turn.text}</span>
          </li>
        ))}
      </ol>
      {job.data?.status === "failed" || result?.error ? (
        <p className="small">{result?.error ?? job.data?.error} You can fill it in by hand instead.</p>
      ) : null}
      <form className="stack" onSubmit={send}>
        <textarea rows={3} value={text} maxLength={4000} onChange={(event) => setText(event.target.value)} aria-label="Your answer" />
        <div className="row">
          <button type="submit" className="primary" disabled={working || !text.trim()}>
            {working ? "Thinking..." : "Send"}
          </button>
          {turns.length ? (
            <button type="button" onClick={() => (setTurns([]), setJobId(null))}>
              Start over
            </button>
          ) : null}
        </div>
      </form>
      <ErrorNote error={coach.error} />
    </div>
  );
}

function DraftForm({ initial, onBack, onClose }: { initial: GoalDraft; onBack: () => void; onClose: () => void }) {
  const save = useSetGoal();
  const navigate = useNavigate();
  const { data: projects } = useBrainProjects();
  // What you want and the best outcome are one note on the board.
  const [draft, setDraft] = useState<GoalDraft>({
    ...initial,
    board: { ...initial.board, wish: [initial.board.wish, initial.board.outcome].filter(Boolean).join("\n\n"), outcome: "" },
  });
  const [target, setTarget] = useState(initial.measure?.target !== undefined ? String(initial.measure.target) : "");
  const [unit, setUnit] = useState(initial.measure?.unit ?? "");
  const [steps, setSteps] = useState(initial.first_steps.join("\n"));
  const set = (patch: Partial<GoalDraft>) => setDraft({ ...draft, ...patch });
  const board = (key: keyof GoalDraft["board"], value: string) => setDraft({ ...draft, board: { ...draft.board, [key]: value } });
  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate(
      {
        ...draft,
        due: draft.due || undefined,
        measure: target.trim() ? { kind: "enter", target: Number(target), unit: unit.trim() || undefined } : null,
        first_steps: steps.split("\n").map((s) => s.trim()).filter(Boolean).slice(0, 3),
        project: draft.project || undefined,
      },
      {
        onSuccess: (made) => {
          onClose();
          navigate(goalUrl(made.id));
        },
      },
    );
  }
  return (
    <form className="stack" onSubmit={submit} aria-label="Your goal">
      <Field label="The goal" hint="In a sentence, the way you would say it.">
        <input required maxLength={160} value={draft.title} onChange={(event) => set({ title: event.target.value })} />
      </Field>
      <Field label="Why" hint="What reaching it gets you.">
        <input maxLength={600} value={draft.why} onChange={(event) => set({ why: event.target.value })} />
      </Field>
      <div className="row wrap">
        <Field label="A number to reach" hint="Optional: you enter it at each check-in.">
          <input type="number" step="any" className="narrow" value={target} onChange={(event) => setTarget(event.target.value)} />
        </Field>
        <Field label="Unit">
          <input maxLength={30} className="narrow" placeholder="a session" value={unit} onChange={(event) => setUnit(event.target.value)} />
        </Field>
        <Field label="By">
          <input type="date" value={draft.due} onChange={(event) => set({ due: event.target.value })} />
        </Field>
        <Field label="Check in">
          <select value={draft.cadence} onChange={(event) => set({ cadence: event.target.value as GoalDraft["cadence"] })}>
            <option value="daily">daily</option>
            <option value="weekly">weekly</option>
            <option value="monthly">monthly</option>
          </select>
        </Field>
      </div>
      <Field label="What you want, and the best outcome">
        <textarea rows={2} value={draft.board.wish ?? ""} onChange={(event) => board("wish", event.target.value)} />
      </Field>
      <Field label="What gets in the way">
        <textarea rows={2} value={draft.board.obstacle ?? ""} onChange={(event) => board("obstacle", event.target.value)} />
      </Field>
      <Field label="If it happens, you will">
        <textarea rows={2} value={draft.board.plan ?? ""} onChange={(event) => board("plan", event.target.value)} />
      </Field>
      <Field label="First steps" hint="At most three, one a line. They wait as suggestions you can make part of the plan.">
        <textarea rows={3} value={steps} onChange={(event) => setSteps(event.target.value)} />
      </Field>
      {projects?.length ? (
        <Field label="Link a project">
          <select value={draft.project} onChange={(event) => set({ project: event.target.value })}>
            <option value="">None</option>
            {projects
              .filter((p) => p.active)
              .map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
          </select>
        </Field>
      ) : null}
      <div className="row">
        <button type="submit" className="primary" disabled={save.isPending || !draft.title.trim()}>
          Save goal
        </button>
        <button type="button" onClick={onBack}>
          Start over
        </button>
      </div>
      <ErrorNote error={save.error} />
    </form>
  );
}
