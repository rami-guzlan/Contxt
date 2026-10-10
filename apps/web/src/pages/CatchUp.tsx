// Catch up: what needs you, as a plan rather than a pile. After time away, a recap comes first
// (what went in on its own, what moved, what your AI could not answer). Then one card at a
// time: decisions with a recommendation and its reason, groups to keep with one tap, a small
// weekly dose of upkeep, and offers to decide once. Keys: Enter takes the recommendation, 1 to
// 5 pick an action, L is later. On a touch screen, swipe right for the recommendation and left
// for later. Everything is undoable; "Review everything" stays one click away.
//
// A suggestion that changes a baseline (a rule, a must-hold, a note you confirmed or AIs use a
// lot) gets a card of its own: its choices open only after the two are compared, and revising
// the baseline takes a reason of a few words. Kept quickly, card after card, and the next card
// says so plainly. Each decision records how long its card was shown.

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
import type {
  BrainDecision,
  CardAction,
  CardBaseline,
  CatchUpPlan,
  JudgmentCard,
  LegacyOffer,
  ModelVerdict,
  Nudge,
  Offer,
  QuickGroup,
  ScheduledRevision,
  Serves,
  UpkeepCard,
  WentIn,
} from "../api/types";
import { type Item, minutes, queueOf } from "../lib/catchup";
import { Compare } from "../components/Diff";
import { GoalSteps, SlippedGoals } from "../components/goals/GoalsCatchUp";
import { LoopCatchUp } from "../components/loop/LoopCatchUp";
import { TasksCatchUp } from "../components/tasks/TasksCatchUp";
import { ErrorNote, Loading } from "../components/ui";
import { onDay, plural, when } from "../lib/format";
import { day, entryUrl } from "./brain/shared";

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
        pace={plan.pace ?? DEFAULT_PACE}
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
  const checks = plan.work ?? [];
  const cards = queueOf(plan).length;
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
            {checks.length ? (
              <li>
                <strong>{checks.length}</strong> {checks.length === 1 ? "check" : "checks"} in Work
              </li>
            ) : null}
            {plan.goals?.length ? (
              <li>
                <strong>{plan.goals.length}</strong> agent {plan.goals.length === 1 ? "goal" : "goals"} slipped
              </li>
            ) : null}
            {plan.loop?.length ? (
              <li>
                <strong>{plan.loop.length}</strong> {plan.loop.length === 1 ? "thing" : "things"} to keep true
              </li>
            ) : null}
          </ul>
          <WorkChecks items={checks} />
          <TasksCatchUp plan={plan} />
          <LoopCatchUp plan={plan} />
          <SlippedGoals items={plan.goals ?? []} />
          <GoalSteps groups={plan.goal_steps ?? []} />
          <div className="row">
            {cards ? (
              <button type="button" className="primary big" onClick={onStart} autoFocus>
                Start
              </button>
            ) : null}
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
      <Scheduled items={plan.scheduled ?? []} />
      <p className="muted small">
        {plan.counts.snoozed ? `${plural(plan.counts.snoozed, "item")} set for later. ` : ""}
        <button type="button" className="link small" onClick={onSeen}>
          Mark as caught up
        </button>
      </p>
    </div>
  );
}

