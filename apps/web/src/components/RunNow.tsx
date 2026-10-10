// Running a task now: with a CLI on this computer (the app starts it and shows its work
// as it goes), or from a prompt pasted into any connected model. Scheduled checks still work
// alongside: both paths claim the same task through the same tools.

import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";

import { get, post } from "../api/client";
import { keys, runnerKeys, useCheckRunners, useInvalidate, useLocalRun, useRunners } from "../api/hooks";
import type { LocalRun, RunEvent, RunnerStatus } from "../api/types";
import { CopyBlock, ErrorNote, Pill } from "./ui";

const ACTIVE = ["starting", "running"];

/** What a task's run button needs to know about it. */
export interface Runnable {
  id: string;
  status: string;
  assignee_id: string | null;
}

/** Whether a task can start now: ready, or a request still waiting for a model. */
export function canRun(task: Runnable): boolean {
  return task.status === "ready" || (task.status === "draft" && !task.assignee_id);
}

/** A task's run controls, with how to get a CLI ready, and its run as it happens. */
export function RunNow({ task }: { task: Runnable }) {
  const [runId, setRunId] = useState<string | null>(null);
  return (
    <div className="run-now">
      <RunButtons task={task} onStarted={setRunId} />
      <RunnerNote />
      {!canRun(task) ? <p className="muted small">Mark the task ready to run it.</p> : null}
      {runId ? <RunConsole runId={runId} /> : null}
    </div>
  );
}

/** The CLI ready to run work on this computer, if there is one, and a way to start a task on it. */
export function useRunHere() {
  const { data: runners, isLoading } = useRunners();
  const invalidate = useInvalidate();
  const runner = runners?.find((r) => r.one_click && r.installed && r.signed_in !== false);
  async function start(taskId: string): Promise<string> {
    if (!runner) throw new Error("No AI app on this computer can run it yet.");
    const run = await post<LocalRun>(`/api/runners/${runner.id}/runs`, { task_id: taskId });
    await invalidate(keys.tasks, runnerKeys, keys.skills);
    return run.id;
  }
  return { runner, checking: isLoading, start };
}

/** Work just asked for: started at once on this computer's CLI when one is ready, shown as it
 * happens; otherwise how to run it (a copied prompt) while it waits for a model. */
export function Working({ task, waiting }: { task: Runnable; waiting: string }) {
  const { runner, checking, start } = useRunHere();
  const [runId, setRunId] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const started = useRef(false);
  useEffect(() => {
    if (started.current || !runner || !canRun(task)) return;
    started.current = true;
    start(task.id).then(setRunId, setError);
  }, [runner, task]);
  if (runId) return <RunConsole runId={runId} />;
  if (checking || (runner && !error)) return <p className="muted small">Starting {runner?.label ?? "your AI"}…</p>;
  return (
    <div className="stack">
      <p className="small" role="status">
        {waiting}
      </p>
      <RunButtons task={task} onStarted={setRunId} />
      <RunnerNote />
      <ErrorNote error={error} />
    </div>
  );
}

