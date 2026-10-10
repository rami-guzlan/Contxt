// Capture: everything brought in before it becomes Brain knowledge. Talk (hold Space or the
// button), record a meeting, upload audio, a transcript or a document. Each one stays private to
// you until you pull from it or file it; audio turns into text on this computer. Writing lives in
// Work, Workspace (docs and links are notes too, so nothing moved).

import { AudioLines, NotebookPen, Square } from "lucide-react";
import { useEffect, useRef, useState, type DragEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { useBringIn, useDistillRequests, useDownloadSpeech, useNewDoc, useNotes, useSpeech } from "../api/hooks";
import type { CaptureKind, DistillRequest, Note } from "../api/types";
import { CAPTURE_NAMES, KindIcon, TranscriptionState, UploadButton, duration } from "../components/CaptureParts";
import { TalkButton, canRecord, useRecorder } from "../components/Talk";
import { FirstVisitTip } from "../components/Tips";
import { Empty, ErrorNote, Loading, Section } from "../components/ui";
import { when } from "../lib/format";
import { LeftOutSearch } from "../components/LeftOutSearch";

const KINDS: { id: CaptureKind | "all"; label: string }[] = [
  { id: "all", label: "Everything" },
  { id: "talk", label: "Talk" },
  { id: "recording", label: "Recordings" },
  { id: "transcript", label: "Transcripts" },
  { id: "document", label: "Documents" },
];
// Docs and links are written in Work, Workspace; Capture is the inbox for what comes in.
const WRITTEN = new Set(["note", "link"]);
const captureUrl = (id: string) => `/capture/${encodeURIComponent(id)}`;

export function CapturePage() {
  const [archived, setArchived] = useState(false);
  const [kind, setKind] = useState<CaptureKind | "all">("all");
  const [over, setOver] = useState(false);
  const { data: notes, isLoading, error } = useNotes(archived);
  const { data: pulls } = useDistillRequests();
  const bring = useBringIn();
  const [failures, setFailures] = useState<string[]>([]);
  const create = useNewDoc();
  const navigate = useNavigate();

  async function bringIn(files: FileList | File[]) {
    const list = Array.from(files);
    const failed: string[] = [];
    let last: Note | null = null;
    for (const file of list) {
      try {
        last = await bring.mutateAsync({ file });
      } catch (caught) {
        failed.push(`${file.name}: ${caught instanceof Error ? caught.message : "it could not be brought in."}`);
      }
    }
    setFailures(failed);
    if (list.length === 1 && last) navigate(captureUrl(last.id));
  }

  const brought = (notes ?? []).filter((n) => !WRITTEN.has(n.capture ?? "note"));
  const counts = new Map<string, number>();
  for (const note of brought) counts.set(note.capture ?? "note", (counts.get(note.capture ?? "note") ?? 0) + 1);
  const shown = brought.filter((n) => kind === "all" || (n.capture ?? "note") === kind);
  return (
    <div
      className={over ? "page capture dropping" : "page capture"}
      onDragOver={(event: DragEvent) => {
        if (event.dataTransfer.types.includes("Files")) {
          event.preventDefault();
          setOver(true);
        }
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(event: DragEvent) => {
        event.preventDefault();
        setOver(false);
        if (event.dataTransfer.files.length) void bringIn(event.dataTransfer.files);
      }}
    >
      <h1>Capture</h1>
      <FirstVisitTip id="capture">
        What you bring in waits here, private to you. Your Brain summarizes each one and pulls out what serves your goals and projects; you
        keep what you want in Catch up.
      </FirstVisitTip>
      <p className="lede">
        What you bring in waits here, private to you, until you pull from it or file it in the Brain. Talk, record a meeting, or drop in audio,
        a transcript or a document. To write or plan, use your <Link to="/work/workspace">Workspace</Link>.
      </p>
      <div className="capture-actions" data-tour="capture-actions">
        <TalkButton big />
        <RecordButton />
        <UploadButton onFiles={(files) => void bringIn(files)} busy={bring.isPending} />
        <button
          type="button"
          disabled={create.isPending}
          onClick={() => create.mutate({ template: "blank" }, { onSuccess: (doc) => navigate(`/work/workspace/${encodeURIComponent(doc.id)}`) })}
          title="A new doc in your Workspace"
        >
          <NotebookPen className="button-icon" aria-hidden="true" />
          Write
        </button>
      </div>
      <p className="small muted">Hold Space anywhere (outside a text field) to talk; tap it to keep listening until you tap again.</p>
      <SpeechNotice />
      {failures.length ? (
        <div className="warning" role="alert">
          {failures.map((line) => (
            <p key={line}>{line}</p>
          ))}
        </div>
      ) : null}
      <ErrorNote error={create.error} />
      <div className="row capture-filters" role="group" aria-label="Show">
        {KINDS.filter((k) => k.id === "all" || counts.get(k.id)).map((k) => (
          <button key={k.id} type="button" className={kind === k.id ? "chip-button active" : "chip-button"} aria-pressed={kind === k.id} onClick={() => setKind(k.id)}>
            {k.label}
            {k.id === "all" ? "" : ` ${counts.get(k.id)}`}
          </button>
        ))}
        <button type="button" className="link" onClick={() => setArchived(!archived)}>
          {archived ? "Back to what you brought in" : "Set aside"}
        </button>
      </div>
      <Section title={archived ? "Set aside" : "Newest first"} tour="capture-list">
        {isLoading ? (
          <Loading />
        ) : !notes ? (
          <ErrorNote error={error} />
        ) : shown.length ? (
          <ul className="capture-list">
            {shown.map((note) => (
              <CaptureRow key={note.id} note={note} pulls={(pulls ?? []).filter((p) => p.items.includes(note.id))} />
            ))}
          </ul>
        ) : (
          <Empty
            why={
              archived
                ? "Nothing is set aside."
                : "Nothing here yet. Talk, or drop in a recording, a transcript or a document: it stays private until you pull from it."
            }
          />
        )}
      </Section>
      <LeftOutSearch />
    </div>
  );
}

/** Where an item stands, in a word: not read yet, summarized, kept (how many), or set aside. */
export function captureStatus(note: Note, pulls: DistillRequest[]): string {
  if (note.archived_at) return "Set aside";
  const kept = pulls.flatMap((p) => p.proposals).filter((p) => p.status === "approved").length;
  if (kept) return `Kept ${kept}`;
  const waiting = pulls.flatMap((p) => p.proposals).filter((p) => p.status === "pending").length;
  if (waiting) return `${waiting} to keep`;
  if (note.digest?.state === "ready") return "Summarized";
  return "Not read yet";
}

function CaptureRow({ note, pulls }: { note: Note; pulls: DistillRequest[] }) {
  const status = captureStatus(note, pulls);
  const kind = note.capture ?? "note";
  const facts = [
    CAPTURE_NAMES[kind],
    note.transcription?.duration ? duration(note.transcription.duration) : null,
    note.original && kind !== "talk" && kind !== "recording" ? note.original.filename : null,
    note.edited_by,
    when(note.updated_at),
  ].filter(Boolean);
  return (
    <li className="capture-row">
      <KindIcon kind={kind} />
      <span className="capture-main">
        <Link to={captureUrl(note.id)}>{note.title}</Link>
        {note.digest?.summary ? <span className="capture-gist">{gist(note.digest.summary)}</span> : null}
        <span className="muted small">{facts.join(" · ")}</span>
      </span>
      <span className={`chip small status-chip status-${status.split(" ")[0]?.toLowerCase()}`}>{status}</span>
      <TranscriptionState note={note} compact />
    </li>
  );
}

/** A summary's first sentence, for a list. */
function gist(summary: string): string {
  const first = summary.match(/^.+?[.!?](\s|$)/)?.[0]?.trim() ?? summary;
  return first.length > 160 ? `${first.slice(0, 159)}…` : first;
}

/** Speech to text needs its model once; say so where talking and recording happen. */
function SpeechNotice() {
  const { data: speech } = useSpeech();
  const download = useDownloadSpeech();
  if (!speech || speech.ready) return null;
  if (!speech.installed) {
    return <p className="notice">Speech to text isn't installed with this app, so talk and recordings are kept but not turned into text.</p>;
  }
  return (
    <div className="notice row">
      <span>
        {speech.downloading
          ? "Downloading the speech model…"
          : `Talk and recordings turn into text on this computer once its speech model is here (about ${speech.about_mb} MB, once).`}
      </span>
      {speech.downloading ? null : (
        <button type="button" disabled={download.isPending} onClick={() => download.mutate()}>
          Download it
        </button>
      )}
      {speech.error ? <span className="error small">{speech.error}</span> : null}
    </div>
  );
}

/** Record a meeting or a longer talk; it is turned into text in the background, with times. */
function RecordButton() {
  const { begin, end } = useRecorder();
  const bring = useBringIn();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const button = useRef<HTMLButtonElement>(null);
  // "+ Add, Record a meeting" lands here with the button ready to press.
  useEffect(() => {
    if (params.get("record")) button.current?.focus();
  }, [params]);
  const [on, setOn] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const started = useRef(0);
  useEffect(() => {
    if (!on) return;
    const timer = window.setInterval(() => setSeconds(Math.floor((Date.now() - started.current) / 1000)), 500);
    return () => window.clearInterval(timer);
  }, [on]);
  async function toggle() {
    setError(null);
    if (!on) {
      if (!canRecord()) {
        setError("This browser can't record here.");
        return;
      }
      try {
        await begin();
      } catch {
        setError("The microphone is blocked. Allow it for this site in your browser, then try again.");
        return;
      }
      started.current = Date.now();
      setSeconds(0);
      setOn(true);
      return;
    }
    setOn(false);
    const blob = await end();
    if (!blob) return;
    const extension = blob.type.includes("mp4") ? "m4a" : "webm";
    bring.mutate(
      { file: new File([blob], `Recording.${extension}`, { type: blob.type }) },
      { onSuccess: (note) => navigate(captureUrl(note.id)), onError: (caught) => setError(caught.message) },
    );
  }
  return (
    <>
      <button ref={button} type="button" className={on ? "record live" : "record"} aria-pressed={on} disabled={bring.isPending} onClick={() => void toggle()}>
        {on ? <Square className="button-icon" aria-hidden="true" /> : <AudioLines className="button-icon" aria-hidden="true" />}
        {on ? `Stop recording ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}` : "Record"}
      </button>
      {error ? <span className="error small">{error}</span> : null}
    </>
  );
}
