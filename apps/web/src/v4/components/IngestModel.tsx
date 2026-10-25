// Which Claude model reads what comes in: the distill of what you capture and the heartbeat's
// judge. Haiku is the default because reading is most of the token cost of keeping a Brain.

import { useDistillSettings, useSetDistillSettings } from "../../api/hooks";
import { css } from "../css";
import { Failure } from "../ui";

const CHOICES: [string, string][] = [
  ["haiku", "Haiku (recommended)"],
  ["sonnet", "Sonnet"],
  ["opus", "Opus"],
  ["", "Claude Code's default"],
];

export function IngestModel() {
  const settings = useDistillSettings();
  const save = useSetDistillSettings();
  const current = settings.data?.model ?? "";
  return (
    <div style={css("display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:10px 0;border-top:1px solid var(--line)")}>
      <label htmlFor="ingest-model" style={css("flex:1;min-width:220px;display:flex;flex-direction:column;gap:2px")}>
        <span style={css("font:500 14px Geist")}>Reading what comes in</span>
        <span style={css("font:400 12.5px/1.45 Geist;color:var(--muted)")}>The model that reads your captures and the heartbeat's news. Haiku keeps this cheap.</span>
      </label>
      <select
        id="ingest-model"
        value={current}
        disabled={settings.isLoading || save.isPending}
        onChange={(e) => save.mutate({ assignee_id: settings.data?.assignee_id ?? null, model: e.target.value || null })}
        style={css("font:400 13px Geist;padding:6px 8px;border-radius:8px;border:1px solid var(--line2);background:var(--surface);color:var(--ink)")}
      >
        {CHOICES.map(([id, label]) => (
          <option key={id || "default"} value={id}>
            {label}
          </option>
        ))}
      </select>
      {save.error ? <Failure error={save.error} /> : null}
    </div>
  );
}
