import { css } from "../css";
import { type HbConnector, useHeartbeat, useRescan } from "../hooks/heartbeat";

/** How to sign a connector in again, for its source, and Check again (v4 backend plan, 17.2). */
export function SignIn({ c }: { c: HbConnector }) {
  const rescan = useRescan();
  if (!c.sign_in) return null;
  return (
    <span style={css("display:flex;gap:8px;align-items:center;flex-wrap:wrap;font:400 12.5px/1.45 Geist;color:var(--ink2)")}>
      {c.sign_in.steps}
      {c.sign_in.url ? (
        <a href={c.sign_in.url} target="_blank" rel="noreferrer" style={css("font:500 12.5px Geist;color:var(--ink)")}>
          Sign in
        </a>
      ) : null}
      <button type="button" disabled={rescan.isPending} onClick={() => rescan.mutate()} style={css("font:500 12.5px Geist;padding:4px 10px;border-radius:999px;border:1px solid var(--line2);background:var(--surface);color:var(--ink)")}>
        {rescan.isPending ? "Checking…" : "Check again"}
      </button>
    </span>
  );
}

/** Catch up: a card for each connector whose sign-in expired. The others keep being read. */
export function SignInCards() {
  const hb = useHeartbeat();
  const waiting = (hb.data?.connectors ?? []).filter((c) => c.sign_in);
  if (!waiting.length) return null;
  return (
    <section aria-label="Connectors to sign in" style={css("display:flex;flex-direction:column;gap:10px")}>
      {waiting.map((c) => (
        <div key={c.id} style={css("padding:16px 20px;border-radius:20px;background:var(--soft);display:flex;flex-direction:column;gap:6px")}>
          <span style={css("font:500 14px Geist")}>{c.name} needs you to sign in again</span>
          <span style={css("font:400 12.5px Geist;color:var(--muted)")}>Your other connectors keep being read.</span>
          <SignIn c={c} />
        </div>
      ))}
    </section>
  );
}
