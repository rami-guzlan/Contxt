// Activity: what your AI asked, what it got, and what changed. Requests: every request from
// every connected app, with what it was handed and why, its tokens and share of the Brain, what
// it opened after, and what it saved; flag a piece that should not have been there, or teach
// what was missing. Changes: the Brain's history and its undo points.

import { useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";

import { useAiRequests, useProposeEntry, useWeekly } from "../api/hooks";
import type { AiRequest, RequestPiece } from "../api/types";
import { Empty, ErrorNote, Loading, Tabs } from "../components/ui";
import { plural, when } from "../lib/format";
import { ActivityPage as ChangesView } from "./brain/Activity";
import { Week } from "./brain/Week";
import { entryUrl, fileViewUrl } from "./brain/shared";

const TABS = [
  { id: "requests", label: "Requests" },
  { id: "changes", label: "Changes" },
] as const;

export function AiActivityPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "changes" ? "changes" : "requests";
  return (
    <div className="page activity">
      <p className="eyebrow">Activity</p>
      <h1>What your AI asked, what it got, what changed</h1>
      <Tabs
        tabs={TABS}
        active={tab}
        onChange={(id) => {
          const next = new URLSearchParams();
          if (id === "changes") next.set("tab", "changes");
          setParams(next, { replace: true });
        }}
      />
      {tab === "changes" ? (
        <>
          <Week />
          <ChangesView />
        </>
      ) : (
        <Requests />
      )}
    </div>
  );
}

