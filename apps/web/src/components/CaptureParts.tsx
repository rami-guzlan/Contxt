// What the places that show captures share: the icon for each kind, how far a spoken one's text
// is, where it came from, and the button that brings files in.

import { AudioLines, FileText, File as FileIcon, Mic, NotebookPen, Upload } from "lucide-react";
import { useRef, type ReactNode } from "react";
import { Link } from "react-router";

import { captureOriginalUrl, useRetryCapture, useSpeech } from "../api/hooks";
import type { CaptureKind, Note } from "../api/types";
import { bytes } from "../lib/format";

export const CAPTURE_NAMES: Record<CaptureKind, string> = {
  note: "Note",
  talk: "Talk",
  recording: "Recording",
  transcript: "Transcript",
  document: "Document",
  link: "Link",
};
export const ACCEPT = "audio/*,video/*,.vtt,.srt,.txt,.md,.docx,.pdf,.pptx,.html,.htm";

export function KindIcon({ kind }: { kind: CaptureKind | undefined }) {
  const props = { className: "capture-icon", "aria-hidden": true } as const;
  if (kind === "talk") return <Mic {...props} />;
  if (kind === "recording") return <AudioLines {...props} />;
  if (kind === "transcript") return <FileText {...props} />;
  if (kind === "document") return <FileIcon {...props} />;
  return <NotebookPen {...props} />;
}

export function duration(seconds: number): string {
  const total = Math.round(seconds);
  const minutes = Math.floor(total / 60);
  return minutes ? `${minutes} min ${String(total % 60).padStart(2, "0")} s` : `${total} s`;
}

/** Where a spoken capture's text is: waiting, being written (how far), or what went wrong. */
export function TranscriptionState({ note, compact = false }: { note: Note; compact?: boolean }) {
  const { data: speech } = useSpeech();
  const retry = useRetryCapture();
  const state = note.transcription?.state;
  if (!state || state === "ready") return null;
  if (state === "failed") {
    return (
      <span className={compact ? "capture-state failed" : "capture-state failed card"}>
        <span className="error">{compact ? "Couldn't turn it into text" : note.transcription?.error ?? "It couldn't be turned into text."}</span>
        <button type="button" disabled={retry.isPending} onClick={() => retry.mutate(note.id)}>
          Try again
        </button>
      </span>
    );
  }
  const percent = Math.round((note.transcription?.progress ?? 0) * 100);
  const waitingForModel = state === "pending" && speech && !speech.ready;
  const text = waitingForModel
    ? "Waiting for the speech model"
    : state === "pending"
      ? "Waiting its turn to become text"
      : `Turning it into text, ${percent}%`;
  return (
    <span className={compact ? "capture-state" : "capture-state card"} role="status">
      <span>{text}</span>
      {state === "working" ? (
        <span className="meter" aria-hidden="true">
          <span style={{ width: `${Math.max(4, percent)}%` }} />
        </span>
      ) : null}
      {waitingForModel && !compact ? <Link to="/settings?tab=connections">Get the speech model</Link> : null}
    </span>
  );
}

/** What the capture came from: its audio to play, or its original to download. */
/** "docs.google.com" for a link's address; the address itself when it does not parse. */
function hostOf(url: string): string {
  try {
    return new URL(url).host || url;
  } catch {
    return url;
  }
}

export function CaptureSource({ note }: { note: Note }) {
  if (note.url)
    return (
      <div className="capture-source">
        <a className="button" href={note.url} target="_blank" rel="noreferrer">
          Open {hostOf(note.url)}
        </a>
        <span className="muted small">A link you keep here. Write below what it is for and what to look at.</span>
      </div>
    );
  if (!note.original) return null;
  const spoken = note.capture === "talk" || note.capture === "recording";
  return (
    <div className="capture-source">
      {spoken ? (
        <audio controls preload="metadata" src={captureOriginalUrl(note.id)} aria-label={`The ${CAPTURE_NAMES[note.capture ?? "recording"].toLowerCase()}`} />
      ) : (
        <span className="muted small">
          Brought in from {note.original.filename} ({bytes(note.original.size)})
        </span>
      )}
      <a className="small" href={captureOriginalUrl(note.id, true)} download>
        Download the original
      </a>
    </div>
  );
}

export function UploadButton({ onFiles, busy, children }: { onFiles: (files: FileList) => void; busy?: boolean; children?: ReactNode }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <input
        ref={input}
        type="file"
        multiple
        accept={ACCEPT}
        hidden
        aria-label="Files to bring in"
        onChange={(event) => {
          if (event.target.files?.length) onFiles(event.target.files);
          event.target.value = "";
        }}
      />
      <button type="button" disabled={busy} onClick={() => input.current?.click()}>
        <Upload className="button-icon" aria-hidden="true" />
        {busy ? "Bringing it in…" : children ?? "Upload"}
      </button>
    </>
  );
}
