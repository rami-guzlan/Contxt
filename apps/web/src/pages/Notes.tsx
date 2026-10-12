// One capture: a note you wrote, or something you said, recorded or brought in (Capture lists
// them all). It is yours alone until you add it to the Brain (as a document, in a project, so every
// AI can quote it) or ask a model to find what in it should last (its suggestions wait in Review).
// Every one keeps its versions; a pause in typing saves. Audio shows its player, and its text once
// this computer has turned it into text.

import { type FormEvent, lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { ApiError, get } from "../api/client";
import {
  keys,
  noteDownloadUrl,
  saveNote,
  useBrainProjects,
  useBrainUndo,
  useDistillRequests,
  useInvalidate,
  useNote,
  useNoteAction,
  useNoteToBrain,
  useNoteVersions,
  useProposeEntry,
  useRememberNote,
  useTask,
} from "../api/hooks";
import type { BrainFiled, DistillRequest, Note } from "../api/types";
import { Compare } from "../components/Diff";
import type { RichEditorHandle } from "../components/RichEditor";
import { DigestPanel } from "../components/Digest";
import { KnowledgeCheck } from "../components/Pull";
import { RunButtons, RunConsole, RunnerNote, canRun } from "../components/RunNow";
import { CaptureSource, TranscriptionState } from "../components/CaptureParts";
import { DocProjects, DocWithAi } from "../components/work/DocWork";
import { ErrorNote, Field, Loading, Tabs } from "../components/ui";
import { label, when } from "../lib/format";

const RichEditor = lazy(() => import("../components/RichEditor"));

const UNTITLED = "Untitled note";
const SAVE_AFTER_MS = 1200;
const WORKING = ["draft", "ready", "claimed", "in_progress"];

// ---------------------------------------------------------------- one note

export function NotePage() {
  const { noteId = "" } = useParams();
  const { data: note, isLoading, error } = useNote(noteId);
  if (isLoading) return <Loading />;
  if (!note) return <ErrorNote error={error} />;
  return (
    <div className="page doc-page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/capture">Capture</Link>
      </nav>
      {/* A new editor once its text is in: what was transcribed replaces the empty page. */}
      <NoteEditor key={`${note.id}:${note.transcription?.state ?? ""}`} note={note} />
    </div>
  );
}

/** Where a note is open: Capture (what came in) or the Workspace (what you write), which adds
 * its projects and AI, when asked, beside it. */
export type NotePlace = "capture" | "workspace";

type SaveState = "saved" | "unsaved" | "saving" | "conflict" | "failed";

/** The note, saved as the person writes: a pause of a moment saves, and a version saved
 * elsewhere (another tab) is not overwritten without asking. */
function useAutosave(note: Note) {
  const invalidate = useInvalidate();
  const { refetch } = useNote(note.id);
  const [title, setTitle] = useState(note.title);
  const [body, setBody] = useState(note.body ?? "");
  const [state, setState] = useState<SaveState>("saved");
  const [savedAt, setSavedAt] = useState(note.updated_at);
  const [resetKey, setResetKey] = useState(0);
  const [revision, setRevision] = useState(note.revision);
  const version = useRef(note.version);
  const pending = useRef<{ title?: string; body?: string }>({});
  const timer = useRef<number | null>(null);

  const flush = useCallback(
    async (force = false): Promise<boolean> => {
      if (timer.current) window.clearTimeout(timer.current);
      timer.current = null;
      const changes = pending.current;
      if (!Object.keys(changes).length) return true;
      pending.current = {};
      setState("saving");
      try {
        const saved = await saveNote(note.id, { ...changes, expected_version: force ? undefined : version.current });
        version.current = saved.version;
        setRevision(saved.revision);
        setSavedAt(saved.updated_at);
        setState(Object.keys(pending.current).length ? "unsaved" : "saved");
        // A note nobody has named takes its first line as its title (the server decides).
        if (!("title" in pending.current)) setTitle((shown) => (shown === UNTITLED ? saved.title : shown));
        void invalidate([...keys.notes, "list"]);
        return true;
      } catch (caught) {
        pending.current = { ...changes, ...pending.current };
        setState(caught instanceof ApiError && caught.status === 409 ? "conflict" : "failed");
        return false;
      }
    },
    [note.id, invalidate],
  );

  function change(next: { title?: string; body?: string }) {
    pending.current = { ...pending.current, ...next };
    setState("unsaved");
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => void flush(), SAVE_AFTER_MS);
  }

  // Leaving the page saves what is waiting; closing the tab with unsaved work asks first. The
  // effect runs once: re-running it on each render would save on every keystroke.
  const latestFlush = useRef(flush);
  latestFlush.current = flush;
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (Object.keys(pending.current).length) event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => {
      window.removeEventListener("beforeunload", warn);
      void latestFlush.current();
    };
  }, []);

  /** Show what the server holds now: after a restore, or a conflict. */
  async function reload() {
    pending.current = {};
    const { data: fresh } = await refetch();
    if (!fresh) return;
    setTitle(fresh.title);
    setBody(fresh.body ?? "");
    version.current = fresh.version;
    setRevision(fresh.revision);
    setSavedAt(fresh.updated_at);
    setState("saved");
    setResetKey((k) => k + 1);
    void invalidate(keys.notes);
  }

  return {
    title,
    body,
    state,
    savedAt,
    resetKey,
    revision,
    flush,
    reload,
    rename(next: string) {
      setTitle(next);
      change({ title: next });
    },
    write(next: string) {
      setBody(next);
      change({ body: next });
    },
  };
}
type Saver = ReturnType<typeof useAutosave>;

