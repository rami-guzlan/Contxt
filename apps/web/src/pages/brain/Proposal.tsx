// One proposal in review: what it says, what it would change in the Brain, and the choices
// that shape how it lands (replace an entry it overlaps, file it under another topic).

import { useState } from "react";
import { Link } from "react-router";

import type {
  BrainCatalog,
  BrainDecision,
  ProposalAnalysis,
  Reconciliation,
  RelatedEntry,
  ReviewBatch,
  ReviewProposal,
} from "../../api/types";
import { Compare } from "../../components/Diff";
import { Markdown } from "../../components/Markdown";
import { type Draft, TextEditor, changes } from "../../components/TextEditor";
import { KeyValues } from "../../components/ui";
import { bytes, label, when } from "../../lib/format";
import { Reconcile } from "./Reconcile";
import { entryUrl } from "./shared";

/** A proposal as it stands before anyone edits it. */
export function originalOf(proposal: ReviewProposal): Draft {
  return { title: titleOf(proposal), summary: proposal.note_summary ?? "", body: proposal.body ?? "" };
}

/** An entry as it stands in the Brain before anyone edits it. */
export function entryOriginal(entry: RelatedEntry): Draft {
  return { title: entry.title, summary: entry.summary ?? "", body: entry.body };
}

/** Everything the person rewrote, as the decisions that carry it: the proposal approved in
 * their words, and each entry they edited so both can stand. */
export function approvalWithEdits(
  proposal: ReviewProposal,
  analysis: ProposalAnalysis,
  choice: Choice | undefined,
  base: BrainDecision,
): BrainDecision[] {
  const own = choice?.draft ? changes(originalOf(proposal), choice.draft) : {};
  const approval: BrainDecision = { ...base, ...own };
  const pool = [...analysis.conflicts, ...analysis.overlaps];
  const edits = Object.entries(choice?.entryDrafts ?? {}).flatMap(([id, draft]): BrainDecision[] => {
    const entry = pool.find((e) => e.id === id);
    if (!entry) return [];
    const changed = changes(entryOriginal(entry), draft);
    if (!Object.keys(changed).length) return [];
    // An edit always carries the whole text, even when only its title changed.
    return [
      {
        action: "edit",
        entry_id: id,
        reason: `Edited while approving “${titleOf(proposal)}”`,
        body: draft.body.trim(),
        ...changed,
      },
    ];
  });
  return [approval, ...edits];
}

/** The newest reconcile request about this pair, and the rewrite it suggested, if any. */
function reconciling(
  proposal: ReviewProposal,
  entryId: string,
  all: Map<string, ReviewProposal>,
): { reconciliation?: Reconciliation; suggestion?: ReviewProposal } {
  const reconciliation = (proposal.reconciliations ?? []).find((r) => r.entry_id === entryId);
  const suggestion = reconciliation?.suggestion_ids.map((id) => all.get(id)).find((p) => p !== undefined);
  return { reconciliation, suggestion };
}

export type Relation = "replace" | "keep";

/** How the person wants a proposal to land. */
export interface Choice {
  relations: Record<string, Relation>; // entry id -> replace it, or keep both
  topic?: string; // file it under another area/topic
  draft?: Draft; // the proposal in the person's own words
  entryDrafts?: Record<string, Draft>; // entries the person rewrote so both can stand
}

export function analysisOf(proposal: ReviewProposal): ProposalAnalysis {
  const a = proposal.analysis ?? {};
  return {
    id: proposal.id,
    kind: a.kind ?? proposal.kind,
    title: a.title ?? proposal.title ?? "",
    route_key: a.route_key ?? proposal.route_key ?? "",
    placement: a.placement ?? "chosen",
    change: a.change ?? (proposal.kind === "note.create" ? "new" : "update"),
    replaces: a.replaces ?? [],
    conflicts: a.conflicts ?? [],
    overlaps: a.overlaps ?? [],
    duplicates: a.duplicates ?? [],
    related: a.related ?? [],
    new_topic: a.new_topic ?? false,
    suggested: a.suggested ?? [],
    base_changed: a.base_changed ?? false,
    problems: a.problems ?? [],
    skill: a.skill,
    skill_before: a.skill_before,
  };
}

/** Near repeats of live entries that the proposal does not already name. */
export function closeOverlaps(a: ProposalAnalysis): RelatedEntry[] {
  return a.overlaps.filter((o) => o.close);
}

