// The flow of one request, in the System Map's visual language: stages left to right (top to
// bottom on a phone), the count that goes in and comes out of each, the time it took, and dots
// moving along the lane between them. A stage that waits for a build step is drawn dashed and
// says so. Movement only explains: the stages fill in one after another, and the dots show what
// flows on. With reduced motion, everything is drawn at once and nothing moves.

import { useEffect, useState } from "react";

import type { StageDrawn } from "./types";

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() =>
    typeof window !== "undefined" && typeof window.matchMedia === "function" ? window.matchMedia("(prefers-reduced-motion: reduce)").matches : false,
  );
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setReduced(media.matches);
    media.addEventListener?.("change", on);
    return () => media.removeEventListener?.("change", on);
  }, []);
  return reduced;
}

/** How many dots a lane carries for `count` things: a few, never a crowd. */
export function dotsFor(count: number | null | undefined): number {
  if (!count || count <= 0) return 0;
  return Math.min(6, 1 + Math.floor(Math.log2(count + 1)));
}

function time(ms: number | null): string {
  if (ms === null || ms === undefined) return "";
  return ms < 1000 ? `${Math.round(ms * 10) / 10} ms` : `${Math.round(ms / 100) / 10} s`;
}

export function FlowMap({ stages, replay = 0 }: { stages: StageDrawn[]; replay?: number }) {
  const reduced = usePrefersReducedMotion();
  const [filled, setFilled] = useState(reduced ? stages.length : 0);

  useEffect(() => {
    if (reduced) {
      setFilled(stages.length);
      return;
    }
    setFilled(0);
    const timer = setInterval(() => setFilled((n) => (n >= stages.length ? n : n + 1)), 420);
    return () => clearInterval(timer);
  }, [stages, reduced, replay]);

  return (
    <ol className="ttb-flow" aria-label="The request, stage by stage">
      {stages.map((stage, index) => {
        const waiting = stage.state === "waiting";
        const reached = index < filled;
        const next = stages[index + 1];
        const dots = !waiting && reached ? dotsFor(stage.out) : 0;
        return (
          <li key={stage.id} className={`ttb-stage ${waiting ? "is-waiting" : "is-done"}${reached ? " is-in" : ""}`} data-stage={stage.id}>
            <div className="ttb-stage-box">
              <h3>{stage.name}</h3>
              {waiting ? (
                <p className="ttb-wait">{stage.note || "Waits for a build step"}</p>
              ) : (
                <>
                  <p className="ttb-counts" aria-label={`${stage.in ?? "no"} in, ${stage.out ?? "no"} out`}>
                    <span className="ttb-count">{stage.in ?? "–"}</span>
                    <span aria-hidden="true" className="ttb-arrow">
                      →
                    </span>
                    <span className="ttb-count">{stage.out ?? "–"}</span>
                  </p>
                  <p className="muted small">{stage.ms !== null && stage.ms !== undefined ? time(stage.ms) : "time: not kept by this engine yet"}</p>
                  {stage.note ? <p className="small">{stage.note}</p> : null}
                </>
              )}
              {stage.dropped.length ? (
                <details>
                  <summary>Dropped or held back ({stage.dropped.length})</summary>
                  <ul className="list compact-list">
                    {stage.dropped.map((d) => (
                      <li key={d.id}>
                        {d.title || d.id} <span className="muted small">{d.why}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}
              {stage.added.length ? (
                <details>
                  <summary>Added ({stage.added.length})</summary>
                  <ul className="list compact-list">
                    {stage.added.map((d) => (
                      <li key={d.id}>
                        {d.title || d.id} <span className="muted small">{d.why}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </div>
            {next ? (
              <span className={`ttb-lane${waiting || next.state === "waiting" ? " is-dashed" : ""}`} aria-hidden="true">
                {Array.from({ length: dots }, (_, k) => (
                  <i key={k} className="ttb-dot" style={{ "--delay": `${-(k * 1.6) / Math.max(1, dots)}s`, "--dur": "1.6s" } as React.CSSProperties} />
                ))}
              </span>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
