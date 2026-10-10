// Knowledge Work, Prompts: your own prompts, kept word for word in the Brain's Library with the
// files that came with them, for when you want them again. A skill is a procedure your Brain uses
// by itself; a prompt waits until you ask for it. Save one here, or from any chat ("save this
// prompt to my Brain"); find it by its words, tags or project; copy it, see every version, make it
// a skill once you use it often. Running it, and seeing what a model gets, is a panel on its
// page: one thing you can do with your words, not the point of keeping them.

import { type ReactNode, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import { useArchivePrompt, useSavedPrompt, useSavedPrompts, useSavePrompt, useUploadToLibrary } from "../../api/hooks";
import type { ComposePicks, SavedPrompt } from "../../api/types";
import { CopyBlock, Empty, ErrorNote, Field, Loading, Section } from "../../components/ui";
import { ScopeChip } from "../../components/work/Scope";
import { plural, when } from "../../lib/format";
import { originLine } from "../../lib/origins";
import { libraryItemUrl } from "../brain/shared";
import { ComposePanel, linkRuns, picksFromLink, ProjectPicker, skillFromPrompt, useSettled } from "./Compose";

export const promptUrl = (id: string) => `/work/prompts/${encodeURIComponent(id)}`;
const OFTEN = 3; // runs after which a prompt is worth writing down as a skill
const DOCUMENT = /\.(md|markdown|txt|pdf|docx|pptx|html?)$/i; // kept as text; anything else is an asset

/** Tags as typed: comma separated, each trimmed, none twice. */
export const tagsOf = (text: string) => [...new Set(text.split(",").map((t) => t.trim().replace(/\s+/g, " ")).filter(Boolean))];

function fromWhere(prompt: SavedPrompt): string {
  if (prompt.origin === "chat") return "saved from a chat";
  if (prompt.origin === "upload") return "saved here";
  return `from ${originLine(prompt.origin).toLowerCase()}`;
}

function excerpt(text: string, limit = 160): string {
  const line = text.replace(/\s+/g, " ").trim();
  return line.length > limit ? `${line.slice(0, limit - 1)}…` : line;
}

const samePicks = (a: ComposePicks, b: ComposePicks) =>
  a.agent === b.agent &&
  a.project === b.project &&
  (["skills", "docs", "library"] as const).every((key) => a[key].join("\n") === b[key].join("\n"));

// ---------------------------------------------------------------- the list

export function PromptsPage() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const settled = useSettled(q, 250);
  const aside = params.get("show") === "aside";
  const tag = params.get("tag");
  const project = params.get("project");
  const { data, isLoading, error } = useSavedPrompts(settled, aside);
  const tags = useMemo(() => [...new Set((data ?? []).flatMap((p) => p.tags))].sort(), [data]);
  const projects = useMemo(
    () => new Map((data ?? []).filter((p) => p.project).map((p) => [p.project as string, p.project_title ?? (p.project as string)])),
    [data],
  );
  const shown = (data ?? []).filter((p) => (!tag || p.tags.includes(tag)) && (!project || p.project === project));
  const pick = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };
  return (
    <div className="work-tab prompts">
      <div className="work-intro">
        <p>
          Your own prompts, kept word for word with the files that came with them, for when you want them again. A skill is a procedure your Brain
          uses by itself; a prompt waits until you ask for it.
        </p>
        <Link className="button primary" to="/work/prompts/new">
          New prompt
        </Link>
      </div>
      <p className="muted small">
        From any chat, ask your AI to “save this prompt to my Brain”: it keeps your exact words here, with the files you attached.
      </p>
      <div className="row prompts-filter">
        <input
          type="search"
          aria-label="Find a prompt"
          placeholder="Find a prompt by its words or tags"
          value={q}
          onChange={(event) => setQ(event.target.value)}
        />
        {projects.size ? (
          <select aria-label="Project" value={project ?? ""} onChange={(event) => pick("project", event.target.value || null)}>
            <option value="">Every project</option>
            {[...projects].map(([id, title]) => (
              <option key={id} value={id}>
                {title}
              </option>
            ))}
          </select>
        ) : null}
        <button type="button" className={aside ? "chip active" : "chip"} aria-pressed={aside} onClick={() => pick("show", aside ? null : "aside")}>
          Set aside
        </button>
      </div>
      {tags.length ? (
        <div className="chips" role="group" aria-label="Tags">
          {tags.map((t) => (
            <button key={t} type="button" className={tag === t ? "chip active" : "chip"} aria-pressed={tag === t} onClick={() => pick("tag", tag === t ? null : t)}>
              {t}
            </button>
          ))}
        </div>
      ) : null}
      {isLoading ? (
        <Loading />
      ) : !data ? (
        <ErrorNote error={error} />
      ) : shown.length ? (
        <ul className="workspace-list" aria-label="Prompts">
          {shown.map((p) => (
            <PromptRow key={p.id} prompt={p} />
          ))}
        </ul>
      ) : (
        <Empty
          why={
            aside
              ? "Nothing set aside."
              : settled || tag || project
                ? "No prompt matches."
                : "No prompts yet. Keep one you will want again, here or from any chat; your Brain keeps every version."
          }
        />
      )}
    </div>
  );
}

