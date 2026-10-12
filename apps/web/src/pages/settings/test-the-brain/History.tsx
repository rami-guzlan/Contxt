// History: every run, filtered by kind, and any two compared: the measures that moved and the
// cases that flipped. Markers show where the engine, the snapshot or a bar changed.

import { useState } from "react";

import { Empty, ErrorNote, Loading, Section } from "../../../components/ui";
import { when } from "../../../lib/format";
import { useTtbCompare, useTtbRuns } from "./api";
import { Chip, dollars, seconds, shown, type Go } from "./shared";
import type { RunRow } from "./types";

const MARKED: [string, string][] = [
  ["engine_ref", "Engine changed"],
  ["snapshot", "Snapshot refreshed"],
  ["gates", "Bars changed"],
  ["lock", "Models changed"],
];

/** What changed between a run and the one before it. */
function markers(run: RunRow, older: RunRow | undefined): string[] {
  if (!older) return [];
  const out: string[] = [];
  for (const [key, words] of MARKED) {
    const now = run.config[key];
    const before = older.config[key];
    if (now !== undefined && before !== undefined && JSON.stringify(now) !== JSON.stringify(before)) {
      out.push(key === "engine_ref" ? `${words}: ${String(before)} to ${String(now)}` : words);
    }
  }
  return out;
}

export function History({ go, a, b }: { go: Go; a?: string; b?: string }) {
  const [kind, setKind] = useState("");
  const all = useTtbRuns();
  const filtered = useTtbRuns(kind || undefined);
  const [picked, setPicked] = useState<string[]>(a && b ? [a, b] : []);
  const compare = useTtbCompare(picked[0], picked[1]);
  if (all.isLoading) return <Loading />;
  const runs = filtered.data?.runs ?? [];
  const kinds = [...new Set((all.data?.runs ?? []).map((r) => r.kind))];
  if (!all.data?.runs.length) {
    return (
      <Empty why="No runs yet. Every run you start is kept here, so you can see how the Brain changes over time.">
        <button type="button" className="primary" onClick={() => go("run")}>
          Go to Run
        </button>
      </Empty>
    );
  }
  const toggle = (run: string) => {
    const next = picked.includes(run) ? picked.filter((p) => p !== run) : [...picked, run].slice(-2);
    // Older first: the list is newest first, so the later one in the list is the older run.
    const order = (all.data?.runs ?? []).map((r) => r.run);
    setPicked(next.length === 2 ? [...next].sort((x, y) => order.indexOf(y) - order.indexOf(x)) : next);
  };
  return (
    <>
      <div className="ttb-filters">
        <label className="field">
          <span className="field-label">Show</span>
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">Every kind of run</option>
            {kinds.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </label>
        <p className="muted small">Tick two runs to compare them.</p>
      </div>
      <div className="table-wrap">
        <table className="table ttb-stack">
          <caption className="sr-only">Every run, newest first</caption>
          <thead>
            <tr>
              <th scope="col">Compare</th>
              <th scope="col">Run</th>
              <th scope="col">When</th>
              <th scope="col">Took</th>
              <th scope="col">Cost</th>
              <th scope="col">Failing</th>
              <th scope="col">What changed</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r, i) => {
              const note = markers(r, runs[i + 1]);
              return (
                <tr key={r.run}>
                  <td data-label="Compare">
                    <input type="checkbox" aria-label={`Compare ${r.run}`} checked={picked.includes(r.run)} onChange={() => toggle(r.run)} />
                  </td>
                  <th scope="row">
                    {r.kind} {!r.valid ? <Chip tone="blocked">Not valid</Chip> : null}
                    <br />
                    <button type="button" className="link small" onClick={() => go("cases", { run: r.run })}>
                      {r.run}
                    </button>
                  </th>
                  <td data-label="When">{when(r.ended ?? r.started)}</td>
                  <td data-label="Took">{seconds(r.cost.seconds)}</td>
                  <td data-label="Cost">{dollars(r.cost.usd_estimate)}</td>
                  <td data-label="Failing">{r.failing}</td>
                  <td className="small" data-label="What changed">{note.length ? note.join("; ") : ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {picked.length === 2 ? (
        <Section title="The two runs side by side">
          {compare.isLoading ? <Loading /> : null}
          <ErrorNote error={compare.error} />
          {compare.data ? (
            <>
              <h4>Measures that moved</h4>
              <table className="table">
                <caption className="sr-only">Measures in the older run against the newer</caption>
                <thead>
                  <tr>
                    <th scope="col">Measure</th>
                    <th scope="col">Before</th>
                    <th scope="col">After</th>
                    <th scope="col">Change</th>
                  </tr>
                </thead>
                <tbody>
                  {compare.data.metrics
                    .filter((m) => m.delta !== 0)
                    .map((m) => (
                      <tr key={m.id}>
                        <th scope="row">{m.id.replace(":", ", ")}</th>
                        <td>{shown(m.from)}</td>
                        <td>{shown(m.to)}</td>
                        <td>
                          {m.delta === null ? "New" : m.delta > 0 ? `up ${shown(Math.abs(m.delta))}` : `down ${shown(Math.abs(m.delta))}`}
                          {m.met_from !== m.met_to && m.met_to !== null ? <span className="small"> {m.met_to ? " now met" : " no longer met"}</span> : null}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
              {compare.data.metrics.every((m) => m.delta === 0) ? <p className="muted">Nothing moved between these two runs.</p> : null}
              <h4>Cases that flipped</h4>
              {compare.data.flipped.length ? (
                <ul className="list compact-list">
                  {compare.data.flipped.map((c) => (
                    <li key={c.id}>
                      <button type="button" className="link" onClick={() => go("cases", { run: compare.data!.b, case: c.id })}>
                        {c.title || c.id}
                      </button>{" "}
                      <Chip tone={c.to ? "done" : "blocked"}>{c.to ? "Now passes" : "Now fails"}</Chip>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted">No case changed its result.</p>
              )}
            </>
          ) : null}
        </Section>
      ) : null}
    </>
  );
}
