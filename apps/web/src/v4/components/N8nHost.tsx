// Gnomon's own n8n, on this computer: it reads your apps with the sign-ins you give it there, so
// the heartbeat spends no tokens reading. Install once, start or stop, and open it to sign in.

import { css } from "../css";
import { useN8nHost, useN8nHostAction } from "../hooks/heartbeat";
import { Btn, Failure, Loading } from "../ui";

export function N8nHost() {
  const host = useN8nHost();
  const act = useN8nHostAction();
  if (host.isLoading) return <Loading what="Looking for n8n" />;
  if (host.error || !host.data) return <Failure error={host.error} retry={() => void host.refetch()} />;
  const h = host.data;
  return (
    <div style={css("display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:12px 14px;border-radius:14px;background:var(--soft)")}>
      <div style={css("flex:1;min-width:220px;display:flex;flex-direction:column;gap:2px")}>
        <span style={css("font:500 14px Geist")}>n8n on this computer{h.version ? ` · ${h.version}` : ""}</span>
        <span role="status" style={css("font:400 12.5px/1.45 Geist;color:var(--ink2)")}>
          {h.line}
        </span>
        <span style={css("font:400 12px/1.45 Geist;color:var(--muted)")}>Reads your apps with the sign-ins you give n8n, read-only, so a read costs no tokens.</span>
      </div>
      {!h.installed ? (
        <Btn kind="primarySm" disabled={act.isPending || h.installing} onClick={() => act.mutate("install")}>
          {h.installing ? "Installing…" : "Host n8n here"}
        </Btn>
      ) : h.running ? (
        <>
          <a href={h.url} target="_blank" rel="noreferrer" style={css("font:500 12.5px Geist;color:var(--ink)")}>
            Open n8n
          </a>
          <Btn kind="ghostSm" disabled={act.isPending} onClick={() => act.mutate("stop")}>
            Stop
          </Btn>
        </>
      ) : (
        <Btn kind="primarySm" disabled={act.isPending} onClick={() => act.mutate("start")}>
          Start n8n
        </Btn>
      )}
      {act.error ? <Failure error={act.error} /> : null}
    </div>
  );
}
