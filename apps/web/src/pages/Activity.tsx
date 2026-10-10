// Activity: what your AI asked, what it got, and what changed. Requests: every request from
// every connected app, with what it was handed and why, its tokens and share of the Brain, what
// it opened after, and what it saved; open the exact text it got, and the startup context when
// that went with it; flag a piece that should not have been there, teach what was missing, or
// label it for your private eval set. Cost and quality: what context cost by day and line, how
// big briefs are, and how well they carry what a task needs. Changes: the Brain's history and
// its undo points.

import { useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";

import { useAiRequest, useAiRequests, useBrainCatalog, useLabelRequest, useProposeEntry, useReport, useWeekly } from "../api/hooks";
import type { AiRequest, CostLineName, EvalCase, ReportCard, RequestPiece, RequestWhy, WhyRow } from "../api/types";
import { Markdown } from "../components/Markdown";
import { Empty, ErrorNote, Loading, Tabs } from "../components/ui";
import { plural, when } from "../lib/format";
import { ActivityPage as ChangesView } from "./brain/Activity";
import { Week } from "./brain/Week";
import { entryUrl, fileViewUrl } from "./brain/shared";

const TABS = [
  { id: "requests", label: "Requests" },
  { id: "report", label: "Cost and quality" },
  { id: "changes", label: "Changes" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export function AiActivityPage() {
  const [params, setParams] = useSearchParams();
  const asked = params.get("tab");
  const tab: TabId = asked === "changes" || asked === "report" ? asked : "requests";
  return (
    <div className="page activity">
      <p className="eyebrow">Activity</p>
      <h1>What your AI asked, what it got, what changed</h1>
      <Tabs
        tabs={TABS}
        active={tab}
        onChange={(id) => {
          const next = new URLSearchParams();
          if (id !== "requests") next.set("tab", id);
          setParams(next, { replace: true });
        }}
      />
      {tab === "changes" ? (
        <>
          <Week />
          <ChangesView />
        </>
      ) : tab === "report" ? (
        <Report />
      ) : (
        <Requests />
      )}
    </div>
  );
}

const LINE_WORDS: Record<CostLineName, string> = {
  fixed: "Fixed overhead",
  briefs: "Briefs, first read",
  rereads: "Briefs, read again",
  rewrites: "Rewritten after pauses",
  jobs: "Background jobs",
};

const LINE_HELP: Record<CostLineName, string> = {
  fixed: "What sits in front of every call: the Brain's instructions, its tool names and, in its own folder, the startup context.",
  briefs: "Each answer from the Brain, written into a chat once.",
  rereads: "The same answers read again from the cache on every later turn, until the chat is compacted.",
  rewrites: "Brain content written to the cache again after a pause longer than the cache lasts.",
  jobs: "Checks, the knowledge agent and runs the app sends to a model.",
};

function usd(value: number): string {
  return value >= 0.1 ? `$${value.toFixed(2)}` : `$${value.toFixed(4)}`;
}

/** What context cost by day and line, brief sizes by request type, and eval results. */
function Report() {
  const [days, setDays] = useState(7);
  const [claudeCode, setClaudeCode] = useState(false);
  const { data, isLoading, error } = useReport(days, claudeCode);
  return (
    <div className="stack">
      <div className="row wrap">
        <label className="inline-select">
          <span className="muted small">Days</span>
          <select value={days} onChange={(event) => setDays(Number(event.target.value))}>
            {[1, 7, 14, 30].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <label className="check">
          <input type="checkbox" checked={claudeCode} onChange={(event) => setClaudeCode(event.target.checked)} />
          <span>
            Use Claude Code's own figures <span className="muted small">(reads token counts from its transcripts on this computer, nothing else)</span>
          </span>
        </label>
      </div>
      {isLoading ? <Loading /> : null}
      <ErrorNote error={error} />
      {data ? <ReportBody report={data} /> : null}
    </div>
  );
}

function ReportBody({ report }: { report: ReportCard }) {
  const { spend } = report;
  const lines = Object.keys(LINE_WORDS) as CostLineName[];
  const totals = Object.fromEntries(lines.map((line) => [line, spend.days.reduce((sum, day) => sum + day.lines[line].usd, 0)])) as Record<
    CostLineName,
    number
  >;
  const all = lines.reduce((sum, line) => sum + totals[line], 0);
  return (
    <>
      <p className="muted small">
        {spend.factor.measured
          ? `Token counts are measured against Claude (×${spend.factor.factor}, ${plural(spend.factor.samples ?? 0, "sample")}).`
          : "Token counts are estimates until you measure them against Claude: run `contxt tokens calibrate` once."}{" "}
        Estimated figures use {spend.model} prices; a brief is read again {spend.later_calls} times on average (
        {spend.later_calls_source === "claude code" ? "from Claude Code" : "assumed"}).
      </p>
      {spend.days.length ? (
        <table className="report-table">
          <thead>
            <tr>
              <th>Line</th>
              <th className="num">Tokens</th>
              <th className="num">Cost</th>
            </tr>
          </thead>
          <tbody>
            {lines.map((line) => (
              <tr key={line}>
                <td>
                  {LINE_WORDS[line]}
                  <span className="muted small"> {LINE_HELP[line]}</span>
                </td>
                <td className="num">{spend.days.reduce((sum, day) => sum + day.lines[line].tokens, 0).toLocaleString()}</td>
                <td className="num">{usd(totals[line])}</td>
              </tr>
            ))}
            <tr>
              <td>
                <strong>All</strong> <span className="muted small">{usd(report.per_day_usd)} a day on average</span>
              </td>
              <td className="num" />
              <td className="num">
                <strong>{usd(all)}</strong>
              </td>
            </tr>
          </tbody>
        </table>
      ) : (
        <p className="muted">No AI asked the Brain anything in this period.</p>
      )}
      {Object.keys(report.brief_tokens_by_type).length ? (
        <p className="small">
          Median brief by kind of request:{" "}
          {Object.entries(report.brief_tokens_by_type)
            .map(([kind, tokens]) => `${kind} ${tokens.toLocaleString()} tokens`)
            .join(", ")}
          .
        </p>
      ) : null}
      {report.private_eval ? <Scores title="Your labeled requests" scores={report.private_eval} /> : null}
      {report.eval ? <Scores title="The Brain's own test cases" scores={report.eval} /> : null}
      <p className="muted small">
        Your private eval set: {report.eval_set.labeled} of {plural(report.eval_set.cases, "request")} labeled, {report.eval_set.held_out} held out
        to test on. Label a request from its row in Requests.
      </p>
    </>
  );
}

function Scores({ title, scores }: { title: string; scores: NonNullable<ReportCard["eval"]> }) {
  return (
    <div>
      <h3>{title}</h3>
      <ul className="plain small">
        {(["tuning", "holdout"] as const)
          .filter((name) => scores[name].cases)
          .map((name) => (
            <li key={name}>
              {name === "holdout" ? "Held out" : "Tuning"}: {plural(scores[name].cases, "request")}, needed notes found{" "}
              {Math.round(scores[name].must_recall * 100)}%, precision {Math.round(scores[name].precision * 100)}%, noise{" "}
              {Math.round(scores[name].noise_share * 100)}% of tokens, {scores[name].avg_tokens.toLocaleString()} tokens on average
            </li>
          ))}
      </ul>
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
  if (piece.kind === "skill") return `/work/skills/${encodeURIComponent(piece.id)}`;
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
  const [labeling, setLabeling] = useState(false);
  const got = request.got.filter((p) => p.kind !== "focus" || !request.project);
  const share = request.share ?? (brainTokens ? request.tokens / brainTokens : 0);
  return (
    <li className="request">
      <button type="button" className="request-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="request-app" title={request.client ?? undefined}>
          {request.app}
        </span>
        <span className="request-text">{request.request}</span>
        <span className="request-meta muted small">
          {when(request.at)} · {request.nothing ? "nothing fit" : `${plural(got.length, "piece")}, ${request.tokens.toLocaleString()} tokens`}
          {share ? ` (${Math.max(1, Math.round(share * 100))}% of your Brain)` : ""}
        </span>
      </button>
      {request.old_engine ? (
        <p className="warning small">{request.app} runs an older version of the Brain's engine: quit it fully and open it again to pick up the new one.</p>
      ) : null}
      {open ? (
        <div className="request-body">
          <p className="request-asked">{request.request}</p>
          {request.project ? (
            <p className="small">
              <span className="why-kind">Project</span> <Link to={`/projects/${encodeURIComponent(request.project.id)}`}>{request.project.title}</Link>
            </p>
          ) : null}
          {got.length ? (
            <>
              <h4 className="request-part">What it got</h4>
              <Pieces pieces={got} />
            </>
          ) : (
            <p className="muted small">Nothing in your Brain fit this request, so the AI answered from what it already knew.</p>
          )}
          {request.opened.length ? (
            <>
              <h4 className="request-part">What it opened after</h4>
              <Pieces pieces={request.opened} />
            </>
          ) : null}
          <Sent request={request} />
          {request.saved.length ? (
            <p className="small">
              Saved: {request.saved.map((s) => `${s.title} (${s.status})`).join(", ")}
            </p>
          ) : null}
          {teaching ? (
            <Teach request={request} onClose={() => setTeaching(false)} />
          ) : labeling ? (
            <Label request={request} onClose={() => setLabeling(false)} />
          ) : (
            <div className="row">
              <button type="button" className="link small" onClick={() => setTeaching(true)}>
                Something was missing? Teach it
              </button>
              <button type="button" className="link small" onClick={() => setLabeling(true)}>
                Label it for your eval
              </button>
            </div>
          )}
        </div>
      ) : null}
    </li>
  );
}

/** Each piece a request got (or opened after), with why, and a way to say it did not belong. */
function Pieces({ pieces }: { pieces: RequestPiece[] }) {
  return (
    <ul className="preview-why">
      {pieces.map((piece) => {
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
  );
}

/** The exact text the request got, and the startup context when that went with it: both as
 * the AI read them, opened on demand. */
function Sent({ request }: { request: AiRequest }) {
  const { data: full, error, isLoading } = useAiRequest(request.id);
  if (isLoading) return <p className="muted small">Loading what it got…</p>;
  if (!full) return <ErrorNote error={error} />;
  return (
    <div className="request-sent">
      {full.text === null ? (
        <p className="muted small">It got notes you don't see, so its text isn't shown here.</p>
      ) : (
        <SentText summary={`The exact text it got (${plural(request.tokens, "token")})`} text={full.text} />
      )}
      {full.startup ? (
        full.startup.text ? (
          <SentText summary="The startup context it got, once for this chat" text={full.startup.text} />
        ) : (
          <p className="muted small">
            It also got the startup context, once for this chat. That version was sent before Contxt kept a copy, and it has changed since.
          </p>
        )
      ) : request.kernel ? (
        <p className="muted small">It also got the startup context, once for this chat.</p>
      ) : null}
      {full.why ? <Why why={full.why} /> : null}
    </div>
  );
}

const OUTCOME_WORDS: Record<WhyRow["outcome"], string> = {
  body: "whole",
  pointer: "as a pointer",
  listed: "listed",
  held: "already in the chat",
  out: "out",
};

/** A candidate's scores, as the ledger kept them. */
function whyScores(row: WhyRow): string {
  const parts: string[] = [];
  if (row.keyword !== null && row.keyword !== undefined) parts.push(`words ${row.keyword.toFixed(2)}`);
  if (row.meaning !== null && row.meaning !== undefined) parts.push(`meaning ${row.meaning.toFixed(2)}`);
  if (row.rerank !== null && row.rerank !== undefined) parts.push(`relevance ${row.rerank.toFixed(2)}`);
  const current = row.kev?.current;
  if (typeof current === "number") parts.push(`current ${current.toFixed(2)}`);
  return parts.join(" · ");
}

function WhyList({ rows, label }: { rows: WhyRow[]; label: string }) {
  if (!rows.length) return <p className="muted small">None.</p>;
  return (
    <ul className="plain why-list" aria-label={label}>
      {rows.map((row) => (
        <li key={`${row.kind}:${row.item}`}>
          {row.kind === "note" ? <Link to={entryUrl(row.item)}>{row.title}</Link> : <span>{row.title}</span>}{" "}
          <span className="kind-chip">{OUTCOME_WORDS[row.outcome] ?? row.outcome}</span>
          <span className="muted small">
            {" "}
            {[row.reason, row.found_by && row.found_by !== row.reason ? `found as ${row.found_by}` : "", whyScores(row)]
              .filter(Boolean)
              .join(" · ")}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Why each candidate went in or stayed out, read back from the ledger, never recomputed. */
function Why({ why }: { why: RequestWhy }) {
  const gate = why.gate
    ? why.gate.by === "reranker"
      ? `; the reranker's best score was ${why.gate.yes.toFixed(2)} against the cut of ${why.gate.cut}`
      : `; the gate said ${why.gate.yes.toFixed(2)} against ${why.gate.cut}`
    : "";
  const engine =
    why.mode === "on"
      ? `The local engine chose these (lock ${why.lock}${gate}${why.rounds ? `; ${plural(why.rounds, "link round")}` : ""}).`
      : `Chosen by words and meaning, without the local engine${why.reason ? ` (${why.reason})` : ""}.`;
  return (
    <details className="request-why">
      <summary>Why these, and not others</summary>
      <p className="muted small">
        {engine}
        {why.ceiling_hit ? " More candidates matched than the ceiling allows; the best were scored." : ""}
      </p>
      {why.notes?.length ? (
        <ul className="plain muted small" aria-label="This computer's fallbacks">
          {why.notes.map((note) => (
            <li key={note}>{note}.</li>
          ))}
        </ul>
      ) : null}
      <h4>Why this</h4>
      <WhyList rows={why.in} label="Why this" />
      <h4>Why not that one</h4>
      <WhyList rows={why.out} label="Why not that one" />
      {why.out_count > why.out.length ? (
        <p className="muted small">and {why.out_count - why.out.length} more out, kept in the ledger.</p>
      ) : null}
    </details>
  );
}

function SentText({ summary, text }: { summary: string; text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <details className="sent-text">
      <summary>{summary}</summary>
      <div className="document compact">
        <Markdown text={text} />
      </div>
      <button
        type="button"
        className="link small"
        onClick={() => void navigator.clipboard?.writeText(text).then(() => setCopied(true), () => undefined)}
      >
        {copied ? "Copied" : "Copy it as sent"}
      </button>
    </details>
  );
}

type Verdict = "needed" | "useful" | "noise" | "";

function verdictsFrom(found: EvalCase | null | undefined): Record<string, Verdict> {
  const out: Record<string, Verdict> = {};
  if (!found?.labeled) return out;
  for (const group of found.must) for (const id of group) if (!found.missing?.includes(id)) out[id] = "needed";
  for (const id of found.useful) out[id] = "useful";
  for (const id of found.noise) out[id] = "noise";
  return out;
}

/** Your labels for this request, for the private eval set the Brain is tuned and tested on:
 * which notes it needed, which helped, which were noise, and which it should have had. They
 * stay on this computer, beside the Brain. */
function Label({ request, onClose }: { request: AiRequest; onClose: () => void }) {
  const { data: full } = useAiRequest(request.id);
  const { data: catalog } = useBrainCatalog();
  const label = useLabelRequest(request.id);
  const notes = [...request.got, ...request.opened].filter((p, i, all) => p.kind === "note" && all.findIndex((q) => q.id === p.id) === i);
  const [verdicts, setVerdicts] = useState<Record<string, Verdict> | null>(null);
  const [missing, setMissing] = useState<string[] | null>(null);
  const [adding, setAdding] = useState("");
  const [nothing, setNothing] = useState<boolean | null>(null);
  const empty = nothing ?? Boolean(full?.eval?.nothing);
  const current = verdicts ?? verdictsFrom(full?.eval);
  const absent = missing ?? full?.eval?.missing ?? [];
  const titles = new Map((catalog?.entries ?? []).map((entry) => [entry.title, entry.id]));
  if (label.isSuccess) {
    return (
      <p className="small" role="status">
        Labeled. It counts in your private eval set: see Cost and quality.{" "}
        <button type="button" className="link" onClick={onClose}>
          Close
        </button>
      </p>
    );
  }
  const pick = (id: string, verdict: Verdict) => setVerdicts({ ...current, [id]: verdict });
  const ids = (verdict: Verdict) => Object.entries(current).filter(([, v]) => v === verdict).map(([id]) => id);
  return (
    <form
      className="stack-tight"
      onSubmit={(event) => {
        event.preventDefault();
        label.mutate(
          empty
            ? { needed: [], useful: [], noise: ids("noise"), missing: [], nothing: true }
            : { needed: ids("needed"), useful: ids("useful"), noise: ids("noise"), missing: absent },
        );
      }}
    >
      <p className="muted small">For each note it got: did the task need it, did it help, or was it noise? Then add any note it should have had.</p>
      <label className="check small">
        <input type="checkbox" checked={empty} onChange={(event) => setNothing(event.target.checked)} /> It should get nothing from
        the Brain (a general question, coding elsewhere, someone else's work): anything it got was noise.
      </label>
      {notes.length ? (
        <ul className="label-list">
          {notes.map((note) => (
            <li key={note.id}>
              <span>{note.title ?? note.id}</span>
              <span className="segmented" role="group" aria-label={`Label ${note.title ?? note.id}`}>
                {(["needed", "useful", "noise"] as const).map((verdict) => (
                  <button
                    key={verdict}
                    type="button"
                    aria-pressed={current[note.id] === verdict}
                    onClick={() => pick(note.id, current[note.id] === verdict ? "" : verdict)}
                  >
                    {verdict === "needed" ? "Needed" : verdict === "useful" ? "Helped" : "Noise"}
                  </button>
                ))}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted small">It got no notes.</p>
      )}
      <label className="field">
        <span className="field-label">It should have had</span>
        <input
          list={`notes-${request.id}`}
          value={adding}
          placeholder="Type a note's title"
          onChange={(event) => {
            const id = titles.get(event.target.value);
            if (id) {
              setMissing([...absent.filter((m) => m !== id), id]);
              setAdding("");
            } else setAdding(event.target.value);
          }}
        />
        <datalist id={`notes-${request.id}`}>
          {(catalog?.entries ?? []).map((entry) => (
            <option key={entry.id} value={entry.title} />
          ))}
        </datalist>
      </label>
      {absent.length ? (
        <ul className="plain small">
          {absent.map((id) => (
            <li key={id}>
              {catalog?.entries.find((entry) => entry.id === id)?.title ?? id}{" "}
              <button type="button" className="link" onClick={() => setMissing(absent.filter((m) => m !== id))}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <div className="row">
        <button
          type="submit"
          className="primary"
          disabled={label.isPending || (!empty && !Object.values(current).some(Boolean) && !absent.length)}
        >
          Save labels
        </button>
        <button type="button" className="link" onClick={onClose}>
          Cancel
        </button>
      </div>
      <ErrorNote error={label.error} />
    </form>
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
      <p className="muted small">
        It becomes a suggested note, with this request as its evidence. Nothing changes until you keep it in Catch up; then every AI gets it
        for requests like this one.
      </p>
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
