// One entry, the way its owner governs it: what it says and its details (About), every
// version with who made it and the way back to any of them (Versions), where it went (Use),
// and everything that happened to it (History).

import { type FormEvent, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { post } from "../../api/client";
import {
  brainFileUrl,
  keys,
  useBrainActivity,
  useBrainCatalog,
  useAcceptTriggers,
  useAskedAs,
  useBrainDecisions,
  useBrainEntry,
  useBrainHistory,
  useBrainPolicies,
  useBrainUndo,
  useEntryDetails,
  useEntryUse,
  useEntryVersions,
  useInvalidate,
} from "../../api/hooks";
import type { BrainCheckpoint, BrainEntrySummary, BrainHistoryRecord, EntryUse, InventoryItem } from "../../api/types";
import { Compare } from "../../components/Diff";
import { Markdown } from "../../components/Markdown";
import { TextEditor, changes } from "../../components/TextEditor";
import { Empty, ErrorNote, Field, KeyValues, Loading, Section, Tabs } from "../../components/ui";
import { label, plural, when } from "../../lib/format";
import { EventList, describeEvent } from "./events";
import { type Decided, DecidedBanner, describeOutcome } from "./decided";
import { EntryChips, day, entryUrl, fileViewUrl, originText, ownerName } from "./shared";

const TABS = [
  { id: "about", label: "About" },
  { id: "versions", label: "Versions" },
  { id: "use", label: "Use" },
  { id: "activity", label: "History" },
] as const;
type Tab = (typeof TABS)[number]["id"];

const CLASSIFICATIONS = ["public", "internal", "confidential", "restricted"];

export function EntryPage() {
  const { entryId = "" } = useParams();
  const { data: catalog } = useBrainCatalog();
  const { data: details } = useEntryDetails(entryId);
  const summary = catalog?.entries.find((e) => e.id === entryId);
  const areaKey = details?.area ?? summary?.area;
  const area = catalog?.areas.find((a) => a.key === areaKey);
  const topic = area?.topics.find((t) => t.key === (details?.topic ?? summary?.topic));
  const areaLabel = area?.label ?? details?.area_label;
  return (
    <div className="entry-page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/brain/entries">All notes</Link>
        {areaKey && areaLabel ? (
          <>
            <span aria-hidden="true">/</span>
            <Link to={`/brain/entries?area=${encodeURIComponent(areaKey)}`}>{areaLabel}</Link>
          </>
        ) : null}
        {area && topic && area.topics.length > 1 ? (
          <>
            <span aria-hidden="true">/</span>
            <Link to={`/brain/entries?area=${encodeURIComponent(area.key)}&topic=${encodeURIComponent(topic.key)}`}>
              {topic.label}
            </Link>
          </>
        ) : null}
      </nav>
      <EntryView id={entryId} summary={summary} />
    </div>
  );
}

export function EntryView({ id, summary }: { id: string; summary?: BrainEntrySummary }) {
  const [params, setParams] = useSearchParams();
  const tab = (TABS.find((t) => t.id === params.get("tab"))?.id ?? "about") as Tab;
  const { data, error } = useBrainEntry(id);
  const { data: details } = useEntryDetails(id);
  const { data: history } = useBrainHistory(id);
  const [decided, setDecided] = useState<Decided | null>(null);
  const [removed, setRemoved] = useState<BrainCheckpoint | null>(null);
  if (removed) return <Removed title={summary?.title ?? id} point={removed} onBack={() => setRemoved(null)} />;
  if (!data && details && !details.live) return <ArchivedEntry details={details} />;
  if (!data) return error ? <ErrorNote error={error} /> : <Loading />;

  function choose(next: Tab) {
    const search = new URLSearchParams(params);
    if (next === "about") search.delete("tab");
    else search.set("tab", next);
    setParams(search, { replace: true });
  }

  return (
    <article className="entry">
      <header className="entry-head">
        <h1>{data.title}</h1>
        {summary ? <EntryChips entry={summary} /> : null}
      </header>
      {data.stale ? (
        <p className="warning">
          {staleNote(data.stale_reason, history)} Models see this warning; verify it before relying on it.
        </p>
      ) : null}
      {decided ? <DecidedBanner decided={decided} onChange={setDecided} /> : null}
      <Tabs tabs={TABS} active={tab} onChange={choose} />
      {tab === "about" ? (
        <About id={id} entry={data} details={details} history={history} summary={summary} onDecided={setDecided} onRemoved={setRemoved} />
      ) : tab === "versions" ? (
        <Versions id={id} onDecided={setDecided} />
      ) : tab === "use" ? (
        <Use id={id} />
      ) : (
        <Activity id={id} />
      )}
    </article>
  );
}

// ---------------------------------------------------------------- About

function About({
  id,
  entry,
  details,
  history,
  summary,
  onDecided,
  onRemoved,
}: {
  id: string;
  entry: NonNullable<ReturnType<typeof useBrainEntry>["data"]>;
  details: InventoryItem | undefined;
  history: BrainHistoryRecord[] | undefined;
  summary: BrainEntrySummary | undefined;
  onDecided: (decided: Decided) => void;
  onRemoved: (point: BrainCheckpoint) => void;
}) {
  const invalidate = useInvalidate();
  const decide = useBrainDecisions();
  const { data: policies } = useBrainPolicies();
  const [reason, setReason] = useState("");
  const [problem, setProblem] = useState<unknown>(null);
  const [editing, setEditing] = useState(false);
  const [minor, setMinor] = useState(false);
  const [changingDetails, setChangingDetails] = useState(false);
  // A new text for a baseline is a revision: it says why, in a few words.
  const [why, setWhy] = useState("");
  const [editProblem, setEditProblem] = useState<string | null>(null);
  const approver = policies?.approver ?? "";
  const baseline = details?.baseline ?? "";

  function save(changed: { title: string; summary: string; body: string }) {
    const initial = { title: entry.title, summary: entry.summary, body: entry.text };
    const revises = !!baseline && !minor && changed.body.trim() !== entry.text.trim();
    if (revises && (why.match(/[\w'-]+/g) ?? []).length < 4) {
      setEditProblem(`This note is a baseline (${baseline}): say in a few words (four at least) why it changes.`);
      return;
    }
    setEditProblem(null);
    decide.mutate(
      {
        decisions: [
          {
            action: "edit",
            entry_id: id,
            reason: revises ? why.trim() : "Edited on its page",
            ...changes(initial, changed),
            body: changed.body.trim(),
            ...(minor ? { minor: true } : {}),
          },
        ],
      },
      {
        onSuccess: (outcome) => {
          const refused = outcome.results.find((r) => !r.ok);
          if (refused) {
            setEditProblem(refused.message);
            return;
          }
          setEditing(false);
          setMinor(false);
          setWhy("");
          onDecided(describeOutcome(outcome));
        },
      },
    );
  }

  function markBaseline(on: boolean) {
    decide.mutate(
      { decisions: [{ action: "update", entry_id: id, fields: { baseline: on ? "true" : "" } }] },
      { onSuccess: (outcome) => onDecided(describeOutcome(outcome)) },
    );
  }

  function remove(why: string) {
    decide.mutate(
      { decisions: [{ action: "archive", entry_id: id, reason: why || "Removed on its page" }] },
      { onSuccess: (outcome) => outcome.checkpoint && onRemoved(outcome.checkpoint) },
    );
  }

  async function act(path: "verify" | "mark", body: Record<string, string>) {
    setProblem(null);
    try {
      await post(`/api/brain/entries/${encodeURIComponent(id)}/${path}`, body);
      setReason("");
      await invalidate(keys.brain);
    } catch (caught) {
      setProblem(caught);
    }
  }

  function markAs(state: "stale" | "disputed") {
    if (!reason.trim()) {
      setProblem(new Error("Say why, so the next person knows what to check."));
      return;
    }
    void act("mark", { state, reason });
  }

  return (
    <div className="entry-layout">
      {editing ? (
        <div className="stack">
          <TextEditor
            label={`Edit ${entry.title}`}
            initial={{ title: entry.title, summary: entry.summary, body: entry.text }}
            saveLabel="Save the note"
            onSave={save}
            onCancel={() => setEditing(false)}
          />
          <label className="check">
            <input type="checkbox" checked={minor} onChange={(event) => setMinor(event.target.checked)} /> A small fix (a typo,
            the wording): not new knowledge, so models are not told it changed
          </label>
          {baseline && !minor ? (
            <Field label="Why does it change?" hint={`It is a baseline (${baseline}): the reason is kept with the change.`}>
              <input value={why} onChange={(event) => setWhy(event.target.value)} />
            </Field>
          ) : null}
          {editProblem ? (
            <p className="warning small" role="alert">
              {editProblem}
            </p>
          ) : null}
        </div>
      ) : (
        <div className="document">
          <Markdown text={entry.text} />
        </div>
      )}
      <aside className="entry-side">
        <Section title="Change it">
          <ChangeEntry busy={decide.isPending} editing={editing} onEdit={() => setEditing(true)} onRemove={remove} />
          <ErrorNote error={decide.error} />
        </Section>
        <Section
          title="About this note"
          actions={
            details && !changingDetails ? (
              <button type="button" className="link" onClick={() => setChangingDetails(true)}>
                Change details
              </button>
            ) : null
          }
        >
          {changingDetails && details ? (
            <DetailsForm
              details={details}
              onDone={(next) => {
                setChangingDetails(false);
                if (next) onDecided(next);
              }}
            />
          ) : (
            <KeyValues
              rows={[
                ["Owner", details ? ownerName(details.owner, approver) : null],
                [
                  "Came from",
                  details?.origin ? (
                    <span title={details.origin.label}>
                      {originText(details.origin)}
                      {details.origin.ref ? <span className="muted small"> {details.origin.ref}</span> : null}
                    </span>
                  ) : null,
                ],
                ["Kind", label(entry.kind)],
                ["Scope", summary?.partition ? `${entry.scope}, sealed to ${summary.partition}` : entry.scope],
                ["Added", day(details?.added ?? summary?.added)],
                ["Text changed", day(details?.revised)],
                ["Last checked", details ? (details.checked ? day(details.verified) : "not yet") : day(entry.verified)],
                ["Next check", details ? nextCheck(details) : null],
                ["Confidence", entry.confidence ? label(entry.confidence) : null],
                ["Baseline", baseline ? `Yes: ${baseline}` : null],
                ["As of", details?.as_of ? day(details.as_of) : null],
                ["Valid until", details?.valid_until ? day(details.valid_until) : null],
                ["Sensitivity", details?.classification ? label(details.classification) : null],
                ["Used", details ? `${plural(details.uses.d30, "time")} in 30 days` : null],
                ["Source", entry.source],
                ["Stored as", entry.path ? <code>{entry.path}</code> : null],
              ]}
            />
          )}
          {details && !changingDetails ? (
            <p className="small">
              {details.baseline_marked ? (
                <button type="button" className="link small" disabled={decide.isPending} onClick={() => markBaseline(false)}>
                  Not a baseline you marked any more
                </button>
              ) : !baseline ? (
                <button type="button" className="link small" disabled={decide.isPending} onClick={() => markBaseline(true)}>
                  Mark it a baseline
                </button>
              ) : null}
              {!baseline ? <span className="muted"> A change to a baseline waits for you, with a reason.</span> : null}
            </p>
          ) : null}
          {details?.supersedes?.length ? (
            <p className="small">
              It replaced:{" "}
              {details.supersedes.map((old, index) => (
                <span key={old}>
                  {index ? ", " : ""}
                  <Link to={entryUrl(old)}>{old}</Link>
                </span>
              ))}
            </p>
          ) : null}
        </Section>
        {details ? <WhenItApplies details={details} onDecided={onDecided} /> : null}
        {details ? <FoundWhen details={details} /> : null}
        {summary?.file ? (
          <Section title="Filed document">
            <p>
              <Link to={fileViewUrl(summary.file)}>{summary.file}</Link>
            </p>
            <a className="button" href={brainFileUrl(summary.file)} download>
              Download
            </a>
          </Section>
        ) : null}
        <Section title="Is it still true?">
          <div className="stack">
            <button type="button" className="primary" onClick={() => void act("verify", {})}>
              Still true
            </button>
            <Field label="Why" hint="To say it needs an update, or is disputed: say what to check.">
              <input value={reason} onChange={(event) => setReason(event.target.value)} />
            </Field>
            <div className="row">
              <button type="button" onClick={() => markAs("stale")}>
                Needs an update
              </button>
              <button type="button" className="danger" onClick={() => markAs("disputed")}>
                Mark disputed
              </button>
            </div>
            <ErrorNote error={problem} />
          </div>
        </Section>
        <Section title="History">
          {history?.length ? (
            <ol className="history">
              {history.slice(0, 6).map((record, index) => (
                <li key={`${record.at}-${index}`}>
                  <span>{describeEvent(record, approver)}</span>
                  <time dateTime={record.at}>{when(record.at)}</time>
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted">No recorded decisions yet.</p>
          )}
        </Section>
      </aside>
    </div>
  );
}

/** When a note reaches a model, in plain words. */
const LOADS: { value: string; label: string; hint: string }[] = [
  { value: "standing", label: "Always", hint: "In every session's startup context." },
  {
    value: "domain",
    label: "Whenever its domain comes up",
    hint: "A must-hold: it goes first into every brief about its domain, even when a request never mentions it.",
  },
  { value: "on-demand", label: "When relevant", hint: "When a request is about it." },
  { value: "manual", label: "Only when asked for", hint: "Opened by name or found by a search, never sent on its own." },
];

function loadLabel(load?: string) {
  return LOADS.find((l) => l.value === (load ?? "on-demand"))?.label ?? load ?? "";
}

/** When this note reaches a model: always, as a must-hold for its domains, when relevant, or
 * only when asked for. A must-hold also says which domains it covers, the words that bring
 * them in, its one line, and whether that line goes into every session. One undo point. */
function WhenItApplies({ details, onDecided }: { details: InventoryItem; onDecided: (decided: Decided) => void }) {
  const decide = useBrainDecisions();
  const initial = {
    load: details.load ?? "on-demand",
    applies_to: (details.applies_to ?? []).join(", ") || details.area,
    triggers: (details.triggers ?? []).join(", "),
    must_text: details.must_text ?? "",
    critical: details.critical ? "true" : "false",
  };
  const [form, setForm] = useState(initial);
  const [open, setOpen] = useState(false);
  const set = (key: keyof typeof form, value: string) => setForm((now) => ({ ...now, [key]: value }));
  const must = form.load === "domain";

  function submit(event: FormEvent) {
    event.preventDefault();
    const fields: Record<string, string> = {};
    const keys: (keyof typeof form)[] = must ? ["load", "applies_to", "triggers", "must_text", "critical"] : ["load"];
    for (const key of keys) {
      if (form[key] !== initial[key] || (must && initial.load !== "domain" && key === "applies_to")) fields[key] = form[key];
    }
    if (!Object.keys(fields).length) return setOpen(false);
    decide.mutate(
      { decisions: [{ action: "update", entry_id: details.id, fields }] },
      {
        onSuccess: (outcome) => {
          if (outcome.results.every((r) => r.ok)) {
            setOpen(false);
            onDecided(describeOutcome(outcome));
          }
        },
      },
    );
  }

  return (
    <Section
      title="When does this apply?"
      actions={
        !open ? (
          <button type="button" className="link" onClick={() => setOpen(true)}>
            Change
          </button>
        ) : null
      }
    >
      {open ? (
        <form className="stack" onSubmit={submit} aria-label="When this note reaches a model">
          <Field label="It reaches a model" hint={LOADS.find((l) => l.value === form.load)?.hint}>
            <select value={form.load} onChange={(event) => set("load", event.target.value)}>
              {LOADS.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
          </Field>
          {must ? (
            <>
              <Field label="Its domains" hint="Areas (food), area/topic pairs (food/diet) or project ids, comma separated.">
                <input value={form.applies_to} onChange={(event) => set("applies_to", event.target.value)} />
              </Field>
              <Field label="Words that bring it in" hint="When a request uses one, this goes into the brief: dinner, lunchbox, restaurant.">
                <textarea rows={3} value={form.triggers} onChange={(event) => set("triggers", event.target.value)} />
              </Field>
              <Field label="The rule in one line" hint="What every brief shows. Empty: its startup line or summary.">
                <input value={form.must_text} onChange={(event) => set("must_text", event.target.value)} />
              </Field>
              <label className="check">
                <input
                  type="checkbox"
                  checked={form.critical === "true"}
                  onChange={(event) => set("critical", event.target.checked ? "true" : "false")}
                />{" "}
                Critical: its line also goes into every session's startup context, for models that cannot ask for a brief (at most three)
              </label>
            </>
          ) : null}
          <div className="row">
            <button type="submit" className="primary" disabled={decide.isPending}>
              Save
            </button>
            <button type="button" onClick={() => setOpen(false)}>
              Cancel
            </button>
          </div>
          <ErrorNote error={decide.error} />
          {decide.data?.results.filter((r) => !r.ok).map((r) => (
            <p key={r.id} className="error" role="alert">
              {r.message}
            </p>
          ))}
        </form>
      ) : (
        <KeyValues
          rows={[
            ["It reaches a model", loadLabel(details.load)],
            ["Its domains", details.load === "domain" ? (details.applies_to ?? []).join(", ") : null],
            ["Comes in when a request mentions", details.load === "domain" ? (details.triggers ?? []).join(", ") || "only its domains" : null],
            ["Every brief shows", details.load === "domain" ? details.must_text : null],
            ["Critical", details.critical ? "Also in every session's startup context" : null],
          ]}
        />
      )}
    </Section>
  );
}

/** How this note is found: the ways people ask for it, when it applies and when not, which a
 * model wrote when it was approved and you can reword (one line each). A must-hold's
 * suggested trigger words wait here for your yes. */
function FoundWhen({ details }: { details: InventoryItem }) {
  const save = useAskedAs(details.id);
  const accept = useAcceptTriggers(details.id);
  const asked = details.asked_as ?? [];
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(asked.join("\n"));
  const suggested = details.suggested_triggers ?? [];

  function submit(event: FormEvent) {
    event.preventDefault();
    const lines = text.split("\n").map((line) => line.trim()).filter(Boolean);
    save.mutate(lines, { onSuccess: () => setOpen(false) });
  }

  return (
    <Section
      title="Found when you ask"
      actions={
        !open ? (
          <button
            type="button"
            className="link"
            onClick={() => {
              setText(asked.join("\n"));
              setOpen(true);
            }}
          >
            Reword
          </button>
        ) : null
      }
    >
      {open ? (
        <form className="stack" onSubmit={submit} aria-label="How this note is asked for">
          <Field label="Ways to ask for it" hint="One per line, in the words you would use. A request close to one of these finds this note.">
            <textarea rows={6} value={text} onChange={(event) => setText(event.target.value)} />
          </Field>
          <div className="row">
            <button type="submit" className="primary" disabled={save.isPending}>
              Save
            </button>
            <button type="button" onClick={() => setOpen(false)}>
              Cancel
            </button>
          </div>
          <ErrorNote error={save.error} />
        </form>
      ) : asked.length ? (
        <ul className="plain">
          {asked.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">
          Not written yet: it is found by its own words. The knowledge agent writes these when a model is chosen.
        </p>
      )}
      <KeyValues
        rows={[
          ["It is for", details.applies_when || null],
          ["Not for", details.not_when || null],
          ["Written", details.enriched ? `${day(details.enriched)}, by a model` : null],
        ]}
      />
      {suggested.length ? (
        <div className="stack">
          <p>Suggested words that bring this rule in: {suggested.join(", ")}</p>
          <div className="row">
            <button type="button" onClick={() => accept.mutate()} disabled={accept.isPending}>
              Use these words
            </button>
          </div>
          <ErrorNote error={accept.error} />
        </div>
      ) : null}
    </Section>
  );
}

/** An entry's details (owner, cadence, sensitivity, place), changed as one undo point. */
function DetailsForm({ details, onDone }: { details: InventoryItem; onDone: (decided: Decided | null) => void }) {
  const { data: policies } = useBrainPolicies();
  const decide = useBrainDecisions();
  const initial = {
    owner: details.owner_set ? details.owner : "",
    review_days: details.review_days_set ? String(details.review_days ?? "") : "",
    review_by: details.review_by ?? "",
    classification: details.classification ?? "internal",
    area: details.area,
    topic: details.topic.split("/").slice(1).join("/") || details.topic,
  };
  const [form, setForm] = useState(initial);
  const set = (key: keyof typeof form, value: string) => setForm((now) => ({ ...now, [key]: value }));
  const approver = policies?.approver ?? "";

  function submit(event: FormEvent) {
    event.preventDefault();
    const fields: Record<string, string> = {};
    for (const key of Object.keys(form) as (keyof typeof form)[]) {
      if (form[key] !== initial[key]) fields[key] = form[key];
    }
    if (!Object.keys(fields).length) return onDone(null);
    decide.mutate(
      { decisions: [{ action: "update", entry_id: details.id, fields }] },
      {
        onSuccess: (outcome) => {
          const failed = outcome.results.filter((r) => !r.ok);
          if (!failed.length) onDone(describeOutcome(outcome));
        },
      },
    );
  }

  return (
    <form className="stack" onSubmit={submit} aria-label="Change the note's details">
      <Field label="Owner" hint="Who answers for it. Empty: the Brain's default owner.">
        <select value={form.owner} onChange={(event) => set("owner", event.target.value)}>
          <option value="">Default ({ownerName(policies?.default_owner ?? "", approver) || "the owner"})</option>
          {(policies?.scopes ?? []).map((scope) => (
            <option key={scope} value={scope}>
              {ownerName(scope, approver)}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Check every (days)" hint="Empty: the policy's cadence for its area or kind.">
        <input inputMode="numeric" value={form.review_days} onChange={(event) => set("review_days", event.target.value)} />
      </Field>
      <Field label="Check by" hint="A date it must be checked by, whatever the cadence.">
        <input type="date" value={form.review_by} onChange={(event) => set("review_by", event.target.value)} />
      </Field>
      <Field label="Sensitivity">
        <select value={form.classification} onChange={(event) => set("classification", event.target.value)}>
          {CLASSIFICATIONS.map((value) => (
            <option key={value} value={value}>
              {label(value)}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Area">
        <select value={form.area} onChange={(event) => set("area", event.target.value)}>
          {(policies?.areas ?? [details.area]).map((key) => (
            <option key={key} value={key}>
              {label(key)}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Topic" hint="A short slug inside the area, like voice.">
        <input value={form.topic} onChange={(event) => set("topic", event.target.value)} />
      </Field>
      <div className="row">
        <button type="submit" className="primary" disabled={decide.isPending}>
          Save the details
        </button>
        <button type="button" onClick={() => onDone(null)}>
          Cancel
        </button>
      </div>
      <ErrorNote error={decide.error} />
      {decide.data?.results.filter((r) => !r.ok).map((r) => (
        <p key={r.id} className="error" role="alert">
          {r.message}
        </p>
      ))}
    </form>
  );
}

/** Editing an entry, or removing it from the Brain: each is an undo point in the History. */
function ChangeEntry({
  busy,
  editing,
  onEdit,
  onRemove,
}: {
  busy: boolean;
  editing: boolean;
  onEdit: () => void;
  onRemove: (reason: string) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [why, setWhy] = useState("");
  if (confirming) {
    return (
      <div className="stack">
        <p className="small">It leaves every task from now on. It stays in the Brain's history, and you can bring it back.</p>
        <Field label="Why remove it" hint="Optional; the history keeps it.">
          <input value={why} onChange={(event) => setWhy(event.target.value)} />
        </Field>
        <div className="row">
          <button type="button" className="danger" disabled={busy} onClick={() => onRemove(why.trim())}>
            Remove it
          </button>
          <button type="button" onClick={() => setConfirming(false)}>
            Cancel
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className="row">
      <button type="button" disabled={busy || editing} onClick={onEdit}>
        Edit
      </button>
      <button type="button" className="danger" disabled={busy} onClick={() => setConfirming(true)}>
        Remove from the Brain
      </button>
    </div>
  );
}

/** An entry just removed: what that means, and the undo right here. */
function Removed({ title, point, onBack }: { title: string; point: BrainCheckpoint; onBack: () => void }) {
  const undo = useBrainUndo();
  return (
    <div className="decided" role="status">
      <div>
        <strong>“{title}” is removed from the Brain.</strong> No task receives it any more; it stays in the Brain's history.
        <ErrorNote error={undo.error} />
      </div>
      <div className="row">
        <button type="button" disabled={undo.isPending} onClick={() => undo.mutate(point.id, { onSuccess: onBack })}>
          Undo
        </button>
        <Link className="button" to="/brain/entries">
          Back to all notes
        </Link>
      </div>
    </div>
  );
}

/** A retired entry: what it said, why it went, and the way back. */
function ArchivedEntry({ details }: { details: InventoryItem }) {
  const decide = useBrainDecisions();
  const [decided, setDecided] = useState<Decided | null>(null);
  const [tab, setTab] = useState<"versions" | "activity">("versions");
  return (
    <article className="entry">
      <header className="entry-head">
        <h1>{details.title}</h1>
        <span className="chips">
          <span className="chip chip-archived">Archived</span>
        </span>
      </header>
      {decided ? <DecidedBanner decided={decided} onChange={setDecided} /> : null}
      <div className="warning">
        <p>
          It no longer goes to any task; it stays as history.
          {details.superseded_by ? (
            <>
              {" "}
              <Link to={entryUrl(details.superseded_by)}>The entry that replaced it</Link> says it now.
            </>
          ) : null}
        </p>
        <button
          type="button"
          disabled={decide.isPending}
          onClick={() =>
            decide.mutate(
              { decisions: [{ action: "unarchive", entry_id: details.id, reason: "Brought back on its page" }] },
              { onSuccess: (outcome) => setDecided(describeOutcome(outcome)) },
            )
          }
        >
          Bring it back
        </button>
        <ErrorNote error={decide.error} />
      </div>
      <Tabs
        tabs={[
          { id: "versions", label: "Versions" },
          { id: "activity", label: "History" },
        ]}
        active={tab}
        onChange={setTab}
      />
      {tab === "versions" ? <Versions id={details.id} onDecided={setDecided} archived /> : <Activity id={details.id} />}
    </article>
  );
}

/** When an entry is next due for a check, and why then. */
function nextCheck(details: InventoryItem): string {
  if (!details.review_due) return "no cadence";
  const every = details.review_days ? ` (every ${plural(details.review_days, "day")})` : "";
  if (details.review_by && details.review_by === details.review_due) return `by ${day(details.review_due)}`;
  return `${day(details.review_due)}${every}`;
}

/** Why an entry is stale, in the words of whoever marked it when someone did. */
function staleNote(reason: string | null, history: BrainHistoryRecord[] | undefined): string {
  if (reason !== "marked stale") return `Stale: ${reason ?? "past its review date"}.`;
  const marked = history?.find((record) => record.action === "marked" && record.state === "stale");
  return marked?.reason ? `Marked stale: “${marked.reason}”.` : "Marked stale.";
}

// ---------------------------------------------------------------- Versions

function Versions({ id, onDecided, archived = false }: { id: string; onDecided: (decided: Decided) => void; archived?: boolean }) {
  const { data: versions, isLoading, error } = useEntryVersions(id, true);
  const { data: policies } = useBrainPolicies();
  const decide = useBrainDecisions();
  const [chosen, setChosen] = useState<string | null>(null);
  const [why, setWhy] = useState("");
  if (isLoading) return <Loading />;
  if (!versions) return <ErrorNote error={error} />;
  if (!versions.length) return <Empty why="No versions recorded yet." />;
  const current = versions[0]!;
  const picked = versions.find((v) => v.ref === chosen && !v.current) ?? null;
  const approver = policies?.approver ?? "";

  function restore() {
    if (!picked) return;
    decide.mutate(
      { decisions: [{ action: "restore", entry_id: id, ref: picked.ref, reason: why.trim() }] },
      {
        onSuccess: (outcome) => {
          setChosen(null);
          setWhy("");
          onDecided(describeOutcome(outcome));
        },
      },
    );
  }

  return (
    <div className="versions">
      <p className="section-lede">
        Every version this note has had, newest first. Pick one to compare it with today's and put it back: the restore is an
        undo point of its own.
      </p>
      <ol className="version-list">
        {versions.map((version) => {
          const made = version.changes.map((c) => describeEvent(c, approver, id));
          return (
            <li key={version.ref} className={version.ref === chosen ? "version active" : "version"}>
              <button
                type="button"
                className="version-pick"
                aria-pressed={version.ref === chosen}
                disabled={!!version.current}
                onClick={() => setChosen(version.ref === chosen ? null : version.ref)}
              >
                <span>
                  <strong>{new Date(version.at).toLocaleString()}</strong>{" "}
                  {version.current ? <span className="chip chip-approved">Now</span> : null}
                  {version.text_changed ? <span className="chip">Text changed</span> : <span className="chip">Details only</span>}
                  {!version.committed ? <span className="chip chip-suggested">Not committed</span> : null}
                </span>
                <span className="muted small">
                  {made.length ? made.join("; ") : version.message || "Recorded in the vault's history"}
                  {version.changes.find((c) => c.reason)?.reason ? ` · “${version.changes.find((c) => c.reason)?.reason}”` : ""}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      {picked ? (
        <div className="restore">
          <Compare
            before={{ label: `Version of ${new Date(picked.at).toLocaleDateString()}`, title: picked.title, body: picked.body ?? "" }}
            after={{ label: "Now", title: current.title, body: current.body ?? "" }}
          />
          {archived ? (
            <p className="muted">Bring the note back first to put this version back.</p>
          ) : (
            <div className="row wrap">
              <Field label="Why put it back" hint="Optional; the history keeps it.">
                <input value={why} onChange={(event) => setWhy(event.target.value)} />
              </Field>
              <button type="button" className="primary" disabled={decide.isPending} onClick={restore}>
                Put this version back
              </button>
            </div>
          )}
          <ErrorNote error={decide.error} />
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------- Use

function Use({ id }: { id: string }) {
  const { data: use, isLoading, error } = useEntryUse(id);
  if (isLoading) return <Loading />;
  if (!use) return <ErrorNote error={error} />;
  const totals = use.totals;
  return (
    <div className="use">
      <p className="use-totals">
        Went to <strong>{plural(totals.total ?? 0, "conversation or AI run", "conversations and AI runs")}</strong> in all:{" "}
        {totals.d7 ?? 0} in the last 7 days, {totals.d30 ?? 0} in the last 30.
        {totals.last ? ` Last on ${day(totals.last)}.` : " Never yet."}
      </p>
      {totals.total ? (
        <p className="muted small">
          In packets {plural(totals.in_packets ?? 0, "time")}, opened afterwards {plural(totals.opened ?? 0, "time")}, in AI work{" "}
          {plural(totals.in_work ?? 0, "time")}; {(totals.tokens ?? 0).toLocaleString()} tokens handed out. Days are counted in UTC.
        </p>
      ) : null}
      <Bars daily={use.daily} />
      <Section title="Recent handouts">
        {use.recent.length ? (
          <ol className="history">
            {use.recent.map((row, index) => (
              <li key={`${row.session_id}-${row.at}-${index}`}>
                <span>
                  <span className={`chip chip-via-${row.via}`}>
                    {row.via === "work" ? "AI work" : row.via === "opened" ? "Opened" : "In a packet"}
                  </span>{" "}
                  {row.work ? (
                    <>
                      {row.work.title} <span className="muted">by {row.work.actor}</span>
                    </>
                  ) : (
                    <span className="muted">conversation {row.session_id}</span>
                  )}
                  {row.request ? <span className="muted"> · asked “{clip(row.request, 140)}”</span> : null}
                  {row.reason ? <span className="small muted"> · {row.reason}</span> : null}
                </span>
                <time dateTime={row.at}>{when(row.at)}</time>
              </li>
            ))}
          </ol>
        ) : (
          <p className="muted">No handouts in the detail window. Daily counts above are kept for good.</p>
        )}
      </Section>
    </div>
  );
}

/** Conversations per day over the last 30 days, as bars. */
function Bars({ daily }: { daily: EntryUse["daily"] }) {
  const days: { day: string; n: number }[] = [];
  const counts = new Map(daily.map((d) => [d.day, d.conversations]));
  for (let back = 29; back >= 0; back--) {
    const date = new Date(Date.now() - back * 86_400_000).toISOString().slice(0, 10);
    days.push({ day: date, n: counts.get(date) ?? 0 });
  }
  const top = Math.max(1, ...days.map((d) => d.n));
  if (!days.some((d) => d.n)) return null;
  return (
    <div className="bars" role="img" aria-label="Uses per day over the last 30 days">
      {days.map((d) => (
        <span key={d.day} className="bar" style={{ height: `${Math.round((d.n / top) * 100)}%` }} title={`${day(d.day)}: ${d.n}`} />
      ))}
    </div>
  );
}

function clip(text: string, limit: number): string {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > limit ? `${flat.slice(0, limit - 1)}…` : flat;
}

// ---------------------------------------------------------------- Activity

function Activity({ id }: { id: string }) {
  const { data: events, isLoading, error } = useBrainActivity({ entry: id });
  const { data: policies } = useBrainPolicies();
  if (isLoading) return <Loading />;
  if (!events) return <ErrorNote error={error} />;
  if (!events.length) return <Empty why="Nothing recorded for this note yet." />;
  return <EventList events={events} approver={policies?.approver} about={id} />;
}