function PromptRow({ prompt }: { prompt: SavedPrompt }) {
  return (
    <li className="workspace-row">
      <span className="kind-chip kind-prompt">{prompt.uses ? plural(prompt.uses, "run") : "Prompt"}</span>
      <div className="workspace-row-main">
        <Link to={promptUrl(prompt.id)} className="workspace-row-title">
          {prompt.title}
        </Link>
        <ScopeChip scope={prompt.scope} />
        {prompt.tags.map((t) => (
          <span key={t} className="tag-chip">
            {t}
          </span>
        ))}
        <p className="muted small">{excerpt(prompt.body)}</p>
        <p className="muted small">
          {[
            fromWhere(prompt),
            prompt.project_title ? `for ${prompt.project_title}` : "",
            prompt.attachments.length ? `with ${plural(prompt.attachments.length, "file")}` : "",
            prompt.uses ? `ran ${plural(prompt.uses, "time")}, last ${when(prompt.last_used)}` : `saved ${when(prompt.updated_at ?? prompt.created_at)}`,
            prompt.uses >= OFTEN ? "used often: worth a skill" : "",
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
      </div>
    </li>
  );
}

// ---------------------------------------------------------------- a new one

export function NewPromptPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const save = useSavePrompt();
  const [body, setBody] = useState(params.get("ask") ?? "");
  const [title, setTitle] = useState("");
  const [tags, setTags] = useState("");
  const [picks, setPicks] = useState<ComposePicks>(() => picksFromLink(params));
  const [running, setRunning] = useState(() => linkRuns(params));
  const named = title.trim() || body.trim().split("\n")[0]?.trim().slice(0, 80) || "";
  return (
    <div className="work-tab prompts">
      <p className="small">
        <Link to="/work/prompts">Prompts</Link>
      </p>
      <form
        className="stack prompt-form"
        aria-label="New prompt"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate({ title: named, body, tags: tagsOf(tags), picks }, { onSuccess: (made) => navigate(promptUrl(made.id)) });
        }}
      >
        <h2>New prompt</h2>
        <Field label="The prompt" hint="Kept word for word, exactly as you write it.">
          <textarea
            rows={10}
            value={body}
            placeholder="For example: three LinkedIn posts for next week from my launch outline, in our voice"
            onChange={(event) => setBody(event.target.value)}
          />
        </Field>
        <Field label="Its name" hint={!title.trim() && named ? `Leave it empty to call it “${named}”.` : undefined}>
          <input maxLength={200} value={title} onChange={(event) => setTitle(event.target.value)} />
        </Field>
        <Field label="Tags" hint="Comma separated, to find it later.">
          <input value={tags} onChange={(event) => setTags(event.target.value)} />
        </Field>
        <ProjectPicker value={picks.project} onChange={(project) => setPicks({ ...picks, project })} />
        <p className="muted small">Files that came with it go on its page, once it is kept.</p>
        <div className="row">
          <button type="submit" className="primary" disabled={!body.trim() || !named || save.isPending}>
            {save.isPending ? "Keeping it…" : "Keep it"}
          </button>
          <Link className="button" to="/work/prompts">
            Cancel
          </Link>
        </div>
        <ErrorNote error={save.error} />
      </form>
      <RunSection open={running} onOpen={() => setRunning(true)}>
        <ComposePanel request={body} onRequest={setBody} picks={picks} onPicks={setPicks} withProject={false} />
      </RunSection>
    </div>
  );
}

