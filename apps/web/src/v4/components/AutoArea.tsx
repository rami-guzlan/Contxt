// An auto-governed area's strip, wired to "Govern this myself" (the auto default, sections 2
// and 3): in Auto it sits above the area, which stays fully usable; "Govern this myself" makes
// that one area wait for the owner, and "Hand it back" returns it to the governing AI. Governed
// Brains show nothing here.

import { useGovernMyself, usePolicy } from "../api";
import { css } from "../css";
import { Btn, Failure } from "../ui";
import { AutoStrip, type AutoStripProps } from "./AutoStrip";

export function AutoArea({ govKey, ...strip }: Omit<AutoStripProps, "onGovern" | "governing"> & { govKey: string }) {
  const policy = usePolicy();
  const gov = useGovernMyself(govKey);
  if (policy.data?.mode !== "auto") return null;
  return (
    <div style={css("display:flex;flex-direction:column;gap:8px")}>
      {gov.governed ? (
        <div style={css("display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:12px 16px;border-radius:14px;background:var(--soft)")}>
          <span style={css("flex:1;min-width:200px;font:400 13.5px/1.5 Geist;color:var(--ink2)")}>
            You govern {strip.area} yourself: changes here wait for you in Catch up.
          </span>
          <Btn kind="ghostSm" disabled={gov.pending} onClick={gov.toggle}>
            Hand it back
          </Btn>
        </div>
      ) : (
        <AutoStrip {...strip} onGovern={gov.toggle} governing={gov.pending} />
      )}
      {gov.error ? <Failure error={gov.error} /> : null}
    </div>
  );
}
