// This computer: which laptop steps run here and which fall back, their speed against the
// budget, and the memory they used; and a link to the local models settings.

import { Link } from "react-router";

import { Empty, KeyValues, Section } from "../../../components/ui";
import { Chip, readyWords } from "./shared";
import type { Qualification, State } from "./types";

function row(q: Qualification) {
  const on = q.state === "on";
  const slow = q.speed_ms != null && q.budget_ms != null && q.speed_ms > q.budget_ms;
  return (
    <tr key={q.step}>
      <th scope="row">{q.step}</th>
      <td>{q.model ?? ""}</td>
      <td>
        <Chip tone={on ? "done" : "active"}>{on ? "Runs here" : "Falls back"}</Chip>
        {!on && q.fallback ? <span className="muted small"> {q.fallback}</span> : null}
      </td>
      <td>
        {q.speed_ms != null ? `${q.speed_ms} ms` : ""}
        {q.budget_ms != null ? <span className="muted small"> of {q.budget_ms} ms</span> : null}
        {slow ? <span className="small"> over the budget</span> : null}
      </td>
      <td>{q.peak_ram_mb != null ? `${q.peak_ram_mb} MB` : ""}</td>
    </tr>
  );
}

export function ThisComputer({ state }: { state: State }) {
  const table = state.status?.qualification ?? [];
  const computer = state.builtin?.computer;
  const waits = (state.builtin?.waits ?? []).filter((w) => w.suite === "The machine check");
  return (
    <>
      <Section title="Which steps run on this computer">
        {table.length ? (
          <div className="table-wrap">
            <table className="table">
              <caption className="sr-only">Each step on this computer</caption>
              <thead>
                <tr>
                  <th scope="col">Step</th>
                  <th scope="col">Model</th>
                  <th scope="col">Here</th>
                  <th scope="col">Speed</th>
                  <th scope="col">Peak memory</th>
                </tr>
              </thead>
              <tbody>{table.map(row)}</tbody>
            </table>
          </div>
        ) : (
          <Empty why={waits[0] ? `${readyWords(waits[0]).text}. It will list each step, whether it runs here or falls back, its speed against the budget, and its memory.` : "Nothing has been checked on this computer yet. Run the machine check from Run when it is listed."} />
        )}
        <p>
          <Link className="button" to="/settings?tab=computer">
            Open the local models settings
          </Link>
        </p>
      </Section>
      {computer ? (
        <Section title="This computer">
          <KeyValues
            rows={[
              ["System", computer.system],
              ["Setup it gets", computer.machine?.setup ?? ""],
              ["Memory", computer.machine?.ram_gb ? `${computer.machine.ram_gb} GB` : ""],
              ["Graphics", computer.machine ? computer.machine.gpu : ""],
              ["Models in memory at once", computer.machine?.models_ram_gb != null ? `${computer.machine.models_ram_gb} GB` : ""],
              ["Local model service", computer.machine ? (computer.machine.engine_running ? "Running" : `Not running${computer.machine.engine_reason ? `: ${computer.machine.engine_reason}` : ""}`) : ""],
              ["Processors", computer.cpus ? String(computer.cpus) : ""],
              ["Matching by meaning", computer.matching.enabled === false ? "Off" : computer.matching.present ? `Ready (${computer.matching.model ?? "local model"})` : "Not downloaded yet"],
              ["Retrieval engine", computer.engine ? "Part of this install" : "Waits for build step 3b"],
            ]}
          />
        </Section>
      ) : null}
    </>
  );
}
