// Review: everything waiting to become long-term context, in batches by the work that proposed
// it. Each batch says what is in it and what needs a look; the clear ones are approved
// together, and every decision is saved as an undo point.

import { useMemo, useState } from "react";
import { Link } from "react-router";

import { useBrainAttention, useBrainCatalog, useBrainDecisions, useBrainReview } from "../../api/hooks";
import type { BrainCatalog, BrainDecision, ReviewBatch, ReviewProposal } from "../../api/types";
import { Empty, ErrorNote, Loading, Section } from "../../components/ui";
import { when } from "../../lib/format";
import {
  type Choice,
  ProposalRow,
  analysisOf,
  approvalWithEdits,
  needsALook,
  replacing,
  titleOf,
  topicLabel,
  unsettled,
} from "./Proposal";
import { BrainChecks, type Decided, DecidedBanner, describeOutcome } from "./decided";
import { needsAttention } from "./shared";

export { proposerName } from "./Proposal";

export function ReviewPage() {
  const { data: attention } = useBrainAttention();
  const checks = attention ? attention.clashes.length + attention.twins.length + attention.flagged.length + attention.recheck.length : 0;
  return (
    <div className="page">
      <h1>Review</h1>
      <p className="lede" data-tour="review">
        What waits for you: what your AI suggested, files waiting for a look, and pieces of the Brain that clash or repeat each
        other.
      </p>
      <Proposals />
      {checks && attention ? (
        <Section title="Wants a look">
          <BrainChecks attention={attention} />
        </Section>
      ) : null}
    </div>
  );
}

function Proposals() {
  const { data: review, isLoading, error } = useBrainReview();
  const { data: catalog } = useBrainCatalog();
  const [decided, setDecided] = useState<Decided | null>(null);
  if (isLoading) return <Loading />;
  if (!review) return <ErrorNote error={error} />;
  const byId = new Map(review.proposals.map((p) => [p.id, p]));
  // A model's rewrite from reconciling is shown beside the pair it settles, not on its own.
  const batches = review.batches.filter((b) => !inline(b, byId));
  const total = review.proposals.length;
  const look = batches.reduce((n, b) => n + b.counts.look, 0);
  return (
    <div className="review">
      {decided ? <DecidedBanner decided={decided} onChange={setDecided} /> : null}
      <p className="section-lede">
        Nothing becomes long-term context until you approve it. Each batch shows what it would add, what it replaces, and what
        needs a look first. Every decision is saved as an undo point in the Brain's{" "}
        <Link to="/brain/history?view=undo">History</Link>.
      </p>
      {total ? (
        <>
          <p className="review-totals">
            <strong>{total}</strong> waiting in {batches.length} batch{batches.length === 1 ? "" : "es"}
            {look ? (
              <>
                {" · "}
                <span className="attention">{look} need a look</span>
              </>
            ) : (
              " · all clear to approve"
            )}
          </p>
          {batches.map((batch) => (
            <BatchCard
              key={`${batch.key}:${batch.proposal_ids.join(",")}`}
              batch={batch}
              proposals={batch.proposal_ids.flatMap((id) => byId.get(id) ?? [])}
              all={byId}
              catalog={catalog}
              onDecided={setDecided}
            />
          ))}
        </>
      ) : (
        <Empty why="Nothing is waiting. What your AI suggests, and what it finds to remember in your notes, lands here." />
      )}
    </div>
  );
}

/** Whether a batch is a model's rewrite shown beside the waiting proposal it reconciles. */
export function inline(batch: ReviewBatch, waiting: Map<string, ReviewProposal>): boolean {
  return !!batch.reconciles && waiting.has(batch.reconciles.proposal_id);
}

export function BatchTiles({ batch }: { batch: ReviewBatch }) {
  const c = batch.counts;
  return (
    <dl className="batch-tiles">
      <div className="tile">
        <dt>Ready</dt>
        <dd>{c.clear}</dd>
      </div>
      <div className={c.look ? "tile attention" : "tile"}>
        <dt>Need a look</dt>
        <dd>{c.look}</dd>
      </div>
      <div className="tile">
        <dt>Replace or change entries</dt>
        <dd>{c.replaces + c.updates}</dd>
      </div>
      {c.files ? (
        <div className="tile">
          <dt>Files</dt>
          <dd>{c.files}</dd>
        </div>
      ) : null}
      {c.skills ? (
        <div className="tile">
          <dt>Skills</dt>
          <dd>{c.skills}</dd>
        </div>
      ) : null}
    </dl>
  );
}

