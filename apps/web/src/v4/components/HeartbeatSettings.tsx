// Settings, Approval: the Heartbeat block under the auto switch. Cadence, quiet hours, the
// connectors found in the person's CLIs (on or off, the regions each feeds) and what a beat costs,
// from the beats' own records.

import { css } from "../css";
import { SignIn } from "./SignIn";
import { checkable, ConnectorSetup, GoalFields } from "./ConnectorSetup";
import { costLine, type HbConnector, testLine, useHeartbeat, useHeartbeatSettings, useN8nFix, useRegions, useRescan, useSetConnector, useTestRead } from "../hooks/heartbeat";
import { Failure, Loading } from "../ui";
import { N8nHost } from "./N8nHost";
import { IngestModel } from "./IngestModel";
import { LearningSettings } from "./LearningSettings";
import { Onboarding } from "./Onboarding";

function every(v: number): string {
  if (v === 1440) return "daily";
  if (v === 60) return "every hour";
  return v % 60 === 0 ? `every ${v / 60} hours` : `every ${v} min`;
}

const chip = (on: boolean) =>
  `padding:5px 11px;border-radius:99px;font:${on ? 500 : 400} 12px Geist;cursor:pointer;${
    on ? "background:var(--ink);color:var(--bg);border:1px solid var(--ink)" : "background:transparent;color:var(--ink);border:1px solid var(--line2)"
  }`;

const STATUS_WORDS: Record<string, string> = {
  ok: "Reading",
  off: "Off",
  unhealthy_sign_in: "Sign in again",
  provider_limit: "Provider limit",
  cannot_confirm_read_only: "Cannot confirm read-only",
  error: "Could not read",
};

function canTurnOn(c: HbConnector): boolean {
  return c.present && c.how !== "computer" && c.status !== "cannot_confirm_read_only";
}

