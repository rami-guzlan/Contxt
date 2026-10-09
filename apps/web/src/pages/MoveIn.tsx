// Moving in: bring what your AIs already know. Pick where it lives (ChatGPT, Claude, Cursor,
// instruction files, or anything pasted), follow two or three steps with a prompt to copy into
// that AI, then paste the answer, or bring in files of any kind (documents, data exports, zips;
// the server reads what it can and names what it could not). Watch the Brain read it: split into ideas, sorted by
// kind, checked against what it knows, private detail flagged, and sifted against your goals and
// projects, each stage with one real example. Choose what stays; it waits in Catch up.

import { Check } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { useMoveInFiles, useMoveInKeep, useMoveInPreview, type MoveInSource } from "../api/hooks";
import type { MoveInIdea, MoveInKept, MoveInKind, MoveInPreview } from "../api/types";
import { CopyBlock, ErrorNote } from "../components/ui";
import { plural } from "../lib/format";

export const PROMPT =
  "List everything you remember about me, my work and my preferences, one fact per line, grouped as: about me, how I like work done, projects, people, facts. Leave out anything you are unsure of.";

interface Guide {
  kind: MoveInKind;
  label: string;
  steps: string[];
  prompt?: string;
}

export const GUIDES: Guide[] = [
  {
    kind: "chatgpt",
    label: "ChatGPT memory",
    steps: [
      "Open ChatGPT and start a new chat.",
      "Paste the prompt below and send it. (Or open Settings, Personalization, Manage memories, and copy them.)",
      "Copy its answer and paste it here.",
    ],
    prompt: PROMPT,
  },
  {
    kind: "claude",
    label: "Claude memory and projects",
    steps: [
      "Open Claude and start a new chat (inside a project, to include what it knows there).",
      "Paste the prompt below and send it. A project's own instructions can be pasted too.",
      "Copy its answer and paste it here.",
    ],
    prompt: PROMPT,
  },
  {
    kind: "cursor",
    label: "Cursor rules and memories",
    steps: [
      "In Cursor, open Settings, Rules: copy your User Rules.",
      "For a project, copy the files in its .cursor/rules folder, and Memories if you use them.",
      "Paste them here, one after another.",
    ],
  },
  {
    kind: "instructions",
    label: "Instruction files (CLAUDE.md, AGENTS.md)",
    steps: [
      "Find CLAUDE.md and AGENTS.md in your projects, and your own one in your home folder (.claude/CLAUDE.md).",
      "Open each one and paste it here, or drop the files on the box (a zip of them works too).",
    ],
  },
  {
    kind: "paste",
    label: "Anything else",
    steps: ["Notes, a bio, a brief: anything you would tell a new colleague. Paste it here."],
  },
];

const STATUS_WORDS: Record<MoveInIdea["status"], string> = {
  new: "New",
  known: "Already known",
  waiting: "Already waiting",
  disagree: "Might disagree",
  private: "Private detail",
};

/** The default choice: what fits, is new to the Brain, and holds no private detail. */
export function chosenByDefault(preview: MoveInPreview): string[] {
  return preview.ideas.filter((i) => (i.status === "new" || i.status === "disagree") && i.fits !== false).map((i) => i.id);
}

export function MoveInPage() {
  return (
    <div className="page move-in">
      <p className="eyebrow">Move in</p>
      <h1>Bring what your AIs already know</h1>
      <p className="lede">
        Once, from each AI you use. The Brain reads it, keeps only what fits your goals and projects (or says who you are and how you work), and you
        choose what stays.
      </p>
      <MoveIn />
    </div>
  );
}

const MAX_SOURCES = 8; // as many as the Brain reads at once

