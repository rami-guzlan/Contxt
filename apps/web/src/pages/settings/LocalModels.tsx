// Settings, On this computer, Local models (brain-logic plan 5.11.16): the machine and its setup,
// each role's model and the pinned options (download, make the default, remove), whether the
// retrieval engine runs in full or in fallback, and the knowledge agent's Claude Code opt-in.

import { useActLocalModels, useLocalModels } from "../../api/hooks";
import type { LocalModelOption, LocalModelRole, LocalModelsOverview } from "../../api/types";
import { ErrorNote, Section } from "../../components/ui";

// What each role does, in a line (brain-logic plan 5.11.16).
const ROLE_HELP: Record<LocalModelRole["role"], string> = {
  embed: "Finds notes and document parts by meaning.",
  rerank: "Scores how relevant each candidate is to a request.",
  decide: "Answers the engine's yes-or-no questions: should a request get anything, does a note add anything new.",
  agent: "The knowledge agent: suggests how to keep your Brain current.",
};

function optionFacts(o: LocalModelOption): string {
  return [
    o.size_gb != null ? `${o.size_gb} GB on disk` : "",
    o.ram_gb != null ? `${o.ram_gb} GB of RAM` : "",
    o.measured?.speed_ms != null ? `${o.measured.speed_ms} ms here` : "",
    o.measured?.quality != null ? `quality ${Math.round(o.measured.quality * 100)}% here` : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

/** This computer's local models: the machine and its setup, each role's model and the pinned
 * options (download, make the default, remove), and whether the engine runs in full. */
export function LocalModels() {
  const { data, error } = useLocalModels();
  const act = useActLocalModels();
  if (!data) return error ? <ErrorNote error={error} /> : null;
  if (!data.enabled || !data.machine || !data.roles) return null;
  const m = data.machine;
  const notice = act.data?.notice;
  return (
    <Section title="Local models">
      <p>
        This computer: {m.ram_gb} GB of RAM{m.gpu ? `, ${m.gpu} with ${m.gpu_gb} GB` : ", no GPU for models"}
        {m.apple_silicon ? ", Apple Silicon" : ""}. Setup: <strong>{data.setup_label}</strong>, about {data.ram_in_use_gb} GB of RAM for its
        models.
      </p>
      <p role="status">
        {data.engine?.ready
          ? "The retrieval engine runs in full: the local models choose what goes into each brief."
          : `The retrieval engine runs in fallback, on words and meaning: ${data.engine?.reason ?? "no model service"}.`}
      </p>
      {data.fallbacks?.length ? (
        <ul className="plain muted small" aria-label="Fallbacks on this computer">
          {data.fallbacks.map((line) => (
            <li key={line}>{line}.</li>
          ))}
        </ul>
      ) : null}
      {data.roles.map((role) => (
        <LocalRole key={role.role} role={role} data={data} act={act} />
      ))}
      <label className="check">
        <input
          type="checkbox"
          checked={Boolean(data.agent_claude_code)}
          disabled={act.isPending}
          onChange={(event) => act.mutate({ action: "claude_code", on: event.target.checked })}
        />
        Let the knowledge agent use Claude Code. It uses your own plan, and the agent's work then leaves this computer.
      </label>
      <div className="row">
        <button type="button" disabled={act.isPending} onClick={() => act.mutate({ action: "check" })}>
          Check this computer again
        </button>
        <button type="button" disabled={act.isPending || !data.engine?.ready} onClick={() => act.mutate({ action: "speed" })}>
          Time the models
        </button>
      </div>
      {notice ? (
        <p className="warning small" role="status">
          {notice}.
        </p>
      ) : null}
      <ErrorNote error={act.error} />
    </Section>
  );
}

function LocalRole({ role, data, act }: { role: LocalModelRole; data: LocalModelsOverview; act: ReturnType<typeof useActLocalModels> }) {
  return (
    <div className="local-role">
      <h3>
        {role.label.charAt(0).toUpperCase() + role.label.slice(1)}: {role.model ?? "none on this setup"}
      </h3>
      <p className="muted small">{ROLE_HELP[role.role]}</p>
      <ul className="list compact-list" aria-label={`${role.label} models`}>
        {role.options.map((o) => {
          const downloading = data.downloading?.includes(o.name);
          return (
            <li key={o.name}>
              <strong>{o.name}</strong> {o.in_use ? <span className="kind-chip">in use</span> : null}
              {o.setup_default && !o.in_use ? <span className="kind-chip">this setup's default</span> : null}
              <span className="muted small"> {optionFacts(o)}</span>
              <div className="row small">
                {o.with_brain ? (
                  <span className="muted">{o.downloaded ? "Here, kept with your Brain" : "Kept with your Brain: download it under Matching by meaning"}</span>
                ) : downloading ? (
                  <span role="status">Downloading…</span>
                ) : o.downloaded ? (
                  <span className="muted">Downloaded and verified</span>
                ) : !o.pinned ? (
                  <span className="muted">Not pinned yet: pinned on a computer that runs it</span>
                ) : (
                  <button type="button" className="link" disabled={act.isPending} onClick={() => act.mutate({ action: "download", name: o.name })}>
                    Download {o.name}
                  </button>
                )}
                {!o.in_use ? (
                  <button
                    type="button"
                    className="link"
                    disabled={act.isPending || !o.fits || !o.downloaded}
                    title={!o.fits ? o.fit_reason : !o.downloaded ? "Download it first" : undefined}
                    onClick={() => act.mutate({ action: "default", name: o.name })}
                  >
                    Make {o.name} the default
                  </button>
                ) : null}
                {o.downloaded && !o.in_use && !o.with_brain ? (
                  <button type="button" className="link" disabled={act.isPending} onClick={() => act.mutate({ action: "remove", name: o.name })}>
                    Remove {o.name}
                  </button>
                ) : null}
              </div>
              {!o.fits ? <p className="muted small">Will not fit here: {o.fit_reason}.</p> : null}
              {o.slow ? <p className="warning small">{o.slow}.</p> : null}
              {data.errors?.[o.name] ? <p className="error small">{data.errors[o.name]}</p> : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