export function HeartbeatSettings() {
  const status = useHeartbeat();
  const regions = useRegions();
  const save = useHeartbeatSettings();
  const rescan = useRescan();
  const toggle = useSetConnector();
  const test = useTestRead();
  const fixes = useN8nFix();
  if (status.isLoading) return <Loading what="Reading the heartbeat" />;
  if (status.error || !status.data) return <Failure error={status.error} retry={() => void status.refetch()} />;
  const s = status.data;
  const names = new Map((regions.data ?? []).map((r) => [r.id, r.name]));
  const dot = s.paused ? "var(--faint)" : s.state === "ready" ? "oklch(0.66 0.14 150)" : "oklch(0.68 0.14 35)";
  return (
    <section aria-label="Heartbeat" style={css("display:flex;flex-direction:column;gap:14px;padding:18px 20px;border-radius:18px;border:1px solid var(--line)")}>
      <div style={css("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
        <span aria-hidden="true" style={css(`width:10px;height:10px;border-radius:50%;flex:none;background:${dot}`)} />
        <span style={css("font:500 16px Geist;flex:1")}>Heartbeat</span>
        <span role="status" style={css("font:400 12.5px Geist;color:var(--muted)")}>
          {s.paused ? "Paused" : s.state === "ready" ? `Every ${s.cadence} min` : s.line}
        </span>
      </div>
      <span style={css("font:400 13.5px/1.5 Geist;color:var(--ink2);max-width:640px")}>
        On each beat, {s.cli_label} reads through the connectors already set up in your CLIs, then updates the live status of each region and the projects inside it. Read-only: it never sends, posts or spends.
      </span>
      <Onboarding connectors={s.connectors} />
      <div role="group" aria-label="Beat every" style={css("display:flex;gap:6px;flex-wrap:wrap;align-items:center")}>
        <span style={css("font:400 12.5px Geist;color:var(--muted);width:96px")}>Beat every</span>
        {s.cadences.map((v) => (
          <button key={v} type="button" aria-pressed={s.cadence === v} disabled={save.isPending} onClick={() => save.mutate({ cadence: v })} style={css(chip(s.cadence === v))}>
            {v} min
          </button>
        ))}
      </div>
      <div role="group" aria-label="Quiet hours" style={css("display:flex;gap:6px;flex-wrap:wrap;align-items:center")}>
        <span style={css("font:400 12.5px Geist;color:var(--muted);width:96px")}>Quiet hours</span>
        {s.quiet_options.map((o) => (
          <button
            key={o.id}
            type="button"
            aria-pressed={s.quiet_hours === o.id}
            disabled={save.isPending}
            onClick={() => save.mutate({ quiet_hours: o.id })}
            style={css(chip(s.quiet_hours === o.id))}
          >
            {o.label}
          </button>
        ))}
      </div>
      {save.error ? <Failure error={save.error} /> : null}
      <div style={css("display:flex;flex-direction:column")}>
        <div style={css("display:flex;justify-content:space-between;align-items:baseline;gap:10px;padding-bottom:6px;flex-wrap:wrap")}>
          <span style={css("font:500 13px Geist")}>Connectors it reads</span>
          <button
            type="button"
            disabled={rescan.isPending}
            onClick={() => rescan.mutate()}
            style={css("padding:7px 14px;border-radius:99px;border:1px solid var(--line2);background:transparent;font:500 12.5px Geist;color:var(--ink);cursor:pointer")}
          >
            {rescan.isPending ? "Looking…" : "Find connectors in my CLIs"}
          </button>
        </div>
        <N8nHost />
        <IngestModel />
        <LearningSettings />
        {rescan.data ? <span style={css("font:400 13px Geist;color:var(--ink2);padding-bottom:8px")}>{rescan.data.line}</span> : null}
        {rescan.error ? <Failure error={rescan.error} /> : null}
        {toggle.error ? <Failure error={toggle.error} /> : null}
        {test.error ? <Failure error={test.error} /> : null}
        {fixes.suggest.error ? <Failure error={fixes.suggest.error} /> : null}
        {fixes.decide.error ? <Failure error={fixes.decide.error} /> : null}
        {s.connectors.length ? (
          s.connectors.map((c) => {
            const feeds = c.feeds.length ? `Feeds ${c.feeds.map((f) => names.get(f) ?? f).join(", ")}` : "Feeds any region it fits";
            const items = c.last_read_at ? ` · ${c.last_items} ${c.last_items === 1 ? "item" : "items"} last beat` : "";
            const readOnly = c.how === "folder" || c.how === "memory" || c.tools.length ? " · read-only" : "";
            return (
              <div key={c.id} style={css("display:flex;align-items:center;gap:12px;padding:10px 0;border-top:1px solid var(--line);flex-wrap:wrap")}>
                <div style={css("flex:1;min-width:200px;display:flex;flex-direction:column;gap:2px")}>
                  <span style={css(`font:500 14px Geist${c.present ? "" : ";color:var(--muted)"}`)}>{c.name}</span>
                  <span style={css("font:400 12px Geist;color:var(--muted)")}>
                    {c.cli_label} · {c.how_label}
                    {readOnly}
                    {items}
                  </span>
                  {c.status_line ? <span style={css("font:400 12px/1.45 Geist;color:var(--ink2)")}>{c.status_line}</span> : null}
                  <SignIn c={c} />
                  {!c.enabled && c.present && !["folder", "computer"].includes(c.how) ? <ConnectorSetup c={c} canTurnOn={canTurnOn(c)} /> : null}
                  {c.enabled && checkable(c) ? (
                    <span style={css("display:flex;gap:8px;align-items:center;flex-wrap:wrap;font:400 12px/1.45 Geist;color:var(--ink2)")}>
                      <button
                        type="button"
                        disabled={test.isPending}
                        onClick={() => test.mutate(c.id)}
                        style={css(chip(false) + ";align-self:flex-start")}
                      >
                        {test.isPending && test.variables === c.id ? "Testing…" : "Test read"}
                      </button>
                      {test.data && test.data.id === c.id ? (
                        <span role="status">
                          {test.data.passed ? "Ready for heartbeats. " : "Not ready. "}
                          {testLine(test.data)}
                        </span>
                      ) : null}
                    </span>
                  ) : null}
                  {c.how === "n8n" && c.fix ? (
                    <span style={css("display:flex;gap:8px;align-items:center;flex-wrap:wrap;font:400 12.5px/1.45 Geist")}>
                      Suggested fix: {c.fix}
                      <button type="button" disabled={fixes.decide.isPending} onClick={() => fixes.decide.mutate({ id: c.id, keep: true })} style={css(chip(true))}>
                        Keep
                      </button>
                      <button type="button" disabled={fixes.decide.isPending} onClick={() => fixes.decide.mutate({ id: c.id, keep: false })} style={css(chip(false))}>
                        Skip
                      </button>
                    </span>
                  ) : c.how === "n8n" && c.status === "error" ? (
                    <button type="button" disabled={fixes.suggest.isPending} onClick={() => fixes.suggest.mutate(c.id)} style={css(chip(false) + ";align-self:flex-start")}>
                      {fixes.suggest.isPending ? "Asking…" : "Suggest a fix"}
                    </button>
                  ) : null}
                  {c.enabled && c.how !== "folder" ? <GoalFields c={c} /> : null}
                </div>
                <span style={css("font:400 12.5px Geist;color:var(--ink2);min-width:160px")}>{feeds}</span>
                {c.how === "folder" ? (
                  <span style={css("font:400 12.5px Geist;color:var(--muted)")}>Every beat · no tokens</span>
                ) : (
                  <label style={css("display:flex;align-items:center;gap:6px;font:400 12.5px Geist;color:var(--ink2)")}>
                    Read
                    <select
                      aria-label={`How often ${c.name} is read`}
                      value={c.cadence_minutes ?? 0}
                      disabled={toggle.isPending}
                      onChange={(e) => toggle.mutate({ id: c.id, cadence_minutes: Number(e.target.value) })}
                      style={css("font:400 12.5px Geist;padding:4px 6px;border-radius:8px;border:1px solid var(--line2);background:var(--surface);color:var(--ink)")}
                    >
                      <option value={0}>every beat</option>
                      {(s.own_cadences ?? s.cadences)
                        .filter((v) => v > s.cadence)
                        .map((v) => (
                          <option key={v} value={v}>
                            {every(v)}
                          </option>
                        ))}
                    </select>
                  </label>
                )}
                <button
                  type="button"
                  aria-pressed={c.enabled}
                  aria-label={`${c.name}: ${c.enabled ? STATUS_WORDS[c.status] ?? "Reading" : "Off"}. ${c.enabled ? "Turn off" : "Turn on"}`}
                  disabled={toggle.isPending || (!c.enabled && !canTurnOn(c))}
                  onClick={() => toggle.mutate({ id: c.id, enabled: !c.enabled })}
                  style={css(chip(c.enabled) + (!c.enabled && !canTurnOn(c) ? ";opacity:.55" : ""))}
                >
                  {c.enabled ? STATUS_WORDS[c.status] ?? "Reading" : "Off"}
                </button>
              </div>
            );
          })
        ) : (
          <span style={css("font:400 13.5px Geist;color:var(--muted);padding:10px 0;border-top:1px solid var(--line)")}>
            No connectors yet. Find connectors in your CLIs to read the MCP servers Claude Code and Codex are set up with.
          </span>
        )}
      </div>
      <span style={css("font:400 12.5px/1.5 Geist;color:var(--muted)")}>
        {costLine(s)}. Gnomon never holds these logins; each CLI uses its own. Connectors that work through computer use are listed but not read yet.
      </span>
    </section>
  );
}
