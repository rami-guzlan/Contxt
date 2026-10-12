// Skills (UX C): the run bar at the top, the review of a run (its steps live while it runs, the
// same transcript replayed once it is done, the brief it was given, what it made and proposed),
// the Brain's own skills with one-click runs, and a quiet drawer of recent runs.

import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router";

import { post } from "../../api/client";
import {
  keys,
  runnerKeys,
  useAddBuiltinSkills,
  useAgent,
  useBrainProjects,
  useBuiltinSkills,
  useInvalidate,
  useLocalRun,
  useRecentRuns,
  useRunAgentAction,
  useRunners,
  useRunPacket,
  useRunSkills,
} from "../../api/hooks";
import type { LocalRun, RunnerStatus, SkillCard, Task } from "../../api/types";
import { plural, when } from "../../lib/format";
import { RunButtons, RunConsole, RunLine } from "../RunNow";
import { LatestRuns } from "../SkillWork";
import { ErrorNote, Pill, Section } from "../ui";

const ACTIVE = ["starting", "running"];
const REPLAY_MS = 120; // between steps when a finished run is replayed

/** The CLIs on this computer that can run work now. */
function readyRunners(runners: RunnerStatus[] | undefined): RunnerStatus[] {
  return (runners ?? []).filter((r) => r.one_click && r.installed && r.signed_in !== false);
}

/** Start a run's task on a CLI on this computer; the run's id. */
async function startOn(runnerId: string, taskId: string): Promise<string> {
  const run = await post<LocalRun>(`/api/runners/${encodeURIComponent(runnerId)}/runs`, { task_id: taskId });
  return run.id;
}

/** Run skills from the top of the page: what you need, the skills to follow in order (or the
 * one that fits), where it runs and the project, then its review as it happens. */
export function RunBar({ skills }: { skills: SkillCard[] }) {
  const runnable = skills.filter((s) => s.use === "run");
  const { data: runners } = useRunners();
  const { data: projects } = useBrainProjects();
  const runSkills = useRunSkills();
  const invalidate = useInvalidate();
  const ready = readyRunners(runners);
  const [ask, setAsk] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [runner, setRunner] = useState("");
  const [project, setProject] = useState("");
  const [task, setTask] = useState<Task | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const chosen = runner || ready[0]?.id || "";

  async function go(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setRunId(null);
    setTask(null);
    try {
      const made = await runSkills.mutateAsync({ names: picked, ask: ask.trim(), project: project || null });
      setTask(made);
      if (chosen) {
        setRunId(await startOn(chosen, made.id));
        await invalidate(runnerKeys, keys.tasks);
      }
    } catch (caught) {
      setError(caught);
    }
  }

  return (
    <section className="skill-panel run-bar" aria-label="Run skills">
      <form className="stack" onSubmit={(event) => void go(event)}>
        <label className="sr-only" htmlFor="run-bar-ask">
          What you need
        </label>
        <textarea id="run-bar-ask" rows={2} placeholder="What you need, in your own words" value={ask} onChange={(e) => setAsk(e.target.value)} />
        <div className="row small run-bar-row">
          <select
            aria-label="Add a skill"
            value=""
            onChange={(e) => {
              const name = e.target.value;
              if (name && !picked.includes(name)) setPicked([...picked, name]);
            }}
          >
            <option value="">{picked.length ? "Add another skill" : "The skill that fits, or pick"}</option>
            {runnable
              .filter((s) => !picked.includes(s.name))
              .map((s) => (
                <option key={s.name} value={s.name}>
                  /{s.name}
                </option>
              ))}
          </select>
          <select aria-label="Where it runs" value={chosen} onChange={(e) => setRunner(e.target.value)}>
            {ready.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label}
              </option>
            ))}
            {!ready.length ? <option value="">No AI app ready here: copy its prompt</option> : null}
            <option value="later" disabled>
              Other command-line AIs: later
            </option>
          </select>
          <select aria-label="Project" value={project} onChange={(e) => setProject(e.target.value)}>
            <option value="">No project</option>
            {(projects ?? [])
              .filter((p) => p.active)
              .map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
          </select>
          <button type="submit" className="primary" disabled={runSkills.isPending || (!ask.trim() && !picked.length)}>
            {runSkills.isPending ? "Starting…" : "Run"}
          </button>
        </div>
        {picked.length ? (
          <ol className="plain row small" aria-label="Skills, in order">
            {picked.map((name, index) => (
              <li key={name} className="chip">
                {index + 1}. /{name}{" "}
                <button type="button" className="link" aria-label={`Remove /${name}`} onClick={() => setPicked(picked.filter((n) => n !== name))}>
                  ×
                </button>
              </li>
            ))}
          </ol>
        ) : null}
      </form>
      <ErrorNote error={error} />
      {task && !runId ? <RunButtons task={task} onStarted={setRunId} /> : null}
      {runId ? <RunReview runId={runId} /> : null}
    </section>
  );
}

/** A run's review: its steps live while it runs; once done, the same transcript (replayed on
 * request), the brief it was given, how it ended, what it made and where its work waits. */