export function NoteEditor({ note, place = "capture" }: { note: Note; place?: NotePlace }) {
  const saver = useAutosave(note);
  const navigate = useNavigate();
  const action = useNoteAction();
  const [selection, setSelection] = useState("");
  const editor = useRef<RichEditorHandle>(null);
  const archived = !!note.archived_at;
  return (
    <div className="doc">
      <header className="doc-head">
        <input className="doc-title" aria-label="Title" value={saver.title} onChange={(event) => saver.rename(event.target.value)} />
        <div className="row small">
          <SaveNote state={saver.state} savedAt={saver.savedAt} />
          <a className="button" href={noteDownloadUrl(note.id)}>
            Download .md
          </a>
          {archived ? (
            <button type="button" onClick={() => action.mutate({ id: note.id, action: "unarchive" }, { onSuccess: () => void saver.reload() })}>
              Bring back
            </button>
          ) : (
            <button
              type="button"
              onClick={() =>
                void saver
                  .flush()
                  .then(() =>
                    action.mutate({ id: note.id, action: "archive" }, { onSuccess: () => navigate(place === "workspace" ? "/work/workspace" : "/capture") }),
                  )
              }
            >
              Set aside
            </button>
          )}
        </div>
      </header>
      {archived ? <p className="notice">This note is set aside. Bring it back to write in it.</p> : null}
      <CaptureSource note={note} />
      <TranscriptionState note={note} />
      {saver.state === "conflict" ? (
        <div className="warning" role="alert">
          <p>This note changed since you opened it (in another tab, say). Your latest changes are not saved.</p>
          <div className="row">
            <button type="button" onClick={() => void saver.reload()}>
              Show the newer one (drop my last edits)
            </button>
            <button type="button" onClick={() => void saver.flush(true)}>
              Keep mine (save over it)
            </button>
          </div>
        </div>
      ) : null}
      <ErrorNote error={action.error} />
      <div className="doc-layout">
        <div className="doc-main">
          {note.transcription && note.transcription.state !== "ready" && !note.body ? (
            <p className="muted">Its text appears here once it is turned into text.</p>
          ) : (
          <Suspense fallback={<Loading />}>
            <RichEditor
              markdown={saver.body}
              label={`${saver.title || "Note"} text`}
              resetKey={saver.resetKey}
              handle={editor}
              onChange={saver.write}
              onSelection={setSelection}
            />
          </Suspense>
          )}
        </div>
        <Side note={note} saver={saver} selection={selection} place={place} />
      </div>
    </div>
  );
}

function SaveNote({ state, savedAt }: { state: SaveState; savedAt: string }) {
  const text = {
    saved: `Saved ${when(savedAt)}`,
    unsaved: "Unsaved changes",
    saving: "Saving…",
    conflict: "Not saved: changed elsewhere",
    failed: "Not saved: will retry on your next edit",
  }[state];
  return (
    <span className={state === "failed" || state === "conflict" ? "error small" : "muted small"} role="status">
      {text}
    </span>
  );
}

const SIDE = [
  { id: "summary", label: "Summary" },
  { id: "brain", label: "Into the Brain" },
  { id: "versions", label: "Versions" },
] as const;
const WORK_SIDE = [{ id: "work", label: "Work" }, ...SIDE] as const;
type SideTab = (typeof WORK_SIDE)[number]["id"];

