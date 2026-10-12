// Goals in Catch up (goals plan 6.11): an agent goal that slipped (one card per slip, saying why
// it appeared, with the trend and what to do next), and the suggested next steps for your goals
// as a quick yes grouped by goal. Your own goals' check-ins are not Catch up items; they live on
// Home and the goal's page.

import { Link } from "react-router";

import { useAnswerStep, useSetAside } from "../../api/hooks";
import type { CatchUpPlan, GoalSuggestion } from "../../api/types";
import { ErrorNote } from "../ui";
import { GoalStatus, Trend, goalUrl } from "./GoalParts";

export function SlippedGoals({ items }: { items: NonNullable<CatchUpPlan["goals"]> }) {
  const aside = useSetAside();
  if (!items.length) return null;
  return (
    <section className="stack-tight" aria-label="Agent goals that slipped">
      <h2 className="small-head">Agent goals that slipped</h2>
      <ul className="list">
        {items.map((card) => (
          <li key={card.key} className="card">
            <p>
              <strong>{card.goal.title}</strong> <GoalStatus goal={card.goal} /> <Trend values={card.goal.trend} />
            </p>
            <p className="small">{card.why}</p>
            <div className="row small">
              <Link className="button primary" to={card.goal.kept_by === "knowledge-agent" ? "/brain/agent" : "/work/agents"}>
                Start
              </Link>
              <button type="button" className="link small" disabled={aside.isPending} onClick={() => aside.mutate({ key: card.key, later: true })}>
                Not now
              </button>
              <Link className="small" to={`/settings?tab=alignment&goal=${encodeURIComponent(card.goal.id)}`}>
                Change the goal
              </Link>
            </div>
          </li>
        ))}
      </ul>
      <ErrorNote error={aside.error} />
    </section>
  );
}

export function GoalSteps({ groups }: { groups: NonNullable<CatchUpPlan["goal_steps"]> }) {
  if (!groups.length) return null;
  return (
    <section className="stack-tight" aria-label="Suggested next steps for your goals">
      <h2 className="small-head">Suggested next steps for your goals</h2>
      {groups.map((group) => (
        <StepGroup key={group.goal} goal={group.goal} title={group.title} steps={group.steps} />
      ))}
    </section>
  );
}

function StepGroup({ goal, title, steps }: { goal: string; title: string; steps: GoalSuggestion[] }) {
  const answer = useAnswerStep(goal);
  return (
    <div className="card">
      <p className="small">
        <Link to={goalUrl(goal)}>{title}</Link>
      </p>
      <ul className="small">
        {steps.map((s) => (
          <li key={s.id} className="row">
            <span>“{s.text}”</span>
            <button type="button" className="link small" disabled={answer.isPending} onClick={() => answer.mutate({ step: s.id, accept: true })}>
              Make it a task
            </button>
            <button type="button" className="link small" disabled={answer.isPending} onClick={() => answer.mutate({ step: s.id, accept: false })}>
              No
            </button>
          </li>
        ))}
      </ul>
      <ErrorNote error={answer.error} />
    </div>
  );
}
