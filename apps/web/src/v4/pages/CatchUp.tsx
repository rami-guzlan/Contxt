// Catch up: every decision waiting, across every source, as v4 draws it (slices 10-isBrain,
// the Catch up tab, and 05-isCards, card mode). The proposals are the ONE store Capture also
// shows (useProposals): the same IDs, so deciding here decides there. Clashes come one at a
// time and ask (keep current, use the new one, keep both dated, mark disputed: never newest
// wins); safe ones can be kept together, still one decision per proposal in one call, one undo
// point. The catch-up plan adds the "Still true?" rechecks, the recap and the offers to decide
// once; standing permissions (type x origin x area, never a blanket rule) replace the two-day
// auto-keep.

import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { useBrainEntry } from "../../api/hooks";
import { type Policy, type Proposal, useDecide, useForgetLearned, useLearned, usePolicy, useProposals, useScout, useSetPolicy, useUndo } from "../api";
import { EditBeforeKeep, ProposalCard } from "../components/ProposalCard";
import { css } from "../css";
import {
  type GovernDecision,
  type Offer,
  type Recap,
  type Recheck,
  type WentIn,
  useCatchUpPlan,
  useCatchUpSeen,
  useGovern,
  useSetAside,
} from "../hooks/catchup";
import { Btn, Failure, Loading, Page, S, Status, Tabs, plural, when } from "../ui";

// ------------------------------------------------------------------ what a proposal is

const IN_PLACE = new Set(["sheet.write", "project.progress", "task.create", "focus.create"]);
const str = (v: unknown) => (typeof v === "string" ? v : "");

export const conflictIds = (p: Proposal) => (p.conflicts || "").split(/[,\s]+/).filter(Boolean);
export const isConflict = (p: Proposal) => conflictIds(p).length > 0 || p.statement_status === "disputed";
const isRule = (p: Proposal) =>
  !isConflict(p) && (str(p.target?.kind) === "rule" || str(p.target?.layer) === "rules" || Boolean(p.target?.critical) || Boolean(p.target?.must_text));
const isInPlace = (p: Proposal) => !isConflict(p) && !isRule(p) && IN_PLACE.has(p.kind);
const isSafe = (p: Proposal) => !isConflict(p) && !isRule(p) && !isInPlace(p);

const textOf = (p: Proposal) => p.body?.trim() || p.summary || p.title || p.id;
const speakerOf = (p: Proposal) => (p.source?.speaker && p.source.speaker !== "unknown" ? p.source.speaker : "Unknown");
const fromOf = (p: Proposal) => p.proposer || "An AI";
const areaOf = (p: Proposal) => str(p.target?.area) || str(p.target?.layer) || (p.route_key || "").split("/")[0] || "";
const destOf = (p: Proposal) => p.destination || p.route_key || "Not stated";
const sourceLine = (p: Proposal) => [p.source ? p.source.id : fromOf(p), when(p.created)].filter(Boolean).join(" · ");

const TYPE_WORDS: Record<string, string> = {
  file: "files",
  fact: "facts",
  decision: "decisions",
  progress: "progress notes",
  preference: "preferences",
  rule: "rules",
  convention: "notes about who you are",
  change: "changes to your notes",
};
const ORIGIN_WORDS: Record<string, string> = { chat: "your AI", folder: "your folders", app: "the app" };
const typeWords = (t: string) => TYPE_WORDS[t] ?? t;
const originWords = (o: string) => ORIGIN_WORDS[o] ?? o;

/** What a decision did, for the undo line. */
export interface Done {
  text: string;
  checkpoint?: string;
}

// ------------------------------------------------------------------ shared bits

const TAG = "padding:3px 9px;border-radius:99px;font:500 11.5px Geist;white-space:nowrap;background:var(--soft);color:var(--ink2)";
const ERR = "font:400 13px Geist;color:oklch(0.55 0.17 28)";
const PANEL = "background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:4px 20px";
const ROW = "display:flex;align-items:center;gap:12px;padding:12px 0;border-top:1px solid var(--line);flex-wrap:wrap";
const TXT_BTN = "flex:none;border:0;background:transparent;font:500 12.5px Geist;color:var(--ink2);padding:0";
const KEEP_BTN = "padding:6px 14px;border-radius:99px;background:var(--soft);border:0;font:500 12.5px Geist;color:var(--ink)";
const CHIP = (on: boolean) =>
  `padding:6px 12px;border-radius:99px;border:0;font:${on ? 500 : 400} 12.5px Geist;white-space:nowrap;background:${on ? "var(--ink)" : "var(--soft)"};color:${on ? "var(--bg)" : "var(--ink)"}`;

function Dot({ hue = 150, glow = false }: { hue?: number; glow?: boolean }) {
  return (
    <span
      aria-hidden="true"
      style={css(`width:8px;height:8px;border-radius:50%;flex:none;background:oklch(0.68 0.13 ${hue})${glow ? `;box-shadow:0 0 0 3px oklch(0.72 0.15 ${hue} / .22)` : ""}`)}
    />
  );
}

function Refused({ error, message }: { error?: unknown; message?: string | null }) {
  const text = message || (error instanceof Error ? error.message : error ? String(error) : "");
  return text ? (
    <span role="alert" style={css(ERR)}>
      {text}
    </span>
  ) : null;
}

/** The last decision, with its undo point. */
function UndoLine({ done, onClear, onUndone }: { done: Done | null; onClear: () => void; onUndone?: () => void }) {
  const undo = useUndo();
  if (!done) return null;
  return (
    <div role="status" style={css("display:flex;align-items:center;gap:12px;padding:12px 16px;border-radius:16px;background:var(--soft);flex-wrap:wrap")}>
      <span style={css("font:400 14px/1.45 Geist;flex:1;min-width:220px")}>{done.text}</span>
      {done.checkpoint ? (
        <button
          onClick={() =>
            undo.mutate(done.checkpoint as string, {
              onSuccess: () => {
                onUndone?.();
                onClear();
              },
            })
          }
          disabled={undo.isPending}
          style={css("border:0;background:transparent;padding:0;font:500 13px Geist;color:var(--ink)")}
        >
          {undo.isPending ? "Undoing…" : "Undo"}
        </button>
      ) : null}
      <button
        onClick={onClear}
        aria-label="Dismiss"
        title="Dismiss"
        style={css("width:28px;height:28px;border-radius:50%;border:0;background:transparent;color:var(--muted);font:400 18px/1 Geist;padding:0")}
      >
        ×
      </button>
      <Refused error={undo.error} />
    </div>
  );
}

