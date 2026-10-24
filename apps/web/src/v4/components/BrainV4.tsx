// The v4 Brain items (spec section 6), drawn as the design draws them: the collapsible map card
// ("What your AIs see first"), level chips, copyable section addresses, the Lore shelf, session
// search for Activity, and the pull budget for Settings. Every value comes from the server.

import { useState } from "react";

import { usePolicy, useSetPolicy } from "../api";
import { css } from "../css";
import { type FoundSession, type Lesson, LEVEL_LABEL, LEVELS, type Level, type MapView, useLore, useMapView, useSections, useSessionSearch } from "../hooks/brainv4";
import { Btn, Empty, Failure, Later, Loaded, Loading, S, when } from "../ui";

const LV_BG: Record<Level, string> = {
  canon: "oklch(0.72 0.1 300 / .2)",
  confirmed: "oklch(0.72 0.1 250 / .16)",
  kept: "var(--soft)",
  tentative: "oklch(0.74 0.12 80 / .2)",
  exhaust: "transparent",
};
const LORE_HUE = "oklch(0.66 0.1 185)";
const ADDR = "border:0;background:var(--soft);padding:2px 8px;border-radius:6px;font:400 11.5px 'Geist Mono';color:var(--ink2);cursor:pointer";
const PILL = (on: boolean) =>
  `padding:5px 12px;border-radius:99px;font:${on ? 500 : 400} 12.5px Geist;cursor:pointer;${
    on ? "background:var(--ink);color:var(--bg);border:1px solid var(--ink)" : "background:transparent;color:var(--ink);border:1px solid var(--line2)"
  }`;

function isLevel(x: string | undefined | null): x is Level {
  return Boolean(x) && (LEVELS as string[]).includes(x as string);
}

/** One entry's level, in words with its glyph. */
export function LevelChip({ level }: { level: string | undefined | null }) {
  if (!isLevel(level)) return null;
  return (
    <span
      style={css(
        `display:inline-flex;align-items:center;padding:2px 8px;border-radius:6px;font:500 11px Geist;white-space:nowrap;flex:none;color:var(--ink);box-shadow:inset 0 0 0 1px var(--line2);background:${LV_BG[level]}`,
      )}
    >
      {LEVEL_LABEL[level]}
    </span>
  );
}

/** A section address that copies itself, and says so. */
export function CopyAddress({ address }: { address: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      title="Copy section address"
      aria-label={`Copy section address ${address}`}
      onClick={(e) => {
        e.stopPropagation();
        void navigator.clipboard?.writeText(address).catch(() => undefined);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1400);
      }}
      style={css(ADDR)}
    >
      {copied ? "Copied" : address}
    </button>
  );
}

/** The addresses of one note, lesson or file, for "Section addresses" on its page. */
export function SectionAddresses({ id }: { id: string }) {
  const q = useSections(id);
  if (q.isLoading) return <Loading what="Reading its sections" />;
  if (q.error) return <span style={css(S.small)}>Section addresses aren't available for this item.</span>;
  const rows = q.data?.sections ?? [];
  if (!rows.length) return null;
  return (
    <div style={css("display:flex;gap:8px;align-items:center;flex-wrap:wrap")}>
      <span style={css("font:400 12px Geist;color:var(--muted)")}>Section addresses</span>
      {rows.map((r) => (
        <CopyAddress key={r.address} address={r.address} />
      ))}
      <span style={css("font:400 12px Geist;color:var(--muted)")}>Click to copy. Paste one into any AI to open just that section.</span>
    </div>
  );
}

// ---------------------------------------------------------------- the map card

interface TierRow {
  t: string;
  s: string;
  addr: string;
}

interface Tier {
  id: string;
  l: string;
  rows: TierRow[];
  more: number;
}

