// "See it on your Brain" (Gnomon Distill Thread): one source's proposed pieces, and where each
// lands. Left, the source's pieces with their anchors and what was left out (with why). Middle,
// the Brain's regions with the thread to where the selected piece lands, and the four routing
// questions in order. Right, the piece: why it goes there, what changes, the source's own words,
// a decision when it differs from the current record, Edit or move, Keep or leave it out.
// Everything comes from the proposals themselves; nothing is decided until the owner decides.

import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";

import { type Proposal, useDecide, useUndo } from "../api";
import { css } from "../css";
import { Btn, Modal } from "../ui";
import { EditBeforeKeep } from "./ProposalCard";

export type Region = "lt" | "pf" | "fr" | "ins";

export const REGION_NAME: Record<Region, string> = {
  lt: "Long-term memory",
  pf: "Context sheets",
  fr: "Projects & goals",
  ins: "Taste profile",
};

/** The Brain region a proposal lands in, from its kind and destination. */
export function regionOf(p: Pick<Proposal, "kind" | "target">): Region {
  const target = p.target ?? {};
  if (target.taste_lens) return "ins";
  if (p.kind === "sheet.write") return "pf";
  if (p.kind === "project.progress" || p.kind === "task.create" || target.kept_group) return "fr";
  return "lt";
}

const HUE: Record<Region | "pa", number> = { lt: 80, pf: 150, fr: 320, ins: 25, pa: 35 };
const ORDER: Region[] = ["ins", "pf", "fr", "lt"];
const QUESTION: Record<Region, string> = {
  ins: "About how you like work to look, feel or work?",
  pf: "True right now, but likely to change?",
  fr: "Part of something you're working toward?",
  lt: "None of those, and still useful next month?",
};
const REACH: Record<Region, string> = {
  lt: "Your AIs get it whenever a request matches it by meaning.",
  pf: "Your AIs get the current value; the history stays home.",
  fr: "Its packet goes first whenever the project comes up.",
  ins: "It works underneath everything, shaping every draft and design.",
};
const LIFE: Record<Region, string> = {
  lt: "Long-term note · still useful next month",
  pf: "Current value · kept until it changes",
  fr: "Project progress or to-do · lives with the project",
  ins: "Preference · usual, not always",
};
const STATEMENT: Record<string, string> = {
  stated: "Stated in source",
  tentative: "Tentative · as said",
  conditional: "Conditional",
  confirmed: "Confirmed",
  disputed: "Disputed · waits for you",
};
// [id, name, hue, [left, top, width, height], radius, kind]
const LOBES: [string, string, number, [number, number, number, number], string, "dest" | "src" | "dim" | "guard"][] = [
  ["fr", "Projects & goals", 320, [70, 34, 200, 170], "60% 40% 35% 65% / 65% 45% 55% 35%", "dest"],
  ["pf", "Context sheets", 150, [22, 116, 122, 142], "65% 35% 45% 55% / 50% 40% 60% 50%", "dest"],
  ["pa", "Capture", 35, [252, 30, 168, 150], "45% 60% 45% 55% / 60% 60% 40% 40%", "src"],
  ["oc", "Files", 210, [394, 118, 108, 140], "35% 65% 60% 40% / 45% 55% 45% 55%", "dim"],
  ["lt", "Long-term memory", 80, [132, 184, 250, 120], "45% 55% 50% 50% / 40% 40% 60% 60%", "dest"],
  ["ce", "Skills & agents", 265, [350, 250, 130, 84], "45% 55% 50% 50% / 50% 50% 50% 50%", "dim"],
  ["bs", "Must-holds", 60, [306, 292, 44, 92], "40% 40% 55% 55% / 25% 25% 70% 70%", "guard"],
  ["ins", "Taste profile", 25, [192, 122, 112, 66], "50%", "dest"],
];
const CENTER: Record<Region | "pa", [number, number]> = { fr: [170, 108], pf: [83, 222], lt: [257, 278], ins: [248, 177], pa: [336, 120] };

function curve(a: [number, number], b: [number, number], bend: number): string {
  const mx = (a[0] + b[0]) / 2;
  const my = (a[1] + b[1]) / 2;
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  return `M ${a[0].toFixed(1)} ${a[1].toFixed(1)} Q ${(mx - dy * bend).toFixed(1)} ${(my + dx * bend).toFixed(1)} ${b[0].toFixed(1)} ${b[1].toFixed(1)}`;
}

