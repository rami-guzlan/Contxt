import { useState } from "react";
import { Link, useSearchParams } from "react-router";

import {
  useActors,
  useBringLegacyIn,
  useDistillSettings,
  useExportLegacy,
  useLegacy,
  useSearch,
  useSetDistillSettings,
} from "../api/hooks";
import type { LegacyReport, LegacySummary } from "../api/types";
import { Empty, ErrorNote, Field, Loading, Section } from "../components/ui";
import { plural, when } from "../lib/format";
import { noteUrl } from "../lib/links";
import { entryUrl } from "./brain/shared";

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
                <Link to={noteUrl(note)}>{note.title}</Link>
                <span className="muted small"> · changed {when(note.updated_at)}</span>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
    </div>
  );
}

/** Which model does the AI work the app starts ("find what to remember", a reconcile). */
export function AiWork() {
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
export function EarlierWorkspace() {
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
          Each project gets (or is matched to) a Brain project; its memories wait for you in Catch up; meeting transcripts and
          documents go into their projects (under Careful and Regulated they wait for your yes first, with their names); open to-dos
          become each project's next steps. Running it again adds only what is new.
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
          <Link to="/catch-up">Catch up</Link>; {plural(report.files_filed, "file")} filed
          {report.files_waiting ? ` and ${plural(report.files_waiting, "file")} waiting, each with its name` : ""};{" "}
          {plural(report.next_steps, "to-do")} made next steps.
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
