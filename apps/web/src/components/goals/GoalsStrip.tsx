// Home's goal strip (goals plan 6.12), and nothing else, so Home stays calm: the goals due a
// check-in with the fill-in inline, at most three agent goals that need you, and on review day
// the weekly review (when it is on). It shows only what applies; without goals, only agent
// goals that need you. The purpose line is Home's own.

import { useState } from "react";
import { Link } from "react-router";

import { useGoalsHome } from "../../api/hooks";
import { CheckIn, GoalStatus, goalUrl } from "./GoalParts";
import { plural } from "../../lib/format";

export function GoalsStrip() {
  const { data: home } = useGoalsHome();
  const [open, setOpen] = useState<string | null>(null);
  if (!home || (!home.check_ins.length && !home.agent_goals.length && !home.review)) return null;
  return (
    <section className="goals-strip" aria-label="Your goals">
      {home.check_ins.length ? (
        <div className="stack">
          <p>
            <strong>Check in on {plural(home.check_ins.length, "goal")}</strong>
          </p>
          <ul className="small stack">
            {home.check_ins.map((g) => (
              <li key={g.id}>
                <Link to={goalUrl(g.id)}>{g.title}</Link>{" "}
                <button type="button" className="link small" aria-expanded={open === g.id} onClick={() => setOpen(open === g.id ? null : g.id)}>
                  {open === g.id ? "Close" : "Check in"}
                </button>
                {open === g.id ? <CheckIn goal={g} onDone={() => setOpen(null)} /> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {home.agent_goals.length ? (
        <div>
          <p>
            <strong>Agent goals that need you</strong>
          </p>
          <ul className="small">
            {home.agent_goals.map((g) => (
              <li key={g.id}>
                <Link to={`/settings?tab=alignment&goal=${encodeURIComponent(g.id)}`}>{g.title}</Link> <GoalStatus goal={g} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {home.review ? (
        <div className="card weekly-review">
          <h2>This week</h2>
          {home.review.goals.length ? (
            <ul className="small">
              {home.review.goals.map((g) => (
                <li key={g.id}>
                  {g.title}: {g.words}
                  {g.flag ? <span className="muted"> ({g.flag})</span> : null}
                </li>
              ))}
            </ul>
          ) : null}
          {home.review.agent_goals.length ? (
            <p className="small">Agent goals that slipped: {home.review.agent_goals.map((g) => `${g.title} (${g.words})`).join("; ")}</p>
          ) : null}
          {home.review.notes.length ? (
            <ul className="small">
              {home.review.notes.map((n, i) => (
                <li key={i}>
                  {n.goal}: {n.line}
                </li>
              ))}
            </ul>
          ) : null}
          {home.review.next_steps.length ? (
            <p className="small">Next: {home.review.next_steps.map((s) => s.text).join("; ")}</p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
