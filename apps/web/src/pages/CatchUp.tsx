// Catch up: what needs you, as a plan rather than a pile. After time away, a recap comes first
// (what went in on its own, what moved, what your AI could not answer). Then one card at a
// time: decisions with a recommendation and its reason, groups to keep with one tap, a small
// weekly dose of upkeep, and offers to decide once. Keys: Enter takes the recommendation, 1 to
// 5 pick an action, L is later. On a touch screen, swipe right for the recommendation and left
// for later. Everything is undoable; "Review everything" stays one click away.

import { ArrowLeft, Check, ListChecks } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router";

import {
  useBrainDecisions,
  useBrainUndo,
  useBringLegacyIn,
  useCatchUp,
  useCatchUpSeen,
  useCreateBrainProject,
  useMerge,
  useSetAside,
  useSetBrainPolicies,
} from "../api/hooks";
import type { BrainDecision, CardAction, CatchUpPlan, JudgmentCard, LegacyOffer, Nudge, Offer, QuickGroup, Serves, UpkeepCard, WentIn } from "../api/types";
import { type Item, minutes, queueOf } from "../lib/catchup";
import { Compare } from "../components/Diff";
import { ErrorNote, Loading } from "../components/ui";
import { onDay, plural, when } from "../lib/format";
import { entryUrl } from "./brain/shared";

/** What the person did with each card, for the finish. */
interface Done {
  key: string;
  what: string;
  checkpoint?: string | null;
}

export function CatchUpPage() {
  const { data: plan, isLoading, error } = useCatchUp();
  const [stage, setStage] = useState<"recap" | "start" | "run" | "finish">("start");
  const [queue, setQueue] = useState<Item[]>([]);
  const [done, setDone] = useState<Done[]>([]);
  const seen = useCatchUpSeen();
  const recapShown = useRef(false);

  useEffect(() => {
    if (plan && plan.recap_first && !recapShown.current) {
      recapShown.current = true;
      setStage("recap");
    }
  }, [plan]);

  if (isLoading) return <Loading />;
  if (!plan) return <ErrorNote error={error} />;

  if (stage === "recap") return <RecapScreen plan={plan} onNext={() => setStage("start")} />;
  if (stage === "run") {
    return (
      <Run
        queue={queue}
        onDone={(record) => setDone((current) => [...current, record])}
        onFinish={() => {
          seen.mutate();
          setStage("finish");
        }}
      />
    );
  }
  if (stage === "finish") return <Finish plan={plan} done={done} />;
  return (
    <StartScreen
      plan={plan}
      onStart={() => {
        setQueue(queueOf(plan));
        setDone([]);
        setStage("run");
      }}
      onRecap={() => setStage("recap")}
      onSeen={() => seen.mutate()}
    />
  );
}

// ---------------------------------------------------------------- start, recap, finish

function StartScreen({ plan, onStart, onRecap, onSeen }: { plan: CatchUpPlan; onStart: () => void; onRecap: () => void; onSeen: () => void }) {
  const checkIns = plan.counts.upkeep + plan.counts.offers + plan.counts.legacy + plan.nudges.length;
  return (
    <div className="page catch-up">
      <p className="eyebrow">Catch up</p>
      {plan.caught_up && !plan.nudges.length ? (
        <>
          <h1>All caught up</h1>
          <p className="lede">Nothing needs you. What went in on its own is listed below, and every change can be undone.</p>
          <Handled items={plan.handled} total={plan.counts.handled} />
          <div className="row">
            <Link className="button" to="/">
              Back to Home
            </Link>
            <button type="button" className="link" onClick={onRecap}>
              What happened since {onDay(plan.since)}
            </button>
          </div>
        </>
      ) : (
        <>
          <h1>{minutes(plan.seconds).replace(/^a/, "A")}</h1>
          <p className="lede">A plan, not a pile: the few things that need you, one at a time, each with what I recommend.</p>
          <ul className="catch-up-counts">
            {plan.counts.judgment ? (
              <li>
                <strong>{plan.counts.judgment}</strong> {plan.counts.judgment === 1 ? "decision" : "decisions"}
              </li>
            ) : null}
            {plan.counts.quick_items ? (
              <li>
                <strong>{plan.counts.quick_items}</strong> to keep in {plural(plan.counts.quick, "quick group")}
              </li>
            ) : null}
            {checkIns ? (
              <li>
                <strong>{checkIns}</strong> {checkIns === 1 ? "check-in" : "check-ins"}
              </li>
            ) : null}
          </ul>
          <div className="row">
            <button type="button" className="primary big" onClick={onStart} autoFocus>
              Start
            </button>
            <button type="button" className="link" onClick={onRecap}>
              What happened since {onDay(plan.since)}
            </button>
            <Link to="/review" className="link">
              <ListChecks className="button-icon" aria-hidden="true" />
              Review everything
            </Link>
          </div>
          <Handled items={plan.handled} total={plan.counts.handled} />
        </>
      )}
      <p className="muted small">
        {plan.counts.snoozed ? `${plural(plan.counts.snoozed, "item")} set for later. ` : ""}
        <button type="button" className="link small" onClick={onSeen}>
          Mark as caught up
        </button>
      </p>
    </div>
  );
}

