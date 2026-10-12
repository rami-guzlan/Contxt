// Cases: one case at a time, drawn for its kind. A retrieval or brief case shows each note
// colored by its label, with its scores and why; an outcome shows the with and without answers
// side by side; a world shows plants found and missed; a session shows its turns; anything else
// is a table of expected against got. Real text stays on this machine.

import { useEffect, useState } from "react";

import { Empty, ErrorNote, Loading } from "../../../components/ui";
import { useTtbCase, useTtbCases, useTtbRuns } from "./api";
import { Chip, shown, type Go } from "./shared";
import type { CaseFull, CaseRow, NoteView, State } from "./types";

const KIND_WORDS: Record<string, string> = {
  retrieval: "Retrieval and briefs",
  outcome: "Outcomes",
  world: "Worlds",
  session: "Sessions",
  table: "Other checks",
};

export function Cases({ state, go, run, caseId, gate }: { state: State; go: Go; run?: string; caseId?: string; gate?: string }) {
  const runs = useTtbRuns();
  const chosen = run ?? runs.data?.runs[0]?.run;
  const [kind, setKind] = useState("");
  const [result, setResult] = useState("");
  const page = useTtbCases(chosen, { kind: kind || undefined, result: result || undefined, gate });
  const [open, setOpen] = useState<string | undefined>(caseId);
  useEffect(() => setOpen(caseId), [caseId]);

  if (runs.isLoading) return <Loading />;
  if (!runs.data?.runs.length) {
    return (
      <Empty why="No runs yet, so there are no cases to open. Run a check first.">
        <button type="button" className="primary" onClick={() => go("run")}>
          Go to Run
        </button>
      </Empty>
    );
  }
  const kinds = page.data?.kinds ?? [];
  return (
    <div className="ttb-cases">
      <div className="ttb-case-list">
        <div className="ttb-filters">
          <label className="field">
            <span className="field-label">Run</span>
            <select value={chosen} onChange={(e) => go("cases", { run: e.target.value })}>
              {runs.data.runs.map((r) => (
                <option key={r.run} value={r.run}>
                  {r.kind}: {r.run.slice(0, 16)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Kind</span>
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">All kinds</option>
              {kinds.map((k) => (
                <option key={k} value={k}>
                  {KIND_WORDS[k] ?? k}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Result</span>
            <select value={result} onChange={(e) => setResult(e.target.value)}>
              <option value="">Passed and failed</option>
              <option value="fail">Failed</option>
              <option value="pass">Passed</option>
            </select>
          </label>
        </div>
        {gate ? (
          <p className="small">
            Cases behind <code>{gate}</code>, worst first.{" "}
            <button type="button" className="link" onClick={() => go("cases", chosen ? { run: chosen } : {})}>
              Show all
            </button>
          </p>
        ) : null}
        {page.isLoading ? <Loading /> : null}
        <ErrorNote error={page.error} />
        {page.data && !page.data.cases.length ? <p className="muted">No cases match. Change the filters above.</p> : null}
        {page.data?.skipped ? <p className="muted small">{page.data.skipped} line(s) did not fit the contract and were left out.</p> : null}
        <ul className="ttb-list" aria-label="Cases">
          {page.data?.cases.map((c) => (
            <CaseItem key={c.id} row={c} selected={open === c.id} onOpen={() => setOpen(c.id)} />
          ))}
        </ul>
        {page.data && page.data.total > page.data.cases.length ? (
          <p className="muted small">Showing the first {page.data.cases.length} of {page.data.total}. Filter to narrow them.</p>
        ) : null}
      </div>
      <div className="ttb-case-view">
        {open && chosen ? (
          <CaseDetail run={chosen} id={open} state={state} go={go} />
        ) : (
          <p className="muted">Pick a case on the left to see what happened in it.</p>
        )}
      </div>
    </div>
  );
}

function CaseItem({ row, selected, onOpen }: { row: CaseRow; selected: boolean; onOpen: () => void }) {
  const tone = row.pass === true ? "done" : row.pass === false ? "blocked" : "neutral";
  return (
    <li>
      <button type="button" className={selected ? "ttb-item active" : "ttb-item"} aria-current={selected} onClick={onOpen}>
        <Chip tone={tone}>{row.pass === true ? "Passed" : row.pass === false ? "Failed" : "Noted"}</Chip>
        <span className="ttb-item-title">{row.title || row.id}</span>
        <span className="muted small">{KIND_WORDS[row.kind] ?? row.kind}</span>
      </button>
    </li>
  );
}

function CaseDetail({ run, id, state, go }: { run: string; id: string; state: State; go: Go }) {
  const { data, isLoading, error } = useTtbCase(run, id);
  if (isLoading) return <Loading />;
  if (!data) return <ErrorNote error={error} />;
  return (
    <article className="ttb-case" aria-label={data.title || data.id}>
      <header>
        <h3>{data.title || data.id}</h3>
        <p className="small">
          <code>{data.id}</code> {data.suite ? <span className="muted">in {data.suite}</span> : null}{" "}
          {data.pass === true ? <Chip tone="done">Passed</Chip> : data.pass === false ? <Chip tone="blocked">Failed</Chip> : null}{" "}
          {data.sensitive ? <Chip tone="active">Marked sensitive</Chip> : null}
        </p>
        {data.request ? (
          <p className="ttb-request">
            <span className="muted small">The request</span>
            <br />“{data.request}”
          </p>
        ) : null}
        <p>
          <button type="button" onClick={() => go("watch", { run, case: data.id })}>
            Watch this case work
          </button>
        </p>
      </header>
      {data.kind === "retrieval" ? <Retrieval data={data} /> : null}
      {data.kind === "outcome" ? <Outcome data={data} /> : null}
      {data.kind === "world" ? <World data={data} /> : null}
      {data.kind === "session" ? <Session data={data} /> : null}
      {data.kind === "table" || !["retrieval", "outcome", "world", "session"].includes(data.kind) ? <Table data={data} /> : null}
      {Object.keys(data.measures ?? {}).length ? <Measures measures={data.measures} /> : null}
      <p className="muted small">{state.source === "lab" ? "Real text from the Lab, shown here on this computer only." : "From your own Brain, shown here on this computer only."}</p>
    </article>
  );
}

function Measures({ measures }: { measures: Record<string, unknown> }) {
  return (
    <dl className="kv ttb-measures">
      {Object.entries(measures)
        .filter(([, v]) => v !== null && v !== undefined)
        .map(([k, v]) => (
          <div key={k}>
            <dt>{k.replace(/_/g, " ")}</dt>
            <dd>{typeof v === "number" ? shown(v) : String(v)}</dd>
          </div>
        ))}
    </dl>
  );
}

const LABELS: Record<string, { text: string; tone: "done" | "ready" | "blocked" | "active" | "neutral" }> = {
  needed_delivered: { text: "Needed, delivered", tone: "done" },
  needed_missed: { text: "Needed, missed", tone: "blocked" },
  useful: { text: "Useful", tone: "ready" },
  noise: { text: "Noise", tone: "active" },
  wrong: { text: "Wrong", tone: "blocked" },
  judge: { text: "Marked by a judge", tone: "neutral" },
  unlabeled: { text: "Not labeled", tone: "neutral" },
};

export function NoteRow({ note }: { note: NoteView }) {
  const label = LABELS[note.label ?? ""] ?? { text: note.label || "Not labeled", tone: "neutral" as const };
  const scores = Object.entries(note.scores ?? {});
  return (
    <li className={`ttb-note-row label-${note.label ?? "none"}`}>
      <div className="row">
        <strong>{note.title || note.id}</strong>
        <Chip tone={label.tone}>{label.text}</Chip>
        {note.form ? <span className="muted small">{note.form === "none" ? "not in the brief" : note.form === "pointer" ? "as a pointer" : "in full"}</span> : null}
      </div>
      {scores.length ? (
        <p className="small muted">
          {scores.map(([k, v]) => `${k} ${shown(v)}`).join(", ")}
        </p>
      ) : null}
      {note.why ? <p className="small">{note.why}</p> : null}
    </li>
  );
}

function Retrieval({ data }: { data: CaseFull }) {
  const view = data.view;
  return (
    <>
      <h4>Notes</h4>
      {view.notes?.length ? (
        <ul className="ttb-notes">
          {view.notes.map((n) => (
            <NoteRow key={`${n.id}:${n.label}`} note={n} />
          ))}
        </ul>
      ) : (
        <p className="muted">No notes were recorded for this case.</p>
      )}
      {view.waits ? <p className="muted small">{view.waits}</p> : null}
      {view.standards?.length ? (
        <>
          <h4>Standards</h4>
          <ul className="list compact-list">
            {view.standards.map((s) => (
              <li key={s.id}>
                <Chip tone={s.pass ? "done" : "blocked"}>{s.pass ? "Passed" : "Failed"}</Chip> {s.name}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {view.brief ? (
        <details>
          <summary>The brief as delivered</summary>
          <pre className="ttb-pre">{view.brief}</pre>
        </details>
      ) : null}
    </>
  );
}

function Outcome({ data }: { data: CaseFull }) {
  const v = data.view;
  return (
    <>
      <div className="ttb-sides">
        <section className="ttb-side without" aria-label="Without your Brain">
          <h4>Without your Brain</h4>
          <p className="ttb-answer">{v.without?.text ?? "No answer recorded."}</p>
        </section>
        <section className="ttb-side with" aria-label="With your Brain">
          <h4>With your Brain</h4>
          <p className="ttb-answer">{v.with?.text ?? "No answer recorded."}</p>
        </section>
      </div>
      {v.key_points?.length ? (
        <>
          <h4>Key points</h4>
          <table className="table">
            <caption className="sr-only">Which answer had each key point</caption>
            <thead>
              <tr>
                <th scope="col">Point</th>
                <th scope="col">Without</th>
                <th scope="col">With</th>
              </tr>
            </thead>
            <tbody>
              {v.key_points.map((p) => (
                <tr key={p.text}>
                  <th scope="row">{p.text}</th>
                  <td>{p.without ? "Yes" : "No"}</td>
                  <td>{p.with ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}
      {v.violations?.length ? (
        <>
          <h4>Rules broken</h4>
          <ul className="list compact-list">
            {v.violations.map((x, i) => (
              <li key={i} className="ttb-violation">
                <strong>{x.rule}</strong> <span className="muted small">in the answer {x.arm === "with" ? "with" : "without"} your Brain</span>
                <br />
                <mark>{x.text}</mark>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </>
  );
}

function World({ data }: { data: CaseFull }) {
  const v = data.view;
  return (
    <>
      <h4>Planted changes</h4>
      <ul className="list compact-list">
        {(v.plants ?? []).map((p) => (
          <li key={p.id}>
            <Chip tone={p.found ? "done" : "blocked"}>{p.found ? "Found" : "Missed"}</Chip> {p.what}
          </li>
        ))}
      </ul>
      {v.false_alarms?.length ? (
        <>
          <h4>False alarms</h4>
          <ul className="list compact-list">
            {v.false_alarms.map((f, i) => (
              <li key={i}>{f.what}</li>
            ))}
          </ul>
        </>
      ) : null}
      {v.suggestions?.length ? (
        <>
          <h4>Suggestions</h4>
          <ul className="list compact-list">
            {v.suggestions.map((s, i) => (
              <li key={i}>
                {s.text}
                {s.impact?.length ? <span className="muted small"> Touches: {s.impact.join(", ")}.</span> : null}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </>
  );
}

function Session({ data }: { data: CaseFull }) {
  const v = data.view;
  return (
    <>
      <ol className="ttb-turns">
        {(v.turns ?? []).map((t, i) => (
          <li key={i} className={`turn-${t.role}`}>
            <span className="muted small">{t.role === "user" ? "You" : t.role === "brain" ? "The Brain" : t.role}</span>
            <p>{t.text}</p>
          </li>
        ))}
      </ol>
      {v.checks?.length ? (
        <ul className="list compact-list">
          {v.checks.map((c) => (
            <li key={c.name}>
              <Chip tone={c.pass ? "done" : "blocked"}>{c.pass ? "Passed" : "Failed"}</Chip> {c.name}
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}

function Table({ data }: { data: CaseFull }) {
  const rows = data.view.rows;
  if (!rows?.length) return <p className="muted">This case has nothing more to show.</p>;
  const columns = data.view.columns ?? ["What", "Expected", "Got"];
  const [first = "What", second = "Expected", third = "Got"] = columns;
  const showExpected = rows.some((r) => r.expected);
  return (
    <table className="table">
      <caption className="sr-only">Expected against got</caption>
      <thead>
        <tr>
          <th scope="col">{first}</th>
          {showExpected ? <th scope="col">{second}</th> : null}
          <th scope="col">{showExpected ? third : (columns[1] ?? third)}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={`${r.label}:${i}`} className={r.pass === false ? "ttb-fail" : undefined}>
            <th scope="row">{r.label}</th>
            {showExpected ? <td>{r.expected}</td> : null}
            <td>{r.got}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
