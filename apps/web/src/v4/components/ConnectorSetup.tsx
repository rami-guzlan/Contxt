// Settings, Approval, the Heartbeat block: setting a connector up for heartbeats, the same for
// every source (v4 backend plan, 17.2). Found, then the check (signed in, read-only, one test
// read, nothing kept), then what to look for and leave out, how often, and on.

import { css } from "../css";
import { type HbConnector, testLine, type TestRead, useSetConnector, useTestRead } from "../hooks/heartbeat";

const field = "font:400 12.5px Geist;padding:5px 8px;border-radius:8px;border:1px solid var(--line2);background:var(--surface);color:var(--ink);max-width:420px;width:100%;box-sizing:border-box";
const chip = (on: boolean) =>
  `padding:5px 11px;border-radius:99px;font:${on ? 500 : 400} 12px Geist;cursor:pointer;align-self:flex-start;${
    on ? "background:var(--ink);color:var(--bg);border:1px solid var(--ink)" : "background:transparent;color:var(--ink);border:1px solid var(--line2)"
  }`;

/** Reads that go through a model: a check can sign in and test-read them. */
export function checkable(c: HbConnector): boolean {
  return c.present && !["folder", "memory", "n8n", "computer"].includes(c.how);
}

function Mark({ ok }: { ok: boolean | null }) {
  const sign = ok === null ? "○" : ok ? "✓" : "✕";
  return (
    <span aria-hidden="true" style={css(`width:14px;flex:none;color:${ok === false ? "oklch(0.6 0.16 30)" : ok ? "oklch(0.6 0.14 150)" : "var(--faint)"}`)}>
      {sign}
    </span>
  );
}

function Step({ ok, label, children }: { ok: boolean | null; label: string; children?: React.ReactNode }) {
  return (
    <li style={css("display:flex;gap:8px;align-items:flex-start;font:400 12.5px/1.5 Geist;color:var(--ink2)")}>
      <Mark ok={ok} />
      <span style={css("display:flex;flex-direction:column;gap:4px;flex:1")}>
        <span>
          <span style={css("font-weight:500;color:var(--ink)")}>{label}</span>
          {ok === true ? " · done" : ok === false ? " · needs you" : ""}
        </span>
        {children}
      </span>
    </li>
  );
}

/** What a connector's reads look for and leave out, saved when the field is left. */
export function GoalFields({ c }: { c: HbConnector }) {
  const save = useSetConnector();
  return (
    <span style={css("display:flex;flex-direction:column;gap:6px")}>
      <input
        key={`${c.id}:ask:${c.ask ?? ""}`}
        aria-label={`What ${c.name} looks for`}
        placeholder="What to look for, in your words (optional)"
        defaultValue={c.ask ?? ""}
        onBlur={(e) => {
          if (e.target.value.trim() !== (c.ask ?? "")) save.mutate({ id: c.id, ask: e.target.value.trim() });
        }}
        style={css(field)}
      />
      {c.how !== "memory" ? (
        <input
          key={`${c.id}:skip:${c.skip ?? ""}`}
          aria-label={`What ${c.name} leaves out`}
          placeholder="Leave out items that mention, comma separated (optional)"
          defaultValue={c.skip ?? ""}
          onBlur={(e) => {
            if (e.target.value.trim() !== (c.skip ?? "")) save.mutate({ id: c.id, skip: e.target.value.trim() });
          }}
          style={css(field)}
        />
      ) : null}
    </span>
  );
}

function stepOk(t: TestRead | undefined, step: string): boolean | null {
  const s = t?.steps.find((x) => x.step === step);
  return s ? s.ok : null;
}

/** The setup steps for a connector that is not on yet: found to on, without a terminal. */
export function ConnectorSetup({ c, canTurnOn }: { c: HbConnector; canTurnOn: boolean }) {
  const test = useTestRead();
  const toggle = useSetConnector();
  const t = test.data && test.data.id === c.id ? test.data : undefined;
  const needsCheck = checkable(c);
  const checked = needsCheck ? (t ? t.passed : null) : true;
  const failed = t?.steps.find((s) => !s.ok);
  return (
    <ol aria-label={`Set up ${c.name}`} style={css("list-style:none;margin:4px 0 0;padding:10px 12px;border-radius:12px;background:var(--soft);display:flex;flex-direction:column;gap:8px")}>
      <Step ok={c.present} label="Found">
        <span>{c.present ? `In ${c.found_in}.` : "Not found on this computer now. Find connectors in your CLIs again."}</span>
      </Step>
      {needsCheck ? (
        <Step ok={checked} label="Signed in, read-only, test read">
          <span style={css("display:flex;gap:8px;align-items:center;flex-wrap:wrap")}>
            <button type="button" disabled={test.isPending} onClick={() => test.mutate(c.id)} style={css(chip(false))}>
              {test.isPending ? "Testing…" : t ? "Test again" : "Test read"}
            </button>
            {t ? (
              <span role="status">
                {t.passed ? "Ready for heartbeats. " : "Not ready. "}
                {testLine(t)}
              </span>
            ) : (
              <span>One sample read; nothing it finds is kept.</span>
            )}
          </span>
          {failed && failed.step === "signed in" ? <span>Sign in with the steps above, then test again.</span> : null}
          {stepOk(t, "read-only") === false ? <span>No tool of it only reads, so the heartbeat cannot use it.</span> : null}
        </Step>
      ) : null}
      <Step ok={c.ask || c.skip ? true : null} label="What to look for and leave out">
        <GoalFields c={c} />
      </Step>
      <Step ok={null} label="How often">
        <span>Choose how often it is read on the right; every beat is the default.</span>
      </Step>
      <Step ok={c.enabled} label="On">
        <button
          type="button"
          disabled={toggle.isPending || !canTurnOn || checked === false}
          onClick={() => toggle.mutate({ id: c.id, enabled: true })}
          style={css(chip(true) + (!canTurnOn || checked === false ? ";opacity:.55" : ""))}
        >
          Turn on {c.name}
        </button>
        {checked === null ? <span>Test it first to see what a read finds and costs, or turn it on now.</span> : null}
      </Step>
    </ol>
  );
}
