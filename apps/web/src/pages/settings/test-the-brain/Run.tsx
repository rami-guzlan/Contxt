// Run: one button per kind of run the source lists, with what it covers, how long it took last
// time and what it costs. A paid run shows its estimate and needs a second press. The run
// streams live, suite by suite, and can be cancelled at any time. One run at a time.

import { useState } from "react";

import { ApiError } from "../../../api/client";
import { ErrorNote, Section } from "../../../components/ui";
import { when } from "../../../lib/format";
import { useCancelRun, useLiveRun, useStartRun } from "./api";
import { Chip, dollars, seconds, type Go } from "./shared";
import type { ActiveRun, ProgressEvent, RunKind, State } from "./types";

export function RunView({ state, go }: { state: State; go: Go }) {
  const status = state.status;
  const live = useLiveRun(true);
  const start = useStartRun();
  const cancel = useCancelRun();
  const [armed, setArmed] = useState<string | null>(null);
  const [request, setRequest] = useState("");
  const [suites, setSuites] = useState<Record<string, string>>({});
  const active = live.active;
  const running = active?.state === "running" || !!state.running;
  const lockedBy = status?.lock_holder && !(active?.state === "running") ? status.lock_holder : null;
  const asksForRequest = (kind: RunKind) => state.source === "builtin" && kind.id === "difference";

  const press = (kind: RunKind) => {
    if (kind.paid && armed !== kind.id) {
      setArmed(kind.id);
      return;
    }
    start.mutate(
      { kind: kind.id, suite: suites[kind.id] || null, confirm: kind.paid ? true : undefined, request: asksForRequest(kind) ? request || null : null },
      {
        onSuccess: () => {
          setArmed(null);
          void live.refresh();
        },
      },
    );
  };

  if (!status) return <ErrorNote error={state.error ?? "Nothing to run yet."} />;
  return (
    <>
      <Section title="What will run">
        <dl className="kv">
          <div>
            <dt>Source</dt>
            <dd>{state.lab?.name ?? state.builtin?.name ?? "Checks on your own Brain"}</dd>
          </div>
          <div>
            <dt>Brain under test</dt>
            <dd>{state.source === "lab" ? (status.brain ?? "The Lab's own Brain") + " (never your own)" : (status.brain ?? "your Brain") + ", read on a copy"}</dd>
          </div>
          {status.engine_ref ? (
            <div>
              <dt>Engine version</dt>
              <dd>{status.engine_ref}</dd>
            </div>
          ) : null}
          {status.machine_setup ? (
            <div>
              <dt>This machine</dt>
              <dd>{status.machine_setup}</dd>
            </div>
          ) : null}
        </dl>
        {lockedBy ? (
          <p className="ttb-note" role="status">
            The Lab is busy: run {lockedBy} is going. You can follow it below and cancel it, or wait for it to finish.
          </p>
        ) : null}
      </Section>
      <ul className="ttb-kinds">
        {status.run_kinds.map((kind) => (
          <li key={kind.id} className="ttb-kind">
            <div className="row">
              <strong>{kind.name || kind.id}</strong>
              {kind.paid ? <Chip tone="active">Paid</Chip> : <Chip tone="done">Free</Chip>}
            </div>
            <p className="small">{kind.covers}</p>
            <p className="muted small">{lastWords(kind)}</p>
            {kind.suites.length ? (
              <label className="field">
                <span className="field-label">Which part</span>
                <select value={suites[kind.id] ?? ""} onChange={(e) => setSuites({ ...suites, [kind.id]: e.target.value })}>
                  <option value="">Everything it covers</option>
                  {kind.suites.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            {asksForRequest(kind) ? (
              <label className="field">
                <span className="field-label">The request to compare</span>
                <textarea rows={2} value={request} onChange={(e) => setRequest(e.target.value)} placeholder="Leave empty to use your latest request" />
              </label>
            ) : null}
            {armed === kind.id ? (
              <p className="ttb-note" role="status">
                {estimate(kind)} Press the button again to run it.
              </p>
            ) : null}
            <div className="row">
              <button type="button" className="primary" disabled={running || start.isPending || !!lockedBy} onClick={() => press(kind)}>
                {armed === kind.id ? `Yes, run ${kind.name || kind.id}` : `Run ${kind.name || kind.id}`}
              </button>
              {armed === kind.id ? (
                <button type="button" className="link" onClick={() => setArmed(null)}>
                  Not now
                </button>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
      <ErrorNote error={startError(start.error)} />
      <LiveRun
        active={active}
        events={live.events}
        lockedBy={lockedBy}
        onCancel={(run) => cancel.mutate(run, { onSuccess: () => void live.refresh() })}
        cancelling={cancel.isPending}
        go={go}
      />
      <ErrorNote error={cancel.error} />
    </>
  );
}

function startError(error: unknown): unknown {
  if (error instanceof ApiError && error.details.needs_confirmation) return null;
  return error;
}

function lastWords(kind: RunKind): string {
  const last = kind.last;
  if (!last || (!last.at && !last.seconds)) return "Not run yet.";
  const bits = [last.at ? `Last run ${when(last.at)}` : "Last run", last.seconds ? `took ${seconds(last.seconds)}` : "", last.usd ? `cost ${dollars(last.usd)}` : ""];
  return bits.filter(Boolean).join(", ") + ".";
}

function estimate(kind: RunKind): string {
  const e = kind.estimate;
  const parts: string[] = [];
  if (e?.usd) parts.push(`about ${dollars(e.usd)}`);
  if (e?.calls) parts.push(`about ${e.calls} model calls on your plan`);
  if (e?.seconds) parts.push(`about ${seconds(e.seconds)}`);
  return `${kind.name || kind.id} uses paid model calls${parts.length ? `: ${parts.join(", ")}` : ""}.`;
}

// ---------------------------------------------------------------- the live run

interface SuiteLine {
  suite: string;
  done: number;
  total: number;
  ended: boolean;
}

function fold(events: ProgressEvent[]): { suites: SuiteLine[]; failures: ProgressEvent[]; messages: ProgressEvent[] } {
  const suites = new Map<string, SuiteLine>();
  const failures: ProgressEvent[] = [];
  const messages: ProgressEvent[] = [];
  for (const e of events) {
    const name = e.suite ?? "";
    if (e.event === "suite_start") suites.set(name, { suite: name, done: 0, total: e.total ?? 0, ended: false });
    if (e.event === "case_done" && name) {
      const line = suites.get(name) ?? { suite: name, done: 0, total: e.total ?? 0, ended: false };
      line.done = e.done ?? line.done + 1;
      line.total = e.total ?? line.total;
      suites.set(name, line);
    }
    if (e.event === "suite_end" && name) {
      const line = suites.get(name) ?? { suite: name, done: 0, total: e.total ?? 0, ended: true };
      line.ended = true;
      line.done = e.done ?? line.done;
      line.total = e.total ?? line.total;
      suites.set(name, line);
    }
    if (e.event === "failure") failures.push(e);
    if (e.message && e.event !== "failure") messages.push(e);
  }
  return { suites: [...suites.values()], failures, messages };
}

function LiveRun({
  active,
  events,
  lockedBy,
  onCancel,
  cancelling,
  go,
}: {
  active: ActiveRun | null;
  events: ProgressEvent[];
  lockedBy: string | null;
  onCancel: (run: string) => void;
  cancelling: boolean;
  go: Go;
}) {
  if (!active) return null;
  const { suites, failures, messages } = fold(events);
  const running = active.state === "running";
  const runId = active.run;
  const verdict: Record<string, { text: string; tone: "done" | "blocked" | "active" | "ready" }> = {
    running: { text: "Running", tone: "ready" },
    done: { text: "Finished", tone: "done" },
    failed: { text: "Stopped with an error", tone: "blocked" },
    cancelled: { text: "Cancelled", tone: "active" },
  };
  const word = verdict[active.state] ?? verdict["running"]!;
  return (
    <Section
      title={running ? "Running now" : "The last run"}
      actions={
        running && runId ? (
          <button type="button" disabled={cancelling} onClick={() => onCancel(runId)}>
            {cancelling ? "Cancelling…" : "Cancel this run"}
          </button>
        ) : null
      }
    >
      <p>
        <Chip tone={word.tone}>{word.text}</Chip> <span className="small">{active.kind ?? "a run"}</span>
        {runId ? <span className="muted small"> {runId}</span> : null}
      </p>
      {active.ours === false ? <p className="muted small">{active.message}</p> : null}
      {lockedBy && !running ? <p className="muted small">Run {lockedBy} holds the Lab's run lock.</p> : null}
      <ul className="ttb-suites" aria-live="polite">
        {suites.map((s) => (
          <li key={s.suite}>
            <span>{s.suite}</span>
            <progress max={s.total || 1} value={s.done} aria-label={`${s.suite}: ${s.done} of ${s.total || "?"} cases`} />
            <span className="muted small">
              {s.done} of {s.total || "?"}
              {s.ended ? " done" : ""}
            </span>
          </li>
        ))}
      </ul>
      {failures.length ? (
        <>
          <h4>Failures as they happened</h4>
          <ul className="list compact-list">
            {failures.map((f, i) => (
              <li key={i}>
                {f.case ? <code>{f.case}</code> : null} {f.message}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {messages.length && running ? <p className="muted small">{messages[messages.length - 1]?.message}</p> : null}
      {!running && active.state === "done" ? (
        <p>
          <button type="button" className="primary" onClick={() => go("cases", runId ? { run: runId } : {})}>
            Open its cases
          </button>{" "}
          <button type="button" className="link" onClick={() => go("overview")}>
            See what it means for the Brain
          </button>
        </p>
      ) : null}
      {active.state === "failed" ? (
        <p className="error" role="alert">
          {active.message || "The run stopped with an error."} Check the Lab's own log, then run it again.
        </p>
      ) : null}
      {active.state === "cancelled" ? <p className="muted">{active.message || "Stopped on request."} Nothing is left running.</p> : null}
    </Section>
  );
}
