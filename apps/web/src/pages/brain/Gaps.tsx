// Gaps: requests the Brain served poorly. Either nothing matched, or the AI found an entry by
// searching that the packet should have brought (routing missed it: the entry lacks the words
// people ask with). Each one can be taught, fixed, or dismissed.

import { type FormEvent, useState } from "react";
import { Link } from "react-router";

import { useBrainDecisions, useBrainGaps, useDismissGap, useProposeEntry } from "../../api/hooks";
import type { BrainGap } from "../../api/types";
import { Empty, ErrorNote, Field, Loading } from "../../components/ui";
import { when } from "../../lib/format";
import { entryUrl } from "./shared";

export function GapsPage() {
  const { data: gaps, isLoading, error } = useBrainGaps(30);
  if (isLoading) return <Loading />;
  if (!gaps) return <ErrorNote error={error} />;
  const searched = gaps.filter((g) => g.kind === "searched");
  const nothing = gaps.filter((g) => g.kind === "nothing");
  return (
    <div className="gaps">
      <p className="section-lede">
        What the Brain could not serve well in the last 30 days. A request that found nothing may be worth teaching it; an entry
        the AI had to look for itself needs the words people ask with in its title or summary. Dismiss what does not matter.
      </p>
      {!gaps.length ? <Empty why="No gaps in the last 30 days: every request found what it needed, or asked for nothing the Brain should know." /> : null}
      {searched.length ? (
        <section className="section">
          <header className="section-head">
            <h2>Found by searching ({searched.length})</h2>
          </header>
          <ul className="gap-list">
            {searched.map((gap) => (
              <Gap key={gap.key} gap={gap} />
            ))}
          </ul>
        </section>
      ) : null}
      {nothing.length ? (
        <section className="section">
          <header className="section-head">
            <h2>Nothing matched ({nothing.length})</h2>
          </header>
          <ul className="gap-list">
            {nothing.map((gap) => (
              <Gap key={gap.key} gap={gap} />
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function Gap({ gap }: { gap: BrainGap }) {
  const dismiss = useDismissGap();
  const decide = useBrainDecisions();
  const [teaching, setTeaching] = useState(false);
  const [asked, setAsked] = useState(false);
  return (
    <li className="card gap">
      <p>
        Asked <q>{gap.request || "(no words)"}</q> <span className="muted small">{when(gap.at)}</span>
      </p>
      {gap.kind === "searched" && gap.entry ? (
        <p>
          The AI had to find <Link to={entryUrl(gap.entry)}>{gap.entry_title ?? gap.entry}</Link> itself: its title or summary
          lacks these words.
        </p>
      ) : (
        <p className="muted">
          Nothing matched.
          {gap.close.length ? (
            <>
              {" "}
              Closest: {gap.close.map((c, index) => (
                <span key={c.id}>
                  {index ? ", " : ""}
                  <Link to={entryUrl(c.id)}>{c.title}</Link>
                </span>
              ))}
              .
            </>
          ) : null}
        </p>
      )}
      <div className="row wrap">
        {gap.kind === "searched" && gap.entry ? (
          asked ? (
            <span className="muted small">Marked as needing an update, with why. It shows on the entry.</span>
          ) : (
            <>
              <Link className="button" to={entryUrl(gap.entry)}>
                Fix its summary
              </Link>
              <button
                type="button"
                disabled={decide.isPending}
                onClick={() =>
                  decide.mutate(
                    {
                      decisions: [
                        {
                          action: "mark",
                          entry_id: gap.entry ?? "",
                          state: "stale",
                          reason: `Add the words people ask with to its title or summary: “${gap.request}”`,
                        },
                      ],
                    },
                    { onSuccess: () => setAsked(true) },
                  )
                }
              >
                Needs an update
              </button>
            </>
          )
        ) : (
          <button type="button" onClick={() => setTeaching(!teaching)}>
            Teach it
          </button>
        )}
        <button type="button" className="link" disabled={dismiss.isPending} onClick={() => dismiss.mutate(gap.key)}>
          Dismiss
        </button>
      </div>
      <ErrorNote error={decide.error ?? dismiss.error} />
      {teaching ? <Teach request={gap.request} onDone={() => setTeaching(false)} /> : null}
    </li>
  );
}

/** Propose an entry that answers a request; it waits in Review like every proposal. */
function Teach({ request, onDone }: { request: string; onDone: () => void }) {
  const propose = useProposeEntry();
  const [title, setTitle] = useState("");
  const [statement, setStatement] = useState("");
  const [sent, setSent] = useState(false);

  function submit(event: FormEvent) {
    event.preventDefault();
    propose.mutate(
      { title: title.trim(), statement: statement.trim(), kind: "fact", evidence: `Asked: ${request}` },
      { onSuccess: () => setSent(true) },
    );
  }

  if (sent) {
    return (
      <p className="small">
        Proposed. It waits in <Link to="/review">Review</Link> for your approval.{" "}
        <button type="button" className="link" onClick={onDone}>
          Close
        </button>
      </p>
    );
  }
  return (
    <form className="stack" onSubmit={submit} aria-label="Teach the Brain">
      <Field label="Title" hint="What the entry is for, in a few words.">
        <input value={title} onChange={(event) => setTitle(event.target.value)} required />
      </Field>
      <Field label="What it should say">
        <textarea rows={4} value={statement} onChange={(event) => setStatement(event.target.value)} required />
      </Field>
      <div className="row">
        <button type="submit" className="primary" disabled={propose.isPending}>
          Propose it
        </button>
        <button type="button" onClick={onDone}>
          Cancel
        </button>
      </div>
      <ErrorNote error={propose.error} />
    </form>
  );
}