// ---------------------------------------------------------------- one prompt

export function PromptPage() {
  const { promptId = "" } = useParams();
  const { data: prompt, isLoading, error } = useSavedPrompt(promptId);
  if (isLoading) return <Loading />;
  if (!prompt) return <ErrorNote error={error} />;
  return <PromptView key={`${prompt.id}:${prompt.version}`} prompt={prompt} />;
}

function PromptView({ prompt }: { prompt: SavedPrompt }) {
  const [editing, setEditing] = useState(false);
  const archive = useArchivePrompt();
  const aside = !!prompt.archived_at;
  return (
    <div className="work-tab prompts prompt-page">
      <p className="small">
        <Link to="/work/prompts">Prompts</Link>
      </p>
      <header className="prompt-head">
        <h2>{prompt.title}</h2>
        <ScopeChip scope={prompt.scope} />
        {prompt.tags.map((t) => (
          <span key={t} className="tag-chip">
            {t}
          </span>
        ))}
      </header>
      <p className="muted small">
        {[
          fromWhere(prompt),
          prompt.project_title ? `for ${prompt.project_title}` : "",
          `version ${prompt.version}`,
          prompt.uses ? `ran ${plural(prompt.uses, "time")}, last ${when(prompt.last_used)}` : "not run yet",
          aside ? "set aside" : "",
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>
      {editing ? <EditPrompt prompt={prompt} onDone={() => setEditing(false)} /> : <CopyBlock text={prompt.body} label="The prompt, word for word" />}
      <div className="row">
        {!editing && !aside ? (
          <button type="button" onClick={() => setEditing(true)}>
            Edit
          </button>
        ) : null}
        <Link className="button" to={skillFromPrompt({ request: prompt.body, ...prompt.picks })}>
          {prompt.uses >= OFTEN ? "Used often: make it a skill" : "Make it a skill"}
        </Link>
        <button type="button" disabled={archive.isPending} onClick={() => archive.mutate({ id: prompt.id, back: aside })}>
          {aside ? "Bring it back" : "Set aside"}
        </button>
      </div>
      <ErrorNote error={archive.error} />
      <Attachments prompt={prompt} />
      <Versions prompt={prompt} />
      {aside ? null : <RunPrompt prompt={prompt} />}
    </div>
  );
}

function EditPrompt({ prompt, onDone }: { prompt: SavedPrompt; onDone: () => void }) {
  const save = useSavePrompt();
  const [title, setTitle] = useState(prompt.title);
  const [body, setBody] = useState(prompt.body);
  const [tags, setTags] = useState(prompt.tags.join(", "));
  const [project, setProject] = useState(prompt.project);
  return (
    <form
      className="stack prompt-form"
      aria-label="Edit the prompt"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate(
          { id: prompt.id, title: title.trim(), body, tags: tagsOf(tags), picks: { ...prompt.picks, project }, expected_version: prompt.version },
          { onSuccess: onDone },
        );
      }}
    >
      <Field label="Its name">
        <input required maxLength={200} value={title} onChange={(event) => setTitle(event.target.value)} />
      </Field>
      <Field label="The prompt" hint="New words are a new version; the earlier ones stay below.">
        <textarea rows={10} value={body} onChange={(event) => setBody(event.target.value)} />
      </Field>
      <Field label="Tags" hint="Comma separated.">
        <input value={tags} onChange={(event) => setTags(event.target.value)} />
      </Field>
      <ProjectPicker value={project} onChange={setProject} />
      <div className="row">
        <button type="submit" className="primary" disabled={!title.trim() || !body.trim() || save.isPending}>
          {save.isPending ? "Saving…" : "Save"}
        </button>
        <button type="button" onClick={onDone}>
          Cancel
        </button>
      </div>
      <ErrorNote error={save.error} />
    </form>
  );
}

