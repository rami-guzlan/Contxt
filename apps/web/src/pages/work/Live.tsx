// Workspace's live context (UX plan 4.3): sheets, boards and calendars your AIs read and keep
// current, the medium-term context of the State tier. Your docs stay your thinking space; these
// are values that change too often for review, kept structured, logged and current.

import { type FormEvent, useCallback, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { useLive, useLiveAct, useRowHistory, useSheet } from "../../api/hooks";
import type { ColumnType, Friction, SheetView, StateRow, StateWaiting } from "../../api/types";
import { Board, Calendar, Grid, dateColumns, statusColumns } from "../../components/live/SheetViews";
import { Empty, ErrorNote, Field, Loading, Section } from "../../components/ui";
import { when } from "../../lib/format";

const FRICTION_WORDS: Record<Friction, string> = { free: "AIs may change", confirm: "Ask me first", locked: "Only me" };
const TYPES: ColumnType[] = ["text", "number", "money", "date", "date_range", "status", "person", "link", "reference"];

export const sheetUrl = (id: string) => `/work/live/${encodeURIComponent(id)}`;

/** The live context group on Workspace: the sheets, a new one from a template, and what waits. */
export function LiveSection() {
  const { data, isLoading, error } = useLive();
  const act = useLiveAct();
  const [template, setTemplate] = useState("accounts");
  if (isLoading) return <Loading />;
  if (!data) return <ErrorNote error={error} />;
  return (
    <Section title="Live context">
      <p className="muted small">
        Sheets, boards and calendars your AIs read and keep current: accounts, repos, a content calendar. Every change is logged with who made it,
        and a value an AI filled is marked until you touch it.
      </p>
      {data.sheets.length ? (
        <ul className="list compact-list">
          {data.sheets.map((s) => (
            <li key={s.id}>
              <Link to={sheetUrl(s.id)}>{s.title}</Link>
              <span className="muted small"> · {s.columns.length} columns{s.builtin ? " · built in" : ""}</span>
            </li>
          ))}
        </ul>
      ) : (
        <Empty why="No live context yet. Start a sheet from a template." />
      )}
      <div className="row">
        <select aria-label="Template" value={template} onChange={(event) => setTemplate(event.target.value)}>
          {data.templates
            .filter((t) => !data.sheets.some((s) => s.id === t.id) || !t.builtin)
            .map((t) => (
              <option key={t.id} value={t.id}>
                {t.title}
              </option>
            ))}
        </select>
        <button type="button" className="primary" disabled={act.isPending} onClick={() => act.mutate({ action: "create_sheet", fields: { template } })}>
          New sheet
        </button>
      </div>
      <ErrorNote error={act.error} />
      <Waiting items={data.waiting} />
    </Section>
  );
}

/** AI values that wait for your tap (columns set to "Ask me first", or everything under Regulated). */
export function Waiting({ items }: { items: StateWaiting[] }) {
  const act = useLiveAct();
  if (!items.length) return null;
  return (
    <div className="stack">
      <h3 className="small-head">Waiting for you</h3>
      <ul className="list compact-list small">
        {items.map((w) => (
          <li key={w.event}>
            {w.sheet_title} · {w.row} · {w.column}: <strong>{String(w.value)}</strong> <span className="muted">({w.source || "an AI"})</span>{" "}
            <button type="button" className="link small" onClick={() => act.mutate({ action: "decide", fields: { sheet: w.sheet, row: w.row, event: w.event, accept: true } })}>
              Keep
            </button>{" "}
            <button type="button" className="link small" onClick={() => act.mutate({ action: "decide", fields: { sheet: w.sheet, row: w.row, event: w.event, accept: false } })}>
              Turn down
            </button>
          </li>
        ))}
      </ul>
      <ErrorNote error={act.error} />
    </div>
  );
}

export function SheetPage() {
  const { sheetId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const { data, isLoading, error } = useSheet(sheetId);
  const act = useLiveAct();
  const [open, setOpen] = useState<StateRow | null>(null);
  const write = useCallback(
    (row: StateRow, values: Record<string, unknown>) => act.mutate({ action: "write", fields: { sheet: sheetId, row: row.key, values } }),
    [act, sheetId],
  );
  if (isLoading) return <Loading />;
  if (!data) return <ErrorNote error={error} />;
  const statuses = statusColumns(data);
  const dates = dateColumns(data);
  const view = params.get("view") ?? "grid";
  const by = params.get("by");
  const set = (next: Record<string, string>) => setParams({ ...Object.fromEntries(params), ...next }, { replace: true });
  return (
    <div className="work-tab sheet-page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/work/workspace">Workspace</Link>
      </nav>
      <h1>{data.sheet.title}</h1>
      {data.sheet.description ? <p className="lede">{data.sheet.description}</p> : null}
      <div className="row" role="tablist" aria-label="View">
        {(["grid", "board", "calendar"] as const).map((v) => (
          <button
            key={v}
            type="button"
            role="tab"
            aria-selected={view === v}
            disabled={(v === "board" && !statuses.length) || (v === "calendar" && !dates.length)}
            className={view === v ? "primary" : ""}
            onClick={() => set({ view: v })}
          >
            {v === "grid" ? "Sheet" : v === "board" ? "Board" : "Calendar"}
          </button>
        ))}
        {view === "board" && statuses.length > 1 ? (
          <select aria-label="Group by" value={by ?? statuses[0]?.name} onChange={(event) => set({ by: event.target.value })}>
            {statuses.map((c) => (
              <option key={c.name}>{c.name}</option>
            ))}
          </select>
        ) : null}
        {view === "calendar" && dates.length > 1 ? (
          <select aria-label="Place by" value={by ?? dates[0]?.name} onChange={(event) => set({ by: event.target.value })}>
            {dates.map((c) => (
              <option key={c.name}>{c.name}</option>
            ))}
          </select>
        ) : null}
      </div>
      <ErrorNote error={act.error} />
      {view === "board" && statuses.length ? (
        <Board view={data} by={statuses.find((c) => c.name === by) ?? statuses[0]!} onWrite={write} onOpen={setOpen} />
      ) : view === "calendar" && dates.length ? (
        <Calendar view={data} by={dates.find((c) => c.name === by) ?? dates[0]!} onWrite={write} onOpen={setOpen} />
      ) : (
        <Grid view={data} onWrite={write} onOpen={setOpen} />
      )}
      <Summary view={data} />
      <p className="muted small legend">
        <span className="cell-ai">AI-filled</span> until you touch it · <span className="cell-stale">older than its column allows</span> ·{" "}
        <span className="cell-computed">computed</span>
      </p>
      {data.sheet.builtin ? null : <AddRow sheet={data.sheet.id} keyName={data.sheet.key} />}
      <Columns view={data} />
      {open ? <RowDrawer view={data} row={data.rows.find((r) => r.id === open.id) ?? open} onClose={() => setOpen(null)} /> : null}
    </div>
  );
}

function Summary({ view }: { view: SheetView }) {
  const parts: string[] = [`${view.summary.rows} rows`];
  for (const column of view.sheet.columns) {
    const entry = view.summary.columns[column.name];
    if (!entry) continue;
    if (entry.by_status && Object.keys(entry.by_status).length) {
      parts.push(`${column.name}: ${Object.entries(entry.by_status).map(([k, v]) => `${v} ${k.replaceAll("_", " ")}`).join(", ")}`);
    } else if (entry.sum !== undefined && entry.filled) {
      parts.push(`${column.name}: sum ${entry.sum}, average ${entry.average ?? "?"}`);
    }
  }
  return (
    <p className="small sheet-summary" aria-label="Summary">
      {parts.join(" · ")}
    </p>
  );
}

function AddRow({ sheet, keyName }: { sheet: string; keyName: string }) {
  const act = useLiveAct();
  const [key, setKey] = useState("");
  return (
    <form
      className="row"
      onSubmit={(event: FormEvent) => {
        event.preventDefault();
        act.mutate({ action: "add_row", fields: { sheet, key: key.trim() } }, { onSuccess: () => setKey("") });
      }}
    >
      <input aria-label={`New row (${keyName})`} placeholder={`New ${keyName.toLowerCase()}`} value={key} maxLength={200} onChange={(event) => setKey(event.target.value)} />
      <button type="submit" disabled={!key.trim() || act.isPending}>
        Add row
      </button>
      <ErrorNote error={act.error} />
    </form>
  );
}

/** Columns: who may change each, how old it may get, and a new one (a formula included). */
function Columns({ view }: { view: SheetView }) {
  const act = useLiveAct();
  const [name, setName] = useState("");
  const [type, setType] = useState<ColumnType>("text");
  const [friction, setFriction] = useState<Friction>("free");
  const [options, setOptions] = useState("");
  const [formula, setFormula] = useState("");
  const [age, setAge] = useState("");
  return (
    <details className="sheet-columns">
      <summary>Columns</summary>
      <ul className="small">
        {view.sheet.columns.map((c) => (
          <li key={c.name}>
            <strong>{c.name}</strong> · {c.formula ? `computed: ${c.formula_words ?? c.formula}` : `${c.type}, ${FRICTION_WORDS[c.friction]}`}
            {c.age_days ? ` · out of date after ${c.age_days} days` : ""}
          </li>
        ))}
      </ul>
      <form
        className="stack"
        aria-label="New column"
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          act.mutate(
            {
              action: "add_column",
              fields: {
                sheet: view.sheet.id,
                column: {
                  name: name.trim(),
                  type,
                  friction,
                  options: options.split(",").map((o) => o.trim()).filter(Boolean),
                  formula: formula.trim(),
                  age_days: age ? Number(age) : null,
                },
              },
            },
            { onSuccess: () => (setName(""), setFormula("")) },
          );
        }}
      >
        <div className="row wrap">
          <Field label="Name">
            <input value={name} maxLength={80} onChange={(event) => setName(event.target.value)} />
          </Field>
          <Field label="Type">
            <select value={type} onChange={(event) => setType(event.target.value as ColumnType)}>
              {TYPES.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </Field>
          <Field label="Who may change it">
            <select value={friction} onChange={(event) => setFriction(event.target.value as Friction)}>
              {(Object.keys(FRICTION_WORDS) as Friction[]).map((f) => (
                <option key={f} value={f}>
                  {FRICTION_WORDS[f]}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Out of date after (days)">
            <input type="number" min={1} className="narrow" value={age} onChange={(event) => setAge(event.target.value)} />
          </Field>
        </div>
        {type === "status" ? (
          <Field label="Values" hint="Comma separated.">
            <input value={options} onChange={(event) => setOptions(event.target.value)} />
          </Field>
        ) : null}
        <Field label="Formula (optional)" hint='Column names in brackets: [Renewal date] - TODAY(), IF([Health] = "red", "At risk", ""), COUNT("issues").'>
          <input value={formula} maxLength={300} onChange={(event) => setFormula(event.target.value)} />
        </Field>
        <button type="submit" disabled={!name.trim() || act.isPending}>
          Add column
        </button>
        <ErrorNote error={act.error} />
      </form>
    </details>
  );
}

function RowDrawer({ view, row, onClose }: { view: SheetView; row: StateRow; onClose: () => void }) {
  const { data: history } = useRowHistory(view.sheet.id, row.key);
  const act = useLiveAct();
  return (
    <aside className="card side-panel" aria-label={row.key}>
      <header className="row">
        <h2>{row.key}</h2>
        <button type="button" className="link small" onClick={onClose}>
          Close
        </button>
      </header>
      <ul className="small stack">
        {view.sheet.columns.map((c) => {
          const cell = row.cells[c.name];
          const value = c.formula ? row.computed[c.name] : cell?.value;
          if (value === undefined || value === null || value === "") return null;
          return (
            <li key={c.name}>
              <strong>{c.name}</strong>: {String(value)}{" "}
              {c.formula ? <span className="cell-computed">computed</span> : null}
              {cell?.ai ? (
                <>
                  <span className="cell-ai">AI-filled</span>{" "}
                  <button type="button" className="link small" onClick={() => act.mutate({ action: "touch", fields: { sheet: view.sheet.id, row: row.key, column: c.name } })}>
                    Keep as it is
                  </button>
                </>
              ) : null}
              {cell?.stale ? <span className="cell-stale"> may be out of date</span> : null}
              {cell ? <span className="muted"> · {when(cell.as_of || cell.at)}</span> : null}
            </li>
          );
        })}
      </ul>
      {row.pending.length ? (
        <>
          <h3 className="small-head">Waiting for you</h3>
          <ul className="small">
            {row.pending.map((e) => (
              <li key={e.id}>
                {e.column}: {String(e.value)}{" "}
                <button type="button" className="link small" onClick={() => act.mutate({ action: "decide", fields: { sheet: view.sheet.id, row: row.key, event: e.id, accept: true } })}>
                  Keep
                </button>{" "}
                <button type="button" className="link small" onClick={() => act.mutate({ action: "decide", fields: { sheet: view.sheet.id, row: row.key, event: e.id, accept: false } })}>
                  Turn down
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : null}
      <h3 className="small-head">History</h3>
      <ul className="small updates">
        {(history ?? [])
          .filter((e) => e.kind === "cell")
          .slice(0, 40)
          .map((e, i) => (
            <li key={e.id ?? i}>
              <span className="muted">{when(e.at)}</span> {e.column}: {String(e.value ?? "")} <span className="muted">({e.by}{e.ai ? ", an AI" : ""}{e.pending ? ", waits" : ""})</span>
            </li>
          ))}
      </ul>
      <ErrorNote error={act.error} />
    </aside>
  );
}
