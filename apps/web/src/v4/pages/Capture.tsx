// Capture (v4 isCapture, Release 1): the only way in. Write or paste, upload any file, record a
// meeting. Every source is listed with where it really stands (captured to searchable), and
// picking one opens its section: the lifecycle, what to do next, and one card per proposed
// piece, decided here as in Catch up. Scout sits beside it.

import { type RefObject, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";

import type { DistillRequest, Note } from "../../api/types";
import { canRecord, useRecorder } from "../../components/Talk";
import { type Proposal, type SourceStatus, useInclude, useProposals, useReadAgain } from "../api";
import { DistillThread } from "../components/DistillThread";
import { ProposalCard } from "../components/ProposalCard";
import { Scout } from "../components/Scout";
import { css } from "../css";
import {
  KIND_LABEL,
  type SourceKind,
  proposalsFrom,
  sourceKind,
  useDistill,
  useDistillRequests,
  useNotes,
  useRetryReading,
  useSaveText,
  useStatuses,
  useUpload,
} from "../hooks/capture";
import { Btn, Failure, Later, Loading, Status, when } from "../ui";

// ------------------------------------------------------------------ shared with the detail page

export const STATUS_LABEL: Record<SourceStatus["status"], string> = {
  captured: "Captured",
  analysis_pending: "Analysis pending",
  retrying: "Retrying…",
  awaiting_review: "Awaiting review",
  indexing: "Indexing · not searchable yet",
  partial: "Partly searchable",
  searchable: "Searchable",
  nothing_kept: "Captured · nothing kept",
  excluded: "Excluded",
  failed: "Failed · see why",
};

const STEPS = ["Captured", "Analysis", "Review", "Accepted", "Indexing", "Searchable"];
const STAGE_AT: Record<SourceStatus["stage"], number> = { captured: 0, analysis: 1, review: 2, accepted: 3, indexing: 4, searchable: 5 };

/** Where a source is: Captured, Analysis, Review, Accepted, Indexing, Searchable. */
export function Lifecycle({ status }: { status: SourceStatus }) {
  const k = status.status;
  const idx = k === "failed" ? 1 : k === "excluded" ? 0 : (STAGE_AT[status.stage] ?? 0);
  return (
    <ol aria-label="Where this source is" style={css("list-style:none;margin:0;padding:0;display:flex;gap:4px;flex-wrap:wrap")}>
      {STEPS.map((label, i) => {
        const cur = i === idx;
        const done = i < idx;
        const text = cur && k === "failed" ? "Failed at analysis" : cur && k === "excluded" ? "Captured · excluded" : cur && k === "partial" ? "Partly searchable" : label;
        return (
          <li
            key={label}
            aria-current={cur ? "step" : undefined}
            style={css(
              `padding:5px 12px;border-radius:99px;font:${cur ? 500 : 400} 12.5px Geist;color:${done || cur ? "var(--ink)" : "var(--muted)"};background:${cur ? (k === "failed" ? "oklch(0.64 0.17 28 / .2)" : "var(--surface)") : "transparent"};box-shadow:${cur ? "var(--shadow)" : "inset 0 0 0 1px var(--line2)"}`,
            )}
          >
            {text}
            {done ? " ✓" : ""}
          </li>
        );
      })}
    </ol>
  );
}

/** What the status means, in plain words, and what to do next. */
export function statusNote(s: SourceStatus): string {
  switch (s.status) {
    case "awaiting_review":
      return `${s.waiting === 1 ? "1 piece waits" : `${s.waiting} pieces wait`} for you. Nothing from this source is searchable until you keep it and indexing finishes.`;
    case "analysis_pending":
      return s.detail && !s.task_id ? `${s.detail} Then your AI can read it.` : "Your AI is reading this and drafting proposals. You can leave; they'll wait here.";
    case "retrying":
      return "Retrying with the same settings…";
    case "captured":
      return "Saved privately. Not read by your AI yet: press Distill to have it propose what to keep.";
    case "nothing_kept":
      return "You skipped everything. The source stays in Capture; nothing from it is sent.";
    case "indexing":
      return "Kept and indexing. Not searchable until this finishes.";
    case "partial":
      return `${s.detail || `${s.searchable} of ${s.kept} kept pieces searchable.`} The rest is still indexing, so your AI can't find it yet.`;
    case "searchable":
      return "Kept pieces from this source are searchable and can be sent to your AI.";
    case "failed":
      return `${s.detail || "It could not be read."} Nothing was analysed. Retry uses the same model; it never switches to another one.`;
    case "excluded":
      return `You excluded this. It stays in Capture only, is never indexed, and is never sent to an AI.${s.detail ? ` Why: ${s.detail}` : ""}`;
    default:
      return "";
  }
}

/** The status note, with Retry, "I've allowed access" or Include in Brain where they apply. */
export function StatusNote({ id, status }: { id: string; status: SourceStatus }) {
  const readAgain = useReadAgain();
  const reread = useRetryReading();
  const include = useInclude();
  const [allowed, setAllowed] = useState(false);
  const k = status.status;
  const tone = k === "failed" ? "oklch(0.64 0.17 28 / .1)" : ["analysis_pending", "retrying", "partial"].includes(k) ? "oklch(0.74 0.12 80 / .14)" : "var(--soft)";
  // A failed model run is read again with the same model; a failed transcription is turned
  // into text again.
  const retry = () => (status.task_id ? readAgain.mutate({ id }) : reread.mutate(id));
  const busy = readAgain.isPending || reread.isPending;
  const error = readAgain.error ?? reread.error ?? include.error;
  return (
    <div role="status" style={css(`display:flex;gap:12px;align-items:center;padding:14px 16px;border-radius:14px;flex-wrap:wrap;background:${tone}`)}>
      <span style={css("font:400 14px/1.5 Geist;flex:1;min-width:220px")}>
        {statusNote(status)}
        {allowed && k === "failed" ? " Noted. Retry to check access again." : ""}
      </span>
      {k === "failed" && status.can_retry ? (
        <div style={css("display:flex;gap:8px;flex-wrap:wrap")}>
          <Btn kind="primary" onClick={retry} disabled={busy} style="padding:9px 16px;font:500 13.5px Geist">
            {busy ? "Retrying…" : "Retry"}
          </Btn>
          {!allowed ? (
            <Btn kind="ghost" onClick={() => setAllowed(true)} style="padding:9px 16px;font:500 13.5px Geist">
              I’ve allowed access
            </Btn>
          ) : null}
        </div>
      ) : null}
      {k === "excluded" ? (
        <Btn kind="ghost" onClick={() => include.mutate({ id })} disabled={include.isPending} style="padding:9px 16px;font:500 13.5px Geist">
          Include in Brain
        </Btn>
      ) : null}
      {error ? (
        <span role="alert" style={css("flex-basis:100%;font:400 13px Geist;color:oklch(0.55 0.17 28)")}>
          {(error as Error).message}
        </span>
      ) : null}
    </div>
  );
}

/** The proposal cards of one source; a card decided here stays (with Undo) after the list
 * refreshes without it. */
export function SourceCards({ proposals, onBrain }: { proposals: Proposal[]; onBrain?: () => void }) {
  const [touched, setTouched] = useState<Record<string, Proposal>>({});
  const shown = useMemo(() => {
    const ids = new Set(proposals.map((p) => p.id));
    return [...proposals, ...Object.values(touched).filter((p) => !ids.has(p.id))];
  }, [proposals, touched]);
  return (
    <>
      {shown.map((p) => (
        <div key={p.id} onClickCapture={() => setTouched((t) => (t[p.id] ? t : { ...t, [p.id]: p }))}>
          <ProposalCard p={p} onBrain={onBrain} />
        </div>
      ))}
    </>
  );
}

/** The distill requests' left-out pieces, newest request first. */
export function leftOutOf(requests: DistillRequest[] | undefined): { statement: string; why: string }[] {
  const latest = (requests ?? []).find((r) => (r.left_out ?? []).length > 0);
  return latest?.left_out ?? [];
}

export function canDistill(s: SourceStatus | undefined): boolean {
  if (!s) return false;
  return !["excluded", "analysis_pending", "retrying", "failed", "awaiting_review"].includes(s.status);
}

// ------------------------------------------------------------------ the page

const FILTERS: ["all" | SourceKind, string][] = [
  ["all", "Everything"],
  ["Meeting", "Meetings"],
  ["Upload", "Uploads"],
  ["Voice", "Voice notes"],
  ["Note", "Notes"],
];
const TS = (on: boolean) =>
  `padding:7px 14px;border-radius:99px;border:0;white-space:nowrap;font:${on ? 500 : 400} 13px Geist;background:${on ? "var(--ink)" : "transparent"};color:${on ? "var(--bg)" : "var(--ink2)"}`;
export const OUTLINE = "padding:9px 16px;border-radius:99px;border:1px solid var(--line2);background:transparent;color:var(--ink);font:500 13.5px Geist";
export const SOLID = "padding:9px 16px;border-radius:99px;background:var(--ink);color:var(--bg);border:0;font:500 13.5px Geist";

export function kindOf(n: Note): string {
  const ext = n.original?.filename?.includes(".") ? n.original.filename.split(".").pop() : "";
  return (ext || KIND_LABEL[sourceKind(n)]).toUpperCase();
}

function metaOf(n: Note): string {
  return [n.id, kindOf(n), when(n.created_at), n.projects?.length ? (n.projects.length === 1 ? "1 project" : `${n.projects.length} projects`) : "No project"].join(" · ");
}

export function CapturePage() {
  const [params, setParams] = useSearchParams();
  const notes = useNotes();
  const list = useMemo(() => notes.data ?? [], [notes.data]);
  const ids = useMemo(() => list.map((n) => n.id), [list]);
  const statuses = useStatuses(ids);
  const [filter, setFilter] = useState<"all" | SourceKind>("all");
  const [selId, setSelId] = useState<string | null>(params.get("source"));
  const [jump, setJump] = useState(false);
  const head = useRef<HTMLHeadingElement>(null);
  const text = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const recordButton = useRef<HTMLButtonElement>(null);

  // The quick links (Write or paste, Upload a file, Record a meeting) land here.
  useEffect(() => {
    if (params.get("paste")) text.current?.focus();
    if (params.get("upload")) fileInput.current?.click();
    if (params.get("record")) recordButton.current?.focus();
  }, [params]);

  const pick = useCallback(
    (id: string) => {
      setSelId(id);
      setJump(true);
      const next = new URLSearchParams(params);
      next.set("source", id);
      ["paste", "upload", "record"].forEach((k) => next.delete(k));
      setParams(next, { replace: true });
    },
    [params, setParams],
  );

  useEffect(() => {
    if (!jump || !head.current) return;
    head.current.scrollIntoView?.({ behavior: "smooth", block: "start" });
    head.current.focus({ preventScroll: true });
    setJump(false);
  }, [jump, selId]);

  const shown = list.filter((n) => filter === "all" || sourceKind(n) === filter);
  const selected = list.find((n) => n.id === selId) ?? null;

  return (
    <div className="gn-page" style={css("max-width:1200px;margin:0 auto;padding:56px 48px 96px;display:flex;flex-direction:column;gap:28px;box-sizing:border-box")}>
      <div style={css("display:flex;flex-direction:column;gap:8px")}>
        <h1 style={css("margin:0;font:400 44px/1.1 Newsreader;letter-spacing:-.02em")}>Capture</h1>
        <span style={css("font:400 17px/1.5 Geist;color:var(--ink2);max-width:760px")}>
          Everything comes in here: pasted text, files, meetings and Scout findings. It stays private until you keep something, and nothing is searchable until indexing finishes.
        </span>
      </div>
      <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:20px;align-items:start")}>
        <div style={css("display:flex;flex-direction:column;gap:20px;min-width:0")}>
          <Intake textRef={text} fileRef={fileInput} recordRef={recordButton} onSaved={pick} />
          <div style={css("display:flex;flex-direction:column;gap:10px")}>
            <div style={css("display:flex;justify-content:space-between;align-items:baseline")}>
              <h2 style={css("margin:0;font:400 28px Newsreader")}>Sources</h2>
              <span style={css("font:400 13px Geist;color:var(--muted)")}>{notes.data ? (shown.length === 1 ? "1 source" : `${shown.length} sources`) : ""}</span>
            </div>
            <div role="group" aria-label="Show" style={css("display:flex;gap:6px;flex-wrap:wrap")}>
              {FILTERS.map(([id, label]) => (
                <button key={id} aria-pressed={filter === id} onClick={() => setFilter(id)} style={css(TS(filter === id))}>
                  {label} · {id === "all" ? list.length : list.filter((n) => sourceKind(n) === id).length}
                </button>
              ))}
            </div>
            <div role="list" aria-label="Sources" style={css("background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:4px 8px")}>
              {notes.isLoading ? (
                <div style={css("padding:0 10px")}>
                  <Loading what="Loading your sources" />
                </div>
              ) : notes.error ? (
                <div style={css("padding:10px")}>
                  <Failure error={notes.error} retry={() => void notes.refetch()} />
                </div>
              ) : shown.length === 0 ? (
                <div style={css("padding:28px 0;text-align:center;font:400 14px Geist;color:var(--muted)")}>
                  {list.length ? "Nothing of this kind yet." : "Nothing here yet. Write, paste, upload a file or record a meeting above."}
                </div>
              ) : (
                shown.map((n) => {
                  const st = statuses.data?.[n.id];
                  const on = n.id === selId;
                  return (
                    <div role="listitem" key={n.id}>
                      <button
                        onClick={() => pick(n.id)}
                        aria-pressed={on}
                        className="gn-hover"
                        style={css(
                          `display:flex;align-items:center;gap:14px;padding:12px 10px;border:0;border-bottom:1px solid var(--line);border-radius:10px;background:${on ? "var(--soft)" : "transparent"};width:100%;text-align:left;color:var(--ink);flex-wrap:wrap;cursor:pointer`,
                        )}
                      >
                        <span style={css("padding:3px 9px;border-radius:99px;font:500 11.5px Geist;background:var(--soft);color:var(--ink2);flex:none")}>{KIND_LABEL[sourceKind(n)]}</span>
                        <div style={css("flex:1;min-width:180px;display:flex;flex-direction:column;gap:3px")}>
                          <span style={css("font:400 15.5px Geist")}>{n.title || "Untitled"}</span>
                          <span style={css("font:400 12.5px Geist;color:var(--muted)")}>{metaOf(n)}</span>
                        </div>
                        {st ? (
                          <Status kind={st.status}>{STATUS_LABEL[st.status] ?? st.label}</Status>
                        ) : (
                          <Status kind="captured">{statuses.error ? "Status unavailable" : "Checking status"}</Status>
                        )}
                      </button>
                    </div>
                  );
                })
              )}
            </div>
            {statuses.error ? <Failure error={statuses.error} retry={() => void statuses.refetch()} /> : null}
          </div>
        </div>
        <Scout />
      </div>
      {selected ? <Selected note={selected} status={statuses.data?.[selected.id]} headRef={head} /> : null}
    </div>
  );
}

// ------------------------------------------------------------------ intake

function Intake({
  textRef,
  fileRef,
  recordRef,
  onSaved,
}: {
  textRef: RefObject<HTMLTextAreaElement | null>;
  fileRef: RefObject<HTMLInputElement | null>;
  recordRef: RefObject<HTMLButtonElement | null>;
  onSaved: (id: string) => void;
}) {
  const save = useSaveText();
  const upload = useUpload();
  const { begin, end } = useRecorder();
  const [value, setValue] = useState("");
  const [rec, setRec] = useState<"idle" | "asking" | "rec" | "sending">("idle");
  const [seconds, setSeconds] = useState(0);
  const [recError, setRecError] = useState<string | null>(null);
  const started = useRef(0);
  const recordable = canRecord();

  useEffect(() => {
    if (rec !== "rec") return;
    const timer = window.setInterval(() => setSeconds(Math.floor((Date.now() - started.current) / 1000)), 500);
    return () => window.clearInterval(timer);
  }, [rec]);

  async function toggleMeeting() {
    setRecError(null);
    if (rec === "idle") {
      setRec("asking");
      try {
        await begin();
      } catch {
        setRec("idle");
        setRecError("The microphone is blocked. Allow it for this site in your browser, then try again.");
        return;
      }
      started.current = Date.now();
      setSeconds(0);
      setRec("rec");
      return;
    }
    if (rec !== "rec") return;
    setRec("sending");
    const blob = await end();
    if (!blob || blob.size === 0) {
      setRec("idle");
      setRecError("Nothing was recorded. Try again.");
      return;
    }
    upload.mutate(
      { file: blob, title: `Meeting, ${when(new Date().toISOString())}` },
      {
        onSuccess: (note) => {
          setRec("idle");
          onSaved(note.id);
        },
        onError: () => setRec("idle"),
      },
    );
  }

  const time = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  const canSave = value.trim().length > 0 && !save.isPending;
  const error = save.error ?? upload.error;

  return (
    <div style={css("background:var(--surface);border-radius:22px;box-shadow:var(--shadow2);padding:16px 18px 14px;display:flex;flex-direction:column;gap:10px")}>
      <label htmlFor="r1paste" style={css("font:500 13px Geist")}>
        Write or paste
      </label>
      <textarea
        id="r1paste"
        ref={textRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        rows={3}
        placeholder="Notes, an email, a chat, a transcript…"
        style={css("border:1px solid var(--line2);border-radius:12px;outline:none;resize:vertical;background:transparent;color:var(--ink);font:400 15px/1.55 Geist;padding:10px 12px")}
      />
      <div style={css("display:flex;gap:8px;align-items:center;flex-wrap:wrap")}>
        <input
          ref={fileRef}
          type="file"
          multiple
          aria-label="Choose a file to upload"
          className="gn-sr"
          tabIndex={-1}
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            e.target.value = "";
            files.forEach((file) => upload.mutate({ file }, { onSuccess: (note) => onSaved(note.id) }));
          }}
        />
        <button onClick={() => fileRef.current?.click()} disabled={upload.isPending} style={css(OUTLINE)}>
          {upload.isPending && rec === "idle" ? "Uploading…" : "Upload a file"}
        </button>
        <button
          ref={recordRef}
          onClick={() => void toggleMeeting()}
          disabled={!recordable || rec === "asking" || rec === "sending"}
          aria-pressed={rec === "rec"}
          title={recordable ? "Recorded here, turned into text on this computer" : "This browser can't record here."}
          style={css(OUTLINE)}
        >
          {rec === "rec" ? `Stop recording · ${time}` : rec === "asking" ? "Allow the microphone…" : rec === "sending" ? "Saving the recording…" : "Record a meeting"}
        </button>
        <span style={css("font:400 12px Geist;color:var(--muted);flex:1;min-width:140px")}>
          {recordable ? "Read on this computer first. Private until you keep something." : "This browser can't record here. Upload a recording instead."}
        </span>
        <button
          onClick={() =>
            save.mutate(
              { body: value.trim() },
              {
                onSuccess: (note) => {
                  setValue("");
                  onSaved(note.id);
                },
              },
            )
          }
          disabled={!canSave}
          style={css(
            `padding:8px 16px;border-radius:99px;border:0;font:500 13.5px Geist;${value.trim() ? "background:var(--ink);color:var(--bg)" : "background:var(--soft);color:var(--muted);cursor:not-allowed"}`,
          )}
        >
          {save.isPending ? "Saving…" : "Save to Capture"}
        </button>
      </div>
      {recError ? <span role="alert" style={css("font:400 13px Geist;color:oklch(0.55 0.17 28)")}>{recError}</span> : null}
      {error ? <span role="alert" style={css("font:400 13px Geist;color:oklch(0.55 0.17 28)")}>{(error as Error).message}</span> : null}
    </div>
  );
}