export function MoveIn({ onDone }: { onDone?: (kept: MoveInKept | null) => void }) {
  const [sources, setSources] = useState<MoveInSource[]>([]);
  const [kind, setKind] = useState<MoveInKind>("chatgpt");
  const [text, setText] = useState("");
  const preview = useMoveInPreview();
  const keep = useMoveInKeep();
  const reading = useMoveInFiles();
  const [chosen, setChosen] = useState<string[] | null>(null);
  const [kept, setKept] = useState<MoveInKept | null>(null);
  const [fileNotes, setFileNotes] = useState<string[]>([]);
  const guide = GUIDES.find((g) => g.kind === kind) ?? (GUIDES[0] as Guide);

  const read = (next: MoveInSource[]) => {
    setSources(next);
    preview.mutate(next, { onSuccess: (result) => setChosen(chosenByDefault(result)) });
  };

  const add = () => {
    if (!text.trim()) return;
    read([...sources, { kind, text, label: guide.label }]);
    setText("");
  };

  /** Files of any type, zips included: the server reads what it can and says what it could not. */
  const addFiles = (list: File[]) => {
    if (!list.length) return;
    reading.mutate(list, {
      onSuccess: (found) => {
        const room = MAX_SOURCES - sources.length;
        const taken = found.sources.slice(0, Math.max(0, room));
        const notes = [
          ...found.sources.filter((s) => s.note).map((s) => `${s.label}: ${s.note}`),
          ...found.skipped.map((s) => `${s.name}: not read, ${s.why}.`),
        ];
        if (found.sources.length > taken.length) notes.push(`Only ${MAX_SOURCES} sources are read at a time: bring the rest in next.`);
        setFileNotes(notes);
        if (taken.length) read([...sources, ...taken.map((s) => ({ kind: s.kind, text: s.text, label: s.label }))]);
      },
    });
  };

  if (kept) {
    return (
      <div className="move-in-done" role="status">
        <h2>
          <Check className="title-icon" aria-hidden="true" /> {plural(kept.proposed.length, "suggestion")} wait in Catch up
        </h2>
        <p>
          Keep them there and every AI you connect knows them.
          {kept.already.length ? ` ${plural(kept.already.length, "was", "were")} already waiting.` : ""}
          {kept.secrets_left_out ? ` ${plural(kept.secrets_left_out, "password or key")} left out: keep those in a password manager.` : ""}
        </p>
        {kept.refused.length ? <p className="warning small">Not taken: {kept.refused.map((r) => r.message).join("; ")}</p> : null}
        <div className="row">
          {onDone ? (
            <button type="button" className="primary" onClick={() => onDone(kept)}>
              Continue
            </button>
          ) : (
            <Link className="button primary" to="/catch-up">
              Catch up now
            </Link>
          )}
          <button
            type="button"
            className="link"
            onClick={() => {
              setKept(null);
              setSources([]);
              preview.reset();
              setChosen(null);
            }}
          >
            Move in from another AI
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="move-in-flow">
      <fieldset className="source-pick">
        <legend className="field-label">Where it lives</legend>
        <div className="chips">
          {GUIDES.map((g) => (
            <button key={g.kind} type="button" className={g.kind === kind ? "chip-button active" : "chip-button"} aria-pressed={g.kind === kind} onClick={() => setKind(g.kind)}>
              {g.label}
            </button>
          ))}
        </div>
        <p className="muted small">
          Meetings, transcripts and documents go through <Link to="/capture">Capture</Link>, where the Brain summarizes each one and pulls out what
          matters.
        </p>
      </fieldset>
      <ol className="steps">
        {guide.steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
      {guide.prompt ? <CopyBlock label="The prompt to copy" text={guide.prompt} prose /> : null}
      <label className="field">
        <span className="field-label">Paste it here</span>
        <textarea
          rows={8}
          value={text}
          placeholder="Paste what it said, or drop files here: any kind, zip files and data exports too"
          onChange={(event) => setText(event.target.value)}
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            const dropped = Array.from(event.dataTransfer.files ?? []);
            if (!dropped.length) return;
            event.preventDefault();
            addFiles(dropped);
          }}
        />
      </label>
      <div className="row">
        <button type="button" className="primary" disabled={!text.trim() || preview.isPending} onClick={add}>
          {preview.isPending ? "Reading…" : sources.length ? "Read this too" : "Read it"}
        </button>
        <label className="button file-pick">
          {reading.isPending ? "Reading files…" : "Or choose files"}
          <input
            type="file"
            multiple
            className="sr-only"
            aria-label="Choose files to bring in (any kind, zip files too)"
            disabled={reading.isPending || sources.length >= MAX_SOURCES}
            onChange={(event) => {
              addFiles(Array.from(event.target.files ?? []));
              event.target.value = "";
            }}
          />
        </label>
        {sources.length ? <span className="muted small">Read so far: {sources.map((s) => s.label).join(", ")}</span> : null}
        {onDone ? (
          <button type="button" className="link" onClick={() => onDone(null)}>
            Skip this for now
          </button>
        ) : null}
      </div>
      <p className="muted small">
        Any kind of file: documents, text, instruction files, a data export from ChatGPT or Claude (its conversations become your own words, newest
        first), or a zip of all of them. Pictures and recordings are named, not read.
      </p>
      {fileNotes.length ? (
        <ul className="muted small move-in-notes" aria-label="What happened to your files">
          {fileNotes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
      <ErrorNote error={preview.error ?? reading.error} />
      {preview.data && chosen ? (
        <>
          <Pipeline preview={preview.data} />
          <Choose preview={preview.data} chosen={chosen} onChange={setChosen} />
          <ErrorNote error={keep.error} />
          <div className="row">
            <button
              type="button"
              className="primary"
              disabled={!chosen.length || keep.isPending}
              onClick={() => keep.mutate({ sources, ids: chosen }, { onSuccess: setKept })}
            >
              {keep.isPending ? "Keeping…" : `Keep ${plural(chosen.length, "idea")}`}
            </button>
            <span className="muted small">They wait in Catch up for your yes. Nothing changes before that.</span>
          </div>
        </>
      ) : null}
    </div>
  );
}

/** Watch it learn: each stage with its real count and one real example to open. */
export function Pipeline({ preview }: { preview: MoveInPreview }) {
  const s = preview.stages;
  const byId = new Map(preview.ideas.map((i) => [i.id, i]));
  const example = (key: string) => byId.get(preview.examples[key] ?? "");
  const projects = Object.entries(s.for_projects ?? {});
  const stages: { label: string; count: string; example?: MoveInIdea; show: (i: MoveInIdea) => string }[] = [
    { label: "Read", count: `${s.chars.toLocaleString()} characters from ${plural(s.sources, "source")}`, show: () => "" },
    { label: "Split into ideas", count: plural(s.ideas, "idea"), example: example("split"), show: (i) => `“${i.original}” becomes “${i.text}”` },
    {
      label: "Sorted by kind",
      count: Object.entries(s.kinds)
        .filter(([, n]) => n)
        .map(([k, n]) => `${n} ${KIND_WORDS[k] ?? k}`)
        .join(", "),
      show: () => "",
    },
    { label: "Already known", count: plural(s.known + s.waiting, "idea"), example: example("known"), show: (i) => `“${i.text}”: ${i.why}${i.match ? `, in “${i.match.title}”` : ""}` },
    { label: "Might disagree", count: plural(s.disagree, "idea"), example: example("disagree"), show: (i) => `“${i.text}”: ${i.why}` },
    { label: "Private detail flagged", count: plural(s.private, "idea"), example: example("private"), show: (i) => `“${i.text}”: ${i.why}` },
  ];
  if (s.sifted) {
    stages.push({
      label: "Fits your goals and projects",
      count:
        `${plural(s.fits ?? 0, "idea")}` +
        (s.for_goals ? `: ${s.for_goals} for your goals` : "") +
        projects.map(([title, n]) => `, ${n} for ${title}`).join("") +
        (s.left_out ? `. Left out ${s.left_out}: see why below` : ""),
      example: example("left_out") ?? example("fits"),
      show: (i) => (i.fits ? `“${i.text}”: for ${i.serves.project?.title ?? i.serves.goal}` : `“${i.text}”: left out, ${i.left_out}`),
    });
  }
  return (
    <ol className="pipeline" aria-label="How the Brain read it">
      {stages.map((stage) => (
        <li key={stage.label}>
          <span className="pipeline-label">{stage.label}</span> <span className="muted">{stage.count}</span>
          {stage.example && stage.show(stage.example) ? (
            <details>
              <summary className="small">One example</summary>
              <p className="small">{stage.show(stage.example)}</p>
            </details>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

const KIND_WORDS: Record<string, string> = { identity: "about you", rule: "how you work", state: "where things stand", fact: "facts" };

function Choose({ preview, chosen, onChange }: { preview: MoveInPreview; chosen: string[]; onChange: (ids: string[]) => void }) {
  const toggle = (id: string, on: boolean) => onChange(on ? [...chosen, id] : chosen.filter((x) => x !== id));
  const keepable = preview.ideas.filter((i) => i.status !== "known" && i.status !== "waiting");
  const groups: [string, MoveInIdea[]][] = [
    ["For your goals and projects", keepable.filter((i) => i.fits && (i.serves.goal || i.serves.project))],
    ["About you and how you work", keepable.filter((i) => i.fits && !i.serves.goal && !i.serves.project)],
    ["Left out: tick to keep anyway", keepable.filter((i) => !i.fits)],
    ["Already in your Brain", preview.ideas.filter((i) => i.status === "known" || i.status === "waiting")],
  ];
  return (
    <div className="choose">
      {groups
        .filter(([, ideas]) => ideas.length)
        .map(([title, ideas]) => (
          <section key={title}>
            <h3>
              {title} <span className="muted small">({ideas.length})</span>
            </h3>
            <ul className="list quick-items">
              {ideas.map((idea) => {
                const known = idea.status === "known" || idea.status === "waiting";
                return (
                  <li key={idea.id}>
                    <label className="check">
                      <input type="checkbox" disabled={known || idea.secret} checked={chosen.includes(idea.id)} onChange={(event) => toggle(idea.id, event.target.checked)} />{" "}
                      {idea.text}
                      <span className="muted small">
                        {" "}
                        · {STATUS_WORDS[idea.status]}
                        {idea.serves.project ? ` · for ${idea.serves.project.title}` : idea.serves.goal ? ` · ${idea.serves.goal}` : ""}
                        {idea.left_out ? ` · ${idea.left_out}` : ""}
                        {idea.status === "private" || idea.status === "disagree" ? ` · ${idea.why}` : ""}
                      </span>
                    </label>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
    </div>
  );
}
