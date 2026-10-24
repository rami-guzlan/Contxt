// The auto strip (the auto default, section 3): in the flow above an auto-governed area, never a
// cover over it. "{agent} keeps {area}", the last beat and the next, What it did, Govern this
// myself (the caller wires it to governance), one line on what it does here, and two or three
// live links to the matching regions on Home. Everything under it stays usable.

import { useNavigate } from "react-router";

import { usePolicy } from "../api";
import { css } from "../css";
import { clock, useHeartbeat, useRegions } from "../hooks/heartbeat";

export interface AutoStripProps {
  /** The area in words: "Catch up", "Project status", "the Q4 webinar packet". */
  area: string;
  /** One line on what the governing AI does here. */
  what: string;
  /** The Brain regions this area draws on: the live links open them on Home. */
  regions?: string[];
  /** Make this area Governed (the owner keeps it). */
  onGovern: () => void;
  /** Disable the button while the change is under way. */
  governing?: boolean;
}

export function AutoStrip({ area, what, regions: wanted = [], onGovern, governing = false }: AutoStripProps) {
  const navigate = useNavigate();
  const policy = usePolicy();
  const status = useHeartbeat();
  const regions = useRegions();
  if (policy.data?.mode !== "auto") return null;
  const s = status.data;
  const agent = s?.cli_label ?? "Your AI";
  const last = s?.last_beat;
  const beat = !s
    ? ""
    : s.paused
      ? "Heartbeat paused"
      : last
        ? `Heartbeat ${clock(last.started_at)}${s.next_beat_at ? ` · next ${clock(s.next_beat_at)}` : ""}`
        : `No beat yet${s.next_beat_at ? ` · next ${clock(s.next_beat_at)}` : ""}`;
  const rows = (regions.data ?? []).filter((r) => !wanted.length || wanted.includes(r.id));
  const links = rows
    .filter((r) => r.lines.length)
    .slice(0, 3)
    .map((r) => {
      const fresh = r.lines.filter((l) => l.new_this_beat && l.status !== "undone").length;
      const at = last ? ` from the ${clock(last.started_at)} beat` : "";
      return {
        id: r.id,
        t: fresh ? `${r.name}: ${fresh} ${fresh === 1 ? "line" : "lines"}${at}` : `${r.name}: ${r.lines[0]?.text ?? ""}`,
      };
    });
  return (
    <div style={css("display:flex;flex-direction:column;gap:10px;padding:14px 16px;border-radius:16px;background:oklch(0.74 0.12 150 / .1);margin-bottom:4px")}>
      <div style={css("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
        <span
          aria-hidden="true"
          style={css(`width:8px;height:8px;border-radius:50%;flex:none;background:${s?.paused ? "var(--faint)" : "oklch(0.7 0.14 150)"}`)}
        />
        <span style={css("font:500 13.5px Geist")}>
          {agent} keeps {area}
        </span>
        <span role="status" style={css("font:400 12.5px Geist;color:var(--muted);flex:1;min-width:160px")}>
          {beat}
        </span>
        <button type="button" onClick={() => navigate("/#what-it-did")} style={css("border:0;background:transparent;font:500 12.5px Geist;color:var(--ink2);cursor:pointer")}>
          What it did →
        </button>
        <button
          type="button"
          disabled={governing}
          onClick={onGovern}
          style={css("padding:7px 14px;border-radius:99px;border:1px solid var(--line2);background:transparent;font:500 12.5px Geist;color:var(--ink);cursor:pointer")}
        >
          Govern this myself
        </button>
      </div>
      <span style={css("font:400 13px/1.5 Geist;color:var(--ink2)")}>{what} Everything below stays yours to open, edit and undo.</span>
      {links.length ? (
        <div style={css("display:flex;gap:6px;flex-wrap:wrap")}>
          {links.map((x) => (
            <button
              key={x.id}
              type="button"
              onClick={() => navigate(`/?region=${encodeURIComponent(x.id)}#world`)}
              style={css("padding:4px 10px;border-radius:99px;border:0;background:var(--surface);font:400 12px Geist;color:var(--ink);cursor:pointer;text-align:left")}
            >
              {x.t}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