function Requests() {
  const [app, setApp] = useState("");
  const [pages, setPages] = useState<string[]>([""]);
  const { data: weeks } = useWeekly(1);
  const week = weeks?.[weeks.length - 1];
  return (
    <>
      <p className="muted">
        {week?.packets ? `This week your AIs asked ${plural(week.packets, "time")}, in ${plural(week.conversations, "chat")}. ` : ""}
        Each request got only the part of your Brain it needed. Kept for 90 days.
      </p>
      {pages.map((before, i) => (
        <RequestPage
          key={`${app}:${before}`}
          app={app}
          before={before}
          onApps={(apps) =>
            i === 0 && apps.length > 1 ? (
              <label className="inline-select">
                <span className="muted small">App</span>
                <select value={app} onChange={(event) => { setApp(event.target.value); setPages([""]); }}>
                  <option value="">Every app</option>
                  {apps.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
            ) : null
          }
          onOlder={i === pages.length - 1 ? (last) => setPages((current) => [...current, last]) : undefined}
        />
      ))}
    </>
  );
}

function RequestPage({
  app,
  before,
  onApps,
  onOlder,
}: {
  app: string;
  before: string;
  onApps: (apps: string[]) => ReactNode;
  onOlder?: (last: string) => void;
}) {
  const { data, isLoading, error } = useAiRequests({ limit: 30, before: before || undefined, app: app || undefined });
  if (isLoading) return <Loading />;
  if (!data) return <ErrorNote error={error} />;
  if (!data.requests.length && !before) {
    return (
      <Empty why="No AI has asked your Brain anything yet. Connect an app in Settings, then ask it something: every request shows here.">
        <Link className="button" to="/settings?tab=apps">
          Connect an AI app
        </Link>
      </Empty>
    );
  }
  const last = data.requests[data.requests.length - 1];
  return (
    <>
      {onApps(data.apps)}
      <ul className="requests">
        {data.requests.map((request) => (
          <RequestRow key={request.id} request={request} brainTokens={data.brain_tokens} />
        ))}
      </ul>
      {onOlder && last && data.requests.length >= 30 ? (
        <button type="button" onClick={() => onOlder(last.id)}>
          Older requests
        </button>
      ) : null}
    </>
  );
}

function pieceLink(piece: RequestPiece): string | null {
  if (piece.kind === "note") return entryUrl(piece.id);
  if (piece.kind === "focus") return `/projects/${encodeURIComponent(piece.id)}`;
  if ((piece.kind === "section" || piece.kind === "reference") && piece.path) return fileViewUrl(piece.path);
  if (piece.kind === "skill") return `/skills/${encodeURIComponent(piece.id)}`;
  return null;
}

const PIECE_WORDS: Record<string, string> = {
  note: "Note",
  section: "From a file",
  reference: "File",
  focus: "Project",
  skill: "Skill",
  kernel: "Startup context",
  system: "How the Brain works",
};

export function RequestRow({ request, brainTokens }: { request: AiRequest; brainTokens: number }) {
  const [open, setOpen] = useState(false);
  const [teaching, setTeaching] = useState(false);
  const got = request.got.filter((p) => p.kind !== "focus" || !request.project);
  const share = request.share ?? (brainTokens ? request.tokens / brainTokens : 0);
  return (
    <li className="request">
      <button type="button" className="request-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="request-app">{request.app}</span>
        <span className="request-text">{request.request}</span>
        <span className="muted small">
          {when(request.at)} · {request.nothing ? "nothing fit" : `${plural(got.length, "piece")}, ${request.tokens.toLocaleString()} tokens`}
          {share ? ` (${Math.max(1, Math.round(share * 100))}% of your Brain)` : ""}
        </span>
      </button>
      {request.old_engine ? (
        <p className="warning small">{request.app} runs an older version of the Brain's engine: quit it fully and open it again to pick up the new one.</p>
      ) : null}
      {open ? (
        <div className="request-body">
          {request.project ? (
            <p className="small">
              <span className="why-kind">Project</span> <Link to={`/projects/${encodeURIComponent(request.project.id)}`}>{request.project.title}</Link>
            </p>
          ) : null}
          {request.kernel ? <p className="small muted">It also got the startup context, once for this chat.</p> : null}
          {got.length ? (
            <ul className="preview-why">
              {got.map((piece) => {
                const url = pieceLink(piece);
                return (
                  <li key={`${piece.kind}:${piece.id}`}>
                    <span className="why-kind">{PIECE_WORDS[piece.kind] ?? piece.kind}</span>
                    <span>
                      {url ? <Link to={url}>{piece.title ?? piece.id}</Link> : (piece.title ?? piece.id)}{" "}
                      {piece.why ? <span className="muted">({piece.why})</span> : null}
                      {piece.kind === "note" ? (
                        <Link className="small" to={`${entryUrl(piece.id)}?mark=1`}>
                          {" "}
                          Shouldn't be here?
                        </Link>
                      ) : null}
                    </span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="muted small">Nothing in your Brain fit this request, so the AI answered from what it already knew.</p>
          )}
          {request.opened.length ? (
            <p className="small">
              Opened after: {request.opened.map((p) => p.title ?? p.id).join(", ")}
            </p>
          ) : null}
          {request.saved.length ? (
            <p className="small">
              Saved: {request.saved.map((s) => `${s.title} (${s.status})`).join(", ")}
            </p>
          ) : null}
          {teaching ? (
            <Teach request={request} onClose={() => setTeaching(false)} />
          ) : (
            <button type="button" className="link small" onClick={() => setTeaching(true)}>
              Something was missing? Teach it
            </button>
          )}
        </div>
      ) : null}
    </li>
  );
}

/** What it should have known, in the person's words: a suggestion that waits in Catch up. */
function Teach({ request, onClose }: { request: AiRequest; onClose: () => void }) {
  const propose = useProposeEntry();
  const [text, setText] = useState("");
  if (propose.isSuccess) {
    return (
      <p className="small" role="status">
        Saved. It waits in <Link to="/catch-up">Catch up</Link>; once kept, every AI gets it for requests like this one.
      </p>
    );
  }
  return (
    <form
      className="stack-tight"
      onSubmit={(event) => {
        event.preventDefault();
        const statement = text.trim();
        if (!statement) return;
        propose.mutate({
          title: (statement.split(/[.!?]\s/)[0] ?? statement).slice(0, 80),
          statement,
          evidence: `Missing when ${request.app} was asked: “${request.request}”`,
        });
      }}
    >
      <label className="field">
        <span className="field-label">What should it have known?</span>
        <textarea rows={3} value={text} onChange={(event) => setText(event.target.value)} />
      </label>
      <div className="row">
        <button type="submit" className="primary" disabled={!text.trim() || propose.isPending}>
          Teach it
        </button>
        <button type="button" className="link" onClick={onClose}>
          Cancel
        </button>
      </div>
      <ErrorNote error={propose.error} />
    </form>
  );
}