/** Something to settle before approving (the server counts these as "look"). */
export function needsALook(a: ProposalAnalysis): boolean {
  return !!(a.conflicts.length || closeOverlaps(a).length || a.duplicates.length || a.problems.length);
}

/** A contradiction must be settled first: replace the entry, or keep both on purpose. */
export function unsettled(a: ProposalAnalysis, choice: Choice | undefined): RelatedEntry[] {
  return a.conflicts.filter((c) => !choice?.relations[c.id]);
}

/** The entries approving it archives: the ones it names, and the ones the person chose. */
export function replacing(a: ProposalAnalysis, choice: Choice | undefined): string[] {
  const chosen = Object.entries(choice?.relations ?? {})
    .filter(([, relation]) => relation === "replace")
    .map(([id]) => id);
  const named = a.change === "new" ? a.replaces.map((r) => r.id) : [];
  return [...new Set([...named, ...chosen])];
}

/** A proposal's name: its title, else what it would file, else its one-line summary. */
export function titleOf(proposal: ReviewProposal): string {
  const skill = proposal.kind?.startsWith("skill.") ? proposal.target?.name : null;
  if (typeof skill === "string" && skill) return `/${skill}`;
  const file = proposal.files?.[0]?.path.split("/").pop();
  return proposal.title || proposal.note_summary || file || proposal.summary || proposal.id;
}

/** "model:Claude Code (act_...)" reads as "Claude Code (a model)"; Brain handles pass through. */
export function proposerName(raw: string | undefined): string {
  const match = /^(human|model|system):(.+?) \([^)]*\)$/.exec(raw ?? "");
  if (!match) return raw || "someone";
  return match[1] === "model" ? `${match[2]} (a model)` : (match[2] ?? "someone");
}

/** "company/offers" as people read it: "Company / Offers", from the catalog when it knows. */
export function topicLabel(routeKey: string, catalog?: BrainCatalog): string {
  const [areaKey = "", topicKey = ""] = routeKey.split("/");
  const area = catalog?.areas.find((a) => a.key === areaKey);
  const topic = area?.topics.find((t) => t.key === routeKey);
  const nice = (text: string) => text.replace(/-/g, " ").replace(/^./, (c) => c.toUpperCase());
  const areaName = area?.label ?? nice(areaKey);
  if (!topicKey || topicKey === areaKey) return areaName;
  return `${areaName} / ${topic?.label ?? nice(topicKey)}`;
}

function Badge({ analysis }: { analysis: ProposalAnalysis }) {
  if (analysis.conflicts.length) return <span className="chip chip-conflict">Contradicts an entry</span>;
  if (analysis.problems.length) return <span className="chip chip-conflict">Check first</span>;
  if (closeOverlaps(analysis).length) return <span className="chip chip-close">Close to an entry</span>;
  if (analysis.duplicates.length) return <span className="chip chip-close">Repeats a proposal</span>;
  if (analysis.change === "new" && analysis.replaces.length) return <span className="chip chip-replace">Replaces an entry</span>;
  if (analysis.change === "update") return <span className="chip chip-replace">Changes an entry</span>;
  if (analysis.change === "retire") return <span className="chip chip-conflict">Retires an entry</span>;
  if (analysis.change === "skill")
    return <span className="chip chip-kind">{analysis.kind === "skill.update" ? "Changes a skill" : "New skill"}</span>;
  if (analysis.change === "file") return <span className="chip chip-kind">{label(analysis.change)}</span>;
  return <span className="chip chip-new">New</span>;
}

/** The one-line account of what approving does, shown under the title. */
function Effect({ analysis, choice, catalog }: { analysis: ProposalAnalysis; choice?: Choice; catalog?: BrainCatalog }) {
  const target = choice?.topic ?? analysis.route_key;
  const gone = replacing(analysis, choice);
  const names = (ids: string[], pool: RelatedEntry[]) =>
    ids.map((id) => pool.find((e) => e.id === id)?.title ?? id).join(", ");
  const pool = [...analysis.replaces, ...analysis.conflicts, ...analysis.overlaps];
  return (
    <p className="effect">
      {target ? (
        <span>
          Files under {topicLabel(target, catalog)}
          {choice?.topic ? " (moved)" : analysis.placement === "guessed" ? " (placed by guess)" : ""}
          {analysis.new_topic && !choice?.topic ? ", a new topic" : ""}
        </span>
      ) : null}
      {analysis.change === "update" && analysis.replaces[0] ? <span>Rewrites “{analysis.replaces[0].title}”</span> : null}
      {analysis.change === "retire" && analysis.replaces[0] ? <span>Archives “{analysis.replaces[0].title}”</span> : null}
      {gone.length ? <span>Archives {names(gone, pool)}</span> : null}
      {choice?.draft ? <span>Approved in your words</span> : null}
      {Object.keys(choice?.entryDrafts ?? {}).length ? (
        <span>Also edits {names(Object.keys(choice?.entryDrafts ?? {}), pool)}</span>
      ) : null}
    </p>
  );
}

