// How the heartbeat learns: your goal (what makes a change relevant), the filters that drop
// what you never want, when the distill runs (nightly, or each beat as before) and how long
// the buffer is kept. Heartbeat learning, docs/dev/plans/heartbeat-learning-plan.md.

import { useEffect, useState } from "react";

import { css } from "../css";
import { useLearning, useSetLearning } from "../hooks/heartbeat";
import { Btn, Failure, Loaded } from "../ui";

const FIELD = "font:400 13.5px Geist;padding:7px 10px;border-radius:10px;border:1px solid var(--line2);background:var(--surface);color:var(--ink)";

export function LearningSettings() {
  const learning = useLearning();
  const save = useSetLearning();
  const [goal, setGoal] = useState("");
  const [pattern, setPattern] = useState("");
  useEffect(() => setGoal(learning.data?.goal ?? ""), [learning.data?.goal]);
  return (
    <div style={css("display:flex;flex-direction:column;gap:12px;padding:12px 0;border-top:1px solid var(--line)")}>
      <span style={css("font:500 14px Geist")}>How it learns</span>
      <Loaded q={learning}>
        {(s) => (
          <>
            <label htmlFor="learn-goal" style={css("display:flex;flex-direction:column;gap:4px;font:400 12.5px Geist;color:var(--muted)")}>
              Your goal: what makes a change worth keeping
              <textarea id="learn-goal" rows={2} value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="For example: run the Q4 webinar series and keep the website launch on time" style={css(FIELD + ";resize:vertical")} />
            </label>
            <div>
              <Btn kind="ghostSm" disabled={save.isPending || goal === s.goal} onClick={() => save.mutate({ goal })}>
                Save goal
              </Btn>
            </div>
            <div style={css("display:flex;flex-direction:column;gap:6px")}>
              <span style={css("font:400 12.5px Geist;color:var(--muted)")}>Filters: changes that match are dropped, unless your goal makes them relevant</span>
              {s.filters.map((f, i) => (
                <div key={`${f.pattern}-${i}`} style={css("display:flex;gap:8px;align-items:center")}>
                  <code style={css("flex:1;font:400 12.5px 'Geist Mono';padding:5px 8px;border-radius:8px;background:var(--soft)")}>{f.pattern}</code>
                  <Btn kind="ghostSm" disabled={save.isPending} onClick={() => save.mutate({ filters: s.filters.filter((_, k) => k !== i) })}>
                    Remove
                  </Btn>
                </div>
              ))}
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (!pattern.trim()) return;
                  save.mutate({ filters: [...s.filters, { pattern: pattern.trim() }] }, { onSuccess: () => setPattern("") });
                }}
                style={css("display:flex;gap:8px;flex-wrap:wrap")}
              >
                <input id="learn-filter" aria-label="New filter" value={pattern} onChange={(e) => setPattern(e.target.value)} placeholder="newsletter, or /^Re: out of office/" style={css(FIELD + ";flex:1;min-width:200px")} />
                <Btn kind="ghostSm" type="submit" disabled={save.isPending || !pattern.trim()}>
                  Add filter
                </Btn>
              </form>
            </div>
            <div style={css("display:flex;gap:14px;flex-wrap:wrap;align-items:center")}>
              <label htmlFor="learn-mode" style={css("display:flex;gap:6px;align-items:center;font:400 13px Geist")}>
                Learn
                <select id="learn-mode" value={s.learn} disabled={save.isPending} onChange={(e) => save.mutate({ learn: e.target.value as "nightly" | "per_beat" })} style={css(FIELD)}>
                  <option value="nightly">nightly (recommended)</option>
                  <option value="per_beat">every beat</option>
                </select>
              </label>
              {s.learn === "nightly" ? (
                <label htmlFor="learn-at" style={css("display:flex;gap:6px;align-items:center;font:400 13px Geist")}>
                  at
                  <input id="learn-at" type="time" value={s.distill_at} disabled={save.isPending} onChange={(e) => e.target.value && save.mutate({ distill_at: e.target.value })} style={css(FIELD)} />
                </label>
              ) : null}
              <label htmlFor="learn-days" style={css("display:flex;gap:6px;align-items:center;font:400 13px Geist")}>
                Keep the buffer
                <select id="learn-days" value={s.buffer_days} disabled={save.isPending} onChange={(e) => save.mutate({ buffer_days: Number(e.target.value) })} style={css(FIELD)}>
                  {[7, 14, 30, 90].map((d) => (
                    <option key={d} value={d}>
                      {d} days
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </>
        )}
      </Loaded>
      {save.error ? <Failure error={save.error} /> : null}
    </div>
  );
}
