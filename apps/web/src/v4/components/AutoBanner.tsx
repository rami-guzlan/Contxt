// The Brain's auto banner: who governs it, how many regions the last beat updated, and links to
// The world right now and What it did. Shown only when the Brain is auto-governed.

import { useNavigate } from "react-router";

import { usePolicy } from "../api";
import { css } from "../css";
import { clock, useHeartbeat, useRegions } from "../hooks/heartbeat";

export function AutoBanner() {
  const navigate = useNavigate();
  const policy = usePolicy();
  const status = useHeartbeat();
  const regions = useRegions();
  if (policy.data?.mode !== "auto" || !status.data) return null;
  const s = status.data;
  const updated = (regions.data ?? []).filter((r) => r.new_this_beat > 0).length;
  const last = s.last_beat;
  const line = s.paused
    ? `Auto-governed by ${s.cli_label}. The heartbeat is paused.`
    : last
      ? `Auto-governed by ${s.cli_label}. Heartbeat ${clock(last.started_at)}: ${updated} ${updated === 1 ? "region" : "regions"} updated. Only must-holds wait here.`
      : `Auto-governed by ${s.cli_label}. No beat yet. Only must-holds wait here.`;
  return (
    <div role="status" style={css("display:flex;align-items:center;gap:12px;padding:12px 16px;border-radius:14px;background:oklch(0.74 0.12 150 / .12);flex-wrap:wrap")}>
      <span
        aria-hidden="true"
        style={css(`width:8px;height:8px;border-radius:50%;flex:none;background:${s.paused ? "var(--faint)" : "oklch(0.7 0.14 150)"};${s.paused ? "" : "animation:gnDot 1.6s infinite"}`)}
      />
      <span style={css("font:400 14px Geist;flex:1;min-width:220px")}>{line}</span>
      <button type="button" onClick={() => navigate("/#world")} style={css("border:0;background:transparent;font:500 13px Geist;color:var(--ink2);cursor:pointer")}>
        The world right now →
      </button>
      <button type="button" onClick={() => navigate("/#what-it-did")} style={css("border:0;background:transparent;font:500 13px Geist;color:var(--ink2);cursor:pointer")}>
        What it did →
      </button>
    </div>
  );
}