function isDark(): boolean {
  if (typeof document === "undefined") return false;
  const set = document.documentElement.dataset.theme;
  if (set) return set === "dark";
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function after(p: Proposal): string {
  return p.body?.trim() || p.summary || p.title;
}

function mark(p: Proposal, region: Region): string {
  if (p.conflicts || p.statement_status === "disputed") return "DIFFERS FROM THE CURRENT RECORD";
  if (p.current_body) return "UPDATES WHAT IT KNOWS";
  if (region === "ins") return "SHAPES YOUR TASTE";
  return "NEW";
}

function needsYou(p: Proposal): boolean {
  return Boolean(p.conflicts) || p.statement_status === "disputed";
}

interface Outcome {
  kept: boolean;
  checkpoint?: string;
}

export interface LeftOut {
  statement: string;
  why: string;
}

/** The thread for one source's proposals. With `onClose` it opens as a dialog; without, inline. */
export function DistillThread({
  proposals,
  sourceTitle,
  onClose,
  leftOut = [],
}: {
  proposals: Proposal[];
  sourceTitle: string;
  onClose?: () => void;
  leftOut?: LeftOut[];
}) {
  const panel = <ThreadPanel proposals={proposals} sourceTitle={sourceTitle} onClose={onClose} leftOut={leftOut} />;
  if (!onClose) return panel;
  return (
    <Modal title="See it on your Brain" eyebrow={sourceTitle.toUpperCase()} onClose={onClose} width={1240}>
      {panel}
    </Modal>
  );
}

function ThreadPanel({ proposals, sourceTitle, onClose, leftOut }: { proposals: Proposal[]; sourceTitle: string; onClose?: () => void; leftOut: LeftOut[] }) {
  const decide = useDecide();
  const undo = useUndo();
  const [outcomes, setOutcomes] = useState<Record<string, Outcome>>({});
  const [seen, setSeen] = useState<Proposal[]>(proposals);
  const [selId, setSelId] = useState<string | null>(proposals[0]?.id ?? null);
  const [editing, setEditing] = useState<Proposal | null>(null);
  const [batch, setBatch] = useState<{ ids: string[]; checkpoint?: string } | null>(null);
  // Pieces being decided here: they stay in view while the list refreshes without them.
  const touched = useRef(new Set<string>());

  // Keep the pieces decided here in view (with Undo) after the list refreshes without them.
  useEffect(() => {
    setSeen((before) => {
      const now = new Map(proposals.map((p) => [p.id, p]));
      const had = new Set(before.map((p) => p.id));
      const stay = before
        .filter((p) => now.has(p.id) || outcomes[p.id] || touched.current.has(p.id))
        .map((p) => now.get(p.id) ?? p);
      return [...stay, ...proposals.filter((p) => !had.has(p.id))];
    });
  }, [proposals, outcomes]);

  const pieces = seen;
  const dark = isDark();
  const tint = (h: number) => (dark ? `oklch(0.74 0.12 ${h} / 0.2)` : `oklch(0.93 0.045 ${h})`);
  const deep = (h: number) => (dark ? `oklch(0.86 0.1 ${h})` : `oklch(0.42 0.1 ${h})`);
  const solid = (h: number) => `oklch(0.66 0.13 ${h})`;
  const glow = (h: number) => (dark ? `oklch(0.6 0.12 ${h} / .5)` : `oklch(0.85 0.09 ${h})`);
  const dotS = (h: number, s = 9) => `width:${s}px;height:${s}px;border-radius:50%;flex:none;background:${solid(h)}`;

  const regions = useMemo(() => new Map(pieces.map((p) => [p.id, regionOf(p)])), [pieces]);
  const live = pieces.filter((p) => !(outcomes[p.id] && !outcomes[p.id]?.kept));
  const waiting = pieces.filter((p) => !outcomes[p.id]);
  const sp = pieces.find((p) => p.id === selId) ?? pieces[0];
  const n = (p: Proposal) => pieces.indexOf(p) + 1;

  if (!sp) {
    return (
      <div style={css("padding:28px;border-radius:22px;background:var(--surface);box-shadow:var(--shadow);display:flex;flex-direction:column;gap:8px")}>
        <span style={css("font:500 15px Geist")}>Nothing from {sourceTitle} waits to land on your Brain.</span>
        <span style={css("font:400 14px/1.5 Geist;color:var(--ink2)")}>Distill it first, and its pieces show here, each with where it would go and why.</span>
        {leftOut.length ? <LeftOutList leftOut={leftOut} /> : null}
      </div>
    );
  }

  const sd = regions.get(sp.id) ?? "lt";
  const spOut = Boolean(outcomes[sp.id] && !outcomes[sp.id]?.kept);
  const spDone = outcomes[sp.id];
  const slot: Record<string, [number, number]> = {};
  ORDER.forEach((s) => {
    const group = live.filter((p) => regions.get(p.id) === s);
    group.forEach((p, k) => {
      slot[p.id] = [CENTER[s][0] + (k - (group.length - 1) / 2) * 26, CENTER[s][1]];
    });
  });
  const lines: { d: string; c: string; w: number; o: number }[] = [];
  ORDER.forEach((s) => {
    if (live.some((p) => regions.get(p.id) === s)) lines.push({ d: curve(CENTER.pa, CENTER[s], 0.2), c: solid(HUE[s]), w: 1.6, o: 0.3 });
  });
  if (!spOut) lines.push({ d: curve(CENTER.pa, slot[sp.id] ?? CENTER[sd], 0.2), c: solid(HUE[sd]), w: 3.2, o: 1 });
  const hitAt = ORDER.indexOf(sd);
  const keepable = waiting.filter((p) => !needsYou(p));
  const needsN = waiting.length - keepable.length;

  function record(ids: string[], kept: boolean, checkpoint?: string) {
    setOutcomes((o) => ({ ...o, ...Object.fromEntries(ids.map((id) => [id, { kept, checkpoint }])) }));
  }

  function act(p: Proposal, keep: boolean, extra: { body?: string; destination?: Record<string, string> } = {}) {
    touched.current.add(p.id);
    decide.mutate([{ action: keep ? "approve" : "reject", proposal_id: p.id, ...extra }], {
      onSuccess: (r) => {
        if (!r.results[0]?.ok) return;
        record([p.id], keep, r.checkpoint?.id);
        setEditing(null);
      },
    });
  }

  function keepAll() {
    const ids = keepable.map((p) => p.id);
    if (!ids.length) return;
    ids.forEach((id) => touched.current.add(id));
    decide.mutate(
      ids.map((id) => ({ action: "approve" as const, proposal_id: id })),
      {
        onSuccess: (r) => {
          const ok = r.results.filter((x) => x.ok).map((x) => x.id);
          record(ok, true, r.checkpoint?.id);
          setBatch({ ids: ok, checkpoint: r.checkpoint?.id });
        },
      },
    );
  }

  function undoIt(checkpoint: string, ids: string[]) {
    undo.mutate(checkpoint, {
      onSuccess: () => {
        setOutcomes((o) => Object.fromEntries(Object.entries(o).filter(([id]) => !ids.includes(id))));
        setBatch(null);
      },
    });
  }

  const tagFor = (p: Proposal) => {
    const d = regions.get(p.id) ?? "lt";
    const o = outcomes[p.id];
    if (o && !o.kept) return { t: "Left out by you", c: "var(--muted)" };
    if (o?.kept) return { t: `Kept · ${REGION_NAME[d]}`, c: deep(HUE[d]) };
    return needsYou(p) ? { t: `→ ${REGION_NAME[d]} · needs you`, c: "oklch(0.6 0.13 60)" } : { t: `→ ${REGION_NAME[d]}`, c: deep(HUE[d]) };
  };

  const sourceLink = sp.source?.id?.startsWith("context_item:") ? `/capture/${encodeURIComponent(sp.source.id.slice("context_item:".length))}` : null;
  const srcVer = [sp.source?.version || "version unknown", sp.source?.locator || "exact location unavailable"].join(" · ");

  return (
    <div style={css("display:flex;flex-direction:column;border-radius:22px;background:var(--surface);box-shadow:var(--shadow);overflow:hidden;color:var(--ink)")}>
      <div style={css("display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap;padding:14px 22px;border-bottom:1px solid var(--line)")}>
        <span style={css("display:flex;align-items:center;gap:8px;font:400 12.5px Geist;color:var(--ink2)")}>
          <span style={css("width:7px;height:7px;border-radius:50%;background:oklch(0.66 0.13 150)")} />
          {sourceTitle} · {pieces.length === 1 ? "1 piece proposed" : `${pieces.length} pieces proposed`}
          {leftOut.length ? ` · ${leftOut.length} left out` : ""}
        </span>
        <div role="group" aria-label="Where the pieces go" style={css("display:flex;gap:6px;flex-wrap:wrap")}>
          {(["lt", "pf", "fr", "ins"] as Region[]).map((s) => {
            const count = live.filter((p) => regions.get(p.id) === s).length;
            const on = !spOut && sd === s;
            return (
              <button
                key={s}
                onClick={() => {
                  const first = live.find((p) => regions.get(p.id) === s);
                  if (first) setSelId(first.id);
                }}
                style={css(
                  `display:flex;align-items:center;gap:7px;padding:5px 11px;border-radius:99px;border:1px solid ${on ? solid(HUE[s]) : "var(--line2)"};background:${on ? tint(HUE[s]) : "var(--surface)"};font:500 12px Geist;color:${count ? "var(--ink)" : "var(--muted)"}`,
                )}
              >
                <span style={css(dotS(HUE[s], 8))} />
                {REGION_NAME[s]} · {count}
              </button>
            );
          })}
          <span style={css("display:flex;align-items:center;gap:7px;padding:5px 11px;border-radius:99px;border:1px solid var(--line2);background:var(--surface);font:500 12px Geist;color:var(--ink2)")}>
            <span style={css("width:8px;height:8px;border-radius:50%;background:var(--line2)")} />
            Left out · {leftOut.length + pieces.length - live.length}
          </span>
        </div>
      </div>
      <div style={css("display:flex;flex-wrap:wrap;align-items:stretch")}>
        <div style={css("flex:1 1 330px;max-width:100%;box-sizing:border-box;padding:16px 12px 20px 16px;display:flex;flex-direction:column;gap:2px")}>
          <span style={css("font:500 12.5px Geist;color:var(--muted);padding:0 10px 8px")}>What it says</span>
          {pieces.map((p) => {
            const d = regions.get(p.id) ?? "lt";
            const out = Boolean(outcomes[p.id] && !outcomes[p.id]?.kept);
            const on = p.id === sp.id;
            const tag = tagFor(p);
            return (
              <button
                key={p.id}
                onClick={() => setSelId(p.id)}
                aria-pressed={on}
                className="gn-hover"
                style={css(
                  `display:flex;gap:12px;align-items:flex-start;text-align:left;padding:10px;border:0;border-radius:14px;color:var(--ink);background:${on ? tint(HUE[d]) : "transparent"};${on ? `box-shadow:inset 0 0 0 1.5px ${solid(HUE[d])}` : ""}`,
                )}
              >
                <span
                  style={css(
                    `flex:none;width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;font:600 11px Geist;margin-top:1px;${out ? "background:var(--soft);color:var(--muted)" : `background:${solid(HUE[d])};color:#fff`}`,
                  )}
                >
                  {n(p)}
                </span>
                <span style={css("flex:1;min-width:0;display:flex;flex-direction:column;gap:4px")}>
                  <span style={css("display:flex;align-items:center;gap:6px;flex-wrap:wrap")}>
                    <span style={css("padding:1px 6px;border-radius:5px;background:var(--soft);font:500 11px 'Geist Mono';color:var(--ink2)")}>
                      {p.source?.locator || "Not anchored"}
                    </span>
                    <span style={css("font:400 11.5px Geist;color:var(--muted)")}>
                      {p.source?.speaker && p.source.speaker !== "unknown" ? p.source.speaker : "Speaker unknown"}
                    </span>
                  </span>
                  <span style={css(`font:400 14px/1.5 Geist;color:${out ? "var(--muted)" : "var(--ink)"}`)}>
                    {p.source?.excerpt ? `“${p.source.excerpt}”` : after(p)}
                  </span>
                  <span style={css(`font:500 11.5px Geist;color:${tag.c}`)}>{tag.t}</span>
                </span>
              </button>
            );
          })}
          {leftOut.map((l, i) => (
            <div key={`out-${i}`} style={css("display:flex;gap:12px;align-items:flex-start;text-align:left;padding:10px;border-radius:14px")}>
              <span style={css("flex:none;width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;font:600 11px Geist;margin-top:1px;background:var(--soft);color:var(--muted)")}>
                ·
              </span>
              <span style={css("flex:1;min-width:0;display:flex;flex-direction:column;gap:4px")}>
                <span style={css("font:italic 400 14px/1.5 Geist;color:var(--muted)")}>{l.statement}</span>
                <span style={css("font:500 11.5px Geist;color:var(--muted)")}>Left out · {l.why || "no reason recorded"}</span>
              </span>
            </div>
          ))}
        </div>
        <div style={css("flex:1 1 512px;min-width:min(100%,512px);max-width:100%;overflow-x:auto;box-sizing:border-box;padding:20px 5px 22px;display:flex;flex-direction:column;align-items:center;gap:16px;background:var(--bg)")}>
          <div role="img" aria-label={spOut ? "This piece is left out" : `Piece ${n(sp)} lands in ${REGION_NAME[sd]}`} style={css("position:relative;width:502px;height:384px;flex:none")}>
            {LOBES.map(([id, name, h, [l, t, w, hh], rad, kind]) => {
              const lit = !spOut && sd === id;
              const act = kind === "dest" || kind === "src";
              const count = id in REGION_NAME ? live.filter((p) => regions.get(p.id) === id).length : 0;
              const sub = id in REGION_NAME ? (count ? `+${count}` : "") : id === "pa" ? `${live.length} pieces in` : id === "oc" ? "The source stays here" : "";
              const bg = kind === "dim" ? "var(--soft)" : kind === "guard" ? tint(60) : lit ? glow(h) : tint(h);
              const pad = id === "fr" ? "justify-content:flex-start;padding-top:30px;" : id === "pa" ? "justify-content:flex-start;padding-top:40px;" : id === "ins" ? "justify-content:flex-start;padding-top:9px;" : "justify-content:center;";
              return (
                <div
                  key={id}
                  style={css(
                    `position:absolute;left:${l}px;top:${t}px;width:${w}px;height:${hh}px;border-radius:${rad};background:${bg};${id === "ins" ? `border:1.5px dashed ${deep(h)};` : ""}${lit ? `box-shadow:0 0 0 3px ${solid(h)};` : ""}display:flex;flex-direction:column;align-items:center;${pad}gap:1px;box-sizing:border-box;transition:background .45s,box-shadow .45s;z-index:${id === "ins" ? 3 : 1}`,
                  )}
                >
                  <span style={css(`font:500 ${act ? 12.5 : 11}px/1.2 Geist;color:${act ? deep(h) : "var(--muted)"};text-align:center;padding:0 6px`)}>{kind === "guard" ? "" : name}</span>
                  <span style={css(`font:400 10.5px/1.25 Geist;color:${act ? deep(h) : "var(--muted)"};opacity:.85;text-align:center;padding:0 6px`)}>{sub}</span>
                </div>
              );
            })}
            <span style={css("position:absolute;left:358px;top:340px;width:130px;font:400 11px/1.35 Geist;color:var(--muted)")}>Must-holds guard every change</span>
            <svg width={502} height={384} viewBox="0 0 502 384" aria-hidden="true" style={{ position: "absolute", left: 0, top: 0, pointerEvents: "none", overflow: "visible", zIndex: 4 }}>
              {lines.map((l, i) => (
                <path key={i} d={l.d} fill="none" stroke={l.c} strokeWidth={l.w} strokeLinecap="round" opacity={l.o} />
              ))}
            </svg>
            {live.map((p) => {
              const [x, y] = slot[p.id] ?? CENTER.lt;
              const h = HUE[regions.get(p.id) ?? "lt"];
              const on = p.id === sp.id;
              return (
                <button
                  key={p.id}
                  onClick={() => setSelId(p.id)}
                  aria-label={`Piece ${n(p)}`}
                  style={css(
                    `position:absolute;left:${x - 11}px;top:${y - 11}px;width:22px;height:22px;border-radius:50%;border:0;padding:0;background:${solid(h)};color:#fff;font:600 11px Geist;display:flex;align-items:center;justify-content:center;z-index:5;cursor:pointer;transition:left .4s,top .4s;box-shadow:${on ? `0 0 0 3px var(--surface),0 0 0 5px ${solid(h)}` : "0 1px 3px rgba(0,0,0,.18)"}`,
                  )}
                >
                  {n(p)}
                </button>
              );
            })}
          </div>
          <div style={css("width:464px;max-width:100%;display:flex;flex-direction:column;gap:4px")}>
            <div style={css("display:flex;justify-content:space-between;align-items:baseline;padding:0 12px 4px")}>
              <span style={css("font:500 12.5px Geist;color:var(--muted)")}>How it decided, in order</span>
              <span style={css("font:400 11.5px Geist;color:var(--muted)")}>the first yes wins</span>
            </div>
            <ol aria-label="Routing questions" style={css("list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:4px")}>
              {ORDER.map((s, i) => {
                const hit = !spOut && s === sd;
                return (
                  <li key={s} style={css(`display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:12px;${hit ? `background:${tint(HUE[s])};` : ""}`)}>
                    <span style={css(dotS(HUE[s]))} />
                    <span style={css("flex:1;min-width:0;display:flex;flex-direction:column;gap:1px")}>
                      <span style={css("font:500 13px Geist")}>{REGION_NAME[s]}</span>
                      <span style={css("font:400 12.5px Geist;color:var(--ink2)")}>{QUESTION[s]}</span>
                    </span>
                    <span style={css(`font:500 12px Geist;color:${hit ? deep(HUE[s]) : "var(--muted)"}`)}>{spOut ? "" : hit ? "Yes" : i < hitAt ? "No" : ""}</span>
                  </li>
                );
              })}
            </ol>
          </div>
        </div>
        <div style={css("flex:1 1 300px;min-width:0;padding:22px 24px 22px 22px;display:flex;flex-direction:column;gap:15px")}>
          <span style={css("font:500 11px 'Geist Mono';letter-spacing:.06em;color:var(--muted)")}>
            PIECE {n(sp)} OF {pieces.length} · {mark(sp, sd)}
          </span>
          <div style={css("display:flex;justify-content:space-between;align-items:flex-start;gap:10px")}>
            <span style={css("font:400 22px/1.25 Newsreader;text-wrap:pretty")}>{after(sp)}</span>
            {!spDone ? (
              <button
                onClick={() => setEditing(sp)}
                style={css("flex:none;padding:5px 12px;border-radius:99px;border:1px solid var(--line2);background:transparent;color:var(--ink);font:500 12px Geist")}
              >
                Edit
              </button>
            ) : null}
          </div>
          <div style={css("display:flex;align-items:center;gap:8px;flex-wrap:wrap")}>
            <span style={css(`padding:4px 11px;border-radius:99px;font:500 12.5px Geist;background:${tint(HUE[sd])};color:${deep(HUE[sd])}`)}>{REGION_NAME[sd]}</span>
            <span style={css("font:400 12.5px Geist;color:var(--muted)")}>{sp.destination || sp.route_key}</span>
          </div>
          <div style={css("display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:-6px")}>
            <span style={css("padding:3px 9px;border-radius:99px;border:1px solid var(--line2);font:500 11.5px Geist;color:var(--ink2)")}>
              {needsYou(sp) ? STATEMENT.disputed : (STATEMENT[sp.statement_status] ?? (sp.statement_status || STATEMENT.stated))}
            </span>
            <span style={css("font:400 12px Geist;color:var(--muted)")}>{LIFE[sd]}</span>
          </div>
          <div style={css("display:flex;flex-direction:column;gap:4px;padding:12px 14px;border-radius:14px;background:var(--soft)")}>
            <span style={css("font:500 12px Geist;color:var(--muted)")}>Why here</span>
            <span style={css("font:400 14px/1.5 Geist;text-wrap:pretty")}>
              {spOut ? "Left out. It stays in the original, and nothing in your Brain changes." : sp.reason ? `${sp.reason} ${REACH[sd]}` : REACH[sd]}
            </span>
          </div>
          {!spOut ? (
            <div style={css("display:flex;flex-direction:column;gap:6px")}>
              <span style={css("font:500 12px Geist;color:var(--muted)")}>What changes</span>
              <div style={css("display:flex;gap:6px;align-items:center;flex-wrap:wrap;font:400 13px/1.4 Geist")}>
                {sp.current_body ? (
                  <>
                    <span style={css("padding:2px 8px;border-radius:7px;background:oklch(0.64 0.17 28 / .12);text-decoration:line-through;color:var(--ink2)")}>{sp.current_body.slice(0, 220)}</span>
                    <span style={css("color:var(--muted)")}>→</span>
                  </>
                ) : null}
                <span style={css("padding:2px 8px;border-radius:7px;background:oklch(0.62 0.14 150 / .16)")}>{sp.current_body ? after(sp) : `New in ${REGION_NAME[sd]}`}</span>
              </div>
            </div>
          ) : null}
          <div style={css("display:flex;flex-direction:column;gap:6px")}>
            <div style={css("display:flex;justify-content:space-between;align-items:baseline;gap:8px")}>
              <span style={css("font:500 12px Geist;color:var(--muted)")}>Source text, word for word · {srcVer}</span>
              {sourceLink ? (
                <Link to={sourceLink} style={css("font:500 12px Geist;text-decoration:underline;text-underline-offset:3px;color:var(--ink)")}>
                  Open the source
                </Link>
              ) : null}
            </div>
            <pre style={css("margin:0;padding:10px 12px;border-radius:12px;background:var(--soft);font:400 11.5px/1.65 'Geist Mono';color:var(--ink2);white-space:pre-wrap;word-break:break-word")}>
              {sp.source?.excerpt || "The source's exact words weren't recorded for this piece."}
            </pre>
            <span style={css("font:400 11.5px/1.45 Geist;color:var(--muted)")}>
              The headline above is your AI's reading of it. Keeping approves storage; it doesn't verify it.
            </span>
          </div>
          {needsYou(sp) && !spDone ? (
            <div style={css("display:flex;flex-direction:column;gap:8px;padding:12px 14px;border-radius:14px;border:1px solid oklch(0.78 0.11 70)")}>
              <span style={css("font:500 13px Geist")}>You decide: which is current?</span>
              <dl style={css("margin:0;display:grid;grid-template-columns:auto 1fr;gap:5px 12px;font:400 12.5px/1.45 Geist")}>
                <dt style={css("color:var(--muted)")}>Current record</dt>
                <dd style={css("margin:0;color:var(--ink)")}>{sp.current_body?.slice(0, 220) || "What your Brain holds now"}</dd>
                <dt style={css("color:var(--muted)")}>Proposed</dt>
                <dd style={css("margin:0;color:var(--ink)")}>{after(sp)}</dd>
                {sp.conflicts ? (
                  <>
                    <dt style={css("color:var(--muted)")}>Differs from</dt>
                    <dd style={css("margin:0;color:var(--ink)")}>{sp.conflicts}</dd>
                  </>
                ) : null}
              </dl>
              <span style={css("font:400 11.5px Geist;color:var(--muted)")}>Older info imported later never overwrites the current record.</span>
              <div style={css("display:flex;gap:6px;flex-wrap:wrap")}>
                <Btn kind="primarySm" onClick={() => act(sp, true)} disabled={decide.isPending}>
                  The new one is current
                </Btn>
                <Btn kind="ghostSm" onClick={() => act(sp, false)} disabled={decide.isPending}>
                  Keep the current one
                </Btn>
              </div>
            </div>
          ) : null}
          {spDone ? (
            <div role="status" style={css("display:flex;gap:10px;align-items:center;padding:12px 14px;border-radius:14px;background:var(--soft);flex-wrap:wrap")}>
              <span style={css("font:400 13.5px/1.5 Geist;flex:1;min-width:200px")}>
                {spDone.kept ? `Kept by you. Goes to ${REGION_NAME[sd]}. Indexing, not searchable yet.` : "Left out by you. Nothing in your Brain changed."}
              </span>
              {spDone.checkpoint ? (
                <button
                  onClick={() => undoIt(spDone.checkpoint as string, batch && batch.checkpoint === spDone.checkpoint ? batch.ids : [sp.id])}
                  disabled={undo.isPending}
                  style={css("border:0;background:transparent;padding:0;font:500 13px Geist;color:var(--ink)")}
                >
                  Undo
                </button>
              ) : null}
            </div>
          ) : (
            <div style={css("display:flex;flex-direction:column;gap:8px;padding-top:2px")}>
              {!needsYou(sp) ? (
                <div style={css("display:flex;gap:6px;flex-wrap:wrap")}>
                  <Btn kind="primarySm" onClick={() => act(sp, true)} disabled={decide.isPending}>
                    Keep this one
                  </Btn>
                </div>
              ) : null}
              <span style={css("font:500 12px Geist;color:var(--muted)")}>Put it somewhere else</span>
              <div style={css("display:flex;gap:6px;flex-wrap:wrap")}>
                <button
                  onClick={() => setEditing(sp)}
                  style={css("display:flex;align-items:center;gap:7px;padding:6px 12px;border-radius:99px;border:1px solid var(--line2);background:var(--surface);font:400 12.5px Geist;color:var(--ink)")}
                >
                  {ORDER.filter((s) => s !== sd).map((s) => (
                    <span key={s} style={css(dotS(HUE[s], 8))} />
                  ))}
                  Choose where it goes
                </button>
              </div>
              <button
                onClick={() => act(sp, false)}
                disabled={decide.isPending}
                style={css("align-self:flex-start;border:0;background:transparent;padding:4px 0;font:500 13px Geist;color:var(--ink2)")}
              >
                Leave this one out
              </button>
            </div>
          )}
          {decide.error ? <span role="alert" style={css("font:400 13px Geist;color:oklch(0.55 0.17 28)")}>{(decide.error as Error).message}</span> : null}
          {undo.error ? <span role="alert" style={css("font:400 13px Geist;color:oklch(0.55 0.17 28)")}>{(undo.error as Error).message}</span> : null}
        </div>
      </div>
      <div style={css("display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap;padding:14px 22px;border-top:1px solid var(--line);background:var(--bg)")}>
        <span style={css("font:400 13px/1.5 Geist;color:var(--ink2)")}>
          {waiting.length
            ? `${keepable.length === 1 ? "1 piece is" : `${keepable.length} pieces are`} ready to keep${needsN ? `, and ${needsN} ${needsN === 1 ? "waits" : "wait"} for you to pick which is current` : ""}. Every line above is kept, waiting or left out with a reason. The source stays in Capture.`
            : "Every piece is decided. The source stays in Capture."}
        </span>
        <div style={css("display:flex;gap:8px")}>
          {onClose ? (
            <Btn kind="ghost" onClick={onClose}>
              Leave it private
            </Btn>
          ) : null}
          {batch?.checkpoint ? (
            <Btn kind="ghost" onClick={() => undoIt(batch.checkpoint as string, batch.ids)} disabled={undo.isPending}>
              Undo keeping {batch.ids.length}
            </Btn>
          ) : null}
          {keepable.length ? (
            <Btn kind="primary" onClick={keepAll} disabled={decide.isPending}>
              {needsN ? `Keep ${keepable.length}, decide ${needsN} later` : `Keep ${keepable.length}`}
            </Btn>
          ) : null}
        </div>
      </div>
      {editing ? <EditBeforeKeep p={editing} onClose={() => setEditing(null)} onSave={(extra) => act(editing, true, extra)} busy={decide.isPending} /> : null}
    </div>
  );
}

function LeftOutList({ leftOut }: { leftOut: LeftOut[] }) {
  return (
    <div style={css("display:flex;flex-direction:column")}>
      <span style={css("font:500 13px Geist;color:var(--muted);padding:8px 0")}>Left out, and why</span>
      {leftOut.map((l, i) => (
        <div key={i} style={css("display:flex;gap:14px;padding:10px 0;border-top:1px solid var(--line);flex-wrap:wrap")}>
          <span style={css("font:400 14px Geist;flex:1;color:var(--ink2)")}>{l.statement}</span>
          <span style={css("font:400 13px Geist;color:var(--muted)")}>{l.why}</span>
        </div>
      ))}
    </div>
  );
}