/** Beside the note: what it says, the ways it reaches the Brain, and every version. What was
 * brought in opens on its summary; a note typed here on the ways into the Brain. */
function Side({ note, saver, selection, place }: { note: Note; saver: Saver; selection: string; place: NotePlace }) {
  const [side, setSide] = useState<SideTab>(place === "workspace" ? "work" : note.capture && note.capture !== "note" ? "summary" : "brain");
  return (
    <aside className="doc-side" aria-label="Beside the note" data-tour="notes-panel">
      <Tabs tabs={place === "workspace" ? WORK_SIDE : SIDE} active={side} onChange={setSide} />
      {side === "work" ? (
        <div className="stack">
          <DocProjects note={note} />
          <DocWithAi note={note} beforeAsk={() => saver.flush()} />
        </div>
      ) : side === "summary" ? (
        <DigestPanel note={note} hasText={!!saver.body.trim()} />
      ) : side === "brain" ? (
        <div className="stack">
          {selection ? <RememberSelection note={note} selection={selection} revision={saver.revision} /> : null}
          <FindWhatToRemember note={note} saver={saver} />
          <section className="side-part" aria-label="Knowledge check">
            <h3>Knowledge check</h3>
            <p className="muted small">What your Brain already knows of it, what is new, what disagrees, and what is off your goals.</p>
            <KnowledgeCheck title={note.title} captureId={note.id} />
          </section>
          <AddToBrain note={note} saver={saver} />
          <TeachSkill note={note} />
        </div>
      ) : (
        <Versions note={note} current={saver.body} title={saver.title} beforeChange={saver.flush} onChanged={saver.reload} />
      )}
    </aside>
  );
}

/** How something was done, turned into a skill your AI follows next time (it waits in Review). */
function TeachSkill({ note }: { note: Note }) {
  return (
    <section className="side-part" aria-label="Teach a skill from it">
      <h3>Teach a skill from it</h3>
      <p className="muted small">
        When this shows how something should be made (a post, a proposal, a recap), your AI can write it up as a skill to follow next
        time.
      </p>
      <Link className="button small" to={`/work/skills?capture=${encodeURIComponent(note.id)}`}>
        Teach a skill
      </Link>
    </section>
  );
}