function BatchCard({
  batch,
  proposals,
  all,
  catalog,
  onDecided,
}: {
  batch: ReviewBatch;
  proposals: ReviewProposal[];
  all: Map<string, ReviewProposal>;
  catalog?: BrainCatalog;
  onDecided: (decided: Decided) => void;
}) {
  const analyses = useMemo(() => new Map(proposals.map((p) => [p.id, analysisOf(p)])), [proposals]);
  const look = proposals.filter((p) => needsALook(analysisOf(p)));
  const ready = proposals.filter((p) => !needsALook(analysisOf(p)));
  const [selected, setSelected] = useState<Set<string>>(() => new Set(ready.map((p) => p.id)));
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [open, setOpen] = useState<Set<string>>(() => new Set());
  const [archive, setArchive] = useState<Set<string>>(() => new Set());
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const decide = useBrainDecisions();

  const source = { title: batch.title, ...(batch.task_id ? { task_id: batch.task_id } : {}) };
  const run = (decisions: BrainDecision[]) =>
    decide.mutate({ decisions, source }, { onSuccess: (outcome) => onDecided(describeOutcome(outcome)) });

  /** Approving one proposal: with the entries it replaces, its topic, and every edit the person
   * made to it or to an entry beside it (all in the same undo point). */
  function approval(proposal: ReviewProposal): BrainDecision[] {
    const analysis = analyses.get(proposal.id) ?? analysisOf(proposal);
    const choice = choices[proposal.id];
    const chose = Object.values(choice?.relations ?? {}).includes("replace");
    return approvalWithEdits(proposal, analysis, choice, {
      action: "approve",
      proposal_id: proposal.id,
      ...(chose ? { replaces: replacing(analysis, choice) } : {}),
      ...(choice?.topic ? { topic: choice.topic } : {}),
    });
  }

  const chosen = proposals.filter((p) => selected.has(p.id));
  const archivedByApproval = new Set(chosen.flatMap((p) => replacing(analyses.get(p.id) ?? analysisOf(p), choices[p.id])));
  const tidy = tidyCandidates(batch, catalog, archivedByApproval);
  const archiving = [...archive].filter((id) => !archivedByApproval.has(id));
  const adds = chosen.filter((p) => analyses.get(p.id)?.change === "new" || analyses.get(p.id)?.change === "file").length;
  const changes = chosen.filter((p) => analyses.get(p.id)?.change === "update").length;
  const removes = archivedByApproval.size + archiving.length;
  const effect = [
    adds ? `adds ${adds} entr${adds === 1 ? "y" : "ies"}` : "",
    changes ? `changes ${changes}` : "",
    removes ? `archives ${removes}` : "",
  ]
    .filter(Boolean)
    .join(", ");

  const toggle = (set: Set<string>, id: string, on: boolean) => {
    const next = new Set(set);
    if (on) next.add(id);
    else next.delete(id);
    return next;
  };

  function row(proposal: ReviewProposal) {
    const analysis = analyses.get(proposal.id) ?? analysisOf(proposal);
    return (
      <ProposalRow
        key={proposal.id}
        proposal={proposal}
        batch={batch}
        catalog={catalog}
        selected={selected.has(proposal.id)}
        onSelect={(on) => setSelected((s) => toggle(s, proposal.id, on))}
        choice={choices[proposal.id]}
        onChoose={(choice) => {
          setChoices((all) => ({ ...all, [proposal.id]: choice }));
          if (!unsettled(analysis, choice).length && analysis.conflicts.length) {
            setSelected((s) => toggle(s, proposal.id, true));
          }
        }}
        open={open.has(proposal.id)}
        onToggle={() => setOpen((s) => toggle(s, proposal.id, !s.has(proposal.id)))}
        onDecide={(approve, why) =>
          run(approve ? approval(proposal) : [{ action: "reject", proposal_id: proposal.id, reason: why }])
        }
        onRun={run}
        all={all}
        busy={decide.isPending}
      />
    );
  }

  const groups = new Map<string, ReviewProposal[]>();
  for (const proposal of ready) {
    const key = choices[proposal.id]?.topic ?? analyses.get(proposal.id)?.route_key ?? "";
    groups.set(key, [...(groups.get(key) ?? []), proposal]);
  }

  return (
    <section className="batch-card" aria-label={batch.title}>
      <header className="batch-head">
        <div>
          <p className="eyebrow">
            {batch.task_id ? "From a task" : "Proposed directly"} · {batch.proposer}
            {batch.created ? ` · ${when(batch.created)}` : ""}
          </p>
          <h2>{batch.title}</h2>
          {batch.documents.length ? (
            <p className="muted">
              Read from {batch.documents.map((d) => d.title).join(", ")} ·{" "}
              <Link to="/brain/files?tab=uploads">see the files</Link>
            </p>
          ) : null}
        </div>
        <BatchTiles batch={batch} />
      </header>

      {batch.topics.length ? (
        <p className="batch-topics">
          <span className="muted">Would file under </span>
          {batch.topics.map((t) => (
            <span key={t.route_key} className="chip">
              {topicLabel(t.route_key, catalog)} {t.count}
            </span>
          ))}
        </p>
      ) : null}

      {look.length ? (
        <section className="review-group attention-group">
          <h3>
            Needs a look <span className="facet-count">{look.length}</span>
          </h3>
          <p className="muted small">
            These contradict, nearly repeat or clash with something. Open each one, compare, and choose.
          </p>
          <ul className="review-list">{look.map(row)}</ul>
        </section>
      ) : null}

      {ready.length ? (
        <section className="review-group">
          <h3>
            Ready to approve <span className="facet-count">{ready.length}</span>
          </h3>
          {[...groups].map(([key, members]) => (
            <div key={key} className="review-topic">
              <h4>
                {key ? topicLabel(key, catalog) : "Elsewhere"} <span className="muted">{members.length}</span>
              </h4>
              <ul className="review-list">{members.map(row)}</ul>
            </div>
          ))}
        </section>
      ) : null}

      {tidy.length ? (
        <details className="tidy">
          <summary>
            Tidy up while you are here <span className="muted">({tidy.length} entr{tidy.length === 1 ? "y" : "ies"} to check)</span>
          </summary>
          <p className="muted small">
            Entries in the same topics that are stale or disputed. Archive the ones this batch makes redundant; Undo brings them
            back.
          </p>
          <ul className="tidy-list">
            {tidy.map((entry) => (
              <li key={entry.id}>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={archive.has(entry.id)}
                    onChange={(event) => setArchive((s) => toggle(s, entry.id, event.target.checked))}
                  />
                  Archive “{entry.title}”
                </label>
                <span className="muted small"> {entry.why}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      <div className="decision-bar" role="group" aria-label={`Decide ${batch.title}`}>
        <div className="decision-summary">
          <strong>
            {chosen.length} of {proposals.length} selected
          </strong>
          {effect ? <span className="muted"> · Approving {effect}. You can undo it from History.</span> : null}
          <span className="select-helpers">
            <button type="button" className="link" onClick={() => setSelected(new Set(ready.map((p) => p.id)))}>
              Select the ready ones ({ready.length})
            </button>
            <button
              type="button"
              className="link"
              onClick={() =>
                setSelected(
                  new Set(proposals.filter((p) => !unsettled(analyses.get(p.id) ?? analysisOf(p), choices[p.id]).length).map((p) => p.id)),
                )
              }
            >
              All
            </button>
            <button type="button" className="link" onClick={() => setSelected(new Set())}>
              None
            </button>
          </span>
        </div>
        <div className="row">
          <button
            type="button"
            className="primary"
            disabled={decide.isPending || (!chosen.length && !archiving.length)}
            onClick={() =>
              run([
                ...chosen.flatMap(approval),
                ...archiving.map((id) => ({ action: "archive" as const, entry_id: id, reason: "Tidied up in review" })),
              ])
            }
          >
            {chosen.length || !archiving.length ? `Approve ${chosen.length}` : `Archive ${archiving.length}`}
          </button>
          <button type="button" className="danger" disabled={decide.isPending || !chosen.length} onClick={() => setRejecting(true)}>
            Reject {chosen.length}…
          </button>
          {decide.isPending ? (
            <span className="muted" aria-live="polite">
              Saving the decisions and an undo point…
            </span>
          ) : null}
        </div>
        {rejecting ? (
          <form
            className="row reject-form"
            onSubmit={(event) => {
              event.preventDefault();
              run(chosen.map((p) => ({ action: "reject", proposal_id: p.id, reason })));
              setRejecting(false);
            }}
          >
            <input
              aria-label="Why reject them"
              placeholder="Why, so the next pass knows"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
            <button type="submit" className="danger">
              Reject {chosen.length}
            </button>
            <button type="button" onClick={() => setRejecting(false)}>
              Cancel
            </button>
          </form>
        ) : null}
        <ErrorNote error={decide.error} />
      </div>
    </section>
  );
}

/** Entries worth a second look while reviewing: stale or disputed ones in the topics this batch
 * files into, unless approving already archives them. */
function tidyCandidates(
  batch: ReviewBatch,
  catalog: BrainCatalog | undefined,
  archived: Set<string>,
): { id: string; title: string; why: string }[] {
  const topics = new Set(batch.topics.map((t) => t.route_key));
  return (catalog?.entries ?? [])
    .filter((entry) => topics.has(entry.topic) && needsAttention(entry) && !archived.has(entry.id))
    .map((entry) => ({
      id: entry.id,
      title: entry.title,
      why: entry.stale_reason ? `Stale: ${entry.stale_reason}.` : "Marked disputed.",
    }));
}

export { titleOf };