export function ProposalRow({
  proposal,
  batch,
  catalog,
  selected,
  onSelect,
  choice,
  onChoose,
  open,
  onToggle,
  onDecide,
  onRun,
  all,
  busy,
}: {
  proposal: ReviewProposal;
  batch: ReviewBatch;
  catalog?: BrainCatalog;
  selected: boolean;
  onSelect: (on: boolean) => void;
  choice?: Choice;
  onChoose: (choice: Choice) => void;
  open: boolean;
  onToggle: () => void;
  onDecide: (approve: boolean, reason: string) => void;
  onRun: (decisions: BrainDecision[]) => void; // several decisions as one undo point
  all: Map<string, ReviewProposal>; // every waiting proposal, for rewrites a model suggested
  busy: boolean;
}) {
  const analysis = analysisOf(proposal);
  const waiting = unsettled(analysis, choice);
  const name = titleOf(proposal);
  const summary = proposal.note_summary || proposal.summary || "";
  return (
    <li className={open ? "review-row open" : "review-row"}>
      <div className="review-row-head">
        <input
          type="checkbox"
          aria-label={`Select ${name}`}
          checked={selected}
          disabled={waiting.length > 0}
          title={waiting.length ? "Settle the contradiction first: open it and choose" : undefined}
          onChange={(event) => onSelect(event.target.checked)}
        />
        <button type="button" className="review-row-main" aria-expanded={open} onClick={onToggle}>
          <span className="review-row-title">
            <Badge analysis={analysis} />
            <strong>{name}</strong>
          </span>
          {summary && summary !== name ? <span className="review-row-summary">{summary}</span> : null}
          <Effect analysis={analysis} choice={choice} catalog={catalog} />
        </button>
      </div>
      {open ? (
        <ProposalDetail
          proposal={proposal}
          analysis={analysis}
          batch={batch}
          catalog={catalog}
          choice={choice}
          onChoose={onChoose}
          onDecide={onDecide}
          onRun={onRun}
          all={all}
          busy={busy}
        />
      ) : null}
    </li>
  );
}