/** The suggestion as v4 frames it: who, where from, where to, what it does, in the source's words. */
function Suggestion({ p }: { p: Proposal }) {
  const cell = (k: string, v: string) => (
    <div key={k} style={css("display:flex;flex-direction:column;gap:2px;min-width:0")}>
      <span style={css("font:500 11.5px Geist;color:var(--muted)")}>{k}</span>
      <span style={css("font:400 13px/1.4 Geist;word-break:break-word")}>{v}</span>
    </div>
  );
  const who = speakerOf(p);
  return (
    <div
      style={css(
        "display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px 16px;padding:14px 16px;border-radius:16px;border:1.5px dashed oklch(0.68 0.14 35);background:var(--surface);box-sizing:border-box",
      )}
    >
      <span style={css("grid-column:1 / -1;font:500 10.5px 'Geist Mono';letter-spacing:.06em;color:var(--ink2)")}>{p.id} · ASSISTANT SUGGESTION · NOT APPROVED YET</span>
      {cell("Source · version", p.source ? `${p.source.id}${p.source.version ? ` · ${p.source.version}` : ""}` : "No source recorded")}
      {cell("Passage", p.source?.locator || "Exact location unavailable")}
      {cell("Speaker", who)}
      {cell("Effective", p.effective || "Not stated")}
      {cell("Destination", destOf(p))}
      {cell("Operation", p.operation || p.kind)}
      {p.source?.excerpt ? (
        <span style={css("grid-column:1 / -1;font:400 15px/1.45 Newsreader;padding:8px 12px;border-radius:10px;background:var(--soft)")}>{p.source.excerpt}</span>
      ) : null}
      <span style={css("grid-column:1 / -1;font:400 12px/1.45 Geist;color:var(--ink2)")}>
        Keeping stores it as said by {who === "Unknown" ? "an unknown speaker" : who}. It doesn't confirm it's true.
      </span>
    </div>
  );
}

// ------------------------------------------------------------------ a clash: it asks, never newest wins