function tiers(m: MapView, all: boolean): Tier[] {
  // The short map shows each tier whole unless it was cut; `cut` says by how many.
  const cap = (id: string, n: number) => (all ? n : n - (m.cut[id] ?? 0));
  const take = <T,>(id: string, list: T[]) => list.slice(0, cap(id, list.length));
  const counts = LEVELS.map((k) => `${k} ${m.levels[k] ?? 0}`).join(" · ");
  const out: Tier[] = [
    { id: "areas", l: "Top areas", rows: take("areas", m.areas).map((a) => ({ t: `${a.name} · ${a.notes}`, s: a.covers, addr: "" })), more: 0 },
    {
      id: "projects",
      l: "Active projects",
      rows: take("projects", m.projects).map((p) => ({ t: p.name, s: p.aka.length ? `aka ${p.aka.slice(0, 2).map((x) => `“${x}”`).join(", ")}` : "", addr: p.address })),
      more: 0,
    },
    { id: "sheets", l: "Sheets", rows: take("sheets", m.sheets).map((s) => ({ t: s.name, s: s.columns.join(" · "), addr: "" })), more: 0 },
    { id: "must_holds", l: "Must-hold domains", rows: take("must_holds", m.must_holds).map((x) => ({ t: x.name, s: "", addr: "" })), more: 0 },
    { id: "lore", l: "Lore", rows: take("lore", m.lore).map((x) => ({ t: x.name, s: "", addr: x.address ?? "" })), more: 0 },
    { id: "levels", l: "By level", rows: [{ t: counts, s: "", addr: "" }], more: 0 },
  ];
  const total: Record<string, number> = { areas: m.areas.length, projects: m.projects.length, sheets: m.sheets.length, must_holds: m.must_holds.length, lore: m.lore.length, levels: 1 };
  return out.map((t) => ({ ...t, more: all ? 0 : Math.max(0, (total[t.id] ?? 0) - t.rows.length) }));
}