export function RunReview({ runId }: { runId: string }) {
  const { data: run, error } = useLocalRun(runId);
  const [briefOpen, setBriefOpen] = useState(false);
  const packet = useRunPacket(runId, briefOpen);
  const [shown, setShown] = useState<number | null>(null); // steps shown while replaying
  const total = run?.events.length ?? 0;
  useEffect(() => {
    if (shown === null || shown >= total) return;
    const timer = window.setTimeout(() => setShown(shown + 1), REPLAY_MS);
    return () => window.clearTimeout(timer);
  }, [shown, total]);
  if (!run) return <ErrorNote error={error} />;
  const finished = !ACTIVE.includes(run.status);
  const steps = shown === null ? run.events : run.events.slice(0, shown);
  return (
    <div className="run-review" aria-label={`Review of ${run.task_title}`}>
      <details
        className="run-brief"
        onToggle={(event) => setBriefOpen((event.currentTarget as HTMLDetailsElement).open)}
      >
        <summary>The brief it was given</summary>
        {packet.data?.available ? (
          <pre className="prewrap small">{packet.data.text}</pre>
        ) : packet.isFetched ? (
          <p className="muted small">Its brief is no longer kept.</p>
        ) : null}
      </details>
      {finished ? (
        <div className="console" aria-label={`Run of ${run.task_title}`}>
          <div className="console-head">
            <Pill status={run.status} />
            <span className="muted">{run.task_title}</span>
            <span className="muted small">{when(run.finished_at ?? run.started_at)}</span>
            <button type="button" className="link" onClick={() => setShown(0)} disabled={shown !== null && shown < total}>
              Replay
            </button>
          </div>
          <ol className="console-lines" role="log">
            {steps.map((event) => (
              <li key={event.seq} className={`line line-${event.kind}`}>
                <RunLine event={event} />
              </li>
            ))}
          </ol>
        </div>
      ) : (
        <RunConsole runId={runId} />
      )}
      {finished ? (
        <p className="small">
          {run.summary ? <strong>{run.summary} </strong> : null}
          {run.made?.length ? <span>{plural(run.made.length, "file")} made. </span> : null}
          <Link to={run.link ?? "/review"}>See what it proposed</Link>
        </p>
      ) : null}
    </div>
  );
}

/** The Brain's own skills (its upkeep) and the knowledge agent's actions, one click each. */
export function BrainSkills({ skills }: { skills: SkillCard[] }) {
  const { data: builtins } = useBuiltinSkills();
  const add = useAddBuiltinSkills();
  const { data: agent } = useAgent();
  const runAction = useRunAgentAction();
  const runSkills = useRunSkills();
  const { data: runners } = useRunners();
  const ready = readyRunners(runners)[0];
  const [task, setTask] = useState<Task | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [started, setStarted] = useState("");
  const [error, setError] = useState<unknown>(null);
  const byName = new Map(skills.map((s) => [s.name, s]));
  const installed = (builtins?.skills ?? []).filter((s) => s.installed);

  async function runSkill(name: string) {
    setError(null);
    setRunId(null);
    setTask(null);
    setStarted("");
    try {
      const made = await runSkills.mutateAsync({ names: [name], ask: `Run /${name} on this Brain.` });
      setTask(made);
      if (ready) setRunId(await startOn(ready.id, made.id));
    } catch (caught) {
      setError(caught);
    }
  }

  if (!installed.length && !agent?.actions.length) return null;
  return (
    <Section title="Brain skills">
      <p className="muted small">What keeps your Brain itself in order, and the knowledge agent's upkeep. One click runs each.</p>
      <ul className="list builtins" aria-label="Brain skills">
        {installed.map((skill) => {
          const card = byName.get(skill.name);
          return (
            <li key={skill.name}>
              <strong>/{skill.name}</strong> <span className="muted small">{skill.description.split(/(?<=[.!?])\s/)[0]}</span>{" "}
              {card?.use === "run" ? (
                <button type="button" className="small" disabled={runSkills.isPending} onClick={() => void runSkill(skill.name)}>
                  Run /{skill.name}
                </button>
              ) : (
                <span className="muted small">In any chat: /{skill.name}</span>
              )}
            </li>
          );
        })}
        {(agent?.actions ?? []).map((action) => (
          <li key={action.id}>
            <strong>{action.label}</strong> <span className="muted small">{action.blurb}</span>{" "}
            <button
              type="button"
              className="small"
              disabled={runAction.isPending}
              onClick={() => runAction.mutate({ action: action.id }, { onSuccess: () => setStarted(action.label) })}
            >
              Run {action.label.toLowerCase()}
            </button>
          </li>
        ))}
      </ul>
      {builtins?.missing.length ? (
        <button type="button" disabled={add.isPending} onClick={() => add.mutate(undefined)}>
          {add.isPending ? "Adding…" : `Add the ${plural(builtins.missing.length, "missing one")}`}
        </button>
      ) : null}
      {started ? (
        <p className="small" role="status">
          {started}: the knowledge agent is on it. <Link to="/brain/agent">See it work</Link>
        </p>
      ) : null}
      <ErrorNote error={error ?? runAction.error ?? add.error} />
      {task && !runId ? <RunButtons task={task} onStarted={setRunId} /> : null}
      {runId ? <RunReview runId={runId} /> : null}
    </Section>
  );
}

/** Recent runs, quietly: closed until opened; a run opens its review. */
export function RecentRuns() {
  const { data: runs } = useRecentRuns();
  const [open, setOpen] = useState<string | null>(null);
  const list = (runs ?? []).slice(0, 12);
  return (
    <details className="recent-runs">
      <summary>Recent runs{list.length ? ` (${list.length})` : ""}</summary>
      {list.length ? (
        <ul className="plain" aria-label="Runs on this computer">
          {list.map((run) => (
            <li key={run.id} className="row small">
              <button type="button" className="link" aria-expanded={open === run.id} onClick={() => setOpen(open === run.id ? null : run.id)}>
                {run.task_title}
              </button>
              <Pill status={run.status} />
              <span className="muted">{when(run.started_at)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted small">Nothing has run on this computer yet.</p>
      )}
      {open ? <RunReview runId={open} /> : null}
      <LatestRuns />
    </details>
  );
}