function ConflictCard({ p, pos, onDone, onLater }: { p: Proposal; pos?: string; onDone: (d: Done) => void; onLater?: () => void }) {
  const govern = useGovern();
  const ids = conflictIds(p);
  const other = useBrainEntry(p.current_body ? "" : (ids[0] ?? ""));
  const [reason, setReason] = useState("");
  const [editing, setEditing] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const current = p.current_body ?? other.data?.text ?? null;
  const why = reason.trim();
  const busy = govern.isPending;

  function run(decisions: GovernDecision[], label: string, text: string) {
    setRefused(null);
    govern.mutate(
      { decisions, label, source: { catch_up: `proposal:${p.id}` } },
      {
        onSuccess: (r) => {
          const first = r.results[0];
          if (!first?.ok) {
            setRefused(first?.message || "Nothing changed.");
            return;
          }
          const later = r.results.slice(1).find((x) => !x.ok);
          setEditing(false);
          onDone({ text: later ? `${text} But: ${later.message}` : text, checkpoint: r.checkpoint?.id });
        },
      },
    );
  }

  const approve = (extra: Partial<GovernDecision> = {}): GovernDecision => ({ action: "approve", proposal_id: p.id, ...(why ? { reason: why } : {}), ...extra });
  const options: Act[] = ids.length
    ? [
        {
          label: "Keep current",
          run: () => run([{ action: "reject", proposal_id: p.id, reason: why || "Kept the current record" }], `Kept current over ${p.id}`, `Kept the current record. ${p.id} was not kept.`),
        },
        {
          label: "Use the new one",
          run: () => run([approve({ replaces: ids })], `Used ${p.id}`, `${p.id} kept, replacing ${ids.join(", ")} · indexing, not searchable yet.`),
        },
        {
          label: "Keep both, dated",
          run: () => run([approve()], `Kept both: ${p.id}`, `${p.id} kept next to ${ids.join(", ")}, each with its date · indexing, not searchable yet.`),
        },
        {
          label: "Mark disputed",
          disabled: !why,
          hint: why ? undefined : "Add a few words on why first",
          run: () =>
            run(
              [approve(), ...ids.map((id): GovernDecision => ({ action: "mark", entry_id: id, state: "disputed", reason: why }))],
              `Disputed: ${p.id}`,
              `${p.id} kept and marked disputed with ${ids.join(", ")}. Both go to your AI, labelled.`,
            ),
        },
      ]
    : [
        { label: "Keep it, marked disputed", run: () => run([approve()], `Kept ${p.id}`, `${p.id} kept, still marked disputed in its source · indexing, not searchable yet.`) },
        {
          label: "Skip it",
          run: () => run([{ action: "reject", proposal_id: p.id, reason: why || "Skipped in Catch up" }], `Skipped ${p.id}`, `${p.id} skipped. Nothing in your Brain changed.`),
        },
      ];

  return (
    <div style={css("display:flex;flex-direction:column;gap:14px")}>
      <div style={css("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
        <span style={css(TAG + ";background:oklch(0.94 0.035 35);color:oklch(0.42 0.09 35)")}>{ids.length ? "Clashes with your Brain" : "Disputed in its source"}</span>
        <span style={css("font:400 12.5px Geist;color:var(--muted)")}>{sourceLine(p)}</span>
        {pos ? <span style={css("margin-left:auto;font:400 12px Geist;color:var(--muted)")}>{pos}</span> : null}
      </div>
      <span style={css("font:400 23px/1.35 Newsreader;text-wrap:pretty")}>{textOf(p)}</span>
      <button
        onClick={() => setEditing(true)}
        disabled={busy}
        style={css("align-self:flex-start;padding:6px 13px;border-radius:99px;border:1px solid var(--line2);background:transparent;font:500 12.5px Geist;color:var(--ink)")}
      >
        Edit before keeping
      </button>
      <Suggestion p={p} />
      {ids.length ? (
        <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:10px")}>
          <div style={css("padding:12px 14px;border-radius:14px;background:var(--soft);display:flex;flex-direction:column;gap:4px")}>
            <span style={css("font:500 10.5px 'Geist Mono';color:var(--muted)")}>CURRENT · APPROVED</span>
            <span style={css("font:400 13.5px/1.45 Geist")}>{current ? current.slice(0, 400) : other.isLoading ? "Loading the current record…" : `Held in ${ids.join(", ")}`}</span>
            <span style={css("font:400 12px Geist;color:var(--muted)")}>{ids.join(", ")}</span>
          </div>
          <div style={css("padding:12px 14px;border-radius:14px;border:1px solid oklch(0.68 0.14 35);display:flex;flex-direction:column;gap:4px")}>
            <span style={css("font:500 10.5px 'Geist Mono';color:oklch(0.55 0.13 35)")}>PROPOSED · NOT APPROVED</span>
            <span style={css("font:400 13.5px/1.45 Geist")}>{textOf(p).slice(0, 400)}</span>
            <span style={css("font:400 12px Geist;color:var(--muted)")}>{sourceLine(p)}</span>
          </div>
        </div>
      ) : null}
      <span style={css("font:400 12.5px/1.5 Geist;color:var(--ink2)")}>
        Nothing replaces the current record until you pick. Newer is never assumed to win: older information imported later never overwrites it.
      </span>
      <label style={css("display:flex;flex-direction:column;gap:4px;font:500 12px Geist;color:var(--muted)")}>
        Why (a few words; changing a rule needs one)
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="A few words on why"
          style={css("box-sizing:border-box;border:1px solid var(--line2);border-radius:12px;padding:10px 14px;outline:none;background:var(--surface);color:var(--ink);font:400 14px Geist")}
        />
      </label>
      <div style={css("display:flex;flex-direction:column;gap:8px")}>
        {options.map((o) => (
          <button
            key={o.label}
            onClick={o.run}
            disabled={busy || o.disabled}
            title={o.hint}
            className="gn-hover"
            style={css(
              `padding:12px 16px;border-radius:14px;background:var(--surface);border:1px solid var(--line2);font:400 15px Geist;color:var(--ink);text-align:left;${o.disabled ? "opacity:.55" : ""}`,
            )}
          >
            {o.label}
            {o.hint ? <span style={css("margin-left:8px;font:400 12px Geist;color:var(--muted)")}>{o.hint}</span> : null}
          </button>
        ))}
      </div>
      {onLater ? (
        <button onClick={onLater} disabled={busy} style={css(S.link + ";font-size:13px")}>
          Not now, show the next one
        </button>
      ) : null}
      <Refused error={govern.error} message={refused} />
      {editing ? (
        <EditBeforeKeep
          p={p}
          onClose={() => setEditing(false)}
          busy={busy}
          onSave={(extra) => run([approve(extra)], `Kept ${p.id}, edited`, `${p.id} kept in your words · indexing, not searchable yet.`)}
        />
      ) : null}
    </div>
  );
}

// ------------------------------------------------------------------ the other cards in today's stack

interface Act {
  label: string;
  run: () => void;
  disabled?: boolean;
  hint?: string;
}

function StackFrame({
  tag,
  hue,
  src,
  pos,
  title,
  children,
  a,
  b,
  later,
  busy,
  error,
}: {
  tag: string;
  hue: number;
  src: string;
  pos: string;
  title: string;
  children?: ReactNode;
  a: Act;
  b: Act;
  later?: Act;
  busy?: boolean;
  error?: string | null;
}) {
  return (
    <div style={css("display:flex;flex-direction:column;gap:14px")}>
      <div style={css("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
        <span style={css(`${TAG};background:oklch(0.94 0.035 ${hue});color:oklch(0.42 0.09 ${hue})`)}>{tag}</span>
        <span style={css("font:400 12.5px Geist;color:var(--muted)")}>{src}</span>
        <span style={css("margin-left:auto;font:400 12px Geist;color:var(--muted)")}>{pos}</span>
      </div>
      <span style={css("font:400 23px/1.35 Newsreader;text-wrap:pretty")}>{title}</span>
      {children}
      <div style={css("display:flex;gap:10px;flex-wrap:wrap;padding-top:2px;align-items:center")}>
        <button
          onClick={b.run}
          disabled={busy || b.disabled}
          style={css("padding:11px 18px;border-radius:99px;border:1px solid var(--line2);background:transparent;color:var(--ink);font:500 14px Geist")}
        >
          {b.label}
        </button>
        <button
          onClick={a.run}
          disabled={busy || a.disabled}
          title={a.hint}
          style={css(`padding:11px 20px;border-radius:99px;background:var(--ink);color:var(--bg);border:0;font:500 14px Geist;${a.disabled ? "opacity:.55" : ""}`)}
        >
          {a.label}
        </button>
        {a.hint ? <span style={css("font:400 12px Geist;color:var(--muted)")}>{a.hint}</span> : null}
        {later ? (
          <button onClick={later.run} disabled={busy} style={css(TXT_BTN + ";margin-left:auto")}>
            {later.label}
          </button>
        ) : null}
      </div>
      <Refused message={error} />
    </div>
  );
}

const msg = (e: unknown) => (e instanceof Error ? e.message : null);

function RecheckCard({ card, pos, onDone }: { card: Recheck; pos: string; onDone: (d: Done) => void }) {
  const govern = useGovern();
  const aside = useSetAside();
  const [refused, setRefused] = useState<string | null>(null);
  function run(d: GovernDecision, label: string, text: string) {
    setRefused(null);
    govern.mutate(
      { decisions: [d], label, source: { catch_up: card.key } },
      { onSuccess: (r) => (r.results[0]?.ok ? onDone({ text, checkpoint: r.checkpoint?.id }) : setRefused(r.results[0]?.message || "Nothing changed.")) },
    );
  }
  return (
    <StackFrame
      tag="Still true?"
      hue={210}
      src={[card.why, card.uses ? `used in ${plural(card.uses, "chat")} this month` : ""].filter(Boolean).join(" · ")}
      pos={pos}
      title={card.title}
      busy={govern.isPending || aside.isPending}
      b={{ label: "Not anymore", run: () => run({ action: "archive", entry_id: card.id, reason: "No longer true" }, `Retired ${card.title}`, `Retired "${card.title}". Undo puts it back.`) }}
      a={{ label: "Still true", run: () => run({ action: "verify", entry_id: card.id }, `Still true: ${card.title}`, `Checked "${card.title}". It stops being stale.`) }}
      later={{ label: "Later", run: () => aside.mutate({ key: card.key, later: true }) }}
      error={refused || msg(govern.error) || msg(aside.error)}
    >
      {card.summary ? <span style={css("font:400 14px/1.5 Geist;color:var(--ink2)")}>{card.summary}</span> : null}
    </StackFrame>
  );
}

function OfferCard({ offer, pos, onDone }: { offer: Offer; pos: string; onDone: (d: Done) => void }) {
  const policy = usePolicy();
  const set = useSetPolicy();
  const aside = useSetAside();
  const [area, setArea] = useState("");
  function letIn() {
    const standing = policy.data?.standing ?? [];
    set.mutate(
      { standing: [...standing, { type: offer.type, origin: offer.origin, area, paused: false }] },
      {
        onSuccess: () =>
          aside.mutate(
            { key: offer.key },
            {
              onSuccess: () =>
                onDone({ text: `Done. ${typeWords(offer.type)} from ${originWords(offer.origin)} in ${area} go straight in now. Pause or remove it under Standing permissions.` }),
            },
          ),
      },
    );
  }
  return (
    <StackFrame
      tag="Decide once"
      hue={265}
      src={offer.detail}
      pos={pos}
      title={offer.title}
      busy={set.isPending || aside.isPending}
      b={{ label: "Keep asking", run: () => aside.mutate({ key: offer.key }, { onSuccess: () => onDone({ text: "It keeps asking, one at a time." }) }) }}
      a={{ label: "Let them in", run: letIn, disabled: !area, hint: area ? undefined : "Pick an area first" }}
      error={msg(set.error) || msg(aside.error)}
    >
      <label style={css("display:flex;flex-direction:column;gap:4px;font:500 12px Geist;color:var(--muted);align-self:flex-start")}>
        In which area (never a blanket rule)
        <select value={area} onChange={(e) => setArea(e.target.value)} style={css(S.input + ";font:500 13px Geist;padding:6px 8px")}>
          <option value="">Choose an area…</option>
          {(policy.data?.areas ?? []).map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>
      </label>
    </StackFrame>
  );
}

function RecapCard({ recap, pos, onDone }: { recap: Recap; pos: string; onDone: (d: Done) => void }) {
  const seen = useCatchUpSeen();
  const undo = useUndo();
  const navigate = useNavigate();
  const [undone, setUndone] = useState<Record<string, boolean>>({});
  return (
    <StackFrame
      tag="While you were away"
      hue={150}
      src="These went in on their own: your preset or a standing permission let them in"
      pos={pos}
      title={`${plural(recap.went_in_total, "thing")} went in on ${recap.went_in_total === 1 ? "its" : "their"} own`}
      busy={seen.isPending}
      b={{ label: "Undo one", run: () => navigate("/activity") }}
      a={{ label: "Looks right", run: () => seen.mutate(undefined, { onSuccess: () => onDone({ text: "Noted. The next recap starts from now." }) }) }}
      error={msg(seen.error) || msg(undo.error)}
    >
      <div style={css("display:flex;flex-direction:column")}>
        {recap.went_in.slice(0, 5).map((x) => (
          <div key={x.id + x.at} style={css("display:flex;gap:10px;padding:9px 0;border-top:1px solid var(--line);font:400 14px Geist;align-items:center")}>
            <span style={css(`flex:1;${undone[x.id] ? "text-decoration:line-through;color:var(--muted)" : ""}`)}>{x.title}</span>
            {x.checkpoint ? (
              <button
                onClick={() => undo.mutate(x.checkpoint as string, { onSuccess: () => setUndone((u) => ({ ...u, [x.id]: true })) })}
                disabled={undo.isPending || undone[x.id]}
                style={css(TXT_BTN + ";font-size:12px")}
              >
                {undone[x.id] ? "Undone" : "Undo"}
              </button>
            ) : (
              <span style={css("font:400 12px Geist;color:var(--muted)")}>Undo in Activity</span>
            )}
          </div>
        ))}
      </div>
    </StackFrame>
  );
}

// ------------------------------------------------------------------ one row in a list (safe, in place, rules)

function DecideRow({ p, label, onDone, onOpen }: { p: Proposal; label: string; onDone: (d: Done) => void; onOpen?: () => void }) {
  const decide = useDecide();
  const [editing, setEditing] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  function act(keep: boolean, extra: { body?: string; destination?: Record<string, string> } = {}) {
    setRefused(null);
    decide.mutate([{ action: keep ? "approve" : "reject", proposal_id: p.id, ...extra }], {
      onSuccess: (r) => {
        if (!r.results[0]?.ok) return setRefused(r.results[0]?.message || "Nothing changed.");
        setEditing(false);
        onDone({ text: keep ? `${p.id} kept · indexing, not searchable yet.` : `${p.id} tossed. Nothing in your Brain changed.`, checkpoint: r.checkpoint?.id });
      },
    });
  }
  return (
    <div style={css(ROW)}>
      <div style={css("display:flex;flex-direction:column;gap:2px;flex:1;min-width:220px")}>
        <span style={css("font:400 11.5px Geist;color:var(--muted)")}>{label}</span>
        <span style={css("font:400 14.5px/1.45 Geist")}>{textOf(p)}</span>
        <span style={css("font:400 12px Geist;color:var(--muted)")}>
          {p.id} · {sourceLine(p)}
        </span>
        <Refused error={decide.error} message={refused} />
      </div>
      <button onClick={() => setEditing(true)} disabled={decide.isPending} style={css(TXT_BTN)}>
        Edit
      </button>
      {onOpen ? (
        <button onClick={onOpen} style={css(TXT_BTN)}>
          Open
        </button>
      ) : null}
      <button onClick={() => act(false)} disabled={decide.isPending} style={css(TXT_BTN + ";color:var(--muted)")}>
        Toss
      </button>
      <button onClick={() => act(true)} disabled={decide.isPending} style={css(KEEP_BTN)}>
        Keep
      </button>
      {editing ? <EditBeforeKeep p={p} onClose={() => setEditing(false)} onSave={(extra) => act(true, extra)} busy={decide.isPending} /> : null}
    </div>
  );
}

// ------------------------------------------------------------------ safe to keep, by where it came from

function SafeToKeep({ safe, onDone }: { safe: Proposal[]; onDone: (d: Done) => void }) {
  const decide = useDecide();
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [refused, setRefused] = useState<string | null>(null);
  const groups = useMemo(() => {
    const out = new Map<string, Proposal[]>();
    for (const p of safe) out.set(fromOf(p), [...(out.get(fromOf(p)) ?? []), p]);
    return [...out.entries()];
  }, [safe]);

  function keepAll(items: Proposal[]) {
    setRefused(null);
    // One decision per proposal, in one call: one undo point takes them all back.
    decide.mutate(
      items.map((p) => ({ action: "approve" as const, proposal_id: p.id })),
      {
        onSuccess: (r) => {
          const kept = r.results.filter((x) => x.ok).length;
          const bad = r.results.find((x) => !x.ok);
          if (!kept) return setRefused(bad?.message || "Nothing changed.");
          onDone({
            text: `Kept ${kept}${bad ? ` of ${items.length} (${bad.message})` : ""} · indexing, not searchable yet. One undo point takes them all back.`,
            checkpoint: r.checkpoint?.id,
          });
        },
      },
    );
  }

  return (
    <div style={css(PANEL)}>
      <div style={css("display:flex;align-items:center;gap:12px;padding:16px 0 12px;flex-wrap:wrap")}>
        <div style={css("display:flex;flex-direction:column;gap:2px;flex:1;min-width:200px")}>
          <span style={css("font:500 15px Geist")}>Safe to keep · {safe.length}</span>
          <span style={css("font:400 12.5px Geist;color:var(--muted)")}>Nothing in your Brain disagrees with these. Rules, clashes and changes in place wait on their own.</span>
        </div>
        <button
          onClick={() => keepAll(safe)}
          disabled={decide.isPending}
          style={css("padding:9px 18px;border-radius:99px;background:var(--ink);color:var(--bg);border:0;font:500 13.5px Geist")}
        >
          {decide.isPending ? "Keeping…" : "Keep all"}
        </button>
      </div>
      <Refused error={decide.error} message={refused} />
      {groups.map(([from, items]) => {
        const isOpen = Boolean(open[from]);
        const areas = [...new Set(items.map(areaOf))].filter(Boolean).join(", ");
        return (
          <div key={from} style={css("border-top:1px solid var(--line)")}>
            <div style={css("display:flex;align-items:center;gap:10px;padding:12px 0")}>
              <button
                onClick={() => setOpen((o) => ({ ...o, [from]: !isOpen }))}
                aria-expanded={isOpen}
                style={css("flex:1;min-width:0;display:flex;align-items:center;gap:12px;border:0;background:transparent;text-align:left;color:var(--ink);padding:0")}
              >
                <Dot hue={210} />
                <span style={css("display:flex;flex-direction:column;gap:1px;min-width:0")}>
                  <span style={css("font:400 14.5px Geist")}>
                    {items.length} from {from}
                  </span>
                  {areas ? <span style={css("font:400 12px Geist;color:var(--muted)")}>{areas}</span> : null}
                </span>
                <span aria-hidden="true" style={css("font:400 11px Geist;color:var(--muted)")}>
                  {isOpen ? "▴" : "▾"}
                </span>
              </button>
              <button
                onClick={() => keepAll(items)}
                disabled={decide.isPending}
                style={css("padding:6px 12px;border-radius:99px;background:var(--soft);border:0;font:500 12.5px Geist;color:var(--ink)")}
              >
                Keep {items.length}
              </button>
            </div>
            {isOpen ? (
              <div style={css("display:flex;flex-direction:column;padding:0 0 10px 20px")}>
                {items.map((p) => (
                  <DecideRow key={p.id} p={p} label={`Goes to ${destOf(p)}`} onDone={onDone} />
                ))}
              </div>
            ) : null}
          </div>
        );
      })}
      <div style={css("padding:12px 0 14px;border-top:1px solid var(--line);font:400 13px/1.45 Geist;color:var(--ink2)")}>
        To let safe ones keep themselves, add a standing permission below: one kind, from one place, in one area. Pause or remove it anytime.
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ standing permissions

function StandingPermissions() {
  const policy = usePolicy();
  const set = useSetPolicy();
  const [type, setType] = useState("");
  const [origin, setOrigin] = useState("");
  const [area, setArea] = useState("");
  if (policy.isLoading) return <Loading what="Loading standing permissions" />;
  if (policy.error || !policy.data) return <Failure error={policy.error} retry={() => void policy.refetch()} />;
  const data: Policy = policy.data;
  const rules = data.standing ?? [];
  const save = (standing: Policy["standing"]) => set.mutate({ standing });
  const exists = rules.some((r) => r.type === type && r.origin === origin && r.area === area);
  const select = (label: string, value: string, onChange: (v: string) => void, options: [string, string][]) => (
    <label style={css("display:flex;flex-direction:column;gap:4px;font:500 12px Geist;color:var(--muted)")}>
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)} style={css(S.input + ";font:500 13px Geist;padding:6px 8px")}>
        <option value="">Choose…</option>
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </label>
  );
  return (
    <section aria-label="Standing permissions" style={css(PANEL + ";padding:4px 20px 16px")}>
      <div style={css("display:flex;flex-direction:column;gap:2px;padding:16px 0 10px")}>
        <span style={css("font:500 15px Geist")}>Standing permissions · {rules.length}</span>
        <span style={css("font:400 12.5px/1.45 Geist;color:var(--muted)")}>
          Each lets one kind of change, from one place, in one area, go in on its own, with undo. It replaces the two-day auto-keep. Rule changes, must-holds and clashes
          still wait. At most {data.auto_daily_cap} go in on their own a day ({data.auto_applied_today} in the last 24 hours).
        </span>
      </div>
      {rules.length === 0 ? <div style={css(ROW + ";font:400 13.5px Geist;color:var(--ink2)")}>None yet. Everything waits for you.</div> : null}
      {rules.map((r, i) => (
        <div key={`${r.type}:${r.origin}:${r.area}`} style={css(ROW)}>
          <span style={css("flex:1;min-width:220px;font:400 14px Geist")}>
            Let {typeWords(r.type)} from {originWords(r.origin)} in {r.area === "*" ? "every area" : r.area} in
          </span>
          <Status kind={r.paused ? "skipped" : "searchable"}>{r.paused ? "Paused" : "On"}</Status>
          <button onClick={() => save(rules.map((x, j) => (j === i ? { ...x, paused: !x.paused } : x)))} disabled={set.isPending} style={css(TXT_BTN)}>
            {r.paused ? "Resume" : "Pause"}
          </button>
          <button onClick={() => save(rules.filter((_x, j) => j !== i))} disabled={set.isPending} style={css(TXT_BTN + ";color:var(--muted)")}>
            Remove
          </button>
        </div>
      ))}
      <div style={css("display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end;padding-top:12px;border-top:1px solid var(--line)")}>
        <span style={css("font:500 13.5px Geist;width:100%")}>Always let these in</span>
        {select(
          "Kind",
          type,
          setType,
          (data.capture_types ?? []).filter((t) => t !== "rule").map((t) => [t, typeWords(t)]),
        )}
        {select("From", origin, setOrigin, (data.capture_origins ?? []).map((o) => [o, originWords(o)]))}
        {select("Area", area, setArea, (data.areas ?? []).map((a) => [a, a]))}
        <Btn
          kind="primarySm"
          disabled={!type || !origin || !area || exists || set.isPending}
          onClick={() => save([...rules, { type, origin, area, paused: false }])}
          title={exists ? "That one is already on" : undefined}
        >
          Add
        </Btn>
      </div>
      <Refused error={set.error} />
    </section>
  );
}

// ------------------------------------------------------------------ everything, in one list

type Filter = "all" | "conflicts" | "scout";

function Everything({ proposals }: { proposals: Proposal[] }) {
  const scout = useScout();
  const [filter, setFilter] = useState<Filter>("all");
  const [source, setSource] = useState("");
  const scoutIds = useMemo(() => new Set((scout.data?.differences ?? []).map((d) => d.capture_id).filter(Boolean) as string[]), [scout.data]);
  const fromScout = (p: Proposal) => scoutIds.has(p.source?.id ?? "") || str(p.target?.origin) === "scout";
  const scoutKnown = Boolean(scout.data) || proposals.some((p) => str(p.target?.origin));
  const sources = [...new Set(proposals.map((p) => p.source?.id).filter(Boolean) as string[])].sort();
  const shown = proposals.filter(
    (p) => (filter === "all" || (filter === "conflicts" && isConflict(p)) || (filter === "scout" && fromScout(p))) && (!source || p.source?.id === source),
  );
  const chip = (id: Filter, label: string, n: number) => (
    <button key={id} aria-pressed={filter === id} onClick={() => setFilter(id)} style={css(CHIP(filter === id))}>
      {label} · {n}
    </button>
  );
  return (
    <section aria-label="Everything waiting" style={css("display:flex;flex-direction:column;gap:14px")}>
      <div style={css("display:flex;gap:6px;flex-wrap:wrap;align-items:center")}>
        {chip("all", "All", proposals.length)}
        {chip("conflicts", "Conflicts", proposals.filter(isConflict).length)}
        {scoutKnown ? chip("scout", "From Scout", proposals.filter(fromScout).length) : null}
        <label style={css("display:flex;align-items:center;gap:6px;font:400 12.5px Geist;color:var(--muted);margin-left:auto")}>
          Source
          <select value={source} onChange={(e) => setSource(e.target.value)} style={css(S.input + ";font:500 12.5px Geist;padding:5px 8px")}>
            <option value="">Every source</option>
            {sources.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      </div>
      {!scoutKnown ? <span style={css(S.small)}>From Scout is not available yet: these proposals don't say whether Scout brought their source in.</span> : null}
      {shown.length === 0 ? <span style={css(S.muted)}>Nothing waits under this filter.</span> : shown.map((p) => <ProposalCard key={p.id} p={p} />)}
    </section>
  );
}

// ------------------------------------------------------------------ What changed (what went in on its own)

function dayOf(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Earlier";
  const today = new Date();
  const yesterday = new Date(today.getTime() - 86400000);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function WhatChanged() {
  const plan = useCatchUpPlan();
  const policy = usePolicy();
  const learned = useLearned();
  const forget = useForgetLearned();
  const undo = useUndo();
  const [filter, setFilter] = useState("All");
  const [undone, setUndone] = useState<Record<string, boolean>>({});
  if (plan.isLoading) return <Loading what="Loading what changed" />;
  if (plan.error || !plan.data) return <Failure error={plan.error} retry={() => void plan.refetch()} />;
  const handled: WentIn[] = plan.data.handled ?? [];
  const total = plan.data.recap?.went_in_total ?? handled.length;
  const filters = [...new Set(["All", ...handled.map((x) => x.source).filter(Boolean), ...handled.map((x) => x.kind).filter(Boolean)])];
  const shown = handled.filter((x) => filter === "All" || x.source === filter || x.kind === filter);
  const days = [...new Set(shown.map((x) => dayOf(x.at)))];
  return (
    <div style={css("max-width:820px;display:flex;flex-direction:column;gap:20px")}>
      <div style={css("display:flex;flex-direction:column;gap:6px")}>
        <div style={css("display:flex;align-items:center;gap:12px;flex-wrap:wrap")}>
          <h2 style={css("margin:0;font:400 28px/1.2 Newsreader")}>What changed</h2>
          <span style={css("display:flex;align-items:center;gap:8px;padding:5px 12px;border-radius:99px;background:oklch(0.74 0.12 150 / .14);font:500 12.5px Geist")}>
            <Dot />
            Went in on its own
          </span>
        </div>
        <span style={css("font:400 15px/1.5 Geist;color:var(--ink2)")}>
          Since {when(plan.data.since) || "you last looked"}: {plural(total, "change")} went in on {total === 1 ? "its" : "their"} own.
          {policy.data ? ` ${policy.data.auto_applied_today} of at most ${policy.data.auto_daily_cap} in the last 24 hours.` : ""}
        </span>
      </div>
      {handled.length ? (
        <div style={css("display:flex;gap:6px;flex-wrap:wrap")}>
          {filters.map((l) => (
            <button key={l} aria-pressed={filter === l} onClick={() => setFilter(l)} style={css(CHIP(filter === l))}>
              {l}
            </button>
          ))}
        </div>
      ) : (
        <span style={css(S.muted)}>Nothing went in on its own since you last looked.</span>
      )}
      {days.map((day) => (
        <div key={day} style={css("display:flex;flex-direction:column;gap:8px")}>
          <span style={css("font:500 13px Geist;color:var(--muted)")}>{day}</span>
          <div style={css("background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:0 20px")}>
            {shown
              .filter((x) => dayOf(x.at) === day)
              .map((x) => {
                const k = x.id + x.at;
                const u = Boolean(undone[k]);
                return (
                  <div key={k} style={css("display:flex;align-items:flex-start;gap:14px;padding:14px 0;border-top:1px solid var(--line)")}>
                    <span style={css(TAG)}>{x.kind || "Added"}</span>
                    <div style={css("flex:1;min-width:0;display:flex;flex-direction:column;gap:4px")}>
                      <span style={css(`font:400 14.5px/1.45 Geist;${u ? "text-decoration:line-through;color:var(--muted)" : ""}`)}>{x.title}</span>
                      <span style={css("font:400 12px Geist;color:var(--muted)")}>{[x.source, x.capture, x.path].filter(Boolean).join(" · ")}</span>
                    </div>
                    <span style={css("font:400 12px Geist;color:var(--muted);white-space:nowrap")}>{when(x.at)}</span>
                    {x.checkpoint ? (
                      <button
                        onClick={() => undo.mutate(x.checkpoint as string, { onSuccess: () => setUndone((s) => ({ ...s, [k]: true })) })}
                        disabled={u || undo.isPending}
                        style={css("border:0;background:transparent;font:500 12.5px Geist;color:var(--ink);padding:0;width:52px;text-align:right")}
                      >
                        {u ? "Undone" : "Undo"}
                      </button>
                    ) : null}
                  </div>
                );
              })}
          </div>
        </div>
      ))}
      <Refused error={undo.error} />
      <div style={css("display:flex;flex-direction:column;gap:8px")}>
        <span style={css("font:500 15px Geist")}>Learned from your undos</span>
        {learned.isLoading ? <Loading /> : null}
        {learned.error ? <Failure error={learned.error} retry={() => void learned.refetch()} /> : null}
        {learned.data && learned.data.length === 0 ? (
          <span style={css(S.muted)}>Nothing yet. When you undo something that went in on its own, it asks first next time.</span>
        ) : null}
        {(learned.data ?? []).map((l) => (
          <div key={l.id} style={css("display:flex;align-items:center;gap:10px;padding:10px 14px;border-radius:14px;border:1px solid var(--line)")}>
            <span style={css("font:400 14px Geist;flex:1")}>{l.says}</span>
            <button
              onClick={() => forget.mutate(l.id)}
              disabled={forget.isPending}
              aria-label={`Let it try again: ${l.says}`}
              title="Let it try again"
              style={css("border:0;background:transparent;color:var(--faint);font:400 15px Geist;padding:0")}
            >
              ×
            </button>
          </div>
        ))}
        <span style={css("font:400 12px Geist;color:var(--muted)")}>It follows these from now on. Remove one to let it try again.</span>
        <Refused error={forget.error} />
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ the Catch up tab

type StackItem =
  | { key: string; kind: "conflict"; p: Proposal }
  | { key: string; kind: "recheck"; card: Recheck }
  | { key: string; kind: "recap"; recap: Recap }
  | { key: string; kind: "offer"; offer: Offer };

/** The Catch up tab: what needs you, or what changed. The Brain page embeds it. */
export function CatchUpPanel() {
  const [view, setView] = useState<"needs" | "changed">("needs");
  return (
    <div style={css("display:flex;flex-direction:column;gap:22px")}>
      <Tabs
        label="Catch up"
        value={view}
        onChange={setView}
        options={[
          ["needs", "Needs you"],
          ["changed", "What changed"],
        ]}
      />
      {view === "needs" ? <NeedsYou /> : <WhatChanged />}
    </div>
  );
}

function NeedsYou() {
  const navigate = useNavigate();
  const proposals = useProposals();
  const plan = useCatchUpPlan();
  const [done, setDone] = useState<Done | null>(null);
  const [later, setLater] = useState<string[]>([]);
  const [list, setList] = useState(false);

  if (proposals.isLoading) return <Loading what="Loading what waits" />;
  if (proposals.error) return <Failure error={proposals.error} retry={() => void proposals.refetch()} />;

  const all = proposals.data ?? [];
  const conflicts = all.filter(isConflict);
  const safe = all.filter(isSafe);
  const inPlace = all.filter(isInPlace);
  const rules = all.filter(isRule);
  const recap = plan.data?.recap;

  const stack: StackItem[] = [
    ...conflicts.map((p): StackItem => ({ key: `proposal:${p.id}`, kind: "conflict", p })),
    ...((plan.data?.upkeep ?? []).filter((u) => u.type === "recheck") as Recheck[]).map((card): StackItem => ({ key: card.key, kind: "recheck", card })),
    ...(recap && recap.went_in_total > 0 && recap.went_in.length ? [{ key: "recap", kind: "recap", recap } as StackItem] : []),
    ...(plan.data?.offers ?? []).map((offer): StackItem => ({ key: offer.key, kind: "offer", offer })),
  ];
  const ordered = [...stack.filter((s) => !later.includes(s.key)), ...(later.map((k) => stack.find((s) => s.key === k)).filter(Boolean) as StackItem[])];
  const today = ordered.slice(0, 5);
  const cur = today[0];
  const pos = cur ? `1 of ${today.length} today` : "";
  const nothing = !cur && all.length === 0;

  const line = nothing
    ? "Nothing needs you. Your AIs will keep suggesting as they learn."
    : [
        `${today.length} need you`,
        `${safe.length} safe to keep`,
        inPlace.length ? `${inPlace.length} where they'd land` : "",
        rules.length ? `${rules.length} saved for Sunday` : "",
        plan.data?.minutes ? `about ${plural(plan.data.minutes, "minute")}` : "",
      ]
        .filter(Boolean)
        .join(" · ");
  const deferNext = () => cur && setLater((l) => [...l.filter((k) => k !== cur.key), cur.key]);
  const openOf = (p: Proposal) => {
    const sheet = str(p.target?.sheet);
    const project = str(p.target?.project) || str(p.target?.focus);
    if (sheet) return () => navigate(`/brain/sheets/${encodeURIComponent(sheet)}`);
    if (project) return () => navigate(`/projects/${encodeURIComponent(project)}`);
    return undefined;
  };

  return (
    <div style={css("max-width:760px;display:flex;flex-direction:column;gap:22px")}>
      <div style={css("display:flex;flex-direction:column;gap:6px")}>
        <h2 style={css("margin:0;font:400 28px/1.2 Newsreader;letter-spacing:-.01em")}>{nothing ? "Your Brain is up to date." : "Catch up"}</h2>
        <span style={css("font:400 15px/1.5 Geist;color:var(--ink2)")}>{line}</span>
      </div>
      <UndoLine done={done} onClear={() => setDone(null)} />
      {plan.error ? <Failure error={plan.error} retry={() => void plan.refetch()} /> : plan.isLoading ? <Loading what="Loading checks and offers" /> : null}

      {cur ? (
        <div style={css("position:relative;padding-bottom:14px")}>
          <div aria-hidden="true" style={css("position:absolute;left:18px;right:18px;bottom:0;height:40px;border-radius:24px;background:var(--soft)")} />
          <div aria-hidden="true" style={css("position:absolute;left:9px;right:9px;bottom:7px;height:40px;border-radius:24px;background:var(--line2)")} />
          <div style={css("position:relative;z-index:1;background:var(--surface);border-radius:24px;box-shadow:var(--shadow2);padding:24px;display:flex;flex-direction:column;gap:14px")}>
            {cur.kind === "conflict" ? (
              <ConflictCard key={cur.key} p={cur.p} pos={pos} onDone={setDone} onLater={today.length > 1 ? deferNext : undefined} />
            ) : cur.kind === "recheck" ? (
              <RecheckCard key={cur.key} card={cur.card} pos={pos} onDone={setDone} />
            ) : cur.kind === "recap" ? (
              <RecapCard key={cur.key} recap={cur.recap} pos={pos} onDone={setDone} />
            ) : (
              <OfferCard key={cur.key} offer={cur.offer} pos={pos} onDone={setDone} />
            )}
          </div>
        </div>
      ) : null}

      {safe.length ? <SafeToKeep safe={safe} onDone={setDone} /> : null}

      {inPlace.length ? (
        <div style={css(PANEL)}>
          <div style={css("display:flex;align-items:center;gap:12px;padding:16px 0 10px")}>
            <Dot hue={60} glow />
            <div style={css("display:flex;flex-direction:column;gap:2px;flex:1;min-width:0")}>
              <span style={css("font:500 15px Geist")}>Where they'd land · {inPlace.length}</span>
              <span style={css("font:400 12.5px Geist;color:var(--muted)")}>These change a sheet, a project or its to-dos. Decide here, or where they'd land.</span>
            </div>
          </div>
          {inPlace.map((p) => (
            <DecideRow key={p.id} p={p} label={destOf(p)} onDone={setDone} onOpen={openOf(p)} />
          ))}
        </div>
      ) : null}

      {rules.length ? (
        <div style={css(PANEL)}>
          <div style={css("display:flex;align-items:center;gap:12px;padding:16px 0 10px")}>
            <Dot hue={80} />
            <div style={css("display:flex;flex-direction:column;gap:2px;flex:1;min-width:0")}>
              <span style={css("font:500 15px Geist")}>Rule changes · {rules.length}</span>
              <span style={css("font:400 12.5px/1.45 Geist;color:var(--muted)")}>Rules reach every AI, so they get their own moment. Saved for a Sunday review, or decide now.</span>
            </div>
          </div>
          {rules.map((p) => (
            <DecideRow key={p.id} p={p} label={areaOf(p) || destOf(p)} onDone={setDone} />
          ))}
        </div>
      ) : null}

      {nothing ? (
        <div style={css("padding:28px;border-radius:24px;background:var(--soft);display:flex;flex-direction:column;gap:16px")}>
          <div style={css("display:flex;align-items:center;gap:10px")}>
            <span aria-hidden="true" style={css("width:10px;height:10px;border-radius:50%;background:oklch(0.62 0.14 150)")} />
            <span style={css("font:500 15px Geist")}>All caught up</span>
          </div>
          {recap ? (
            <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px")}>
              {(
                [
                  [recap.decided?.approved ?? 0, "kept since you last looked"],
                  [recap.decided?.rejected ?? 0, "tossed"],
                  [recap.went_in_total ?? 0, "went in on their own"],
                ] as [number, string][]
              ).map(([n, l]) => (
                <div key={l} style={css("padding:14px 16px;border-radius:16px;background:var(--surface);display:flex;flex-direction:column;gap:2px")}>
                  <span style={css("font:400 26px/1.1 Newsreader")}>{n}</span>
                  <span style={css("font:400 12.5px Geist;color:var(--ink2)")}>{l}</span>
                </div>
              ))}
            </div>
          ) : null}
          <span style={css("font:400 13px Geist;color:var(--muted)")}>Nothing needs you now. New suggestions will show here.</span>
        </div>
      ) : null}

      <StandingPermissions />

      <div style={css("display:flex;gap:18px;justify-content:center;flex-wrap:wrap")}>
        <button onClick={() => navigate("/brain/cards")} style={css("border:0;background:transparent;font:500 13px Geist;color:var(--ink2);padding:0")}>
          Card mode
        </button>
        <button onClick={() => setList((v) => !v)} aria-expanded={list} style={css("border:0;background:transparent;font:500 13px Geist;color:var(--ink2);padding:0")}>
          {list ? "Hide the list" : "Everything, in one list"}
        </button>
      </div>
      {list ? <Everything proposals={all} /> : null}
    </div>
  );
}

/** /brain/catch-up: the same tab, as its own page. */
export function CatchUpPage() {
  const navigate = useNavigate();
  return (
    <Page>
      <div style={css("display:flex;justify-content:space-between;align-items:flex-end;gap:24px;flex-wrap:wrap")}>
        <div style={css("display:flex;flex-direction:column;gap:8px")}>
          <h1 style={css("margin:0;font:400 44px/1.1 Newsreader;letter-spacing:-.02em")}>Catch up</h1>
          <span style={css("font:400 17px/1.5 Geist;color:var(--ink2);max-width:720px")}>
            Decisions waiting across every source. These are the same proposals Capture shows; deciding here updates Capture, the project and the record.
          </span>
        </div>
        <div style={css("display:flex;gap:8px;flex-wrap:wrap")}>
          <button
            onClick={() => navigate("/brain/cards")}
            style={css("padding:10px 18px;border-radius:99px;border:1px solid var(--line2);background:transparent;color:var(--ink);font:500 14px Geist")}
          >
            Card mode
          </button>
          <button
            onClick={() => navigate("/capture")}
            style={css("padding:10px 18px;border-radius:99px;border:1px solid var(--line2);background:transparent;color:var(--ink);font:500 14px Geist")}
          >
            Open Capture
          </button>
        </div>
      </div>
      <CatchUpPanel />
    </Page>
  );
}

// ------------------------------------------------------------------ card mode

/** /brain/cards: one at a time. ← skip, → keep, E to edit. */
export function CardsPage() {
  const navigate = useNavigate();
  const proposals = useProposals();
  const decide = useDecide();
  const [decided, setDecided] = useState<string[]>([]);
  const [done, setDone] = useState<Done | null>(null);
  const [editing, setEditing] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  const remaining = (proposals.data ?? []).filter((p) => !decided.includes(p.id));
  const total = decided.length + remaining.length;
  const card = remaining[0];
  const conflict = card ? isConflict(card) : false;

  function act(keep: boolean, extra: { body?: string; destination?: Record<string, string> } = {}) {
    if (!card || decide.isPending) return;
    const p = card;
    setRefused(null);
    decide.mutate([{ action: keep ? "approve" : "reject", proposal_id: p.id, ...extra }], {
      onSuccess: (r) => {
        if (!r.results[0]?.ok) return setRefused(r.results[0]?.message || "Nothing changed.");
        setEditing(false);
        setDecided((d) => [...d, p.id]);
        setDone({ text: keep ? `${p.id} kept · indexing, not searchable yet.` : `${p.id} skipped. Nothing in your Brain changed.`, checkpoint: r.checkpoint?.id });
      },
    });
  }
  const actRef = useRef(act);
  actRef.current = act;

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && typeof t.closest === "function" && (t.closest("input,textarea,select,[role=dialog]") || t.isContentEditable)) return;
      if (editing || conflict || !card) return;
      if (e.key === "ArrowRight") {
        e.preventDefault();
        actRef.current(true);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        actRef.current(false);
      } else if (e.key === "e" || e.key === "E") {
        e.preventDefault();
        setEditing(true);
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [editing, conflict, card]);

  const segs = Math.min(total, 12);
  const filled = total ? Math.round((decided.length / total) * segs) : 0;

  return (
    <div style={css("min-height:100%;display:flex;flex-direction:column;align-items:center;padding:36px 16px 48px;gap:30px;box-sizing:border-box")}>
      <div style={css("width:100%;max-width:560px;display:flex;justify-content:space-between;align-items:center;gap:12px")}>
        <button onClick={() => navigate("/brain/catch-up")} style={css("border:0;background:transparent;font:400 14px Geist;color:var(--muted);padding:0")}>
          ← Catch up
        </button>
        <div aria-hidden="true" style={css("display:flex;gap:5px")}>
          {Array.from({ length: segs }, (_x, i) => (
            <span key={i} style={css(`width:22px;height:5px;border-radius:99px;background:${i < filled ? "var(--ink)" : "var(--line2)"}`)} />
          ))}
        </div>
        <span style={css("font:400 14px Geist;color:var(--muted)")}>{proposals.data ? `${decided.length} of ${total} today` : ""}</span>
      </div>

      {proposals.isLoading ? <Loading what="Loading what waits" /> : null}
      {proposals.error ? <Failure error={proposals.error} retry={() => void proposals.refetch()} /> : null}
      {done ? (
        <div style={css("width:460px;max-width:100%")}>
          <UndoLine done={done} onClear={() => setDone(null)} onUndone={() => setDecided((d) => d.slice(0, -1))} />
        </div>
      ) : null}

      {card && conflict ? (
        <div style={css("width:560px;max-width:100%;background:var(--surface);border-radius:28px;box-shadow:var(--shadow2);padding:28px;box-sizing:border-box")}>
          <ConflictCard
            key={card.id}
            p={card}
            pos={`${decided.length + 1} of ${total}`}
            onDone={(d) => {
              setDecided((x) => [...x, card.id]);
              setDone(d);
            }}
          />
        </div>
      ) : null}

      {card && !conflict ? (
        <>
          <div style={css("position:relative;width:460px;max-width:100%;margin-top:20px")}>
            <div aria-hidden="true" style={css("position:absolute;inset:0;transform:translateY(24px) scale(.9);background:var(--surface);border-radius:28px;opacity:.5;box-shadow:var(--shadow)")} />
            <div aria-hidden="true" style={css("position:absolute;inset:0;transform:translateY(12px) scale(.95);background:var(--surface);border-radius:28px;opacity:.8;box-shadow:var(--shadow)")} />
            <article
              aria-label={`Proposal ${card.id}`}
              style={css("position:relative;min-height:380px;background:var(--surface);border-radius:28px;box-shadow:var(--shadow2);padding:30px;display:flex;flex-direction:column;gap:14px;box-sizing:border-box")}
            >
              <div style={css("display:flex;align-items:center;gap:8px;flex-wrap:wrap")}>
                <span style={css(TAG)}>{areaOf(card) || "Brain"}</span>
                <span style={css("font:400 13px Geist;color:var(--muted)")}>· {card.operation || card.kind}</span>
              </div>
              <span style={css("font:400 30px/1.25 Newsreader;letter-spacing:-.01em;text-wrap:pretty")}>“{textOf(card)}”</span>
              <div style={css("margin-top:auto;display:flex;flex-direction:column;gap:6px;padding-top:18px;border-top:1px solid var(--line)")}>
                <span style={css("font:400 13px Geist;color:var(--muted)")}>
                  {card.source ? `Heard in ${card.source.id}` : `From ${fromOf(card)}`}
                  {card.created ? `, ${when(card.created)}` : ""}
                </span>
                {card.reason ? <span style={css("font:400 14px/1.5 Geist;color:var(--ink2)")}>{card.reason}</span> : null}
              </div>
            </article>
          </div>
          <div style={css("width:460px;max-width:100%;margin-top:6px")}>
            <Suggestion p={card} />
          </div>
          <div style={css("display:flex;gap:16px;align-items:center")}>
            <button
              onClick={() => act(false)}
              disabled={decide.isPending}
              aria-label="Skip (left arrow)"
              title="Skip (←)"
              className="gn-hover"
              style={css("width:58px;height:58px;border-radius:50%;background:var(--surface);border:1px solid var(--line2);font:400 22px Geist;color:var(--muted)")}
            >
              ×
            </button>
            <button
              onClick={() => setEditing(true)}
              disabled={decide.isPending}
              style={css("padding:0 20px;height:44px;border-radius:99px;background:var(--surface);border:1px solid var(--line2);font:500 14px Geist;color:var(--ink)")}
            >
              Edit
            </button>
            <button
              onClick={() => act(true)}
              disabled={decide.isPending}
              aria-label="Keep (right arrow)"
              title="Keep (→)"
              style={css("width:58px;height:58px;border-radius:50%;background:var(--ink);border:0;font:400 22px Geist;color:var(--bg)")}
            >
              ✓
            </button>
          </div>
          <span style={css("font:400 13px Geist;color:var(--faint)")}>← skip · → keep · E edit</span>
          <Refused error={decide.error} message={refused} />
          {editing ? <EditBeforeKeep p={card} onClose={() => setEditing(false)} onSave={(extra) => act(true, extra)} busy={decide.isPending} /> : null}
        </>
      ) : null}

      {proposals.data && !card ? (
        <div style={css("display:flex;flex-direction:column;align-items:center;gap:22px;padding-top:9vh;text-align:center;max-width:480px")}>
          <div
            aria-hidden="true"
            style={css("width:96px;height:96px;border-radius:50%;background:oklch(0.74 0.12 150);display:flex;align-items:center;justify-content:center;font:400 40px Geist;color:#0f2416")}
          >
            ✓
          </div>
          <h1 style={css("margin:0;font:400 40px/1.15 Newsreader;letter-spacing:-.015em")}>{decided.length ? `That's ${decided.length} for today.` : "All caught up."}</h1>
          <span style={css("font:400 16px/1.55 Geist;color:var(--ink2)")}>
            {decided.length
              ? "Kept pieces index first, then become searchable. Every AI you use gets the update in its next chat."
              : "Nothing left to look at. Your Brain is current."}
          </span>
          <div style={css("display:flex;gap:8px;flex-wrap:wrap;justify-content:center")}>
            <button
              onClick={() => navigate("/brain/catch-up")}
              style={css("padding:10px 18px;border-radius:99px;border:1px solid var(--line2);background:var(--surface);color:var(--ink);font:500 14px Geist")}
            >
              Back to Catch up
            </button>
            <button onClick={() => navigate("/")} style={css("padding:10px 18px;border-radius:99px;background:var(--ink);color:var(--bg);border:0;font:500 14px Geist")}>
              Done for today
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
