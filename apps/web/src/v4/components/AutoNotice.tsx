// The one-time notice of the switch to Auto: Release 1 ships auto-governed, and a Brain from
// before switched once. The owner can keep it (dismiss) or go back to Governed; after that,
// their choice stands and the notice never shows again.

import { usePolicy, useSetPolicy } from "../api";
import { css } from "../css";
import { Btn, Failure } from "../ui";

export function AutoNotice() {
  const policy = usePolicy();
  const set = useSetPolicy();
  const notice = policy.data?.auto_notice;
  if (!notice) return null;
  return (
    <div
      role="status"
      style={css(
        "display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:16px 24px 0;padding:14px 18px;border-radius:16px;background:var(--surface);box-shadow:var(--shadow)",
      )}
    >
      <span style={css("flex:1;min-width:220px;font:400 14px/1.5 Geist;color:var(--ink2)")}>
        <span style={css("font-weight:500;color:var(--ink)")}>Your Brain is auto-governed now.</span> Your AI keeps it current, every change
        has an undo point and its reason, and must-holds, private notes and sealed projects still wait for you. You can go back to Governed.
      </span>
      <Btn kind="primarySm" disabled={set.isPending} onClick={() => set.mutate({ auto_notice: null })}>
        Keep Auto
      </Btn>
      <Btn kind="ghostSm" disabled={set.isPending} onClick={() => set.mutate({ mode: "governed", auto_notice: null })}>
        Go back to Governed
      </Btn>
      {set.error ? <Failure error={set.error} /> : null}
    </div>
  );
}