/** File the note in the Brain as a document, as it reads now: every AI can then quote it. */
function AddToBrain({ note, saver }: { note: Note; saver: Saver }) {
  const { data: projects } = useBrainProjects();
  const file = useNoteToBrain();
  const undo = useBrainUndo();
  const [project, setProject] = useState("");
  const [status, setStatus] = useState("");
  const [filed, setFiled] = useState<BrainFiled | null>(null);
  const [undone, setUndone] = useState(false);

  function submit(event: FormEvent) {
    event.preventDefault();
    setUndone(false);
    void saver.flush().then((ok) => {
      if (!ok) return;
      file.mutate({ id: note.id, project: project || undefined, status: status || undefined }, { onSuccess: setFiled });
    });
  }

  return (
    <section className="side-part" aria-label="Add to the Brain">
      <h3>Add to the Brain</h3>
      <p className="muted small">
        Filed as a document, as it reads now. Your AI then quotes the part a request is about. Adding it again files a new version.
      </p>
      <form className="stack" onSubmit={submit}>
        <Field label="Project">
          <select value={project} onChange={(event) => setProject(event.target.value)}>
            <option value="">None</option>
            {(projects ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Status">
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">None</option>
            <option value="draft">Draft</option>
            <option value="sent">Sent</option>
            <option value="final">Final</option>
          </select>
        </Field>
        <button type="submit" className="primary" disabled={file.isPending || !saver.body.trim()}>
          Add to the Brain
        </button>
      </form>
      {filed && !undone ? (
        <p className="small" role="status">
          {filed.status === "applied"
            ? `In your Brain now${filed.version ? `, version ${filed.version}` : ""}.`
            : filed.status === "pending"
              ? "It waits in Review for your approval."
              : filed.message}{" "}
          {filed.status === "applied" && filed.checkpoint_id ? (
            <button
              type="button"
              className="link"
              disabled={undo.isPending}
              onClick={() => undo.mutate(filed.checkpoint_id ?? "", { onSuccess: () => setUndone(true) })}
            >
              Undo
            </button>
          ) : null}
        </p>
      ) : null}
      {undone ? <p className="small">Taken back out of the Brain.</p> : null}
      <ErrorNote error={file.error ?? undo.error} />
    </section>
  );
}

/** The knowledge agent: what in it serves your goals and active projects, as suggestions that
 * wait in Catch up, each with the goal or project it is for, and what it left out. */
function FindWhatToRemember({ note, saver }: { note: Note; saver: Saver }) {
  const { data: requests } = useDistillRequests(note.id);
  const remember = useRememberNote();
  const [runId, setRunId] = useState<string | null>(null);
  const [guidance, setGuidance] = useState("");
  const open = (requests ?? []).find((r) => WORKING.includes(r.status));
  return (
    <section className="side-part" aria-label="Pull what matters">
      <h3>Pull what matters</h3>
      <p className="muted small">
        Your AI reads it against your goals and active projects and suggests what serves them, each with the goal or project it is for.
        What it leaves out is listed, so you can still pull it. Your words below win over the goals. Nothing goes in until you keep it in
        Catch up.
      </p>
      {open ? (
        <OpenRequest request={open} onStarted={setRunId} />
      ) : (
        <>
          <textarea
            aria-label="What to pull in (optional)"
            placeholder="The decisions and who owns each action, everything about the Q4 polls..."
            rows={2}
            value={guidance}
            onChange={(event) => setGuidance(event.target.value)}
          />
          <button
            type="button"
            disabled={remember.isPending || !saver.body.trim()}
            onClick={() => void saver.flush().then((ok) => ok && remember.mutate({ id: note.id, guidance: guidance.trim() || undefined }))}
          >
            Pull what matters
          </button>
        </>
      )}
      <ErrorNote error={remember.error} />
      {runId ? <RunConsole runId={runId} /> : null}
      <PastRequests requests={(requests ?? []).filter((r) => r !== open)} />
    </section>
  );
}

/** A request still going: who has it, and a way to run it on this computer now. */
function OpenRequest({ request, onStarted }: { request: DistillRequest; onStarted: (runId: string) => void }) {
  const { data: task } = useTask(request.task_id);
  return (
    <div className="stack">
      <p className="small" role="status">
        {request.waiting
          ? "Waiting for a model to take it."
          : `${request.assignee_name ?? "A model"} ${request.status === "ready" ? "will read it at its next check" : "is reading it"}.`}
      </p>
      {task && canRun(task) ? (
        <>
          <RunButtons task={task} onStarted={onStarted} />
          <RunnerNote />
        </>
      ) : null}
    </div>
  );
}

function PastRequests({ requests }: { requests: DistillRequest[] }) {
  const { data: projects } = useBrainProjects();
  if (!requests.length) return null;
  const titles = new Map((projects ?? []).map((p) => [p.id, p.title]));
  return (
    <ul className="compact-list pulls">
      {requests.slice(0, 5).map((r) => {
        const waiting = r.proposals.filter((p) => p.status === "pending").length;
        const groups = new Map<string, number>();
        for (const p of r.proposals) {
          const key = p.project_id ? `for ${titles.get(p.project_id) ?? p.project_id}` : p.goal ? `for ${p.goal}` : "about you";
          groups.set(key, (groups.get(key) ?? 0) + 1);
        }
        return (
          <li key={r.task_id}>
            <span className="small">
              {when(r.updated_at)}: {label(r.status)}
              {r.proposals.length
                ? `, pulled ${r.proposals.length}: ${[...groups.entries()].map(([k, n]) => `${n} ${k}`).join(", ")}`
                : r.status === "done"
                  ? ", nothing to keep"
                  : ""}
              {waiting ? (
                <>
                  {" · "}
                  <Link to="/catch-up">{waiting} waiting in Catch up</Link>
                </>
              ) : null}
            </span>
            {r.summary ? <span className="muted small"> · {r.summary}</span> : null}
            {r.left_out?.length ? <LeftOut items={r.left_out} source={r.title} /> : null}
          </li>
        );
      })}
    </ul>
  );
}

/** What the knowledge agent left out, and why: each one tap from being pulled anyway. */
function LeftOut({ items, source }: { items: { statement: string; why: string }[]; source: string }) {
  const propose = useProposeEntry();
  const [pulled, setPulled] = useState<string[]>([]);
  return (
    <details className="left-out">
      <summary className="small">Left out {items.length}: see why</summary>
      <ul className="compact-list">
        {items.map((item) => (
          <li key={item.statement} className="small">
            {item.statement} <span className="muted">· {item.why}</span>{" "}
            {pulled.includes(item.statement) ? (
              <span className="muted">· pulled, waiting in Catch up</span>
            ) : (
              <button
                type="button"
                className="link small"
                disabled={propose.isPending}
                onClick={() =>
                  propose.mutate(
                    {
                      title: (item.statement.split(/[.!?]\s/)[0] ?? item.statement).slice(0, 80),
                      statement: item.statement,
                      evidence: `Pulled anyway from “${source}”; the knowledge agent had left it out: ${item.why}`,
                    },
                    { onSuccess: () => setPulled((p) => [...p, item.statement]) },
                  )
                }
              >
                Pull anyway
              </button>
            )}
          </li>
        ))}
      </ul>
      <ErrorNote error={propose.error} />
    </details>
  );
}

/** The selected text as a suggestion for the Brain, in the person's own words. */
function RememberSelection({ note, selection, revision }: { note: Note; selection: string; revision: number }) {
  const propose = useProposeEntry();
  const [title, setTitle] = useState("");
  const [done, setDone] = useState(false);
  const first = selection.split("\n").find((line) => line.trim())?.trim() ?? "";

  function submit(event: FormEvent) {
    event.preventDefault();
    propose.mutate(
      {
        title: title.trim() || first.slice(0, 80),
        statement: selection.trim(),
        kind: "fact",
        evidence: `From the note “${note.title}”`,
        origin: `doc:${note.id}@r${revision}`,
      },
      { onSuccess: () => setDone(true) },
    );
  }

  return (
    <section className="side-part with-selection" aria-label="Remember the selection">
      <h3>Remember the selected text</h3>
      {done ? (
        <p className="small">Suggested to the Brain. It waits in Review for your approval.</p>
      ) : (
        <form className="stack" onSubmit={submit}>
          <Field label="Note title" hint="What it is for, in a few words.">
            <input value={title} placeholder={first.slice(0, 80)} onChange={(event) => setTitle(event.target.value)} />
          </Field>
          <button type="submit" disabled={propose.isPending}>
            Suggest it
          </button>
        </form>
      )}
      <ErrorNote error={propose.error} />
    </section>
  );
}

function Versions({
  note,
  current,
  title,
  beforeChange,
  onChanged,
}: {
  note: Note;
  current: string;
  title: string;
  beforeChange: () => Promise<boolean>;
  onChanged: () => Promise<void>;
}) {
  const { data: versions, isLoading } = useNoteVersions(note.id);
  const action = useNoteAction();
  const [picked, setPicked] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [old, setOld] = useState<{ revision: number; body: string; title: string } | null>(null);
  if (isLoading) return <Loading />;
  if (!versions) return null;

  async function pick(revision: number) {
    setPicked(revision);
    const data = await get<{ body: string | null; title: string }>(`/api/notes/${encodeURIComponent(note.id)}/versions/${revision}`);
    setOld({ revision, body: data.body ?? "", title: data.title });
  }

  return (
    <div className="versions">
      <form
        className="row small"
        aria-label="Name this version"
        onSubmit={(event) => {
          event.preventDefault();
          if (!name.trim()) return;
          void beforeChange().then(() => action.mutate({ id: note.id, action: "name", body: { label: name.trim() } }, { onSuccess: () => setName("") }));
        }}
      >
        <input aria-label="Version name" placeholder="Name this version, like “Sent for review”" value={name} onChange={(event) => setName(event.target.value)} />
        <button type="submit" disabled={!name.trim() || action.isPending}>
          Name it
        </button>
      </form>
      <ol className="version-list">
        {versions.map((v) => (
          <li key={v.revision} className={picked === v.revision ? "version active" : "version"}>
            <button type="button" className="version-pick" disabled={v.current} onClick={() => void pick(v.revision)}>
              <span>
                <strong>{v.label ?? `Version ${v.revision}`}</strong> {v.current ? <span className="chip chip-approved">Now</span> : null}
              </span>
              <span className="muted small">
                {v.by}, {when(v.at)}
              </span>
            </button>
          </li>
        ))}
      </ol>
      {old && picked === old.revision ? (
        <div className="restore">
          <Compare before={{ label: `Version ${old.revision}`, title: old.title, body: old.body }} after={{ label: "Now", title, body: current }} />
          <button
            type="button"
            className="primary"
            disabled={action.isPending}
            onClick={() =>
              void beforeChange().then(() =>
                action.mutate(
                  { id: note.id, action: "restore", body: { revision: old.revision } },
                  {
                    onSuccess: () => {
                      setPicked(null);
                      setOld(null);
                      void onChanged();
                    },
                  },
                ),
              )
            }
          >
            Put this version back
          </button>
        </div>
      ) : null}
      <ErrorNote error={action.error} />
    </div>
  );
}