// ------------------------------------------------------------------ the selected source

function Selected({ note, status, headRef }: { note: Note; status?: SourceStatus; headRef: RefObject<HTMLHeadingElement | null> }) {
  const proposals = useProposals();
  const requests = useDistillRequests(note.id);
  const distill = useDistill();
  const [thread, setThread] = useState(false);
  const taskIds = (requests.data ?? []).map((r) => r.task_id);
  const mine = proposalsFrom(proposals.data, note.id, status, taskIds);
  const analysing = status?.status === "analysis_pending" || status?.status === "retrying";

  return (
    <section id="r1-sel" aria-labelledby="r1SelH" style={css("display:flex;flex-direction:column;gap:16px;padding-top:12px;scroll-margin-top:24px")}>
      <div style={css("display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap")}>
        <div style={css("display:flex;flex-direction:column;gap:6px")}>
          <span style={css("font:500 10.5px 'Geist Mono';letter-spacing:.06em;color:var(--muted)")}>
            DISTILL · {note.id} · v{note.version} · {kindOf(note)}
          </span>
          <h2 id="r1SelH" ref={headRef} tabIndex={-1} style={css("margin:0;font:400 32px/1.15 Newsreader;outline:none")}>
            {note.title || "Untitled"}
          </h2>
          <span style={css("font:400 13.5px Geist;color:var(--ink2)")}>
            {[when(note.created_at), KIND_LABEL[sourceKind(note)], note.original?.filename].filter(Boolean).join(" · ")}
          </span>
        </div>
        <div style={css("display:flex;gap:8px;flex-wrap:wrap")}>
          {mine.length > 0 && !analysing ? (
            <button onClick={() => setThread(true)} style={css(SOLID)}>
              See it on your Brain
            </button>
          ) : null}
          {canDistill(status) ? (
            <button onClick={() => distill.mutate(note.id)} disabled={distill.isPending} style={css(mine.length ? OUTLINE : SOLID)}>
              {distill.isPending ? "Starting…" : status?.status === "captured" ? "Distill" : "Distill again"}
            </button>
          ) : null}
          <Link to={`/capture/${encodeURIComponent(note.id)}`} style={css(OUTLINE + ";text-decoration:none;display:inline-block")}>
            Open the source
          </Link>
          <button disabled title="Turning a source into to-dos is not available yet" style={css(OUTLINE + ";color:var(--muted)")}>
            To-dos
            <Later />
          </button>
        </div>
      </div>
      {status ? (
        <>
          <Lifecycle status={status} />
          <StatusNote id={note.id} status={status} />
        </>
      ) : (
        <Loading what="Checking where it stands" />
      )}
      {distill.isSuccess ? (
        <span role="status" style={css("font:400 13.5px Geist;color:var(--ink2)")}>
          Asked your AI to read it. Its proposals will wait here and in Catch up.
        </span>
      ) : null}
      {distill.error ? <Failure error={distill.error} /> : null}
      {proposals.isLoading ? (
        <Loading what="Loading its proposals" />
      ) : proposals.error ? (
        <Failure error={proposals.error} retry={() => void proposals.refetch()} />
      ) : analysing ? null : (
        <>
          {mine.length ? (
            <div style={css("display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap;padding-top:4px")}>
              <span style={css("font:500 15px Geist")}>Pieces from this source · {mine.length} waiting</span>
              <span style={css("font:400 13px Geist;color:var(--muted)")}>Click a piece to see where it lands on your Brain.</span>
            </div>
          ) : null}
          <SourceCards proposals={mine} onBrain={() => setThread(true)} />
        </>
      )}
      {thread ? <DistillThread proposals={mine} sourceTitle={note.title || "Untitled"} onClose={() => setThread(false)} leftOut={leftOutOf(requests.data)} /> : null}
    </section>
  );
}
