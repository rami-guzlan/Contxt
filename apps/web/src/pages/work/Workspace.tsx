// Work, Workspace: where you think first, before working with AI. Docs you write (blank or from a
// template), links (a calendar, a sheet, a folder) and anything else linked to a project, by
// project. Everything here is yours: linking it to a project is a label, never a copy, and no AI
// reads it until you ask (from a doc's Work panel) or add it to the Brain.

import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { useNote, useWorkspace } from "../../api/hooks";
import type { WorkspaceItem, WorkspaceView } from "../../api/types";
import { Empty, ErrorNote, Field, Loading, Section } from "../../components/ui";
import { NewThings, WorkspaceRow } from "../../components/work/WorkspaceParts";
import { WORKSPACE } from "../../lib/links";
import { NoteEditor } from "../Notes";
import { LiveSection } from "./Live";

export function WorkspacePage() {
  const [params, setParams] = useSearchParams();
  const [archived, setArchived] = useState(false);
  const project = params.get("project") ?? "";
  const { data, isLoading, error } = useWorkspace(project === "none" ? "" : project, archived);
  if (isLoading) return <Loading />;
  if (!data) return <ErrorNote error={error} />;
  const items = project === "none" ? data.items.filter((i) => !i.projects.length) : data.items;
  return (
    <div className="work-tab workspace">
      <div className="work-intro">
        <p>
          <strong>Your docs.</strong> Where you think first. Write, outline and plan here, keep the links you work from, and link any of it to a project. It is yours
          alone until you ask your AI about a doc or add it to the Brain.
        </p>
      </div>
      {archived ? null : <NewThings projects={project && project !== "none" ? [project] : []} />}
      <div className="row workspace-show">
        <Field label="Show">
          <select value={project} onChange={(event) => setParams(event.target.value ? { project: event.target.value } : {})}>
            <option value="">Every project</option>
            {data.projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
            <option value="none">No project</option>
          </select>
        </Field>
        <button type="button" className="link" onClick={() => setArchived(!archived)}>
          {archived ? "Back to your Workspace" : "Set aside"}
        </button>
      </div>
      {items.length ? (
        <ByProject view={data} items={items} single={!!project} />
      ) : (
        <Empty
          why={
            archived
              ? "Nothing is set aside."
              : "Nothing here yet. Start a doc (an outline is a good start), or add a link to the calendar or sheet you work from."
          }
        />
      )}
      {archived ? null : <LiveSection />}
    </div>
  );
}

/** Every project with something linked to it, then what has no project. An item linked to two
 * projects shows under both: it is still one item. */
function ByProject({ view, items, single }: { view: WorkspaceView; items: WorkspaceItem[]; single: boolean }) {
  if (single) {
    return (
      <ul className="workspace-list" aria-label="Workspace">
        {items.map((item) => (
          <WorkspaceRow key={item.id} item={item} />
        ))}
      </ul>
    );
  }
  const groups = view.projects
    .map((p) => ({ project: p, items: items.filter((i) => i.projects.some((x) => x.id === p.id)) }))
    .filter((g) => g.items.length);
  const loose = items.filter((i) => !i.projects.length);
  return (
    <div className="stack">
      {groups.map(({ project, items: mine }) => (
        <Section
          key={project.id}
          title={project.title}
          actions={
            <Link className="small" to={`/projects/${encodeURIComponent(project.id)}`}>
              The project
            </Link>
          }
        >
          <ul className="workspace-list" aria-label={project.title}>
            {mine.map((item) => (
              <WorkspaceRow key={item.id} item={item} />
            ))}
          </ul>
        </Section>
      ))}
      {loose.length ? (
        <Section title="No project">
          <ul className="workspace-list" aria-label="No project">
            {loose.map((item) => (
              <WorkspaceRow key={item.id} item={item} />
            ))}
          </ul>
        </Section>
      ) : null}
    </div>
  );
}

export function WorkspaceDocPage() {
  const { docId = "" } = useParams();
  const { data: note, isLoading, error } = useNote(docId);
  if (isLoading) return <Loading />;
  if (!note) return <ErrorNote error={error} />;
  return (
    <div className="doc-page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to={WORKSPACE}>Workspace</Link>
      </nav>
      {/* A new editor once its text is in: what was transcribed replaces the empty page. */}
      <NoteEditor key={`${note.id}:${note.transcription?.state ?? ""}`} note={note} place="workspace" />
    </div>
  );
}
