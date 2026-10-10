// Tasks and State in Catch up (goals plan 6.11, BL 8.4): what was handed to you (it needs your
// judgment), a handoff nobody claimed for a day (Remind or Take back), and a value an AI wrote
// that waits for your tap.

import { useState } from "react";

import { useSetAside, useTakeBack } from "../../api/hooks";
import type { CatchUpPlan } from "../../api/types";
import { Waiting } from "../../pages/work/Live";
import { ErrorNote } from "../ui";
import { TaskDrawer } from "./Tasks";

export function TasksCatchUp({ plan }: { plan: CatchUpPlan }) {
  const aside = useSetAside();
  const takeBack = useTakeBack();
  const [open, setOpen] = useState<string | null>(null);
  const handed = plan.handed ?? [];
  const unclaimed = plan.unclaimed ?? [];
  const waiting = plan.state_waiting ?? [];
  if (!handed.length && !unclaimed.length && !waiting.length) return null;
  return (
    <section className="stack-tight" aria-label="Tasks and values">
      {handed.length ? (
        <>
          <h2 className="small-head">Handed to you</h2>
          <ul className="list">
            {handed.map((t) => (
              <li key={t.id} className="card">
                <p>
                  <strong>
                    {t.id} {t.task}
                  </strong>
                </p>
                {t.card.next_step ? <p className="small">Next step: {t.card.next_step}</p> : null}
                <div className="row small">
                  <button type="button" className="primary" onClick={() => setOpen(t.id)}>
                    Start
                  </button>
                  <button type="button" className="link small" onClick={() => aside.mutate({ key: t.key ?? t.id, later: true })}>
                    Later
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {unclaimed.length ? (
        <>
          <h2 className="small-head">Not claimed for a day</h2>
          <ul className="list compact-list small">
            {unclaimed.map((t) => (
              <li key={t.id}>
                {t.id} {t.task} <span className="muted">({t.owner_label})</span>{" "}
                <button type="button" className="link small" onClick={() => aside.mutate({ key: t.key ?? t.id, later: true })}>
                  Remind
                </button>{" "}
                <button type="button" className="link small" onClick={() => takeBack.mutate(t.id)}>
                  Take back
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : null}
      <Waiting items={waiting} />
      <ErrorNote error={aside.error ?? takeBack.error} />
      {open ? <TaskDrawer id={open} onClose={() => setOpen(null)} /> : null}
    </section>
  );
}
