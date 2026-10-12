// What readings left out (brain-logic plan 7.2, step 6): kept as a record you can search, each
// scored again against your goals and active projects as they stand now, so something left out
// for serving no goal is marked once a goal it fits appears. Pull anyway sends it to Catch up.

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { get } from "../api/client";
import { keys, useProposeEntry } from "../api/hooks";
import { when } from "../lib/format";

interface LeftOutRow {
  statement: string;
  why: string;
  request_id: string;
  source: string;
  at: string;
  fits: string[];
  for_goals: boolean;
}

export function LeftOutSearch() {
  const [q, setQ] = useState("");
  const { data: rows } = useQuery({
    queryKey: [...keys.brain, "left-out", q],
    queryFn: () => get<LeftOutRow[]>(`/api/brain/distill/left-out${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ""}`),
  });
  const propose = useProposeEntry();
  const [pulled, setPulled] = useState<string[]>([]);
  if (!rows?.length && !q) return null;
  const fitting = (rows ?? []).filter((r) => r.fits.length && r.for_goals).length;
  return (
    <details className="left-out-search">
      <summary className="small">
        Left out when reading{fitting ? ` · ${fitting} fit your goals now` : ""}
      </summary>
      <input
        type="search"
        className="small"
        aria-label="Find what was left out"
        placeholder="Find what was left out"
        value={q}
        onChange={(event) => setQ(event.target.value)}
      />
      <ul className="compact-list" aria-label="Left out when reading">
        {(rows ?? []).map((row) => (
          <li key={`${row.request_id}:${row.statement}`} className="small">
            {row.statement} <span className="muted">· {row.why} · from {row.source}, {when(row.at)}</span>
            {row.fits.length && row.for_goals ? <span className="chip small">fits your goals now: {row.fits.join(", ")}</span> : null}{" "}
            {pulled.includes(row.statement) ? (
              <span className="muted">· pulled, waiting in Catch up</span>
            ) : (
              <button
                type="button"
                className="link small"
                disabled={propose.isPending}
                onClick={() =>
                  propose.mutate(
                    {
                      title: (row.statement.split(/[.!?]\s/)[0] ?? row.statement).slice(0, 80),
                      statement: row.statement,
                      evidence: `Pulled anyway from “${row.source}”; it had been left out: ${row.why}`,
                    },
                    { onSuccess: () => setPulled((p) => [...p, row.statement]) },
                  )
                }
              >
                Pull anyway
              </button>
            )}
          </li>
        ))}
      </ul>
      {q && !rows?.length ? <p className="muted small">Nothing left out says that.</p> : null}
    </details>
  );
}
