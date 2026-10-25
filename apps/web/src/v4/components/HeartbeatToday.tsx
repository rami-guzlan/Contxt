// Heartbeat › Today: what the heartbeat captured for tonight's distill, by source, with what a
// filter dropped and why (Bring back) and Forget this; Distill now; and one card for what has
// waited in Catch up over 14 days. Heartbeat learning, docs/dev/plans/heartbeat-learning-plan.md.

import { useNavigate } from "react-router";

import { css } from "../css";
import { type Staged, useDistillNow, useLearning, useStaged, useStagedAction, useStillWaiting } from "../hooks/heartbeat";
import { Failure, Loaded } from "../ui";

const PILL = "border:1px solid var(--line2);background:transparent;border-radius:99px;padding:4px 11px;font:500 12px Geist;color:var(--ink);cursor:pointer";

export function HeartbeatToday() {
  const navigate = useNavigate();
  const learning = useLearning();
  const waiting = useStaged("staged");
  const dropped = useStaged("dropped");
  const act = useStagedAction();
  const distill = useDistillNow();
  const stale = useStillWaiting();
  if (!learning.data || learning.data.learn === "per_beat") return null; // per beat: nothing waits
  return (
    <section aria-label="Today" style={css("background:var(--surface);border-radius:22px;box-shadow:var(--shadow);padding:16px 22px;display:flex;flex-direction:column;gap:12px")}>
      <div style={css("display:flex;align-items:center;gap:12px;flex-wrap:wrap")}>
        <div style={css("flex:1;min-width:220px;display:flex;flex-direction:column;gap:2px")}>
          <span style={css("font:500 15px Geist")}>Today</span>
          <span style={css("font:400 12.5px/1.45 Geist;color:var(--muted)")}>
            What the heartbeat captured. The distill learns from it at {learning.data?.distill_at ?? "19:00"}, and nothing goes into your Brain before then.
          </span>
        </div>
        <button type="button" disabled={distill.isPending} onClick={() => distill.mutate()} style={css(PILL)}>
          {distill.isPending ? "Distilling…" : "Distill now"}
        </button>
      </div>
      {distill.error ? <Failure error={distill.error} /> : null}
      {act.error ? <Failure error={act.error} /> : null}
      {stale.data && stale.data.count > 0 ? (
        <button type="button" onClick={() => navigate("/brain/catch-up")} style={css("text-align:left;border:0;border-radius:14px;padding:12px 14px;background:var(--soft);font:400 13.5px Geist;color:var(--ink);cursor:pointer")}>
          <b style={css("font-weight:500")}>Still waiting:</b> {stale.data.count} from the distill {stale.data.count === 1 ? "has" : "have"} waited in Catch up for over {stale.data.days} days. Decide →
        </button>
      ) : null}
      <Loaded q={waiting} empty={(rows) => (rows.length ? null : <span style={css("font:400 13.5px Geist;color:var(--muted)")}>Nothing captured since the last distill.</span>)}>
        {(rows: Staged[]) => <Groups rows={rows} label="Waiting for tonight" onForget={(id) => act.mutate({ id, action: "forget" })} pending={act.isPending} />}
      </Loaded>
      {dropped.data && dropped.data.length ? (
        <details>
          <summary style={css("font:500 13px Geist;color:var(--ink2);cursor:pointer")}>Dropped by your filters · {dropped.data.length}</summary>
          <Groups rows={dropped.data} label="" onBack={(id) => act.mutate({ id, action: "bring-back" })} pending={act.isPending} />
        </details>
      ) : null}
    </section>
  );
}

function Groups({ rows, label, onForget, onBack, pending }: { rows: Staged[]; label: string; onForget?: (id: string) => void; onBack?: (id: string) => void; pending: boolean }) {
  const by = new Map<string, Staged[]>();
  for (const r of rows) by.set(r.connector, [...(by.get(r.connector) ?? []), r]);
  return (
    <div style={css("display:flex;flex-direction:column;gap:10px")}>
      {label ? <span style={css("font:500 11px 'Geist Mono';letter-spacing:.06em;color:var(--muted)")}>{label.toUpperCase()}</span> : null}
      {[...by.entries()].map(([source, items]) => (
        <div key={source} style={css("display:flex;flex-direction:column")}>
          <span style={css("font:500 13px Geist;padding:4px 0")}>
            {source} · {items.length}
          </span>
          {items.map((r) => (
            <div key={r.id} style={css("display:flex;gap:10px;align-items:baseline;padding:7px 0;border-top:1px solid var(--line);flex-wrap:wrap")}>
              <span style={css("flex:1;min-width:180px;font:400 13.5px/1.45 Geist")}>
                {r.title || r.item_id}
                {r.unclear ? <span style={css("font:400 12px Geist;color:var(--muted)")}> · a filter matched; the distill decides</span> : null}
                {r.status === "dropped" && r.filter ? <span style={css("font:400 12px Geist;color:var(--muted)")}> · {r.filter}</span> : null}
              </span>
              {onForget ? (
                <button type="button" aria-label={`Forget: ${r.title || r.item_id}`} disabled={pending} onClick={() => onForget(r.id)} style={css(PILL)}>
                  Forget this
                </button>
              ) : null}
              {onBack ? (
                <button type="button" aria-label={`Bring back: ${r.title || r.item_id}`} disabled={pending} onClick={() => onBack(r.id)} style={css(PILL)}>
                  Bring back
                </button>
              ) : null}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
