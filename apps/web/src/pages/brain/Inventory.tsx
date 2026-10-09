// The Brain's inventory: everything it holds, as one table to govern it by. Each entry (live
// or archived), skill and filed document with who answers for it, where it came from, how it
// has been used and when it was last checked. Ready-made views find what needs a hand; picked
// columns, filters and grouping shape the rest; bulk actions are one undo point each.

import { type FormEvent, type ReactNode, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { useBrainDecisions, useBrainFlow, useBrainInventory, useBrainPolicies } from "../../api/hooks";
import type { BrainDecision, InventoryItem } from "../../api/types";
import { Empty, ErrorNote, Field, Loading } from "../../components/ui";
import { label, plural } from "../../lib/format";
import { type Decided, DecidedBanner, describeOutcome } from "./decided";
import { day, entryUrl, originText, ownerName, repeats, unusedLabel } from "./shared";

const DAY = 86_400_000;
const daysAgo = (n: number) => new Date(Date.now() - n * DAY).toISOString().slice(0, 10);
const AI_ORIGINS = new Set(["conversation", "workspace", "work"]);

interface View {
  key: string;
  label: string;
  hint: string;
  test: (item: InventoryItem) => boolean;
  sort?: (a: InventoryItem, b: InventoryItem) => number;
}

const isEntry = (i: InventoryItem) => i.type === "note";
const live = (i: InventoryItem) => isEntry(i) && i.live;

export const VIEWS: View[] = [
  { key: "live", label: "Everything live", hint: "Every note your AIs can receive", test: live },
  {
    key: "due",
    label: "Due for a check",
    hint: "Past its review cadence, marked stale, or disputed",
    test: (i) => live(i) && (!!i.stale || i.confidence === "disputed"),
    sort: (a, b) => (a.review_due ?? "").localeCompare(b.review_due ?? ""),
  },
  {
    key: "unused",
    label: "Unused for 60 days",
    hint: "Not handed to any conversation or AI work in 60 days: still worth keeping?",
    test: (i) => live(i) && (i.uses.last ?? "") < daysAgo(59) && (i.added ?? "") < daysAgo(59),
  },
  {
    key: "most",
    label: "Most used",
    hint: "What models receive most in the last 30 days",
    test: (i) => live(i) && i.uses.d30 > 0,
    sort: (a, b) => b.uses.d30 - a.uses.d30 || b.uses.total - a.uses.total,
  },
  {
    key: "changed",
    label: "Changed this week",
    hint: "Text, details or status changed in the last 7 days",
    test: (i) => isEntry(i) && (i.updated ?? "") >= daysAgo(6),
    sort: (a, b) => (b.updated ?? "").localeCompare(a.updated ?? ""),
  },
  {
    key: "unchecked",
    label: "From AI, never checked",
    hint: "Proposed by a model and approved, but no one has confirmed it since",
    test: (i) => live(i) && AI_ORIGINS.has(i.origin?.kind ?? "") && !i.checked,
  },
  {
    key: "heavy",
    label: "Heaviest",
    hint: "The notes that cost the most tokens each time they are sent",
    test: live,
    sort: (a, b) => b.tokens - a.tokens,
  },
  { key: "archived", label: "Archived", hint: "Retired notes, kept as history", test: (i) => isEntry(i) && !i.live },
  { key: "other", label: "Skills and documents", hint: "Procedures and filed documents", test: (i) => !isEntry(i) },
];

interface Column {
  key: string;
  label: string;
  shown: boolean; // on by default
  numeric?: boolean;
  cell: (item: InventoryItem, approver: string) => ReactNode;
  sort: (item: InventoryItem) => string | number;
}

const COLUMNS: Column[] = [
  { key: "area", label: "Area", shown: true, cell: (i) => placeOf(i), sort: (i) => i.topic },
  { key: "owner", label: "Owner", shown: true, cell: (i, me) => ownerName(i.owner, me), sort: (i) => i.owner },
  {
    key: "uses",
    label: "Uses 7 / 30 days",
    shown: true,
    numeric: true,
    cell: (i) => `${i.uses.d7} / ${i.uses.d30}`,
    sort: (i) => i.uses.d30 * 1000 + i.uses.d7,
  },
  { key: "last", label: "Last used", shown: true, cell: (i) => (i.uses.last ? day(i.uses.last) : "never"), sort: (i) => i.uses.last ?? "" },
  { key: "checked", label: "Checked", shown: true, cell: (i) => <Checked item={i} />, sort: (i) => i.review_due ?? i.verified ?? "" },
  { key: "tokens", label: "Tokens", shown: true, numeric: true, cell: (i) => i.tokens.toLocaleString(), sort: (i) => i.tokens },
  { key: "origin", label: "Origin", shown: false, cell: (i) => (i.origin ? originText(i.origin) : ""), sort: (i) => i.origin?.kind ?? "" },
  { key: "confidence", label: "Confidence", shown: false, cell: (i) => (i.confidence ? label(i.confidence) : ""), sort: (i) => i.confidence ?? "" },
  {
    key: "classification",
    label: "Sensitivity",
    shown: false,
    cell: (i) => (i.classification ? label(i.classification) : ""),
    sort: (i) => i.classification ?? "",
  },
  { key: "changes", label: "Changes", shown: false, numeric: true, cell: (i) => i.changes ?? "", sort: (i) => i.changes ?? 0 },
  { key: "total", label: "Uses in all", shown: false, numeric: true, cell: (i) => i.uses.total, sort: (i) => i.uses.total },
  { key: "scope", label: "Scope", shown: false, cell: (i) => i.scope, sort: (i) => i.scope },
  { key: "added", label: "Added", shown: false, cell: (i) => day(i.added), sort: (i) => i.added ?? "" },
  { key: "revised", label: "Text changed", shown: false, cell: (i) => day(i.revised), sort: (i) => i.revised ?? "" },
];

// The entry's own column, sorted by title.
const TITLE: Column = { key: "title", label: "Note", shown: true, cell: () => null, sort: (i) => i.title.toLowerCase() };

const STORE = "brain.inventory.columns";

const capitalize = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

/** Where an item is filed: its area, and its topic when that says more. */
function placeOf(item: InventoryItem): string {
  const topic = item.topic_label;
  if (!topic || topic.toLowerCase() === item.area_label.toLowerCase()) return item.area_label;
  return `${item.area_label} · ${topic}`;
}

function savedColumns(): string[] {
  try {
    const raw = window.localStorage.getItem(STORE);
    const parsed = raw ? (JSON.parse(raw) as unknown) : null;
    if (Array.isArray(parsed) && parsed.every((k) => typeof k === "string")) return parsed;
  } catch {
    // no storage here (a private window): the default columns
  }
  return COLUMNS.filter((c) => c.shown).map((c) => c.key);
}

function saveColumns(keys: string[]) {
  try {
    window.localStorage.setItem(STORE, JSON.stringify(keys));
  } catch {
    // the choice lasts for this visit only
  }
}

/** When it was last checked, and whether a check is due. */
function Checked({ item }: { item: InventoryItem }) {
  if (!isEntry(item)) return null;
  if (item.stale) return <span className="chip chip-stale" title={item.stale}>due</span>;
  if (item.confidence === "disputed") return <span className="chip chip-stale">disputed</span>;
  return (
    <span title={item.review_due ? `Next check ${day(item.review_due)}` : "No review cadence"}>
      {item.checked ? day(item.verified) : <span className="muted">not yet</span>}
    </span>
  );
}

export function InventoryPage() {
  const { data: items, isLoading, error } = useBrainInventory();
  const { data: policies } = useBrainPolicies();
  const { data: flow } = useBrainFlow(7);
  const [params, setParams] = useSearchParams();
  const [columns, setColumns] = useState<string[]>(savedColumns);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [decided, setDecided] = useState<Decided | null>(null);
  const viewKey = params.get("view") ?? (params.get("show") === "attention" ? "due" : "live");
  const view = VIEWS.find((v) => v.key === viewKey) ?? VIEWS[0]!;
  const filters = {
    q: params.get("q") ?? "",
    area: params.get("area") ?? "",
    topic: params.get("topic") ?? "",
    kind: params.get("kind") ?? "",
    owner: params.get("owner") ?? "",
    origin: params.get("origin") ?? "",
    standing: params.get("show") === "standing",
    group: params.get("group") ?? "",
  };
  const [sort, setSort] = useState<{ key: string; down: boolean } | null>(null);

  useEffect(() => setSelected(new Set()), [viewKey]);

  function set(changes: Record<string, string>) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    setParams(next, { replace: true });
  }

  const shown = useMemo(() => {
    const words = filters.q.toLowerCase().split(/\s+/).filter(Boolean);
    const rows = (items ?? []).filter((item) => {
      if (!view.test(item)) return false;
      if (filters.area && item.area !== filters.area) return false;
      if (filters.topic && item.topic !== filters.topic) return false;
      if (filters.kind && item.kind !== filters.kind) return false;
      if (filters.owner && item.owner !== filters.owner) return false;
      if (filters.origin && item.origin?.kind !== filters.origin) return false;
      if (filters.standing && item.load !== "standing") return false;
      const text = `${item.title} ${item.summary} ${item.id} ${item.topic}`.toLowerCase();
      return words.every((word) => text.includes(word));
    });
    const column = sort ? (sort.key === "title" ? TITLE : COLUMNS.find((c) => c.key === sort.key)) : null;
    if (column) {
      rows.sort((a, b) => {
        const [x, y] = [column.sort(a), column.sort(b)];
        const order = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
        return sort?.down ? -order : order;
      });
    } else if (view.sort) {
      rows.sort(view.sort);
    } else {
      rows.sort((a, b) => a.topic.localeCompare(b.topic) || a.title.localeCompare(b.title));
    }
    return rows;
  }, [items, view, filters.q, filters.area, filters.topic, filters.kind, filters.owner, filters.origin, filters.standing, sort]);

  if (isLoading) return <Loading />;
  if (!items) return <ErrorNote error={error} />;
  if (!items.length) {
    return <Empty why="The Brain holds nothing yet. Kept suggestions, pulled context and filed documents appear here." />;
  }

  const approver = policies?.approver ?? "";
  const visible = COLUMNS.filter((c) => columns.includes(c.key));
  const selectable = shown.filter(isEntry);
  const chosen = selectable.filter((i) => selected.has(i.id));
  const facets = facetsOf(items.filter(isEntry));
  const groups = group(shown, filters.group);

  function toggle(id: string) {
    setSelected((now) => {
      const next = new Set(now);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function choose(key: string) {
    const next = columns.includes(key) ? columns.filter((k) => k !== key) : [...columns, key];
    setColumns(next);
    saveColumns(next);
  }

  return (
    <div className="inventory">
      {decided ? <DecidedBanner decided={decided} onChange={setDecided} /> : null}
      <nav className="views" aria-label="Ready-made views">
        {VIEWS.map((v) => {
          const count = items.filter(v.test).length;
          const name = v.key === "unused" ? capitalize(unusedLabel(flow?.usage_since)) : v.label;
          return (
            <button
              key={v.key}
              type="button"
              title={v.hint}
              className={v.key === view.key ? "facet active" : "facet"}
              aria-pressed={v.key === view.key}
              onClick={() => set({ view: v.key === "live" ? "" : v.key, show: "" })}
            >
              <span>{name}</span> <span className="facet-count">{count}</span>
            </button>
          );
        })}
      </nav>
      <div className="inventory-bar">
        <input
          type="search"
          aria-label="Filter by words"
          placeholder="Filter by words…"
          value={filters.q}
          onChange={(event) => set({ q: event.target.value })}
        />
        <Select label="Area" value={filters.area} onChange={(area) => set({ area, topic: "" })} options={facets.areas} />
        <Select label="Kind" value={filters.kind} onChange={(kind) => set({ kind })} options={facets.kinds} />
        <Select
          label="Owner"
          value={filters.owner}
          onChange={(owner) => set({ owner })}
          options={facets.owners.map(([key, n]) => [key, `${ownerName(key, approver)} (${n})`])}
        />
        <Select label="Origin" value={filters.origin} onChange={(origin) => set({ origin })} options={facets.origins} />
        <Select
          label="Group by"
          value={filters.group}
          onChange={(value) => set({ group: value })}
          options={[
            ["area", "Area"],
            ["topic", "Topic"],
            ["owner", "Owner"],
            ["origin", "Origin"],
          ]}
          none="No grouping"
        />
        <ColumnPicker columns={columns} onToggle={choose} />
      </div>
      <p className="result-line">
        <span className="muted">
          {view.hint}. {plural(shown.length, "item")}
          {filters.topic ? ` in ${shown[0]?.topic_label ?? filters.topic}` : ""}.
        </span>
        {filters.q || filters.area || filters.kind || filters.owner || filters.origin || filters.standing ? (
          <button type="button" className="link" onClick={() => setParams(new URLSearchParams(view.key === "live" ? {} : { view: view.key }), { replace: true })}>
            Clear filters
          </button>
        ) : null}
      </p>
      {chosen.length ? (
        <BulkBar
          items={chosen}
          scopes={policies?.scopes ?? []}
          approver={approver}
          areas={policies?.areas ?? []}
          onDone={(next) => {
            setDecided(next);
            setSelected(new Set());
          }}
          onClear={() => setSelected(new Set())}
        />
      ) : null}
      {shown.length ? (
        <table className="table inventory-table">
          <thead>
            <tr>
              <th className="pick">
                <input
                  type="checkbox"
                  aria-label="Select every note shown"
                  checked={!!selectable.length && chosen.length === selectable.length}
                  disabled={!selectable.length}
                  onChange={() => setSelected(chosen.length === selectable.length ? new Set() : new Set(selectable.map((i) => i.id)))}
                />
              </th>
              <th>
                <SortButton label="Note" column="title" sort={sort} onSort={setSort} />
              </th>
              {visible.map((c) => (
                <th key={c.key} className={c.numeric ? "num" : undefined}>
                  <SortButton label={c.label} column={c.key} sort={sort} onSort={setSort} />
                </th>
              ))}
            </tr>
          </thead>
          {groups.map(([name, rows]) => (
            <tbody key={name || "all"}>
              {name ? (
                <tr className="group-row">
                  <th colSpan={visible.length + 2}>
                    {filters.group === "owner" ? ownerName(name, approver) : name} <span className="facet-count">{rows.length}</span>
                  </th>
                </tr>
              ) : null}
              {rows.map((item) => (
                <tr key={`${item.type}:${item.id}`} className={item.live ? undefined : "archived-row"}>
                  <td className="pick">
                    {isEntry(item) ? (
                      <input
                        type="checkbox"
                        aria-label={`Select ${item.title}`}
                        checked={selected.has(item.id)}
                        onChange={() => toggle(item.id)}
                      />
                    ) : null}
                  </td>
                  <td>
                    <ItemTitle item={item} />
                  </td>
                  {visible.map((c) => (
                    <td key={c.key} className={c.numeric ? "num" : undefined}>
                      {c.cell(item, approver)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          ))}
        </table>
      ) : (
        <Empty why="Nothing here with these filters. Clear them, or pick another view." />
      )}
    </div>
  );
}

function ItemTitle({ item }: { item: InventoryItem }) {
  const href =
    item.type === "note"
      ? entryUrl(item.id)
      : item.type === "skill"
        ? `/skills/${encodeURIComponent(item.id)}`
        : `/brain/files/view?path=${encodeURIComponent(item.id)}`;
  return (
    <span className="item-title">
      <Link to={href}>{item.title}</Link>
      {repeats(item.title, item.summary) ? null : <span className="muted small"> {item.summary}</span>}
      <span className="chips">
        {item.type !== "note" ? <span className="chip">{item.type === "skill" ? "Skill" : "Document"}</span> : null}
        {item.load === "standing" ? <span className="chip chip-standing">In every task</span> : null}
        {item.load === "domain" ? (
          <span className="chip chip-standing" title={`Goes first into every brief about ${(item.applies_to ?? []).join(", ")}`}>
            {item.critical ? "Must hold, critical" : "Must hold"}
          </span>
        ) : null}
        {item.baseline && item.load !== "domain" && item.load !== "standing" ? (
          <span className="chip" title={`A baseline: ${item.baseline}. A change to it waits for you, with a reason.`}>
            Baseline
          </span>
        ) : null}
        {!item.live ? <span className="chip chip-archived">Archived</span> : null}
        {item.partition ? <span className="chip">{item.partition}</span> : null}
      </span>
    </span>
  );
}

function SortButton({
  label: text,
  column,
  sort,
  onSort,
}: {
  label: string;
  column: string;
  sort: { key: string; down: boolean } | null;
  onSort: (next: { key: string; down: boolean } | null) => void;
}) {
  const active = sort?.key === column;
  return (
    <button
      type="button"
      className="link sort"
      aria-sort={active ? (sort?.down ? "descending" : "ascending") : undefined}
      onClick={() => onSort(active ? (sort?.down ? null : { key: column, down: true }) : { key: column, down: false })}
    >
      {text}
      {active ? (sort?.down ? " ↓" : " ↑") : ""}
    </button>
  );
}

function Select({
  label: text,
  value,
  onChange,
  options,
  none = "Any",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: [string, string][];
  none?: string;
}) {
  return (
    <label className="inline-select">
      <span className="muted small">{text}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">{none}</option>
        {options.map(([key, name]) => (
          <option key={key} value={key}>
            {name}
          </option>
        ))}
      </select>
    </label>
  );
}

function ColumnPicker({ columns, onToggle }: { columns: string[]; onToggle: (key: string) => void }) {
  return (
    <details className="column-picker">
      <summary>Columns</summary>
      <ul>
        {COLUMNS.map((c) => (
          <li key={c.key}>
            <label>
              <input type="checkbox" checked={columns.includes(c.key)} onChange={() => onToggle(c.key)} /> {c.label}
            </label>
          </li>
        ))}
      </ul>
    </details>
  );
}

function facetsOf(entries: InventoryItem[]) {
  const count = (key: (i: InventoryItem) => string | undefined) => {
    const out = new Map<string, number>();
    for (const item of entries) {
      const value = key(item);
      if (value) out.set(value, (out.get(value) ?? 0) + 1);
    }
    return [...out.entries()].sort((a, b) => b[1] - a[1]);
  };
  const areaNames = new Map(entries.map((i) => [i.area, i.area_label]));
  return {
    areas: count((i) => i.area).map(([key, n]) => [key, `${areaNames.get(key) ?? key} (${n})`] as [string, string]),
    kinds: count((i) => i.kind).map(([key, n]) => [key, `${label(key)} (${n})`] as [string, string]),
    owners: count((i) => i.owner),
    origins: count((i) => i.origin?.kind).map(
      ([key, n]) => [key, `${originText({ kind: key as never, ref: "", label: "" })} (${n})`] as [string, string],
    ),
  };
}

function group(rows: InventoryItem[], by: string): [string, InventoryItem[]][] {
  if (!by) return [["", rows]];
  const key = (i: InventoryItem) =>
    by === "area"
      ? i.area_label
      : by === "topic"
        ? `${i.area_label} / ${i.topic_label}`
        : by === "owner"
          ? i.owner
          : i.origin
            ? originText(i.origin)
            : "Not recorded";
  const out = new Map<string, InventoryItem[]>();
  for (const row of rows) out.set(key(row), [...(out.get(key(row)) ?? []), row]);
  return [...out.entries()].sort((a, b) => a[0].localeCompare(b[0]));
}

type Bulk = "verify" | "mark" | "owner" | "cadence" | "move" | "archive" | "unarchive";

/** What to do with the selected entries: each choice is one batch, one undo point. */
function BulkBar({
  items,
  scopes,
  approver,
  areas,
  onDone,
  onClear,
}: {
  items: InventoryItem[];
  scopes: string[];
  approver: string;
  areas: string[];
  onDone: (decided: Decided) => void;
  onClear: () => void;
}) {
  const decide = useBrainDecisions();
  const [action, setAction] = useState<Bulk | "">("");
  const [text, setText] = useState("");
  const [owner, setOwner] = useState(approver);
  const [area, setArea] = useState("");
  const [problem, setProblem] = useState<unknown>(null);
  const live = items.filter((i) => i.live);
  const archived = items.filter((i) => !i.live);

  function run(decisions: BrainDecision[], label?: string) {
    setProblem(null);
    decide.mutate(
      { decisions, label },
      {
        onSuccess: (outcome) => {
          setAction("");
          setText("");
          onDone(describeOutcome(outcome));
        },
      },
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const ids = live.map((i) => i.id);
    const reason = text.trim();
    if (action === "verify") run(ids.map((id) => ({ action: "verify", entry_id: id })));
    else if (action === "mark") {
      if (!reason) return setProblem(new Error("Say why, so the next person knows what to check."));
      run(ids.map((id) => ({ action: "mark", entry_id: id, state: "stale", reason })));
    } else if (action === "owner") run(ids.map((id) => ({ action: "update", entry_id: id, fields: { owner } })));
    else if (action === "cadence") {
      if (!/^\d*$/.test(reason)) return setProblem(new Error("Give a number of days, or leave it empty to clear it."));
      run(ids.map((id) => ({ action: "update", entry_id: id, fields: { review_days: reason } })));
    } else if (action === "move") {
      const [toArea, topic] = [area, reason.toLowerCase()];
      if (!toArea && !topic) return setProblem(new Error("Choose an area, a topic, or both."));
      run(ids.map((id) => ({ action: "update", entry_id: id, fields: { ...(toArea ? { area: toArea } : {}), ...(topic ? { topic } : {}) } })));
    } else if (action === "archive") run(ids.map((id) => ({ action: "archive", entry_id: id, reason })));
    else if (action === "unarchive") run(archived.map((i) => ({ action: "unarchive", entry_id: i.id, reason })));
  }

  const busy = decide.isPending;
  return (
    <form className="bulk-bar" onSubmit={submit} aria-label="Change the selected notes">
      <p>
        <strong>{plural(items.length, "note")} selected</strong>{" "}
        <button type="button" className="link" onClick={onClear}>
          Clear
        </button>
      </p>
      <div className="row wrap">
        <select aria-label="What to do" value={action} onChange={(event) => setAction(event.target.value as Bulk)}>
          <option value="">Choose what to do…</option>
          {live.length ? (
            <>
              <option value="verify">Still true (checked today)</option>
              <option value="mark">Needs an update…</option>
              <option value="owner">Set the owner…</option>
              <option value="cadence">Set how often to check…</option>
              <option value="move">Move to…</option>
              <option value="archive">Remove from the Brain…</option>
            </>
          ) : null}
          {archived.length ? <option value="unarchive">Bring back</option> : null}
        </select>
        {action === "mark" || action === "archive" || action === "unarchive" ? (
          <Field label={action === "mark" ? "Why" : "Why (optional)"}>
            <input value={text} onChange={(event) => setText(event.target.value)} />
          </Field>
        ) : null}
        {action === "owner" ? (
          <Field label="Owner">
            <select value={owner} onChange={(event) => setOwner(event.target.value)}>
              {scopes.map((scope) => (
                <option key={scope} value={scope}>
                  {ownerName(scope, approver)}
                </option>
              ))}
            </select>
          </Field>
        ) : null}
        {action === "cadence" ? (
          <Field label="Check every (days)" hint="Empty: back to the policy's cadence">
            <input inputMode="numeric" value={text} onChange={(event) => setText(event.target.value)} />
          </Field>
        ) : null}
        {action === "move" ? (
          <>
            <Field label="Area">
              <select value={area} onChange={(event) => setArea(event.target.value)}>
                <option value="">Keep its area</option>
                {areas.map((key) => (
                  <option key={key} value={key}>
                    {label(key)}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Topic" hint="A short slug, like voice">
              <input value={text} onChange={(event) => setText(event.target.value)} />
            </Field>
          </>
        ) : null}
        {action ? (
          <button type="submit" className="primary" disabled={busy}>
            Apply to {plural(action === "unarchive" ? archived.length : live.length, "note")}
          </button>
        ) : null}
      </div>
      <ErrorNote error={problem ?? decide.error} />
    </form>
  );
}