/** "What your AIs see first": the short map that opens every packet, collapsible. */
export function MapCard() {
  const q = useMapView();
  const [open, setOpen] = useState(false);
  const [all, setAll] = useState(false);
  const [raw, setRaw] = useState(false);
  const m = q.data;
  const tok = m ? `About ${m.tokens} tokens · ${m.limit} max` : "";
  const cut = m ? Object.keys(m.cut).length > 0 : false;
  return (
    <div style={css("background:var(--surface);border-radius:24px;box-shadow:var(--shadow);padding:22px;display:flex;flex-direction:column;gap:14px")}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        style={css("display:flex;align-items:center;gap:12px;border:0;background:transparent;padding:0;text-align:left;color:var(--ink);width:100%;flex-wrap:wrap;cursor:pointer")}
      >
        <span style={css("width:10px;height:10px;border-radius:3px;background:var(--ink);flex:none")} />
        <div style={css("display:flex;flex-direction:column;gap:2px;flex:1;min-width:220px")}>
          <span style={css("font:500 15px Geist")}>What your AIs see first</span>
          <span style={css("font:400 13px/1.45 Geist;color:var(--muted)")}>The short map that opens every packet{tok ? ` · ${tok}` : ""}</span>
        </div>
        <span aria-hidden="true" style={css("font:400 13px Geist;color:var(--muted)")}>
          {open ? "▴" : "▾"}
        </span>
      </button>
      {open ? (
        <Loaded q={q}>
          {(map) => (
            <div style={css("display:flex;flex-direction:column;gap:14px")}>
              <div style={css("display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap")}>
                <span style={css("font:400 13px/1.5 Geist;color:var(--ink2);max-width:640px;flex:1;min-width:220px")}>
                  Your AI reads this to know what it could ask for, then pulls only what the task needs.
                </span>
                <div style={css("display:flex;gap:8px;flex-wrap:wrap")}>
                  <Btn kind="ghostSm" style="padding:7px 14px;font:500 12.5px Geist" onClick={() => setRaw((v) => !v)}>
                    {raw ? "Hide the text" : "Show it as sent"}
                  </Btn>
                  <Btn kind="ghostSm" style="padding:7px 14px;font:500 12.5px Geist" onClick={() => setAll((v) => !v)}>
                    {all ? "Show what's sent" : "See everything"}
                  </Btn>
                </div>
              </div>
              {cut && !all ? (
                <div role="status" style={css("display:flex;gap:10px;align-items:center;padding:10px 14px;border-radius:12px;background:oklch(0.74 0.12 80 / .16);flex-wrap:wrap")}>
                  <span style={css("font:400 13.5px/1.45 Geist;flex:1;min-width:220px")}>
                    The map was cut to fit its {map.limit} tokens. Each “+N more” marks a tier that was cut. Your AIs can ask gnomon.map for the full tier; you can see it here with See everything.
                  </span>
                </div>
              ) : null}
              {all ? (
                <span style={css("font:400 12.5px Geist;color:var(--muted)")}>Everything, shown to you only. Your AIs still get the short map; the rest is one gnomon.map call away.</span>
              ) : null}
              <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:10px 28px")}>
                {tiers(map, all).map((ti) => (
                  <div key={ti.id} style={css("display:flex;flex-direction:column;padding:10px 0;border-top:1px solid var(--line)")}>
                    <div style={css("display:flex;justify-content:space-between;gap:8px;padding-bottom:4px")}>
                      <span style={css("font:500 12px Geist;color:var(--muted)")}>{ti.l}</span>
                      {ti.more ? <span style={css("font:500 12px Geist;color:var(--ink)")}>+{ti.more} more</span> : null}
                    </div>
                    {ti.rows.length === 0 ? <span style={css("font:400 13px Geist;color:var(--faint)")}>None yet</span> : null}
                    {ti.rows.map((r, i) => (
                      <div key={`${r.t}-${i}`} style={css("display:flex;gap:8px;align-items:baseline;padding:4px 0;flex-wrap:wrap")}>
                        <span style={css("font:400 14px/1.4 Geist")}>{r.t}</span>
                        {r.s ? <span style={css("font:400 12.5px/1.4 Geist;color:var(--muted);flex:1;min-width:120px")}>{r.s}</span> : null}
                        {r.addr ? <CopyAddress address={r.addr} /> : null}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
              {map.sealed > 0 ? (
                <div style={css("display:flex;gap:10px;align-items:center;padding:10px 14px;border-radius:12px;background:var(--soft);flex-wrap:wrap")}>
                  <span style={css("font:500 10.5px 'Geist Mono';letter-spacing:.05em;color:var(--ink2)")}>ONLY YOU SEE THIS</span>
                  <span style={css("font:400 13.5px/1.45 Geist;flex:1;min-width:220px")}>
                    {map.sealed === 1 ? "1 sealed project is" : `${map.sealed} sealed projects are`} left out of the map: no name, no count. The “+N more” above doesn't include{" "}
                    {map.sealed === 1 ? "it" : "them"}, so nothing hints that {map.sealed === 1 ? "it exists" : "they exist"}.
                  </span>
                </div>
              ) : null}
              {raw ? (
                <pre style={css("margin:0;padding:14px 16px;border-radius:14px;background:var(--code);color:#d8d5cd;font:400 12px/1.6 'Geist Mono';white-space:pre-wrap;word-break:break-word")}>
                  {map.text}
                </pre>
              ) : null}
              <div style={css("display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;padding-top:4px;border-top:1px solid var(--line)")}>
                <span style={css("font:400 13px Geist;color:var(--ink2);padding-top:10px")}>A partial list: absent here doesn't mean absent from the Brain.</span>
                <span style={css("font:400 12px 'Geist Mono';color:var(--muted);padding-top:10px")}>{tok}</span>
              </div>
            </div>
          )}
        </Loaded>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------- the Lore shelf

export function LoreShelf() {
  const q = useLore();
  const [picked, setPicked] = useState<string | null>(null);
  return (
    <div style={css("background:var(--surface);border-radius:24px;box-shadow:var(--shadow);padding:22px;display:flex;flex-direction:column;gap:14px")}>
      <div style={css("display:flex;flex-direction:column;gap:3px")}>
        <div style={css("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
          <span style={css(`width:10px;height:10px;border-radius:3px;background:${LORE_HUE};flex:none`)} />
          <span style={css("font:500 15px Geist")}>Lore</span>
        </div>
        <span style={css("font:400 13px/1.5 Geist;color:var(--ink2)")}>
          Lessons: a short story, the pattern it warns about, and the words that bring it up. Sent in full once per session, then by name.
        </span>
      </div>
      <Loaded q={q} empty={(list) => (list.length ? null : <Empty title="No lessons yet">When an AI is corrected or undone twice for the same kind of thing, it proposes a lesson. It waits in Catch up for you.</Empty>)}>
        {(list) => (
          <div style={css("display:flex;flex-direction:column;gap:10px")}>
            {list.map((l) => (
              <LessonCard key={l.id} lesson={l} open={picked === l.id} onToggle={() => setPicked(picked === l.id ? null : l.id)} />
            ))}
          </div>
        )}
      </Loaded>
    </div>
  );
}

function LessonCard({ lesson: l, open, onToggle }: { lesson: Lesson; open: boolean; onToggle: () => void }) {
  return (
    <div
      style={css(
        `padding:16px;border-radius:18px;border:1px solid ${open ? "var(--ink)" : "var(--line)"};background:var(--surface);display:flex;flex-direction:column;gap:8px;text-align:left;color:var(--ink);min-width:0`,
      )}
    >
      <button type="button" onClick={onToggle} aria-expanded={open} style={css("display:flex;align-items:center;gap:8px;flex-wrap:wrap;border:0;background:transparent;padding:0;text-align:left;color:var(--ink);cursor:pointer")}>
        <span style={css("font:400 19px/1.3 Newsreader;flex:1;min-width:160px")}>{l.title}</span>
        <LevelChip level={l.level} />
      </button>
      <span style={css("font:400 13.5px/1.5 Geist;color:var(--ink2)")}>{l.story}</span>
      <span style={css("display:flex")}>
        <CopyAddress address={l.address} />
      </span>
      {open ? (
        <div style={css("display:flex;flex-direction:column;gap:8px;padding:14px 16px;border-radius:14px;background:var(--bg);border:1px solid var(--line)")}>
          <span style={css("font:500 10.5px 'Geist Mono';letter-spacing:.05em;color:var(--muted)")}>LESSON · KEPT {when(l.added).toUpperCase()}</span>
          <div style={css("display:flex;flex-direction:column;gap:2px")}>
            <span style={css("font:500 12px Geist;color:var(--muted)")}>Warns about</span>
            <span style={css("font:400 14px/1.5 Geist")}>{l.pattern}</span>
          </div>
          <div style={css("display:flex;flex-direction:column;gap:2px")}>
            <span style={css("font:500 12px Geist;color:var(--muted)")}>Brought up by</span>
            <span style={css("font:400 14px/1.5 Geist")}>{l.words.join(" · ")}</span>
          </div>
          <div style={css("display:flex;gap:6px;flex-wrap:wrap")}>
            {l.sections.map((a) => (
              <CopyAddress key={a} address={a} />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------- session search

export function SessionSearch() {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const found = useSessionSearch(q);
  const asked = q.trim().length > 1;
  const list: FoundSession[] = found.data ?? [];
  return (
    <div style={css("background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:18px 20px;display:flex;flex-direction:column;gap:12px")}>
      <div style={css("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
        <span style={css("font:500 15px Geist;flex:1")}>Which session worked on…?</span>
      </div>
      <input
        aria-label="Search past sessions"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="A task, a file, a person or a project"
        style={css("border:1px solid var(--line2);border-radius:14px;padding:11px 14px;outline:none;background:var(--bg);color:var(--ink);font:400 15px Geist")}
      />
      {asked && found.isLoading ? <Loading what="Searching past sessions" /> : null}
      {asked && found.error ? <Failure error={found.error} retry={() => void found.refetch()} /> : null}
      {asked && found.data && list.length === 0 ? (
        <span style={css("font:400 13.5px Geist;color:var(--muted)")}>No session's receipt mentions that. Receipts only list what Contxt gave; work done elsewhere isn't recorded here.</span>
      ) : null}
      {list.length ? (
        <div style={css("display:flex;flex-direction:column")}>
          {list.map((s) => {
            const isOpen = open === s.session_id;
            return (
              <div key={s.session_id} style={css("display:flex;flex-direction:column;border-top:1px solid var(--line)")}>
                <button
                  type="button"
                  aria-expanded={isOpen}
                  onClick={() => setOpen(isOpen ? null : s.session_id)}
                  style={css("display:flex;gap:12px;align-items:center;padding:11px 0;border:0;background:transparent;text-align:left;color:var(--ink);flex-wrap:wrap")}
                >
                  <span style={css("font:500 12px 'Geist Mono'")}>{s.session_id}</span>
                  <span style={css("font:400 14.5px Geist;flex:1;min-width:180px")}>{s.did || "A request"}</span>
                  <span style={css("font:400 12.5px Geist;color:var(--muted)")}>
                    {when(s.date)} · {s.app}
                  </span>
                  <span aria-hidden="true" style={css("font:400 12px Geist;color:var(--muted)")}>
                    {isOpen ? "▾" : "▸"}
                  </span>
                </button>
                {isOpen ? (
                  <div style={css("display:flex;flex-direction:column;gap:4px;padding:0 0 12px 14px")}>
                    <span style={css("font:500 12px Geist;color:var(--muted)")}>What it was given · receipt {s.receipts[s.receipts.length - 1] ?? ""}</span>
                    {s.given.length === 0 ? <span style={css("font:400 13px Geist;color:var(--faint)")}>Nothing from the Brain</span> : null}
                    {s.given.map((g, i) => (
                      <span key={`${g}-${i}`} style={css("font:400 13px/1.45 Geist;color:var(--ink2)")}>
                        {g}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : null}
      <div style={css("display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding-top:4px")}>
        <button
          type="button"
          disabled
          aria-disabled="true"
          style={css("padding:7px 14px;border-radius:99px;border:1px dashed var(--line2);background:transparent;font:500 12.5px Geist;color:var(--muted);cursor:not-allowed")}
        >
          Read that session's own record
          <Later />
        </button>
        <span style={css("font:400 12px Geist;color:var(--muted)")}>Asks you each time.</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- the pull budget

const ITEMS = [1, 2, 3, 5];
const TOKENS = [800, 1500, 3000];

export function PullBudget() {
  const q = usePolicy();
  const set = useSetPolicy();
  const items = Number(q.data?.pull_items ?? 0);
  const tokens = Number(q.data?.pull_tokens ?? 0);
  return (
    <div style={css("display:flex;flex-direction:column;gap:10px")}>
      <span style={css("font:500 15px Geist")}>Pull budget</span>
      {q.isLoading ? <Loading /> : null}
      {q.error ? <Failure error={q.error} retry={() => void q.refetch()} /> : null}
      {q.data ? (
        <>
          <span style={css("font:400 14px/1.5 Geist;color:var(--ink2)")}>
            After the packet, an AI may open up to {items} {items === 1 ? "more item" : "more items"}, about {tokens.toLocaleString()} tokens in all. Past that it gets names only, and the receipt says so.
          </span>
          <div style={css("display:flex;gap:6px;align-items:center;flex-wrap:wrap")} role="group" aria-label="Items per request">
            <span style={css("font:400 12.5px Geist;color:var(--muted);width:140px")}>Items per request</span>
            {ITEMS.map((v) => (
              <button key={v} type="button" aria-pressed={items === v} disabled={set.isPending} onClick={() => set.mutate({ pull_items: v })} style={css(PILL(items === v))}>
                {v}
              </button>
            ))}
          </div>
          <div style={css("display:flex;gap:6px;align-items:center;flex-wrap:wrap")} role="group" aria-label="Tokens per request">
            <span style={css("font:400 12.5px Geist;color:var(--muted);width:140px")}>Tokens per request</span>
            {TOKENS.map((v) => (
              <button key={v} type="button" aria-pressed={tokens === v} disabled={set.isPending} onClick={() => set.mutate({ pull_tokens: v })} style={css(PILL(tokens === v))}>
                {v.toLocaleString()}
              </button>
            ))}
          </div>
          {set.error ? <Failure error={set.error} /> : null}
        </>
      ) : null}
    </div>
  );
}
