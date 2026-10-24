// One capture (v4 isCapDetail, Release 1): its text or transcript, the original to play or
// download, where it stands, its proposals (as cards or on your Brain), and Exclude or Include.

import { useState } from "react";
import { Link, useParams } from "react-router";

import { useExclude, useProposals } from "../api";
import { DistillThread } from "../components/DistillThread";
import { css } from "../css";
import { KIND_LABEL, captureOriginalUrl, proposalsFrom, sourceKind, useDistill, useDistillRequests, useNote, useStatuses } from "../hooks/capture";
import { Btn, Failure, Later, Loading, S, when } from "../ui";
import { Lifecycle, OUTLINE, SOLID, SourceCards, StatusNote, canDistill, kindOf, leftOutOf } from "./Capture";

const TS = (on: boolean) =>
  `padding:7px 14px;border-radius:99px;border:0;white-space:nowrap;font:${on ? 500 : 400} 13px Geist;background:${on ? "var(--ink)" : "transparent"};color:${on ? "var(--bg)" : "var(--ink2)"}`;

function size(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function CaptureDetailPage() {
  const { captureId = "" } = useParams();
  const note = useNote(captureId);
  const statuses = useStatuses(captureId ? [captureId] : []);
  const status = statuses.data?.[captureId];
  const proposals = useProposals();
  const requests = useDistillRequests(captureId);
  const distill = useDistill();
  const exclude = useExclude();
  const [tab, setTab] = useState<"view" | "distill">("view");
  const [mode, setMode] = useState<"brain" | "list">("brain");
  const [reason, setReason] = useState("");

  const wide = tab === "distill" && mode === "brain";
  const wrap = `max-width:${wide ? 1240 : 720}px;margin:0 auto;padding:48px 48px 96px;display:flex;flex-direction:column;gap:28px;box-sizing:border-box`;

  if (note.isLoading)
    return (
      <div className="gn-page" style={css(wrap)}>
        <Loading what="Loading the capture" />
      </div>
    );
  if (note.error || !note.data)
    return (
      <div className="gn-page" style={css(wrap)}>
        <Link to="/capture" style={css("align-self:flex-start;font:400 14px Geist;color:var(--muted);text-decoration:none")}>
          ← Capture
        </Link>
        <Failure error={note.error ?? new Error("No capture with that id.")} retry={() => void note.refetch()} />
      </div>
    );

  const n = note.data;
  const kind = sourceKind(n);
  const viewLabel = kind === "Meeting" || kind === "Voice" ? "Transcript" : kind === "Upload" ? "The file" : "What you wrote";
  const taskIds = (requests.data ?? []).map((r) => r.task_id);
  const mine = proposalsFrom(proposals.data, n.id, status, taskIds);
  const tr = n.transcription;
  const audio = n.original?.mime?.startsWith("audio/") || n.original?.mime?.startsWith("video/");
  const excluded = status?.status === "excluded";

  return (
    <div className="gn-page" style={css(wrap)}>
      <Link to="/capture" style={css("align-self:flex-start;border:0;background:transparent;padding:0;font:400 14px Geist;color:var(--muted);text-decoration:none")}>
        ← Capture
      </Link>
      <div style={css("display:flex;flex-direction:column;gap:10px")}>
        <span style={css("font:500 11px 'Geist Mono';color:var(--muted);letter-spacing:.04em")}>
          {kindOf(n)} · {n.id} · v{n.version}
        </span>
        <h1 style={css("margin:0;font:400 38px/1.15 Newsreader;letter-spacing:-.015em")}>{n.title || "Untitled"}</h1>
        <span style={css("font:400 14px Geist;color:var(--ink2)")}>
          {[when(n.created_at), KIND_LABEL[kind], tr?.duration ? `${Math.round(tr.duration / 60)} min` : "", n.projects?.length ? `${n.projects.length} linked project${n.projects.length === 1 ? "" : "s"}` : "No project"]
            .filter(Boolean)
            .join(" · ")}
        </span>
      </div>
      {status ? (
        <div style={css("display:flex;flex-direction:column;gap:10px")}>
          <Lifecycle status={status} />
          <StatusNote id={n.id} status={status} />
        </div>
      ) : statuses.error ? (
        <Failure error={statuses.error} retry={() => void statuses.refetch()} />
      ) : (
        <Loading what="Checking where it stands" />
      )}
      <div role="tablist" aria-label="Capture" style={css("display:flex;gap:6px;flex-wrap:wrap")}>
        <button role="tab" aria-selected={tab === "view"} onClick={() => setTab("view")} style={css(TS(tab === "view"))}>
          {viewLabel}
        </button>
        <button role="tab" aria-selected={tab === "distill"} onClick={() => setTab("distill")} style={css(TS(tab === "distill"))}>
          Distill into context{mine.length ? ` · ${mine.length}` : ""}
        </button>
        <button role="tab" aria-selected={false} disabled title="Not available yet" style={css(TS(false) + ";color:var(--muted)")}>
          To-dos
          <Later />
        </button>
      </div>

      {tab === "view" ? (
        <div style={css("display:flex;flex-direction:column;gap:22px")}>
          {n.digest?.state === "ready" && n.digest.summary ? (
            <div style={css("padding:18px 20px;border-radius:18px;background:var(--soft);font:400 16px/1.6 Geist")}>{n.digest.summary}</div>
          ) : null}
          {tr && (tr.state === "pending" || tr.state === "working") ? (
            <div role="status" style={css("display:flex;align-items:center;gap:10px;font:400 15px Geist;color:var(--ink2)")}>
              <span style={css("width:8px;height:8px;border-radius:50%;background:oklch(0.74 0.12 80);animation:gnDot 1s infinite")} />
              Turning it into text on this computer{tr.progress ? ` · ${Math.round(tr.progress * 100)}%` : ""}…
            </div>
          ) : tr?.state === "failed" ? (
            <div role="alert" style={css("padding:14px 16px;border-radius:14px;background:oklch(0.64 0.17 28 / .1);font:400 14px/1.5 Geist")}>
              It couldn’t be turned into text: {tr.error || "no reason was given"}. Retry above, or upload a transcript instead.
            </div>
          ) : n.body?.trim() ? (
            <div style={css("display:flex;flex-direction:column")}>
              {n.body.split(/\n{2,}/).map((para, i) => (
                <p key={i} style={css("margin:0;padding:14px 0;border-top:1px solid var(--line);font:400 16px/1.6 Geist;white-space:pre-wrap")}>
                  {para}
                </p>
              ))}
            </div>
          ) : (
            <span style={css(S.muted)}>No text in it yet.</span>
          )}
          {n.original ? (
            <div style={css("padding:18px;border-radius:18px;border:1px solid var(--line);display:flex;flex-direction:column;gap:10px")}>
              <span style={css("font:500 13px Geist;color:var(--muted)")}>The original</span>
              {audio ? <audio controls preload="none" src={captureOriginalUrl(n.id)} style={css("width:100%")} aria-label="Play the original" /> : null}
              <div style={css("display:flex;gap:12px;align-items:center;flex-wrap:wrap")}>
                <span style={css("font:400 14px Geist;flex:1;word-break:break-all")}>
                  {n.original.filename} · {size(n.original.size)}
                </span>
                <a href={captureOriginalUrl(n.id, true)} download style={css(OUTLINE + ";text-decoration:none")}>
                  Download the original
                </a>
              </div>
            </div>
          ) : null}
          <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr));gap:12px")}>
            <button
              onClick={() => setTab("distill")}
              className="gn-hover"
              style={css("padding:20px;border-radius:18px;border:1px solid var(--line);background:var(--surface);text-align:left;color:var(--ink);display:flex;flex-direction:column;gap:4px")}
            >
              <span style={css("font:500 15px Geist")}>Distill into context</span>
              <span style={css("font:400 13px/1.45 Geist;color:var(--muted)")}>Pick what your Brain should keep</span>
            </button>
            <button disabled style={css("padding:20px;border-radius:18px;border:1px solid var(--line);background:var(--surface);text-align:left;color:var(--muted);display:flex;flex-direction:column;gap:4px")}>
              <span style={css("font:500 15px Geist")}>
                Make a to-do list
                <Later />
              </span>
              <span style={css("font:400 13px/1.45 Geist;color:var(--muted)")}>Edit it, then send it to a project</span>
            </button>
          </div>
        </div>
      ) : (
        <div style={css("display:flex;flex-direction:column;gap:16px")}>
          <div style={css("display:flex;gap:8px;align-items:center;flex-wrap:wrap")}>
            <span style={css("font:400 12.5px Geist;color:var(--muted);margin-right:4px")}>See it</span>
            <button aria-pressed={mode === "brain"} onClick={() => setMode("brain")} style={css(TS(mode === "brain"))}>
              On your Brain
            </button>
            <button aria-pressed={mode === "list"} onClick={() => setMode("list")} style={css(TS(mode === "list"))}>
              As a list
            </button>
            {canDistill(status) ? (
              <button onClick={() => distill.mutate(n.id)} disabled={distill.isPending} style={css((mine.length ? OUTLINE : SOLID) + ";margin-left:auto")}>
                {distill.isPending ? "Starting…" : status?.status === "captured" ? "Distill" : "Distill again"}
              </button>
            ) : null}
          </div>
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
          ) : mode === "brain" ? (
            <DistillThread proposals={mine} sourceTitle={n.title || "Untitled"} leftOut={leftOutOf(requests.data)} />
          ) : mine.length ? (
            <SourceCards proposals={mine} onBrain={() => setMode("brain")} />
          ) : (
            <span style={css(S.muted)}>Nothing from it waits for review.</span>
          )}
          {mode === "list" && leftOutOf(requests.data).length ? (
            <div style={css("display:flex;flex-direction:column")}>
              <span style={css("font:500 15px Geist;margin-bottom:8px")}>Left out, and why</span>
              {leftOutOf(requests.data).map((x, i) => (
                <div key={i} style={css("display:flex;align-items:center;gap:14px;padding:13px 0;border-top:1px solid var(--line);flex-wrap:wrap")}>
                  <span style={css("font:400 15px Geist;flex:1;color:var(--ink2)")}>{x.statement}</span>
                  <span style={css("font:400 13px Geist;color:var(--muted)")}>{x.why}</span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )}

      {status && !excluded ? (
        <div style={css("padding:18px;border-radius:18px;border:1px solid var(--line);display:flex;flex-direction:column;gap:10px")}>
          <span style={css("font:500 15px Geist")}>Keep it out of your Brain</span>
          <span style={css("font:400 13.5px/1.5 Geist;color:var(--ink2)")}>
            Excluded, it stays in Capture only: it is never indexed and never sent to an AI. You can include it again any time.
          </span>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (reason.trim()) exclude.mutate({ id: n.id, extra: reason.trim() }, { onSuccess: () => setReason("") });
            }}
            style={css("display:flex;gap:8px;align-items:flex-end;flex-wrap:wrap")}
          >
            <label style={css("display:flex;flex-direction:column;gap:4px;font:500 12px Geist;color:var(--muted);flex:1;min-width:220px")}>
              Why it stays out
              <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={200} placeholder="For example: personal" style={css(S.input + ";font:400 14px Geist")} />
            </label>
            <Btn kind="ghost" type="submit" disabled={!reason.trim() || exclude.isPending}>
              {exclude.isPending ? "Excluding…" : "Exclude"}
            </Btn>
          </form>
          {exclude.error ? (
            <span role="alert" style={css("font:400 13px Geist;color:oklch(0.55 0.17 28)")}>
              {(exclude.error as Error).message}
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
