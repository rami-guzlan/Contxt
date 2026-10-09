// The Workspace's parts, shared by Work, Workspace and each project's page: a row for one item,
// the ways to start something (a doc, a link, a file brought in as a doc), and a project's own
// Workspace section. What is here is the owner's alone: linking it to a project is a label, never
// a copy, and no AI reads it until asked.

import { ExternalLink, FilePlus, Link2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router";

import { useImportDoc, useLinkDocProjects, useNewDoc, useNewLink, useWorkspace } from "../../api/hooks";
import type { DocTemplate, WorkspaceItem } from "../../api/types";
import { when } from "../../lib/format";
import { agentUrl, docUrl, workspaceFor } from "../../lib/links";
import { CAPTURE_NAMES } from "../CaptureParts";
import { ErrorNote, Field, Loading } from "../ui";

export const TEMPLATES: { id: DocTemplate; label: string; hint: string }[] = [
  { id: "blank", label: "Blank", hint: "A page" },
  { id: "outline", label: "Outline", hint: "Points in order: you outline, AI can write" },
  { id: "plan", label: "Plan", hint: "Goal, steps, risks" },
  { id: "decision", label: "Decision", hint: "What, why, what else, who" },
  { id: "progress", label: "Progress update", hint: "What moved, what is stuck, what is next" },
];
const SHOWN = 6; // on a project's page; the rest are in Work

function kindWord(item: WorkspaceItem): string {
  if (item.kind === "doc") return "Doc";
  return CAPTURE_NAMES[item.kind as keyof typeof CAPTURE_NAMES] ?? "Item";
}

function kindChip(item: WorkspaceItem): string {
  return item.kind === "doc" ? "kind-guide" : item.kind === "link" ? "kind-reference" : "kind-influence";
}

/** One item: a doc or an upload opens in Work, a link opens where it points. */
export function WorkspaceRow({ item, compact = false }: { item: WorkspaceItem; compact?: boolean }) {
  const isLink = item.kind === "link" && !!item.url;
  return (
    <li className="workspace-row">
      <span className={`kind-chip ${kindChip(item)}`}>{kindWord(item)}</span>
      <div className="workspace-row-main">
        {isLink ? (
          <a href={item.url ?? "#"} target="_blank" rel="noreferrer" className="workspace-row-title">
            {item.title} <ExternalLink className="inline-icon" aria-hidden="true" />
          </a>
        ) : (
          <Link to={docUrl(item.id)} className="workspace-row-title">
            {item.title}
          </Link>
        )}
        {!compact && item.excerpt ? <p className="muted small">{item.excerpt}</p> : null}
        <p className="muted small">
          {when(item.updated_at)}
          {isLink ? (
            <>
              {" · "}
              <Link to={docUrl(item.id)} aria-label={`${item.title}: its notes and projects`}>
                Notes and projects
              </Link>
            </>
          ) : null}
          {!compact && item.projects.length > 1 ? ` · in ${item.projects.length} projects` : ""}
        </p>
      </div>
    </li>
  );
}

/** New doc (from a template), a link, or a file brought in as a doc, linked to the projects
 * given. Compact (on a project's page) offers a blank doc; Work, Workspace offers each template. */
export function NewThings({ projects, compact = false }: { projects: string[]; compact?: boolean }) {
  const navigate = useNavigate();
  const newDoc = useNewDoc();
  const newLink = useNewLink();
  const importDoc = useImportDoc();
  const [linking, setLinking] = useState(false);
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const file = useRef<HTMLInputElement>(null);
  const open = (id: string) => navigate(docUrl(id));
  const templates = compact ? TEMPLATES.slice(0, 1) : TEMPLATES;
  return (
    <div className="stack">
      <div className="row workspace-new" role="group" aria-label="Start something">
        {templates.map((t) => (
          <button
            key={t.id}
            type="button"
            className={t.id === "blank" ? "primary" : undefined}
            title={t.hint}
            disabled={newDoc.isPending}
            onClick={() => newDoc.mutate({ template: t.id, projects }, { onSuccess: (made) => open(made.id) })}
          >
            {t.id === "blank" ? (
              <>
                <FilePlus className="button-icon" aria-hidden="true" /> New doc
              </>
            ) : (
              t.label
            )}
          </button>
        ))}
        <button type="button" onClick={() => setLinking(!linking)} aria-expanded={linking}>
          <Link2 className="button-icon" aria-hidden="true" /> Add a link
        </button>
        <button type="button" disabled={importDoc.isPending} onClick={() => file.current?.click()}>
          <Upload className="button-icon" aria-hidden="true" /> {importDoc.isPending ? "Bringing it in…" : "Bring in a file"}
        </button>
        <input
          ref={file}
          type="file"
          hidden
          aria-label="A file to bring in as a doc"
          accept=".md,.txt,.html,.htm,.docx,.pptx,.pdf"
          onChange={(event) => {
            const picked = event.target.files?.[0];
            if (picked) importDoc.mutate({ file: picked, projects }, { onSuccess: (made) => open(made.id) });
            event.target.value = "";
          }}
        />
      </div>
      {linking ? (
        <form
          className="inline-form"
          onSubmit={(event) => {
            event.preventDefault();
            newLink.mutate(
              { url: url.trim(), title: title.trim() || undefined, projects },
              {
                onSuccess: () => {
                  setUrl("");
                  setTitle("");
                  setLinking(false);
                },
              },
            );
          }}
        >
          <Field label="The link" hint="A calendar, a sheet, a folder, a page.">
            <input type="url" required value={url} placeholder="https://" onChange={(event) => setUrl(event.target.value)} />
          </Field>
          <Field label="What it is (optional)">
            <input value={title} placeholder="For example: Launch calendar" onChange={(event) => setTitle(event.target.value)} />
          </Field>
          <button type="submit" className="primary" disabled={!url.trim() || newLink.isPending}>
            Keep it
          </button>
        </form>
      ) : null}
      <ErrorNote error={newDoc.error ?? newLink.error ?? importDoc.error} />
    </div>
  );
}

/** A project's own Workspace: what is linked to it, the agents on it, and the ways to add more.
 * His, and private until he shares it (the Files section beside it is what the Brain holds). */
export function ProjectWorkspace({ project }: { project: { id: string; title: string } }) {
  const { data, isLoading, error } = useWorkspace(project.id);
  const items = data?.items ?? [];
  const agents = data?.agents ?? [];
  return (
    <div className="stack project-workspace">
      <p className="muted small">Yours alone: what you work from for it. No AI reads any of it until you ask about a doc or add it to the Brain.</p>
      <NewThings projects={[project.id]} compact />
      {isLoading ? (
        <Loading />
      ) : !data ? (
        <ErrorNote error={error} />
      ) : items.length ? (
        <ul className="workspace-list" aria-label={`Workspace for ${project.title}`}>
          {items.slice(0, SHOWN).map((item) => (
            <WorkspaceRow key={item.id} item={item} compact />
          ))}
        </ul>
      ) : (
        <p className="muted small">Nothing linked yet. Start a doc for it, or keep its calendar or sheet here as a link.</p>
      )}
      {items.length > SHOWN ? (
        <p className="small">
          <Link to={workspaceFor(project.id)}>{items.length - SHOWN} more in Work</Link>
        </p>
      ) : null}
      <LinkExisting project={project.id} />
      {agents.length ? (
        <div>
          <h3 className="small-head">Agents on it</h3>
          <ul className="list compact-list">
            {agents.map((a) => (
              <li key={a.name}>
                <Link to={agentUrl(a.name)}>{a.name}</Link>
                <span className="muted small">
                  {a.role ? ` · ${a.role}` : ""}
                  {a.last_run ? ` · last ran ${when(a.last_run.at)}` : " · not run yet"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

/** Link something already in the Workspace to this project (it stays one item). */
function LinkExisting({ project }: { project: string }) {
  const [open, setOpen] = useState(false);
  if (!open)
    return (
      <p className="small">
        <button type="button" className="link" onClick={() => setOpen(true)}>
          Link something already in your Workspace
        </button>
      </p>
    );
  return <LinkExistingForm project={project} onDone={() => setOpen(false)} />;
}

function LinkExistingForm({ project, onDone }: { project: string; onDone: () => void }) {
  const { data } = useWorkspace();
  const link = useLinkDocProjects();
  const [chosen, setChosen] = useState("");
  const free = (data?.items ?? []).filter((item) => !item.projects.some((p) => p.id === project));
  const item = free.find((i) => i.id === chosen);
  return (
    <form
      className="inline-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (!item) return;
        const keep = item.projects.filter((p) => !p.missing).map((p) => p.id);
        link.mutate({ id: item.id, projects: [...keep, project] }, { onSuccess: onDone });
      }}
    >
      <Field label="From your Workspace">
        <select value={chosen} onChange={(event) => setChosen(event.target.value)}>
          <option value="">{data ? (free.length ? "Choose one" : "Everything is linked already") : "Loading…"}</option>
          {free.map((i) => (
            <option key={i.id} value={i.id}>
              {i.title}
            </option>
          ))}
        </select>
      </Field>
      <div className="row">
        <button type="submit" className="primary" disabled={!item || link.isPending}>
          Link it
        </button>
        <button type="button" onClick={onDone}>
          Cancel
        </button>
      </div>
      <ErrorNote error={link.error} />
    </form>
  );
}
