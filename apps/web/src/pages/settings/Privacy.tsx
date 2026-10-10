// Settings, Approval: redaction for cloud models (brain-logic plan 7.2, decision 13). Emails,
// phone numbers, account and ID numbers in what you bring in are hidden from a cloud model that
// reads it; on under the careful and regulated presets, off under personal unless turned on.

import { useBrainPolicies, useSetBrainPolicies } from "../../api/hooks";

export function RedactCloud() {
  const { data: policies } = useBrainPolicies();
  const set = useSetBrainPolicies();
  if (!policies) return null;
  return (
    <label className="check">
      <input
        type="checkbox"
        checked={policies.redact_cloud !== false}
        disabled={set.isPending}
        onChange={(event) => set.mutate({ redact_cloud: event.target.checked } as never)}
      />{" "}
      Hide private details from cloud AI
      <span className="muted small">
        {" "}
        Emails, phone numbers, account and ID numbers in what you bring in are replaced by what they are ([email], [phone]) before a cloud
        model reads it. You always see them as written.
      </span>
    </label>
  );
}