/** Workflow runs waiting at a check: each opens where you go on, edit what came before, or stop. */
function WorkChecks({ items }: { items: NonNullable<CatchUpPlan["work"]> }) {
  if (!items.length) return null;
  return (
    <section className="stack-tight" aria-label="Waiting in Work">
      <h2 className="small-head">Waiting in Work</h2>
      <ul className="list compact-list">
        {items.map((item) => (
          <li key={item.run_id}>
            <Link to={`/work/workflows/${encodeURIComponent(item.workflow_id)}?run=${encodeURIComponent(item.run_id)}`}>{item.workflow}</Link>
            <span className="muted small">
              {" · "}
              {item.ask} · started {when(item.started_at)}
            </span>
          </li>
        ))}
      </ul>
    </section>
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

const DEFAULT_PACE = { cards: 5, seconds: 6 };

function Run({
  queue,
  pace,
  onDone,
  onFinish,
}: {
  queue: Item[];
  pace: { cards: number; seconds: number };
  onDone: (d: Done) => void;
  onFinish: () => void;
}) {
  const [index, setIndex] = useState(0);
  // When each recent judgment was kept in under `pace.seconds`: a run of them earns a plain word.
  const [fast, setFast] = useState<number[]>([]);
  const shownAt = useRef(Date.now());
  const item = queue[index];
  const next = useCallback(() => {
    if (index + 1 >= queue.length) onFinish();
    else setIndex(index + 1);
  }, [index, queue.length, onFinish]);
  useEffect(() => {
    shownAt.current = Date.now();
  }, [index]);
  useEffect(() => {
    if (!item) onFinish();
  }, [item, onFinish]);
  if (!item) return <Loading />;
  const now = Date.now();
  const recent = fast.filter((t) => now - t < 60_000).length;
  const paceNote = item.kind === "judgment" && recent >= pace.cards ? `You've kept ${recent} in a minute.` : null;
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
      <ItemCard
        key={item.key}
        item={item}
        paceNote={paceNote}
        onDone={(what, checkpoint) => {
          if (item.kind === "judgment") {
            const at = Date.now();
            const quick = (at - shownAt.current) / 1000 < pace.seconds;
            setFast((list) => (quick ? [...list.filter((t) => at - t < 60_000), at] : []));
          }
          onDone({ key: item.key, what, checkpoint });
          next();
        }}
        onSkip={next}
      />
    </div>
  );
}

function ItemCard({
  item,
  paceNote,
  onDone,
  onSkip,
}: {
  item: Item;
  paceNote?: string | null;
  onDone: (what: string, checkpoint?: string | null) => void;
  onSkip: () => void;
}) {
  switch (item.kind) {
    case "legacy":
      return <LegacyCard offer={item.offer} onDone={onDone} onSkip={onSkip} />;
    case "judgment":
      if (item.card.type === "baseline" && item.card.baseline)
        return <BaselineCard card={item.card} baseline={item.card.baseline} paceNote={paceNote} onDone={onDone} onSkip={onSkip} />;
      if (item.card.type === "went_in") return <WentInCard card={item.card} onDone={onDone} onSkip={onSkip} />;
      return <Judgment card={item.card} paceNote={paceNote} onDone={onDone} onSkip={onSkip} />;
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
  locked = false,
  error,
}: {
  tag: string;
  title: ReactNode;
  serves?: Serves;
  children?: ReactNode;
  recommend?: { label: string; reason: string } | null;
  choices: Choice[];
  busy: boolean;
  /** The choices wait for something first (comparing the two). */
  locked?: boolean;
  error?: unknown;
}) {
  const primary = choices.find((c) => c.primary) ?? choices[0];
  const later = choices.find((c) => c.id === "later");
  const start = useRef<number | null>(null);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (busy || locked || (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) || target?.isContentEditable) return;
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
  }, [busy, locked, choices, later, primary]);
  return (
    <article
      className="catch-card"
      aria-busy={busy}
      onPointerDown={(event) => {
        if (event.pointerType === "touch") start.current = event.clientX;
      }}
      onPointerUp={(event) => {
        if (start.current === null || busy || locked) return;
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
            disabled={busy || (locked && choice.id !== "later")}
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
  dispute: "Mark my note disputed",
  keep_note: "Keep my note as it is",
  revise_note: "Revise my note",
  revise: "Revise the baseline",
  both_hold: "Both hold",
  undo: "Take it back",
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

/** Decisions from this page carry the card they came from, so upkeep counts per week, and how
 * many seconds the card was shown first, so quick yeses can be checked again later. A decision
 * the Brain refuses (a baseline revised without a reason) says why. */
function useDecide(key: string) {
  const decide = useBrainDecisions();
  const shown = useRef(Date.now());
  const [failed, setFailed] = useState<string | null>(null);
  const run = (decisions: BrainDecision[], label: string, onDone: (what: string, checkpoint?: string | null) => void, what: string) => {
    setFailed(null);
    decide.mutate(
      { decisions, label, source: { catch_up: key, seconds: Math.round((Date.now() - shown.current) / 1000) } },
      {
        onSuccess: (outcome) => {
          const refused = outcome.results.filter((r) => !r.ok);
          if (refused.length && refused.length === outcome.results.length) {
            setFailed(refused[0]?.message ?? "Nothing changed.");
            return;
          }
          const scheduled = outcome.results.some((r) => r.data?.status === "scheduled");
          onDone(scheduled ? `${what}: scheduled for a day from now, and you can cancel it until then` : what, outcome.checkpoint?.id ?? null);
        },
      },
    );
  };
  return { decide, run, failed };
}

function Judgment({
  card,
  paceNote,
  onDone,
  onSkip,
}: {
  card: JudgmentCard;
  paceNote?: string | null;
  onDone: (what: string, checkpoint?: string | null) => void;
  onSkip: () => void;
}) {
  const { decide, run, failed } = useDecide(card.key);
  const aside = useSetAside();
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(card.body);
  const [comparing, setComparing] = useState(false);
  const id = card.proposal_id ?? "";
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
      case "dispute":
        return run([{ action: "approve", proposal_id: id }], `Disputed “${card.with?.title ?? card.title}”`, onDone, `Marked “${card.with?.title ?? card.title}” disputed`);
      case "keep_note":
        return run(
          [{ action: "reject", proposal_id: id, reason: "Kept the note as it is" }],
          `Kept “${card.with?.title ?? card.title}”`,
          onDone,
          `Kept “${card.with?.title ?? card.title}” as it is`,
        );
      case "revise_note":
        return navigate(entryUrl(card.with?.id ?? ""));
      case "later":
        return aside.mutate({ key: card.key, later: true }, { onSuccess: onSkip });
      default:
        return undefined;
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
      {paceNote ? (
        <p className="pace-note" role="note">
          {paceNote}
        </p>
      ) : null}
      <p className="muted small">
        From {card.source}
        {card.at ? `, ${when(card.at)}` : ""}. {card.why}
      </p>
      {card.held ? <p className="small">It would have gone in on its own, but it waits for you: {card.held.why}.</p> : null}
      <CheckLine check={card.check} />
      {failed ? (
        <p className="warning small" role="alert">
          {failed}
        </p>
      ) : null}
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

const RELATION_WORDS: Record<ModelVerdict["relation"], string> = {
  contradicts: "they disagree",
  narrows: "this one is a narrower case of your note, or an exception to it",
  extends: "this one adds to your note",
  agrees: "they say the same thing",
  unrelated: "they are about different things",
};

/** What your own AI made of the two, side by side, or that it has not read them yet. */
function CheckLine({ check }: { check?: JudgmentCard["check"] }) {
  if (!check || check.model === "none") return null;
  if (!check.verdict) {
    return check.model === "waiting" ? (
      <p className="muted small">Checked by words and figures; your AI has not read the two side by side yet.</p>
    ) : null;
  }
  return (
    <p className="small check-line">
      Your AI read both: {RELATION_WORDS[check.verdict.relation]}.{check.verdict.settle ? ` ${check.verdict.settle}` : ""}
    </p>
  );
}

function wordCount(text: string): number {
  return (text.match(/[\w'-]+/g) ?? []).length;
}

/** What a rule or a must-hold reaches, before it changes. */
function Impact({ impact }: { impact: NonNullable<CardBaseline["impact"]> }) {
  const domains = impact.domains.map((d) => (d === "*" ? "every task" : d));
  return (
    <div className="impact small">
      <p>
        <strong>What it reaches.</strong> It went into {plural(impact.conversations, "conversation")} in the last 30 days
        {domains.length ? `, and goes first into every brief about ${domains.join(", ")}` : ""}.
      </p>
      {impact.recent.length ? (
        <>
          <p className="muted">The latest requests that got it:</p>
          <ul>
            {impact.recent.map((r) => (
              <li key={`${r.at}-${r.request}`}>
                “{r.request.length > 140 ? `${r.request.slice(0, 139)}…` : r.request}”{r.client ? <span className="muted"> ({r.client})</span> : null}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}

/** A suggestion that changes, retires or disagrees with a baseline: the two side by side first,
 * then the choices, and a reason of a few words to revise it. Never part of a quick group. */
function BaselineCard({
  card,
  baseline,
  paceNote,
  onDone,
  onSkip,
}: {
  card: JudgmentCard;
  baseline: CardBaseline;
  paceNote?: string | null;
  onDone: (what: string, checkpoint?: string | null) => void;
  onSkip: () => void;
}) {
  const { decide, run, failed } = useDecide(card.key);
  const aside = useSetAside();
  const [compared, setCompared] = useState(false);
  const [mode, setMode] = useState<"revise" | "both" | null>(null);
  const [reason, setReason] = useState("");
  const id = card.proposal_id ?? "";
  const retire = baseline.change === "retire";
  const repeated = !!baseline.previous_reason && reason.trim().toLowerCase() === baseline.previous_reason.trim().toLowerCase();
  const enough = wordCount(reason) >= baseline.min_words && !repeated;
  const labelOf = (action: CardAction) =>
    action === "revise" ? (retire ? "Retire it" : "Revise the baseline") : action === "keep_mine" ? (retire ? "Keep it" : "Keep the baseline") : (ACTION_LABELS[action] ?? action);
  const act = (action: CardAction) => {
    switch (action) {
      case "revise":
        return setMode("revise");
      case "both_hold":
        return setMode("both");
      case "keep_mine":
        return run([{ action: "reject", proposal_id: id, reason: "Kept the baseline" }], `Kept the baseline “${baseline.title}”`, onDone, `Kept your baseline “${baseline.title}”`);
      case "later":
        return aside.mutate({ key: card.key, later: true }, { onSuccess: onSkip });
      default:
        return undefined;
    }
  };
  const submit = () => {
    const why = reason.trim();
    if (mode === "revise") {
      const replaces = baseline.change === "disagree" ? [baseline.id] : undefined;
      run(
        [{ action: "approve", proposal_id: id, reason: why, replaces }],
        `${retire ? "Retired" : "Revised"} the baseline “${baseline.title}”`,
        onDone,
        retire ? `Retired “${baseline.title}”` : `Revised “${baseline.title}”`,
      );
    } else if (mode === "both") {
      run([{ action: "approve", proposal_id: id, reason: `Both hold: ${why}` }], `Kept both: “${card.title}”`, onDone, `Kept “${card.title}” beside “${baseline.title}”`);
    }
  };
  const ordered = [card.recommend.action as CardAction, ...card.actions.filter((a) => a !== card.recommend.action)].filter((a) =>
    card.actions.includes(a),
  );
  const choices: Choice[] = ordered.map((action) => ({
    id: action,
    label: labelOf(action),
    run: () => act(action),
    primary: action === card.recommend.action,
  }));
  return (
    <CardFrame
      tag={card.tag}
      title={card.title}
      serves={card}
      recommend={{ label: labelOf(card.recommend.action as CardAction).toLowerCase(), reason: card.recommend.reason }}
      choices={choices}
      busy={decide.isPending || aside.isPending}
      locked={!compared}
      error={decide.error ?? aside.error}
    >
      {paceNote ? (
        <p className="pace-note" role="note">
          {paceNote} This one changes a baseline.
        </p>
      ) : null}
      <p className="muted small">
        From {card.source}
        {card.at ? `, ${when(card.at)}` : ""}. {card.why}
      </p>
      {card.held ? <p className="small">It would have gone in on its own, but it waits for you.</p> : null}
      {compared ? (
        <>
          <Compare
            before={{ label: `Your baseline: ${baseline.why}`, title: baseline.title, body: baseline.body }}
            after={{ label: retire ? "It would retire it" : "The suggestion", title: card.title, body: retire ? card.summary || card.title : card.body }}
            marks={baseline.change === "revise"}
          />
          <ul className="baseline-facts small muted">
            <li>
              Your note: added {day(baseline.added) || "earlier"}
              {baseline.revised ? `, last changed ${day(baseline.revised)}` : ""}
              {baseline.approved_by ? `, approved by ${baseline.approved_by}` : ""}
              {baseline.verified ? `, last checked ${day(baseline.verified)}` : ""}. AIs used it in {plural(baseline.uses, "chat")} this month.
            </li>
            <li>
              The suggestion: from {card.source}
              {card.at ? `, ${when(card.at)}` : ""}.
            </li>
          </ul>
          {baseline.impact ? <Impact impact={baseline.impact} /> : null}
          <CheckLine check={card.check} />
        </>
      ) : (
        <div className="row">
          <button type="button" className="primary" onClick={() => setCompared(true)} autoFocus>
            Compare the two
          </button>
          <span className="muted small">The choices open once you have read both.</span>
        </div>
      )}
      {mode ? (
        <div className="stack-tight">
          <label className="field">
            <span className="field-label">
              {mode === "revise" ? (retire ? "Why does it go?" : "Why does it change?") : "Which client, period or scope does each cover?"}
            </span>
            <textarea rows={2} value={reason} onChange={(event) => setReason(event.target.value)} autoFocus />
            <span className="muted small">
              At least {baseline.min_words} words, kept with the change in your Brain's history.
              {repeated ? " That was the reason last time; say what is different now." : ""}
            </span>
          </label>
          <div className="row">
            <button type="button" className="primary" disabled={!enough || decide.isPending} onClick={submit}>
              {mode === "revise" ? (retire ? "Retire it, with this reason" : "Revise it, with this reason") : "Keep both, with this note"}
            </button>
            <button
              type="button"
              className="link"
              onClick={() => {
                setMode(null);
                setReason("");
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}
      {failed ? (
        <p className="warning small" role="alert">
          {failed}
        </p>
      ) : null}
    </CardFrame>
  );
}

/** Something that went in on its own, which your AI then read as disagreeing with a note. */
function WentInCard({ card, onDone, onSkip }: { card: JudgmentCard; onDone: (what: string, checkpoint?: string | null) => void; onSkip: () => void }) {
  const undo = useBrainUndo();
  const aside = useSetAside();
  const navigate = useNavigate();
  const act = (action: CardAction) => {
    switch (action) {
      case "undo":
        if (card.checkpoint) undo.mutate(card.checkpoint, { onSuccess: () => onDone(`Took back “${card.title}”`) });
        return undefined;
      case "keep_both":
        return aside.mutate({ key: card.key }, { onSuccess: () => onDone(`Kept “${card.title}” beside “${card.with?.title ?? "your note"}”`) });
      case "review":
        return navigate(entryUrl(card.entry_id ?? ""));
      case "later":
        return aside.mutate({ key: card.key, later: true }, { onSuccess: onSkip });
      default:
        return undefined;
    }
  };
  const ordered = [card.recommend.action as CardAction, ...card.actions.filter((a) => a !== card.recommend.action)].filter((a) =>
    card.actions.includes(a),
  );
  const labels: Partial<Record<CardAction, string>> = { keep_both: "Keep both", review: "Open it" };
  const choices: Choice[] = ordered.map((action) => ({
    id: action,
    label: labels[action] ?? ACTION_LABELS[action] ?? action,
    run: () => act(action),
    primary: action === card.recommend.action,
  }));
  return (
    <CardFrame
      tag={card.tag}
      title={card.title}
      recommend={{ label: (labels[card.recommend.action as CardAction] ?? ACTION_LABELS[card.recommend.action as CardAction] ?? card.recommend.action).toLowerCase(), reason: card.recommend.reason }}
      choices={choices}
      busy={undo.isPending || aside.isPending}
      error={undo.error ?? aside.error}
    >
      <p className="muted small">
        {card.source}
        {card.at ? `, ${when(card.at)}` : ""}. {card.why}
      </p>
      {card.with ? (
        <Compare
          before={{ label: "Your note", title: card.with.title, body: card.with.body }}
          after={{ label: "What went in", title: card.title, body: card.body }}
          marks={false}
        />
      ) : null}
      <CheckLine check={card.check} />
    </CardFrame>
  );
}

/** Revisions you decided, going in a day later: each can be cancelled until then. */
function Scheduled({ items }: { items: ScheduledRevision[] }) {
  const decide = useBrainDecisions();
  if (!items.length) return null;
  return (
    <section className="scheduled stack-tight" aria-label="Scheduled changes">
      <h2 className="h3">Scheduled</h2>
      <ul className="list">
        {items.map((item) => (
          <li key={item.proposal_id} className="row">
            <span>
              “{item.title}” goes in {when(item.at)}
              {item.reason ? <span className="muted small"> · {item.reason}</span> : null}
            </span>
            <button
              type="button"
              className="link small"
              disabled={decide.isPending}
              onClick={() =>
                decide.mutate({ decisions: [{ action: "unschedule", proposal_id: item.proposal_id }], label: `Cancelled the scheduled change to ${item.title}` })
              }
            >
              Cancel it
            </button>
          </li>
        ))}
      </ul>
      <ErrorNote error={decide.error} />
    </section>
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
  const policy = useSetBrainPolicies();
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
  if (card.type === "spot") {
    return (
      <CardFrame
        tag="Still right?"
        title={card.title}
        recommend={null}
        busy={busy}
        error={error}
        choices={[
          {
            id: "yes",
            label: "Still right",
            primary: true,
            run: () => run([{ action: "verify", entry_id: card.id }], `Still right: ${card.title}`, onDone, `Confirmed “${card.title}”`),
          },
          { id: "edit", label: "Change it", run: () => window.open(entryUrl(card.id), "_self") },
          {
            id: "no",
            label: "Take it out",
            run: () =>
              run([{ action: "archive", entry_id: card.id, reason: "Not right on a second look" }], `Took out ${card.title}`, onDone, `Took out “${card.title}”`),
          },
          later,
        ]}
      >
        <p>{card.summary}</p>
        <p className="muted small">
          {card.why} A second look now and then keeps quick yeses honest.
          {card.uses ? ` Used in ${plural(card.uses, "chat")} this month.` : ""}
        </p>
      </CardFrame>
    );
  }
  if (card.type === "belief") {
    const where = { note: "a note", file: "a filed document", proposal: "a waiting suggestion", rejected: "a suggestion you turned down" }[card.evidence.kind];
    return (
      <CardFrame
        tag="One belief to look at"
        title={card.title}
        recommend={null}
        busy={busy}
        error={error}
        choices={[
          {
            id: "right",
            label: "Still right",
            primary: true,
            run: () => {
              // Settled: the same finding stays away for a season.
              aside.mutate({ key: card.key, days: 90 });
              run([{ action: "verify", entry_id: card.id }], `Still right: ${card.title}`, onDone, `Confirmed “${card.title}”`);
            },
          },
          { id: "revise", label: "Revise it", run: () => window.open(entryUrl(card.id), "_self") },
          {
            id: "dispute",
            label: "Mark it disputed",
            run: () => {
              aside.mutate({ key: card.key, days: 90 });
              run(
                [{ action: "mark", entry_id: card.id, state: "disputed", reason: `Cross-check: ${card.why}`.slice(0, 480) }],
                `Disputed ${card.title}`,
                onDone,
                `Marked “${card.title}” disputed`,
              );
            },
          },
          later,
        ]}
      >
        <p>{card.summary}</p>
        <p className="muted small">
          {card.baseline ? `A baseline: ${card.baseline}. ` : ""}
          Your weekly cross-check found {where} that may say otherwise ({card.found_by === "your AI" ? "read by your AI" : "by its words and figures"}).
        </p>
        <blockquote className="suggestion-text">
          <strong>{card.evidence.title}</strong>: {card.evidence.text}
        </blockquote>
        <p className="small">{card.why}</p>
      </CardFrame>
    );
  }
  if (card.type === "challenger") {
    return (
      <CardFrame
        tag="A challenger for your beliefs?"
        title="Let your AI argue against what your Brain holds, once a week"
        recommend={null}
        busy={busy || policy.isPending}
        error={error ?? policy.error}
        choices={[
          {
            id: "on",
            label: "Turn it on",
            primary: true,
            run: () =>
              policy.mutate({ challenger: true } as never, { onSuccess: () => onDone("Turned the challenger on: it runs once a week") }),
          },
          { id: "no", label: "Not now", run: () => aside.mutate({ key: card.key, days: 90 }, { onSuccess: () => onDone("The challenger stays off") }) },
          later,
        ]}
      >
        <p>
          {card.stale ? "A baseline came back stale, " : `Your Brain holds ${plural(card.baselines, "baseline")}, `}
          so it may be worth a fresh look from outside. Once a week, Claude Code on this computer takes your most used and oldest beliefs, each only as a
          claim to test, and looks for current evidence against them on the web.
        </p>
        <p className="muted small">
          It uses some of your Claude quota, reads the web and nothing else (no files, no shell), and changes nothing: what it finds comes back here as
          challenges for you to settle. One click turns it off in Settings.
        </p>
      </CardFrame>
    );
  }
  if (card.type === "older") {
    return (
      <CardFrame
        tag="A newer value"
        title={`“${card.newer.title}” is newer`}
        recommend={{ label: "retire the older one", reason: "Every brief already carries the newer value; retiring the older keeps your Brain tidy, and it can be undone." }}
        busy={busy}
        error={error}
        choices={[
          {
            id: "retire",
            label: "Retire the older one",
            primary: true,
            run: () =>
              run(
                [{ action: "archive", entry_id: card.older.id, reason: `A newer value: ${card.newer.id}` }],
                `Retired ${card.older.title}`,
                onDone,
                `Retired “${card.older.title}”: “${card.newer.title}” is newer`,
              ),
          },
          { id: "keep", label: "Keep both as history", run: () => aside.mutate({ key: card.key }, { onSuccess: () => onDone(`Kept “${card.older.title}” as history`) }) },
          later,
        ]}
      >
        <div className="compare twins">
          {[
            { side: card.older, label: "Older", when: card.older_as_of },
            { side: card.newer, label: "Newer", when: card.newer_as_of },
          ].map(({ side, label, when: date }) => (
            <div key={side.id} className="compare-side">
              <p className="compare-label">
                {label}
                {date ? `, as of ${day(date)}` : ""}: <Link to={entryUrl(side.id)}>{side.title}</Link>
              </p>
              <p className="small">{side.summary}</p>
            </div>
          ))}
        </div>
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
  if (nudge.type === "agent_goal") {
    return (
      <CardFrame
        tag="A goal with a measure?"
        title={nudge.title}
        recommend={null}
        busy={aside.isPending}
        error={aside.error}
        choices={[
          { id: "set", label: "Set it as a goal", primary: true, run: () => navigate(`/projects?set=${encodeURIComponent(nudge.line)}`) },
          no,
          later,
        ]}
      >
        <p className="muted small">An agent goal has a measure code checks, and its agent speaks up only when it slips.</p>
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
      choices={[{ id: "goals", label: "Open my goals", primary: true, run: () => navigate("/settings?tab=alignment") }, no, later]}
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
