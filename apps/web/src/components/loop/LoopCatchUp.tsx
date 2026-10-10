// The updating loop in Catch up (brain-logic plan 9): "Still true?" after you corrected an AI,
// a rule bent three times, approval health, notes that rest on one source, the quarterly
// alignment review, lessons the knowledge agent learned from your decisions, and its hand-ups.
// Nothing changes a note on its own: each card is a question with a one-tap answer.

import { Link } from "react-router";

import { useAnswerCorrection, useKeepLesson, useRunAgentAction, useSetAside } from "../../api/hooks";
import type { CatchUpPlan, LoopCard } from "../../api/types";
import { entryUrl } from "../../pages/brain/shared";
import { ErrorNote } from "../ui";

const HEADS: Record<LoopCard["type"], string> = {
  still_true: "Still true?",
  bent_rule: "A rule you keep bending",
  approval_health: "How your approvals go",
  corroborate: "Rests on one source",
  quarterly_review: "The quarterly review",
  lesson: "A lesson from your decisions",
  hand_up: "Handed up by the knowledge agent",
};

export function LoopCatchUp({ plan }: { plan: CatchUpPlan }) {
  const cards = plan.loop ?? [];
  const aside = useSetAside();
  const answer = useAnswerCorrection();
  const lesson = useKeepLesson();
  const run = useRunAgentAction();
  if (!cards.length) return null;
  const later = (card: LoopCard) => (
    <button type="button" className="link small" onClick={() => aside.mutate({ key: card.key, later: true })}>
      Later
    </button>
  );
  const dismiss = (card: LoopCard) => (
    <button type="button" className="link small" onClick={() => aside.mutate({ key: card.key })}>
      Set aside
    </button>
  );
  return (
    <section className="stack-tight" aria-label="The updating loop">
      <h2 className="small-head">Keeping what it knows true</h2>
      <ul className="list">
        {cards.map((card) => (
          <li key={card.key} className="card loop-card">
            <p className="eyebrow small">{HEADS[card.type]}</p>
            <p>{card.ask}</p>
            {card.type === "lesson" && card.text ? <p className="muted small">{card.text}</p> : null}
            {card.type === "hand_up" && card.why ? <p className="muted small">Why: {card.why}</p> : null}
            {card.type === "still_true" && card.salience ? (
              <p className="muted small">If it proved wrong, it may matter more than its weight says: you can make it a must-hold.</p>
            ) : null}
            <div className="row small">
              {card.type === "still_true" && card.correction != null ? (
                <>
                  <button type="button" className="primary" onClick={() => answer.mutate({ id: card.correction!, status: "still_true" })}>
                    Still true
                  </button>
                  {card.note ? <Link to={entryUrl(card.note)}>Fix the note</Link> : null}
                  <button type="button" className="link small" onClick={() => answer.mutate({ id: card.correction!, status: "fixed" })}>
                    I fixed it
                  </button>
                  <button type="button" className="link small" onClick={() => answer.mutate({ id: card.correction!, status: "dismissed" })}>
                    Not this note
                  </button>
                </>
              ) : null}
              {(card.type === "bent_rule" || card.type === "corroborate") && card.note ? (
                <>
                  <Link className="button" to={entryUrl(card.note)}>
                    Open {card.title ?? "the note"}
                  </Link>
                  {later(card)}
                  {dismiss(card)}
                </>
              ) : null}
              {card.type === "approval_health" ? (
                <>
                  <Link className="button" to="/settings?tab=approval">
                    Open approval settings
                  </Link>
                  {dismiss(card)}
                </>
              ) : null}
              {card.type === "quarterly_review" ? (
                <>
                  <button type="button" className="primary" disabled={run.isPending} onClick={() => run.mutate({ action: "check-alignment" })}>
                    Run the alignment check
                  </button>
                  {later(card)}
                </>
              ) : null}
              {card.type === "lesson" ? (
                <>
                  <button type="button" className="primary" disabled={lesson.isPending} onClick={() => lesson.mutate(card.key)}>
                    Keep as a note
                  </button>
                  {dismiss(card)}
                </>
              ) : null}
              {card.type === "hand_up" ? (
                <>
                  <Link className="button" to="/brain/agent">
                    Open the knowledge agent
                  </Link>
                  {dismiss(card)}
                </>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
      {run.isSuccess ? (
        <p className="small" role="status">
          The alignment check is running; what it finds comes back here.
        </p>
      ) : null}
      {lesson.isSuccess ? (
        <p className="small" role="status">
          Saved as a suggested note: it waits in Catch up.
        </p>
      ) : null}
      <ErrorNote error={aside.error ?? answer.error ?? lesson.error ?? run.error} />
    </section>
  );
}