function ProposalDetail({
  proposal,
  analysis,
  batch,
  catalog,
  choice,
  onChoose,
  onDecide,
  onRun,
  all,
  busy,
}: {
  proposal: ReviewProposal;
  analysis: ProposalAnalysis;
  batch: ReviewBatch;
  catalog?: BrainCatalog;
  choice?: Choice;
  onChoose: (choice: Choice) => void;
  onDecide: (approve: boolean, reason: string) => void;
  onRun: (decisions: BrainDecision[]) => void;
  all: Map<string, ReviewProposal>;
  busy: boolean;
}) {
  const current = choice ?? { relations: {} };
  // What the page shows as "proposed": the person's own words once they edited it.
  const name = current.draft?.title.trim() || titleOf(proposal);
  const body = current.draft?.body ?? proposal.body ?? "";
  const editable = proposal.kind === "note.create" || proposal.kind === "note.update";
  const relate = (id: string, relation: Relation) =>
    onChoose({ ...current, relations: { ...current.relations, [id]: relation } });
  const target = typeof proposal.target?.evidence === "string" ? proposal.target.evidence : null;
  const related = analysis.overlaps.filter((o) => !o.close);
  const documents = new Map(batch.documents.map((d) => [`context_item:${d.id}`, d.title]));
  const sources = (proposal.sources ?? []).filter((s) => !/^(task|run|brain):/.test(s)).map((s) => documents.get(s) ?? s);
  return (
    <div className="review-detail">
      {analysis.problems.length ? (
        <ul className="warning problems">
          {analysis.problems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      ) : null}

      {analysis.change === "update" && analysis.replaces[0] ? (
        <Compare
          before={{ label: "In the Brain now", title: analysis.replaces[0].title, body: analysis.replaces[0].body }}
          after={{ label: "Proposed", title: name, body }}
        />
      ) : analysis.change === "retire" && analysis.replaces[0] ? (
        <div className="relation">
          <p className="relation-head">Retires this entry. It leaves every task; Undo brings it back.</p>
          <div className="document compact">
            <Markdown text={analysis.replaces[0].body} />
          </div>
        </div>
      ) : analysis.skill_before ? (
        <div className="relation">
          <p className="relation-head">
            A new version of <Link to={`/skills/${encodeURIComponent(analysis.skill?.name ?? "")}`}>{name}</Link>: approving puts it to
            work for every AI you connect, and Undo brings the old one back.
          </p>
          <Compare
            before={{
              label: "The skill now",
              title: name,
              body: analysis.skill_before.body,
              note: changedDescription(analysis) ? analysis.skill_before.description : undefined,
            }}
            after={{
              label: "Proposed",
              title: name,
              body,
              note: changedDescription(analysis) ? analysis.skill?.description : undefined,
            }}
          />
        </div>
      ) : proposal.kind === "skill.create" ? (
        <div className="stack">
          <SkillFacts proposal={proposal} />
          {body ? (
            <div className="document compact">
              <Markdown text={body} />
            </div>
          ) : null}
        </div>
      ) : body ? (
        <div className="document compact">
          <Markdown text={body} />
        </div>
      ) : null}

      {editable ? <EditOwn proposal={proposal} choice={current} onChoose={onChoose} /> : null}

      {analysis.change === "new"
        ? analysis.replaces.map((entry) => (
            <div key={entry.id} className="relation">
              <p className="relation-head">
                Replaces an entry: approving archives “{entry.title}”. It stays in history, and Undo brings it back.
              </p>
              <Compare before={{ label: "In the Brain now", title: entry.title, body: entry.body }} after={{ label: "Proposed", title: name, body }} />
            </div>
          ))
        : null}

      {analysis.conflicts.map((entry) => (
        <div key={entry.id} className="relation conflict">
          <p className="relation-head">
            Contradicts “{entry.title}”. The proposer could not tell which is current; you decide.
          </p>
          <Compare before={{ label: "In the Brain now", title: entry.title, body: entry.body }} after={{ label: "Proposed", title: name, body }} />
          <RelationChoice entry={entry} value={current.relations[entry.id]} onChange={(r) => relate(entry.id, r)} required />
          {current.relations[entry.id] === "keep" ? <EditEntry entry={entry} choice={current} onChoose={onChoose} /> : null}
          <Reconcile proposal={proposal} entry={entry} name={name} onRun={onRun} busy={busy} {...reconciling(proposal, entry.id, all)} />
        </div>
      ))}

      {closeOverlaps(analysis).map((entry) => (
        <div key={entry.id} className="relation close">
          <p className="relation-head">
            Very close to “{entry.title}”{entry.score ? ` (${Math.round(entry.score * 100)}% alike)` : ""}. If they say the same
            thing, keep one.
          </p>
          <Compare before={{ label: "In the Brain now", title: entry.title, body: entry.body }} after={{ label: "Proposed", title: name, body }} />
          <RelationChoice entry={entry} value={current.relations[entry.id] ?? "keep"} onChange={(r) => relate(entry.id, r)} />
          {current.relations[entry.id] !== "replace" ? <EditEntry entry={entry} choice={current} onChoose={onChoose} /> : null}
          <Reconcile proposal={proposal} entry={entry} name={name} onRun={onRun} busy={busy} {...reconciling(proposal, entry.id, all)} />
        </div>
      ))}

      {analysis.duplicates.length ? (
        <div className="relation close">
          <p className="relation-head">
            Says much the same as {analysis.duplicates.map((d) => `“${d.title}”`).join(", ")}, also waiting here. Approve one and
            reject the other.
          </p>
        </div>
      ) : null}

      {proposal.kind === "file.add" || proposal.kind.startsWith("skill.") ? <Upload proposal={proposal} /> : null}

      {proposal.kind === "note.create" ? (
        <Placement analysis={analysis} catalog={catalog} value={current.topic} onChange={(topic) => onChoose({ ...current, topic })} />
      ) : null}

      <details className="provenance">
        <summary>Where it came from</summary>
        <KeyValues
          rows={[
            ["Evidence", target ? <q>{target}</q> : null],
            ["From", sources.length ? sources.join(", ") : null],
            [
              "Checked against",
              [...analysis.related, ...related].length ? (
                <span className="inline-links">
                  {[...analysis.related, ...related].map((entry) => (
                    <Link key={entry.id} to={entryUrl(entry.id)} target="_blank" rel="noreferrer">
                      {entry.title}
                    </Link>
                  ))}
                </span>
              ) : null,
            ],
            ["Proposed by", `${proposerName(proposal.proposer)}${proposal.created ? `, ${when(proposal.created)}` : ""}`],
            ["Why", proposal.reason],
            ["AI work", batch.task_id ? batch.title : null],
          ]}
        />
      </details>

      <RowDecision name={name} busy={busy} blocked={unsettled(analysis, choice).length > 0} onDecide={onDecide} />
    </div>
  );
}

/** The proposal in the person's own words: edited here, approved as edited. */
function EditOwn({
  proposal,
  choice,
  onChoose,
}: {
  proposal: ReviewProposal;
  choice: Choice;
  onChoose: (choice: Choice) => void;
}) {
  const [editing, setEditing] = useState(false);
  if (editing) {
    return (
      <TextEditor
        label={`Edit ${titleOf(proposal)}`}
        initial={choice.draft ?? originalOf(proposal)}
        withSummary={proposal.kind === "note.create"}
        onSave={(draft) => {
          onChoose({ ...choice, draft });
          setEditing(false);
        }}
        onCancel={() => setEditing(false)}
      />
    );
  }
  return (
    <div className="row small">
      <button type="button" onClick={() => setEditing(true)}>
        {choice.draft ? "Edit again" : "Edit before approving"}
      </button>
      {choice.draft ? (
        <>
          <span className="chip chip-edited">Edited by you</span>
          <button type="button" className="link" onClick={() => onChoose({ ...choice, draft: undefined })}>
            Undo my edits
          </button>
        </>
      ) : null}
    </div>
  );
}

/** An entry the person rewrites so it and the proposal can both stand; saved with the
 * approval, in the same undo point. */
function EditEntry({ entry, choice, onChoose }: { entry: RelatedEntry; choice: Choice; onChoose: (choice: Choice) => void }) {
  const [editing, setEditing] = useState(false);
  const draft = choice.entryDrafts?.[entry.id];
  const keep = (next: Draft | undefined) => {
    const drafts = { ...(choice.entryDrafts ?? {}) };
    if (next) drafts[entry.id] = next;
    else delete drafts[entry.id];
    onChoose({ ...choice, entryDrafts: drafts });
  };
  if (editing) {
    return (
      <TextEditor
        label={`Edit ${entry.title}`}
        initial={draft ?? entryOriginal(entry)}
        saveLabel="Keep this edit"
        onSave={(next) => {
          keep(next);
          setEditing(false);
        }}
        onCancel={() => setEditing(false)}
      />
    );
  }
  if (!draft) {
    return (
      <div className="row small">
        <button type="button" onClick={() => setEditing(true)}>
          Edit “{entry.title}” so both can stand
        </button>
      </div>
    );
  }
  return (
    <div className="own-edit">
      <p className="relation-head">Your edit of “{entry.title}” is saved with this approval:</p>
      <Compare
        before={{ label: "In the Brain now", title: entry.title, body: entry.body }}
        after={{ label: "As you edited it", title: draft.title || entry.title, body: draft.body }}
      />
      <div className="row small">
        <button type="button" onClick={() => setEditing(true)}>
          Edit again
        </button>
        <button type="button" className="link" onClick={() => keep(undefined)}>
          Drop my edit
        </button>
      </div>
    </div>
  );
}

function RelationChoice({
  entry,
  value,
  onChange,
  required,
}: {
  entry: RelatedEntry;
  value?: Relation;
  onChange: (relation: Relation) => void;
  required?: boolean;
}) {
  return (
    <fieldset className="relation-choice">
      <legend>{required ? "Choose before approving" : "When you approve it"}</legend>
      <label className="checkbox">
        <input type="radio" name={`relation-${entry.id}`} checked={value === "replace"} onChange={() => onChange("replace")} />
        Replace “{entry.title}” with this (it is archived)
      </label>
      <label className="checkbox">
        <input type="radio" name={`relation-${entry.id}`} checked={value === "keep"} onChange={() => onChange("keep")} />
        Keep both
      </label>
    </fieldset>
  );
}

function Placement({
  analysis,
  catalog,
  value,
  onChange,
}: {
  analysis: ProposalAnalysis;
  catalog?: BrainCatalog;
  value?: string;
  onChange: (topic: string | undefined) => void;
}) {
  const suggested = analysis.suggested.filter((s) => s.topic !== analysis.route_key);
  const all = (catalog?.areas ?? []).flatMap((area) => area.topics.map((topic) => topic.key));
  return (
    <div className="placement">
      <label className="field-label" htmlFor={`place-${analysis.id}`}>
        File it under
      </label>
      <select id={`place-${analysis.id}`} value={value ?? ""} onChange={(event) => onChange(event.target.value || undefined)}>
        <option value="">
          {topicLabel(analysis.route_key, catalog)}
          {analysis.placement === "guessed" ? " (placed by guess)" : ""}
          {analysis.new_topic ? " (new topic)" : ""}
        </option>
        {suggested.length ? (
          <optgroup label="Closest existing topics">
            {suggested.map((s) => (
              <option key={s.topic} value={s.topic}>
                {topicLabel(s.topic, catalog)}
              </option>
            ))}
          </optgroup>
        ) : null}
        <optgroup label="Every topic">
          {all
            .filter((key) => key !== analysis.route_key)
            .map((key) => (
              <option key={key} value={key}>
                {topicLabel(key, catalog)}
              </option>
            ))}
        </optgroup>
      </select>
    </div>
  );
}

function RowDecision({
  name,
  busy,
  blocked,
  onDecide,
}: {
  name: string;
  busy: boolean;
  blocked: boolean;
  onDecide: (approve: boolean, reason: string) => void;
}) {
  return (
    <form
      className="row decision"
      onSubmit={(event) => {
        event.preventDefault();
        const reason = new FormData(event.currentTarget).get("reason");
        onDecide(false, typeof reason === "string" ? reason : "");
      }}
    >
      <button type="button" className="primary" disabled={busy || blocked} onClick={() => onDecide(true, "")}>
        Approve
      </button>
      <input name="reason" aria-label={`Why reject ${name}`} placeholder="Reason, if you reject it" />
      <button type="submit" className="danger" disabled={busy}>
        Reject
      </button>
    </form>
  );
}

/** Whether a new version of a skill also says something new about what the skill is for. */
function changedDescription(analysis: ProposalAnalysis): boolean {
  const now = analysis.skill_before?.description.trim() ?? "";
  const next = analysis.skill?.description.trim() ?? "";
  return !!next && next !== now;
}

/** What a new skill does and when your AI picks it up, as its proposal says. */
function SkillFacts({ proposal }: { proposal: ReviewProposal }) {
  const target = proposal.target ?? {};
  const list = (key: string) => (Array.isArray(target[key]) ? (target[key] as unknown[]).map(String) : []);
  const description = typeof target.description === "string" ? target.description : "";
  const triggers = list("triggers");
  const makes = list("artifacts");
  const loads = list("loads");
  return (
    <dl className="skill-facts">
      {description ? (
        <>
          <dt>What it does</dt>
          <dd>{description}</dd>
        </>
      ) : null}
      {triggers.length ? (
        <>
          <dt>What you say to ask for it</dt>
          <dd>{triggers.map((t) => `“${t}”`).join(", ")}</dd>
        </>
      ) : null}
      {makes.length ? (
        <>
          <dt>What it makes</dt>
          <dd>{makes.join(", ")}</dd>
        </>
      ) : null}
      {loads.length ? (
        <>
          <dt>What it loads</dt>
          <dd>{loads.join(", ")}</dd>
        </>
      ) : null}
    </dl>
  );
}

function Upload({ proposal }: { proposal: ReviewProposal }) {
  return (
    <div className="upload-preview">
      {proposal.files?.length ? (
        <ul className="list">
          {proposal.files.map((file) => (
            <li key={file.path}>
              <code>{file.path}</code> <span className="muted">· {bytes(file.size)}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {proposal.preview ? (
        <details>
          <summary>{proposal.purpose === "reference" ? "The document's text" : "Preview"}</summary>
          <pre className="document compact code-view">{proposal.preview}</pre>
        </details>
      ) : null}
    </div>
  );
}
