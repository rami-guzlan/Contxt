// Triage first (brain-logic plan 7.2, step 2): a cheaper model reads what you bring in by parts
// and only the parts that may hold something durable reach the careful reading. Off until it is
// measured; a cloud model triages redacted text when your preset says so.

import { useAgent, useDistillSettings, useSetDistillSettings } from "../api/hooks";

export function TriageChoice() {
  const { data: settings } = useDistillSettings();
  const { data: agent } = useAgent();
  const set = useSetDistillSettings();
  if (!settings) return null;
  const local = (agent?.models ?? []).filter((m) => m.kind !== "cli" && m.available);
  return (
    <label className="field">
      <span>Triage first</span>
      <select
        aria-label="Triage first"
        value={settings.triage ?? ""}
        disabled={set.isPending}
        onChange={(event) => set.mutate({ ...settings, triage: event.target.value || null })}
      >
        <option value="">Off: read everything</option>
        <option value="claude">With Claude Code</option>
        {local.map((m) => (
          <option key={m.id} value={m.id}>
            With {m.label}
          </option>
        ))}
      </select>
      <span className="muted small">A cheaper first reading skips small talk, so long recordings cost less. Off until it proves itself.</span>
    </label>
  );
}