/** What went in on its own: visible, each one undoable. */
function Handled({ items, total }: { items: WentIn[]; total: number }) {
  const undo = useBrainUndo();
  const [undone, setUndone] = useState<string[]>([]);
  if (!total) return null;
  return (
    <details className="handled">
      <summary>
        Handled for you: {plural(total, "thing")} went in on its own
      </summary>
      <ul className="list compact-list">
        {items.map((item) => (
          <li key={`${item.at}:${item.id}`}>
            {item.live ? <Link to={entryUrl(item.id)}>{item.title}</Link> : item.title}
            <span className="muted small">
              {" "}
              · {item.source} · {when(item.at)}
            </span>
            {item.checkpoint && !undone.includes(item.checkpoint) ? (
              <button
                type="button"
                className="link small"
                disabled={undo.isPending}
                onClick={() => undo.mutate(item.checkpoint!, { onSuccess: () => setUndone((u) => [...u, item.checkpoint!]) })}
              >
                Take back
              </button>
            ) : item.checkpoint ? (
              <span className="muted small"> · taken back</span>
            ) : null}
          </li>
        ))}
      </ul>
      <ErrorNote error={undo.error} />
    </details>
  );
}

export function RecapScreen({ plan, onNext }: { plan: CatchUpPlan; onNext: () => void }) {
  const recap = plan.recap;
  const sources = Object.entries(recap.came_in.by_source).filter(([, n]) => n > 0);
  return (
    <div className="page catch-up recap">
      <p className="eyebrow">While you were away{plan.away_days ? `: ${plural(plan.away_days, "day")}` : ""}</p>
      <h1>Here is what happened since {onDay(recap.since)}</h1>
      <div className="recap-grid">
        <section className="card">
          <h2>Went in on its own</h2>
          <p className="stat-big">{recap.went_in_total}</p>
          <ul className="list compact-list">
            {recap.went_in.slice(0, 5).map((item) => (
              <li key={`${item.at}:${item.id}`}>
                {item.title} <span className="muted small">· {item.source}</span>
              </li>
            ))}
          </ul>
        </section>
        <section className="card">
          <h2>Came in</h2>
          <p className="stat-big">{recap.came_in.total}</p>
          <p className="muted small">{sources.length ? sources.map(([name, n]) => `${n} from ${SOURCE_WORDS[name] ?? name}`).join(", ") : "Nothing new came in."}</p>
          {recap.came_in.waiting ? <p className="small">{plural(recap.came_in.waiting, "suggestion")} wait for you.</p> : null}
        </section>
        <section className="card">
          <h2>Projects that moved</h2>
          {recap.projects.length ? (
            <ul className="list compact-list">
              {recap.projects.map((p) => (
                <li key={p.id}>
                  <Link to={`/projects/${encodeURIComponent(p.id)}`}>{p.title}</Link>
                  {p.last ? <span className="muted small"> · {p.last.summary}</span> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted small">No project moved.</p>
          )}
        </section>
        <section className="card">
          <h2>Questions it couldn't answer</h2>
          <p className="stat-big">{recap.gaps}</p>
          {recap.gaps ? (
            <Link to="/brain/questions" className="small">
              Teach it the answers
            </Link>
          ) : (
            <p className="muted small">It had something for every request.</p>
          )}
        </section>
      </div>
      <button type="button" className="primary big" onClick={onNext} autoFocus>
        {plan.caught_up ? "Done" : `Catch up, ${minutes(plan.seconds)}`}
      </button>
    </div>
  );
}

const SOURCE_WORDS: Record<string, string> = {
  chat: "your AI's chats",
  files: "files",
  you: "you",
  ai_work: "the app's AI work",
  moved_in: "moving in",
  other: "elsewhere",
};

function Finish({ plan, done }: { plan: CatchUpPlan; done: Done[] }) {
  const navigate = useNavigate();
  const kept = done.filter((d) => d.checkpoint);
  return (
    <div className="page catch-up finish" role="status">
      <p className="eyebrow">Catch up</p>
      <h1>
        <Check className="title-icon" aria-hidden="true" /> All caught up
      </h1>
      {done.length ? (
        <>
          <p className="lede">
            {plural(done.length, "thing")} settled. {kept.length ? "Each change has an undo point in Activity, Changes." : ""}
          </p>
          <ul className="list compact-list">
            {done.map((d) => (
              <li key={d.key}>{d.what}</li>
            ))}
          </ul>
        </>
      ) : (
        <p className="lede">Nothing changed this time.</p>
      )}
      <p className="muted">From now on, every AI you connect gets what you kept, and nothing you turned down.</p>
      {plan.health.score !== null ? (
        <p className="small">
          Brain health {plan.health.score}: {plan.health.factors.map((f) => `${f.label.toLowerCase()} ${Math.round(f.score * 100)}%`).join(", ")}.
        </p>
      ) : null}
      <div className="row">
        <button type="button" className="primary" onClick={() => navigate("/")}>
          Back to Home
        </button>
        <Link to="/activity?tab=changes" className="button">
          See the changes
        </Link>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- the run, one card at a time

function Run({ queue, onDone, onFinish }: { queue: Item[]; onDone: (d: Done) => void; onFinish: () => void }) {
  const [index, setIndex] = useState(0);
  const item = queue[index];
  const next = useCallback(() => {
    if (index + 1 >= queue.length) onFinish();
    else setIndex(index + 1);
  }, [index, queue.length, onFinish]);
  useEffect(() => {
    if (!item) onFinish();
  }, [item, onFinish]);
  if (!item) return <Loading />;
  return (
    <div className="page catch-up run">
      <div className="run-head">
        <Link to="/catch-up" reloadDocument className="link small">
          <ArrowLeft className="button-icon" aria-hidden="true" /> Stop for now
        </Link>
        <span className="muted small" aria-live="polite">
          {index + 1} of {queue.length}
        </span>
      </div>
      <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={queue.length} aria-valuenow={index}>
        <span style={{ width: `${(100 * index) / queue.length}%` }} />
      </div>
      <ItemCard key={item.key} item={item} onDone={(what, checkpoint) => {
        onDone({ key: item.key, what, checkpoint });
        next();
      }} onSkip={next} />
    </div>
  );
}

function ItemCard({ item, onDone, onSkip }: { item: Item; onDone: (what: string, checkpoint?: string | null) => void; onSkip: () => void }) {
  switch (item.kind) {
    case "legacy":
      return <LegacyCard offer={item.offer} onDone={onDone} onSkip={onSkip} />;
    case "judgment":
      return <Judgment card={item.card} onDone={onDone} onSkip={onSkip} />;
    case "quick":
      return <Quick group={item.group} onDone={onDone} onSkip={onSkip} />;
    case "upkeep":
      return <Upkeep card={item.card} onDone={onDone} onSkip={onSkip} />;
    case "offer":
      return <OfferCard offer={item.offer} onDone={onDone} onSkip={onSkip} />;
    case "nudge":
      return <NudgeCard nudge={item.nudge} onDone={onDone} onSkip={onSkip} />;
  }
}

interface Choice {
  id: string;
  label: string;
  run: () => void;
  primary?: boolean;
}

/** A card's frame: what it is, what I recommend and why, and the choices; keys and swipes
 * pick them. */
function CardFrame({
  tag,
  title,
  serves,
  children,
  recommend,
  choices,
  busy,
  error,
}: {
  tag: string;
  title: ReactNode;
  serves?: Serves;
  children?: ReactNode;
  recommend?: { label: string; reason: string } | null;
  choices: Choice[];
  busy: boolean;
  error?: unknown;
}) {
  const primary = choices.find((c) => c.primary) ?? choices[0];
  const later = choices.find((c) => c.id === "later");
  const start = useRef<number | null>(null);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (busy || (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) || target?.isContentEditable) return;
      if (event.key === "Enter" && target?.tagName !== "BUTTON" && target?.tagName !== "A") {
        event.preventDefault();
        primary?.run();
      } else if (/^[1-9]$/.test(event.key)) {
        const choice = choices[Number(event.key) - 1];
        if (choice) {
          event.preventDefault();
          choice.run();
        }
      } else if (event.key.toLowerCase() === "l" && later) {
        event.preventDefault();
        later.run();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, choices, later, primary]);
  return (
    <article
      className="catch-card"
      aria-busy={busy}
      onPointerDown={(event) => {
        if (event.pointerType === "touch") start.current = event.clientX;
      }}
      onPointerUp={(event) => {
        if (start.current === null || busy) return;
        const dx = event.clientX - start.current;
        start.current = null;
        if (dx > 80) primary?.run();
        else if (dx < -80) later?.run();
      }}
    >
      <p className="catch-tag">{tag}</p>
      <h2>{title}</h2>
      {serves && (serves.goal || serves.project) ? (
        <p className="serves small">
          {serves.project ? (
            <span className="chip">For {serves.project.title}</span>
          ) : null}
          {serves.goal ? <span className="chip">Serves: {serves.goal}</span> : null}
        </p>
      ) : null}
      {children}
      {recommend ? (
        <p className="recommend">
          <strong>I recommend: {recommend.label}.</strong> {recommend.reason}
        </p>
      ) : null}
      <div className="row catch-actions">
        {choices.map((choice, i) => (
          <button
            key={choice.id}
            type="button"
            className={choice === primary ? "primary" : choice.id === "later" ? "link" : undefined}
            disabled={busy}
            onClick={choice.run}
            title={`Key ${i + 1}`}
          >
            {choice.label}
          </button>
        ))}
      </div>
      <ErrorNote error={error} />
      <p className="muted small keys-hint">Enter takes the recommendation · 1 to {choices.length} pick · L later · swipe on a phone</p>
    </article>
  );
}

const ACTION_LABELS: Record<CardAction, string> = {
  keep_mine: "Keep my note",
  use_this: "Use this instead",
  keep_both: "Keep both",
  edit: "Edit, then keep",
  later: "Later",
  keep_one: "Keep this one",
  not_this: "Not this",
  keep: "Keep it",
  review: "Read it in full",
  compare: "Compare",
};

/** Decisions from this page carry the card they came from, so upkeep counts per week. */
function useDecide(key: string) {
  const decide = useBrainDecisions();
  const run = (decisions: BrainDecision[], label: string, onDone: (what: string, checkpoint?: string | null) => void, what: string) =>
    decide.mutate(
      { decisions, label, source: { catch_up: key } },
      {
        onSuccess: (outcome) => {
          const failed = outcome.results.filter((r) => !r.ok);
          if (failed.length && failed.length === outcome.results.length) return;
          onDone(what, outcome.checkpoint?.id ?? null);
        },
      },
    );
  return { decide, run };
}

function Judgment({ card, onDone, onSkip }: { card: JudgmentCard; onDone: (what: string, checkpoint?: string | null) => void; onSkip: () => void }) {
  const { decide, run } = useDecide(card.key);
  const aside = useSetAside();
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(card.body);
  const [comparing, setComparing] = useState(false);
  const id = card.proposal_id;
  const others = card.duplicates.filter((d) => d !== id);
  const act = (action: CardAction) => {
    switch (action) {
      case "keep_mine":
        return run([{ action: "reject", proposal_id: id, reason: "Kept my note" }], `Kept my note over “${card.title}”`, onDone, `Kept your note over “${card.title}”`);
      case "use_this":
        return run(
          [{ action: "approve", proposal_id: id, replaces: card.with?.id ? [card.with.id] : undefined }],
          `Used “${card.title}” instead`,
          onDone,
          `Used “${card.title}” instead${card.with ? ` of “${card.with.title}”` : ""}`,
        );
      case "keep_both":
      case "keep":
        return run([{ action: "approve", proposal_id: id }], `Kept “${card.title}”`, onDone, `Kept “${card.title}”`);
      case "keep_one":
        return run(
          [{ action: "approve", proposal_id: id }, ...others.map((other) => ({ action: "reject" as const, proposal_id: other, reason: "Said twice" }))],
          `Kept one “${card.title}”`,
          onDone,
          `Kept one “${card.title}”`,
        );
      case "not_this":
        return run([{ action: "reject", proposal_id: id, reason: "Not this" }], `Turned down “${card.title}”`, onDone, `Turned down “${card.title}”`);
      case "edit":
        return setEditing(true);
      case "compare":
        return setComparing((c) => !c);
      case "review":
        return navigate(`/review?proposal=${encodeURIComponent(id)}`);
      case "later":
        return aside.mutate({ key: card.key, later: true }, { onSuccess: onSkip });
    }
  };
  const ordered = [card.recommend.action as CardAction, ...card.actions.filter((a) => a !== card.recommend.action)].filter((a) =>
    card.actions.includes(a),
  );
  const choices: Choice[] = ordered.map((action) => ({
    id: action,
    label: ACTION_LABELS[action] ?? action,
    run: () => act(action),
    primary: action === card.recommend.action,
  }));
  return (
    <CardFrame
      tag={card.tag}
      title={card.title}
      serves={card}
      recommend={{ label: (ACTION_LABELS[card.recommend.action as CardAction] ?? card.recommend.action).toLowerCase(), reason: card.recommend.reason }}
      choices={choices}
      busy={decide.isPending || aside.isPending}
      error={decide.error ?? aside.error}
    >
      <p className="muted small">
        From {card.source}
        {card.at ? `, ${when(card.at)}` : ""}. {card.why}
      </p>
      {editing ? (
        <div className="stack-tight">
          <label className="field">
            <span className="field-label">Your words</span>
            <textarea rows={5} value={text} onChange={(event) => setText(event.target.value)} />
          </label>
          <div className="row">
            <button
              type="button"
              className="primary"
              disabled={!text.trim() || decide.isPending}
              onClick={() => run([{ action: "approve", proposal_id: id, body: text }], `Kept “${card.title}”, edited`, onDone, `Kept “${card.title}”, in your words`)}
            >
              Keep my version
            </button>
            <button type="button" className="link" onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        </div>
      ) : card.with && (comparing || card.type === "conflict" || card.type === "close") ? (
        <Compare
          before={{ label: "Your note", title: card.with.title, body: card.with.body }}
          after={{ label: "The suggestion", title: card.title, body: card.body }}
          marks={card.type !== "conflict"}
        />
      ) : (
        <blockquote className="suggestion-text">{card.body || card.summary}</blockquote>
      )}
    </CardFrame>
  );
}

function Quick({ group, onDone, onSkip }: { group: QuickGroup; onDone: (what: string, checkpoint?: string | null) => void; onSkip: () => void }) {
  const { decide, run } = useDecide(group.key);
  const aside = useSetAside();
  const [left, setLeft] = useState<string[]>([]);
  const kept = group.items.filter((i) => !left.includes(i.id));
  const choices: Choice[] = [
    {
      id: "keep",
      label: left.length ? `Keep ${kept.length}, not ${left.length}` : `Keep all ${group.count}`,
      primary: true,
      run: () =>
        run(
          [
            ...kept.map((i) => ({ action: "approve" as const, proposal_id: i.id })),
            ...left.map((id) => ({ action: "reject" as const, proposal_id: id, reason: "Not this" })),
          ],
          `Kept ${plural(kept.length, "suggestion")}: ${group.title}`,
          onDone,
          `Kept ${group.title.toLowerCase()}${left.length ? ` (not ${left.length})` : ""}`,
        ),
    },
    { id: "later", label: "Later", run: () => aside.mutate({ key: group.key, later: true }, { onSuccess: onSkip }) },
  ];
  return (
    <CardFrame
      tag={group.shapes ? "Quick yes · changes how every AI works" : "Quick yes"}
      title={`${group.title}: ${group.detail}`}
      recommend={{ label: "keep them", reason: `Nothing in your Brain disagrees with them. From ${group.sources.join(", ")}.` }}
      choices={choices}
      busy={decide.isPending || aside.isPending}
      error={decide.error ?? aside.error}
    >
      <ul className="list quick-items">
        {group.items.map((item) => (
          <li key={item.id}>
            <label className="check">
              <input
                type="checkbox"
                checked={!left.includes(item.id)}
                onChange={(event) => setLeft((current) => (event.target.checked ? current.filter((x) => x !== item.id) : [...current, item.id]))}
              />{" "}
              <strong>{item.title}</strong>
              {item.summary ? <span className="muted small"> · {item.summary}</span> : null}
              {item.project ? <span className="chip small">For {item.project.title}</span> : null}
              {item.goal ? <span className="chip small">Serves: {item.goal}</span> : null}
            </label>
          </li>
        ))}
      </ul>
    </CardFrame>
  );
}

function Upkeep({ card, onDone, onSkip }: { card: UpkeepCard; onDone: (what: string, checkpoint?: string | null) => void; onSkip: () => void }) {
  const { decide, run } = useDecide(card.key);
  const aside = useSetAside();
  const merge = useMerge();
  const later = { id: "later", label: "Later", run: () => aside.mutate({ key: card.key, later: true }, { onSuccess: onSkip }) };
  const busy = decide.isPending || aside.isPending || merge.isPending;
  const error = decide.error ?? aside.error ?? merge.error;
  if (card.type === "recheck") {
    return (
      <CardFrame
        tag="Still true?"
        title={card.title}
        recommend={null}
        busy={busy}
        error={error}
        choices={[
          { id: "yes", label: "Yes, still true", primary: true, run: () => run([{ action: "verify", entry_id: card.id }], `Still true: ${card.title}`, onDone, `Confirmed “${card.title}”`) },
          {
            id: "no",
            label: "Not anymore",
            run: () => run([{ action: "archive", entry_id: card.id, reason: "No longer true" }], `Retired ${card.title}`, onDone, `Retired “${card.title}”`),
          },
          { id: "edit", label: "Change it", run: () => window.open(entryUrl(card.id), "_self") },
          later,
        ]}
      >
        <p>{card.summary}</p>
        <p className="muted small">
          {card.why}
          {card.uses ? ` · used in ${plural(card.uses, "chat")} this month` : ""}
        </p>
      </CardFrame>
    );
  }
  if (card.type === "duplicate") {
    const keepA = card.recommend.action === `keep:${card.a.id}`;
    const [keep, drop] = keepA ? [card.a, card.b] : [card.b, card.a];
    return (
      <CardFrame
        tag="Merge these two?"
        title="Two notes that say much the same"
        recommend={{ label: `keep “${keep.title}”`, reason: card.recommend.reason }}
        busy={busy}
        error={error}
        choices={[
          {
            id: "keep",
            label: `Keep “${keep.title}”`,
            primary: true,
            run: () => run([{ action: "archive", entry_id: drop.id, reason: `Same as ${keep.id}` }], `Kept ${keep.title}`, onDone, `Kept “${keep.title}”, retired its twin`),
          },
          {
            id: "other",
            label: `Keep “${drop.title}”`,
            run: () => run([{ action: "archive", entry_id: keep.id, reason: `Same as ${drop.id}` }], `Kept ${drop.title}`, onDone, `Kept “${drop.title}”, retired its twin`),
          },
          {
            id: "merge",
            label: "Write them as one",
            run: () => merge.mutate({ keep_id: keep.id, other_id: drop.id }, { onSuccess: () => onDone(`Asked AI to merge “${keep.title}” and “${drop.title}”: it waits in Review`) }),
          },
          { id: "different", label: "They're different", run: () => aside.mutate({ key: card.key }, { onSuccess: () => onDone("Kept two notes that only look alike") }) },
          later,
        ]}
      >
        <div className="compare twins">
          {[card.a, card.b].map((side) => (
            <div key={side.id} className="compare-side">
              <p className="compare-label">
                <Link to={entryUrl(side.id)}>{side.title}</Link>
              </p>
              <p className="small">{side.summary}</p>
              <p className="muted small">used in {plural(side.uses, "chat")} this month</p>
            </div>
          ))}
        </div>
      </CardFrame>
    );
  }
  if (card.type === "musthold") {
    const triggers = card.triggers.join(", ");
    return (
      <CardFrame
        tag="Must hold?"
        title={card.title}
        recommend={{ label: "make it a must-hold", reason: card.recommend.reason }}
        busy={busy}
        error={error}
        choices={[
          {
            id: "yes",
            label: "Make it a must-hold",
            primary: true,
            run: () =>
              run(
                [{ action: "update", entry_id: card.id, fields: { load: "domain", applies_to: card.area, triggers } }],
                `Must hold: ${card.title}`,
                onDone,
                `“${card.title}” now goes into every brief about ${card.area_label}`,
              ),
          },
          { id: "edit", label: "Choose when it applies", run: () => window.open(entryUrl(card.id), "_self") },
          { id: "no", label: "Leave it as it is", run: () => aside.mutate({ key: card.key }, { onSuccess: () => onDone(`Left “${card.title}” as it is`) }) },
          later,
        ]}
      >
        <p>{card.summary}</p>
        {triggers ? <p className="muted small">It would come in when a request mentions: {triggers}. You can change these words on the note.</p> : null}
      </CardFrame>
    );
  }
  if (card.type === "tidy") {
    return (
      <CardFrame
        tag="Needs tidying"
        title={card.title}
        recommend={null}
        busy={busy}
        error={error}
        choices={[
          { id: "open", label: "Open it", primary: true, run: () => window.open(entryUrl(card.id), "_self") },
          { id: "fine", label: "It's fine as is", run: () => aside.mutate({ key: card.key }, { onSuccess: () => onDone(`Left “${card.title}” as it is`) }) },
          later,
        ]}
      >
        <p className="muted">{card.why}</p>
      </CardFrame>
    );
  }
  return <Unused card={card} onDone={onDone} later={later} />;
}

function Unused({
  card,
  onDone,
  later,
}: {
  card: Extract<UpkeepCard, { type: "unused" }>;
  onDone: (what: string, checkpoint?: string | null) => void;
  later: Choice;
}) {
  const { decide, run } = useDecide(card.key);
  const aside = useSetAside();
  const [keep, setKeep] = useState<string[]>([]);
  const retire = card.items.filter((i) => !keep.includes(i.id));
  return (
    <CardFrame
      tag="Tidy up"
      title={`${plural(card.count, "note")} no AI used in ${card.days} days`}
      recommend={{ label: "archive them", reason: "They are out of every AI's way, and any of them comes back with one click." }}
      busy={decide.isPending || aside.isPending}
      error={decide.error ?? aside.error}
      choices={[
        {
          id: "archive",
          label: `Archive ${retire.length}`,
          primary: true,
          run: () =>
            run(
              retire.map((i) => ({ action: "archive" as const, entry_id: i.id, reason: `No AI used it in ${card.days} days` })),
              `Archived ${plural(retire.length, "unused note")}`,
              onDone,
              `Archived ${plural(retire.length, "unused note")}`,
            ),
        },
        { id: "keep", label: "Keep them", run: () => aside.mutate({ key: card.key }, { onSuccess: () => onDone("Kept the unused notes for now") }) },
        later,
      ]}
    >
      <ul className="list quick-items">
        {card.items.map((item) => (
          <li key={item.id}>
            <label className="check">
              <input
                type="checkbox"
                checked={!keep.includes(item.id)}
                onChange={(event) => setKeep((current) => (event.target.checked ? current.filter((x) => x !== item.id) : [...current, item.id]))}
              />{" "}
              {item.title} <span className="muted small">· {item.topic}</span>
            </label>
          </li>
        ))}
      </ul>
    </CardFrame>
  );
}

function OfferCard({ offer, onDone, onSkip }: { offer: Offer; onDone: (what: string) => void; onSkip: () => void }) {
  const policies = useSetBrainPolicies();
  const aside = useSetAside();
  return (
    <CardFrame
      tag="Decide once"
      title={offer.title}
      recommend={offer.shapes ? null : { label: "yes", reason: `You kept the last ${offer.kept} without a no.` }}
      busy={policies.isPending || aside.isPending}
      error={policies.error ?? aside.error}
      choices={[
        {
          id: "yes",
          label: "Yes, let them in",
          primary: !offer.shapes,
          run: () =>
            policies.mutate(
              { capture: { [offer.type]: { [offer.origin]: "apply" } } } as never,
              { onSuccess: () => onDone(offer.title.replace(/\?$/, ": yes")) },
            ),
        },
        { id: "no", label: "No, keep asking me", primary: offer.shapes, run: () => aside.mutate({ key: offer.key }, { onSuccess: () => onDone(offer.title.replace(/\?$/, ": no")) }) },
        { id: "later", label: "Later", run: () => aside.mutate({ key: offer.key, later: true }, { onSuccess: onSkip }) },
      ]}
    >
      <p>{offer.detail}</p>
      {offer.shapes ? <p className="warning small">These change how every AI works. Most people keep a yes for each.</p> : null}
    </CardFrame>
  );
}

function LegacyCard({ offer, onDone, onSkip }: { offer: LegacyOffer; onDone: (what: string) => void; onSkip: () => void }) {
  const bring = useBringLegacyIn();
  const aside = useSetAside();
  return (
    <CardFrame
      tag={`Once · ${minutes(offer.seconds)}`}
      title={offer.title}
      recommend={{ label: "bring it in", reason: "No AI app can see it where it is now." }}
      busy={bring.isPending || aside.isPending}
      error={bring.error ?? aside.error}
      choices={[
        {
          id: "bring",
          label: "Bring it in",
          primary: true,
          run: () =>
            bring.mutate(undefined, {
              onSuccess: (report) =>
                onDone(
                  `Brought in the earlier workspace: ${plural(report.notes_proposed, "suggestion")} to review` +
                    (report.files_waiting ? `, ${plural(report.files_waiting, "file")} waiting` : "") +
                    (report.files_filed ? `, ${plural(report.files_filed, "file")} filed` : "") +
                    (report.projects_started.length ? `, ${plural(report.projects_started.length, "project")} started` : ""),
                ),
            }),
        },
        { id: "later", label: "Later", run: () => aside.mutate({ key: offer.key, later: true }, { onSuccess: onSkip }) },
        { id: "never", label: "Not this", run: () => aside.mutate({ key: offer.key }, { onSuccess: () => onDone("Left the earlier workspace where it is") }) },
      ]}
    >
      <p>{offer.detail}</p>
    </CardFrame>
  );
}

function NudgeCard({ nudge, onDone, onSkip }: { nudge: Nudge; onDone: (what: string) => void; onSkip: () => void }) {
  const start = useCreateBrainProject();
  const aside = useSetAside();
  const navigate = useNavigate();
  const no = { id: "no", label: "No", run: () => aside.mutate({ key: nudge.key }, { onSuccess: () => onDone(`Not now: ${nudge.title}`) }) };
  const later = { id: "later", label: "Later", run: () => aside.mutate({ key: nudge.key, later: true }, { onSuccess: onSkip }) };
  if (nudge.type === "start_project") {
    return (
      <CardFrame
        tag="Start a project?"
        title={nudge.title}
        recommend={null}
        busy={start.isPending || aside.isPending}
        error={start.error ?? aside.error}
        choices={[
          {
            id: "start",
            label: `Start “${nudge.name}”`,
            primary: true,
            run: () =>
              start.mutate(
                { name: nudge.name, summary: `${nudge.name}, started from “${nudge.capture.title}”.`, aliases: [] },
                { onSuccess: () => onDone(`Started the project “${nudge.name}”`) },
              ),
          },
          no,
          later,
        ]}
      >
        <p className="muted small">
          From <Link to={`/capture/${encodeURIComponent(nudge.capture.id)}`}>{nudge.capture.title}</Link>. Your AI then knows where it stands.
        </p>
      </CardFrame>
    );
  }
  return (
    <CardFrame
      tag="Add to your goals?"
      title={nudge.title}
      recommend={null}
      busy={aside.isPending}
      error={aside.error}
      choices={[{ id: "goals", label: "Open my goals", primary: true, run: () => navigate("/settings?tab=goals") }, no, later]}
    >
      <ul className="list compact-list small">
        {nudge.captures.map((c) => (
          <li key={c.id}>
            <Link to={`/capture/${encodeURIComponent(c.id)}`}>{c.title}</Link>
          </li>
        ))}
      </ul>
    </CardFrame>
  );
}
