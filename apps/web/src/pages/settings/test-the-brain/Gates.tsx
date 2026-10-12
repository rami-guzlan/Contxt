// Gates, read only: every bar with its value, interval, verdict, trend and where it came from.
// Gates change only in the Lab's own pane, never here. A row opens the cases behind it.

import { Empty, ErrorNote, Loading } from "../../../components/ui";
import { useTtbGates } from "./api";
import { Chip, Sparkline, barWords, interval, shown, verdictOf, type Go } from "./shared";

export function Gates({ go }: { go: Go }) {
  const { data, isLoading, error } = useTtbGates();
  if (isLoading) return <Loading />;
  if (!data) return <ErrorNote error={error} />;
  if (!data.gates.length) {
    return (
      <Empty why="No bars are set yet. A bar says how good a measure has to be; the Lab or the checks on your Brain list them here." />
    );
  }
  return (
    <>
      <p className="muted small">
        Read only. A hard bar fails a run; a watch bar is tracked and never fails one. Bars change only in the Lab's own pane, with a reason.
      </p>
      <div className="table-wrap">
        <table className="table ttb-stack">
          <caption className="sr-only">Every bar, with its latest value</caption>
          <thead>
            <tr>
              <th scope="col">Bar</th>
              <th scope="col">Value</th>
              <th scope="col">Needs to be</th>
              <th scope="col">Verdict</th>
              <th scope="col">Over runs</th>
              <th scope="col">Comes from</th>
            </tr>
          </thead>
          <tbody>
            {data.gates.map((g) => {
              const verdict = verdictOf(g);
              return (
                <tr key={g.id}>
                  <th scope="row">
                    {g.name}
                    <span className="muted small"> {g.kind === "hard" ? "hard" : "watch"}</span>
                  </th>
                  <td data-label="Value">
                    {shown(g.value, g.bar)}
                    {g.ci ? <span className="muted small"> ({interval(g.ci, g.bar)})</span> : null}
                  </td>
                  <td data-label="Needs to be">{barWords(g.bar)}</td>
                  <td data-label="Verdict">
                    <Chip tone={verdict.tone}>{verdict.text}</Chip>
                  </td>
                  <td data-label="Over runs">
                    <Sparkline values={g.trend} bar={g.bar} label={g.name} />
                  </td>
                  <td className="small" data-label="Comes from">
                    {g.source || "Not stated"}{" "}
                    {g.run ? (
                      <button type="button" className="link small" onClick={() => go("cases", { run: g.run as string, gate: g.id })}>
                        See its cases
                      </button>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
