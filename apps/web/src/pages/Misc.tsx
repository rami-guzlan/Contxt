import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import { get, patch } from "../api/client";
import {
  keys,
  useActors,
  useBringLegacyIn,
  useDistillSettings,
  useExportLegacy,
  useInvalidate,
  useLegacy,
  useMe,
  useSearch,
  useSetDistillSettings,
} from "../api/hooks";
import type { LegacyReport, LegacySummary } from "../api/types";
import { Empty, ErrorNote, Field, KeyValues, Loading, Section, Tabs } from "../components/ui";
import { plural, when } from "../lib/format";
import { PoliciesPage } from "./brain/Policies";
import { entryUrl } from "./brain/shared";
import { ConnectionsPage } from "./Connections";
import { SetupPage } from "./Setup";

export function SearchPage() {
  const [params] = useSearchParams();
  const q = params.get("q") ?? "";
  const { data, isLoading } = useSearch(q);
  if (isLoading) return <Loading />;
  const total = data ? data.brain.length + data.projects.length + data.notes.length : 0;
  return (
    <div className="page">
      <h1>Search: {q}</h1>
      {!total ? <Empty why="Nothing matches. Try other words." /> : null}
      {data?.projects.length ? (
        <Section title="Projects">
          <ul className="list">
            {data.projects.map((project) => (
              <li key={project.id}>
                <Link to={`/projects/${encodeURIComponent(project.id)}`}>{project.title}</Link>
                {project.summary ? <span className="muted"> · {project.summary}</span> : null}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
      {data?.brain.length ? (
        <Section title="In the Brain">
          <ul className="list">
            {data.brain.map((hit) => (
              <li key={hit.id}>
                <Link to={entryUrl(hit.id)}>{hit.title}</Link>
                {hit.summary ? <span className="muted"> · {hit.summary}</span> : null}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
      {data?.notes.length ? (
        <Section title="Your notes">
          <ul className="list">
            {data.notes.map((note) => (
              <li key={note.id}>
                <Link to={`/capture/${note.id}`}>{note.title}</Link>
                <span className="muted small"> · changed {when(note.updated_at)}</span>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
    </div>
  );
}

const SETTINGS_TABS = [
  { id: "start", label: "Get started" },
  { id: "workspace", label: "Workspace" },
  { id: "connections", label: "AI apps" },
  { id: "policies", label: "Brain policies" },
] as const;

export function SettingsPage() {
  const [params, setParams] = useSearchParams();
  const asked = params.get("tab");
  const tab = asked === "connections" || asked === "start" || asked === "policies" ? asked : "workspace";
  return (
    <div className="page">
      <h1>Settings</h1>
      <Tabs
        tour="settings-tabs"
        tabs={SETTINGS_TABS}
        active={tab}
        onChange={(next) => setParams(next === "workspace" ? {} : { tab: next }, { replace: true })}
      />
      {tab === "connections" ? (
        <ConnectionsPage embedded />
      ) : tab === "start" ? (
        <SetupPage />
      ) : tab === "policies" ? (
        <PoliciesPage />
      ) : (
        <WorkspaceSettings />
      )}
    </div>
  );
}

function WorkspaceSettings() {
  const { data: me } = useMe();
  const invalidate = useInvalidate();
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: () => get<{ version: string; schema_revision: string; brain: boolean }>("/api/health"),
  });
  const [name, setName] = useState("");
  const [timezone, setTimezone] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  async function save(event: FormEvent) {
    event.preventDefault();
    try {
      await patch("/api/workspace", { name: name || undefined, timezone: timezone || undefined });
      setSaved(true);
      await invalidate(keys.me, keys.home);
    } catch (caught) {
      setError(caught);
    }
  }
  return (
    <>
      <Section title="Workspace">
        <form className="inline-form" onSubmit={save}>
          <Field label="Name">
            <input placeholder={me?.workspace.name} value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Timezone" hint="IANA name, such as America/New_York.">
            <input placeholder={me?.workspace.timezone} value={timezone} onChange={(e) => setTimezone(e.target.value)} />
          </Field>
          <button type="submit" className="primary">
            Save
          </button>
          {saved ? <span className="muted">Saved.</span> : null}
          <ErrorNote error={error} />
        </form>
      </Section>
      <Section title="What saves straight into the Brain">
        <p>
          Files, decisions and progress go in at once; rules and preferences your AI captures wait for you in Review. Change this
          per type and per source in <Link to="/settings?tab=policies">Policies</Link>.
        </p>
      </Section>
      <AiWork />
      <EarlierWorkspace />
      <Section title="System">
        <KeyValues
          rows={[
            ["Version", health?.version],
            ["Database revision", health?.schema_revision],
            ["Brain connected", health ? (health.brain ? "yes" : "no") : ""],
            ["Signed in as", me ? `${me.name} (${me.kind})` : ""],
          ]}
        />
      </Section>
      <Section title="Backups and data">
        <p>
          Your data lives in the data directory on this machine, and your Brain in its own folder with its history in git. Back
          both up with <code>workspace backup --with-brain</code>; restore into an empty folder with <code>workspace restore</code>.
        </p>
      </Section>
    </>
  );
}

/** Which model does the AI work the app starts ("find what to remember", a reconcile). */
function AiWork() {
  const { data: actors } = useActors();
  const { data: settings } = useDistillSettings();
  const set = useSetDistillSettings();
  const models = (actors ?? []).filter((a) => a.kind === "model" && !a.disabled_at);
  return (
    <Section title="AI work the app starts">
      <p className="muted">
        Finding what to remember in a note, or reconciling two pieces that clash, is work a model does. With one model
        connected, it does it; with several, choose one. Claude Code on this computer can also take it at once.
      </p>
      {models.length ? (
        <Field label="Model">
          <select
            value={settings?.assignee_id ?? ""}
            disabled={set.isPending}
            onChange={(event) => set.mutate({ assignee_id: event.target.value || null })}
          >
            <option value="">{models.length === 1 ? `${models[0]?.name} (the only one)` : "Choose each time"}</option>
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </Field>
      ) : (
        <p>
          No model is connected yet. <Link to="/settings?tab=connections">Connect one</Link>.
        </p>
      )}
      <ErrorNote error={set.error} />
    </Section>
  );
}

/** The workspace before it became a Brain app: a copy as files, and its context moved in. */
function EarlierWorkspace() {
  const { data: legacy, error } = useLegacy();
  const exporting = useExportLegacy();
  const bringing = useBringLegacyIn();
  const [report, setReport] = useState<LegacyReport | null>(null);
  if (error) return null; // only the owner sees it
  if (!legacy || !legacy.has_any) return null;
  return (
    <Section title="Your earlier workspace" tour="settings-legacy">
      <p>
        Goals, to-dos, meetings, project memory, sheets and canvases are no longer part of the app. Nothing was deleted: copy it
        all out as files, and bring what your AI should know into the Brain.
      </p>
      <p className="muted small">It holds {holdings(legacy)}.</p>
      <div className="stack">
        <div className="row wrap">
          <button type="button" disabled={exporting.isPending} onClick={() => exporting.mutate()}>
            {legacy.exported_at ? "Copy it out again" : "Copy it out as files"}
          </button>
          {legacy.exported_at ? (
            <span className="muted small">
              Copied {when(legacy.exported_at)} to <code>{legacy.export_dir}</code>
            </span>
          ) : null}
        </div>
        {exporting.data ? (
          <p className="muted small">
            Wrote {plural(exporting.data.files, "file")} to <code>{exporting.data.dir}</code>.
          </p>
        ) : null}
        <div className="row wrap">
          <button
            type="button"
            className="primary"
            disabled={bringing.isPending}
            onClick={() => bringing.mutate(undefined, { onSuccess: setReport })}
          >
            {legacy.moved_at ? "Bring in what is new" : "Bring it into the Brain"}
          </button>
          {legacy.moved_at ? <span className="muted small">Brought in {when(legacy.moved_at)}</span> : null}
        </div>
        {bringing.isPending ? (
          <p className="muted small" role="status">
            Bringing it in. This can take a few minutes: each file is read and each change is saved with its history.
          </p>
        ) : null}
        <p className="muted small">
          Each project gets (or is matched to) a Brain project; its memories wait for you in Review; meeting transcripts and
          documents are filed into their projects; open to-dos become each project's next steps. Running it again adds only what
          is new.
        </p>
        {report ? <Brought report={report} /> : null}
        <ErrorNote error={exporting.error ?? bringing.error} />
      </div>
    </Section>
  );
}

function holdings(legacy: LegacySummary): string {
  const c = legacy.counts;
  const parts = [
    c.projects ? plural(c.projects, "project") : "",
    c.goals ? plural(c.goals, "goal") : "",
    c.todos_open ? plural(c.todos_open, "open to-do") : "",
    c.memories ? plural(c.memories, "project memory", "project memories") : "",
    c.transcripts ? plural(c.transcripts, "meeting transcript") : "",
    c.documents ? plural(c.documents, "document") : "",
    c.sheets ? plural(c.sheets, "sheet") : "",
    c.canvases ? plural(c.canvases, "canvas", "canvases") : "",
  ].filter(Boolean);
  return parts.join(", ") || "nothing left to move";
}

function Brought({ report }: { report: LegacyReport }) {
  return (
    <div className="decided" role="status">
      <div>
        <strong>
          {report.projects_started.length
            ? `Started ${plural(report.projects_started.length, "project")} (${report.projects_started.join(", ")}); `
            : ""}
          matched {plural(report.projects_matched, "project")}; {plural(report.notes_proposed, "memory", "memories")} waiting in{" "}
          <Link to="/review">Review</Link>; {plural(report.files_filed, "file")} filed; {plural(report.next_steps, "to-do")} made next
          steps.
        </strong>
        {report.todo_note ? (
          <p>
            Every open to-do is in your note{" "}
            <Link to={`/capture/${report.todo_note}`}>Open to-dos from the earlier workspace</Link>.
          </p>
        ) : null}
        {report.refused.length || report.projects_left.length ? (
          <ul className="error">
            {[...report.projects_left, ...report.refused].map((r) => (
              <li key={`${r.title}:${r.why}`}>
                {r.title}: {r.why}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