/** "Run now" with the CLI that is ready on this computer, and "Copy prompt" for any client. */
export function RunButtons({ task, onStarted }: { task: Runnable; onStarted: (runId: string) => void }) {
  const { data: runners } = useRunners();
  const invalidate = useInvalidate();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const runner = runners?.find((r) => r.one_click && r.installed && r.signed_in !== false);

  async function start(chosen: RunnerStatus) {
    setBusy(true);
    setError(null);
    try {
      const run = await post<LocalRun>(`/api/runners/${chosen.id}/runs`, { task_id: task.id });
      await invalidate(keys.tasks, keys.brain);
      onStarted(run.id);
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="row small">
        {runner ? (
          <button type="button" className="primary" disabled={busy || !canRun(task)} onClick={() => void start(runner)}>
            Run now with {runner.label}
          </button>
        ) : null}
        <CopyPrompt taskId={task.id} />
      </div>
      <ErrorNote error={error} />
    </>
  );
}

/** What stands between this computer and a one-click run, if anything. */
export function RunnerNote() {
  const { data: runners } = useRunners();
  if (!runners) return null;
  const installed = runners.find((r) => r.one_click && r.installed);
  if (installed?.signed_in === false) return <SignIn runner={installed} />;
  if (installed) return null;
  return (
    <p className="muted small">
      To run tasks from here with one click, <Link to="/settings?tab=connections#runners">set up Claude Code on this computer</Link>.
      Meanwhile, copy the prompt into any connected model.
    </p>
  );
}

/** Copies the prompt that runs this one task in any connected client. */
export function CopyPrompt({ taskId }: { taskId: string }) {
  const [state, setState] = useState<"idle" | "copied" | "shown">("idle");
  const [text, setText] = useState("");
  async function copy() {
    const { prompt } = await get<{ prompt: string }>(`/api/tasks/${taskId}/prompt`);
    setText(prompt);
    try {
      if (!navigator.clipboard) throw new Error("no clipboard");
      await navigator.clipboard.writeText(prompt);
      setState("copied");
    } catch {
      setState("shown"); // no clipboard (an insecure context, say): show it to copy by hand
    }
  }
  return (
    <>
      <button type="button" onClick={() => void copy()}>
        {state === "copied" ? "Prompt copied" : "Copy prompt"}
      </button>
      {state === "shown" ? <CopyBlock label="Paste this into a connected model" text={text} /> : null}
    </>
  );
}

/** Helps a person sign a CLI in; the CLI keeps the login, the app never sees it. */
export function SignIn({ runner }: { runner: RunnerStatus }) {
  const check = useCheckRunners();
  const [opened, setOpened] = useState<{ opened: boolean; command: string } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [checking, setChecking] = useState(false);
  async function open() {
    setError(null);
    try {
      setOpened(await post<{ opened: boolean; command: string }>(`/api/runners/${runner.id}/sign-in`));
    } catch (caught) {
      setError(caught);
    }
  }
  async function again() {
    setChecking(true);
    try {
      await check();
    } finally {
      setChecking(false);
    }
  }
  return (
    <div className="sign-in">
      <p>{runner.label} on this computer is not signed in yet.</p>
      <div className="row">
        <button type="button" className="primary" onClick={() => void open()}>
          Sign in to {runner.label}
        </button>
        <button type="button" disabled={checking} onClick={() => void again()}>
          {checking ? "Checking…" : "Check again"}
        </button>
      </div>
      {opened?.opened ? (
        <p className="muted small">A terminal opened: finish signing in there and in your browser, then check again.</p>
      ) : null}
      {opened && !opened.opened ? (
        <p className="muted small">
          Run <code>{opened.command}</code> in a terminal on this computer, then check again.
        </p>
      ) : null}
      <ErrorNote error={error} />
    </div>
  );
}

/** A run's work as it happens: what the model says, the tools it calls, how it ends. */
export function RunConsole({ runId }: { runId: string }) {
  const { data: run, error } = useLocalRun(runId);
  const invalidate = useInvalidate();
  const end = useRef<HTMLLIElement>(null);
  const active = !run || ACTIVE.includes(run.status);
  const count = run?.events.length ?? 0;

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "nearest" });
  }, [count]);
  const status = run?.status;
  // When it ends, everything it touched is worth reading again. (Keyed on the status alone:
  // `invalidate` is a new function every render.)
  useEffect(() => {
    if (status && !ACTIVE.includes(status))
      void invalidate(keys.tasks, keys.brain, keys.notes, keys.home, keys.events, keys.skills, runnerKeys);
  }, [status]);

  if (!run) return <ErrorNote error={error} />;
  return (
    <div className="console" aria-label={`Run of ${run.task_title}`}>
      <div className="console-head">
        <Pill status={run.status} />
        <span className="muted">{run.task_title}</span>
        {active && run.stopping ? <span className="muted small">Stopping…</span> : null}
        {active && !run.stopping ? (
          <button type="button" className="link" onClick={() => void post(`/api/runners/runs/${run.id}/cancel`)}>
            Stop
          </button>
        ) : null}
      </div>
      <ol className="console-lines" role="log" aria-live="polite">
        {run.events.map((event, index) => (
          <li key={event.seq} className={`line line-${event.kind}`} ref={index === run.events.length - 1 ? end : undefined}>
            <RunLine event={event} />
          </li>
        ))}
      </ol>
    </div>
  );
}

/** One step of a run, as the console shows it. */
export function RunLine({ event }: { event: RunEvent }) {
  switch (event.kind) {
    case "tool":
      return (
        <>
          <span className="tool-name">{event.name}</span>
          {event.text ? <span className="muted"> {event.text}</span> : null}
        </>
      );
    case "tool_result":
      return <span className={event.ok === false ? "error" : "muted"}>{event.text || (event.ok ? "done" : "failed")}</span>;
    case "result":
      return <strong>{event.text}</strong>;
    case "done":
      return <strong className={event.ok ? "" : "error"}>{event.text}</strong>;
    case "files":
      return <strong>{event.text}</strong>;
    default:
      return <span className="prewrap">{event.text}</span>;
  }
}