function Attachments({ prompt }: { prompt: SavedPrompt }) {
  const upload = useUploadToLibrary();
  const [file, setFile] = useState<File | null>(null);
  const [picker, setPicker] = useState(0); // a new file input after each one is added
  return (
    <Section title="Files that came with it">
      {prompt.attachments.length ? (
        <ul className="plain" aria-label="Files that came with it">
          {prompt.attachments.map((a) => (
            <li key={a.path}>
              <Link to={libraryItemUrl(a.path)}>{a.title}</Link>{" "}
              <span className="muted small">{a.kind === "asset" ? "kept byte for byte" : "kept as text"}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted small">None yet.</p>
      )}
      {prompt.archived_at ? null : (
        <form
          className="row"
          aria-label="Add a file"
          onSubmit={(event) => {
            event.preventDefault();
            if (!file) return;
            upload.mutate(
              { file, kind: DOCUMENT.test(file.name) ? "reference" : "asset", attach_to: prompt.path, project: prompt.project ?? undefined },
              {
                onSuccess: () => {
                  setFile(null);
                  setPicker((n) => n + 1);
                },
              },
            );
          }}
        >
          <input key={picker} type="file" aria-label="A file that goes with it" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          <button type="submit" disabled={!file || upload.isPending}>
            {upload.isPending ? "Adding…" : "Add it"}
          </button>
        </form>
      )}
      {upload.data?.status === "pending" ? <p className="notice small">It waits for your review in Catch up.</p> : null}
      <ErrorNote error={upload.error} />
    </Section>
  );
}

function Versions({ prompt }: { prompt: SavedPrompt }) {
  const older = prompt.versions.slice(1);
  if (!older.length) return null;
  return (
    <Section title="Earlier versions">
      <ul className="plain" aria-label="Earlier versions">
        {older.map((v) => (
          <li key={v.revision}>
            <details>
              <summary>
                Version {v.revision}
                {v.at ? `, ${when(v.at)}` : ""}
              </summary>
              <CopyBlock text={v.body} label={`Version ${v.revision}`} />
            </details>
          </li>
        ))}
      </ul>
    </Section>
  );
}

/** Running is secondary: closed until asked for. */
function RunSection({ open, onOpen, children }: { open: boolean; onOpen: () => void; children: ReactNode }) {
  return (
    <Section title="Run it, or see what a model gets">
      {open ? (
        children
      ) : (
        <>
          <p className="muted small">
            Optional: pick skills, an agent or documents to go with it, see the whole prompt a model gets with its size, improve the words, or run it
            here.
          </p>
          <button type="button" onClick={onOpen}>
            Run or preview
          </button>
        </>
      )}
    </Section>
  );
}

function RunPrompt({ prompt }: { prompt: SavedPrompt }) {
  const [open, setOpen] = useState(false);
  const [request, setRequest] = useState(prompt.body);
  const kept = { ...prompt.picks, project: prompt.project }; // it runs for the project it is for
  const [picks, setPicks] = useState<ComposePicks>(kept);
  const save = useSavePrompt();
  const newWords = request.trim() !== prompt.body.trim();
  const newPicks = !samePicks(picks, kept);
  return (
    <RunSection open={open} onOpen={() => setOpen(true)}>
      <ComposePanel request={request} onRequest={setRequest} picks={picks} onPicks={setPicks} prompt={prompt} withProject={false} />
      {newWords || newPicks ? (
        <div className="row">
          <button
            type="button"
            disabled={save.isPending}
            onClick={() =>
              save.mutate({
                id: prompt.id,
                ...(newWords ? { body: request } : {}),
                ...(newPicks ? { picks } : {}),
                expected_version: prompt.version,
              })
            }
          >
            {newWords ? "Keep these words as a new version" : "Keep these picks with the prompt"}
          </button>
          <ErrorNote error={save.error} />
        </div>
      ) : null}
    </RunSection>
  );
}
