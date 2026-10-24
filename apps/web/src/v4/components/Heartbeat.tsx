// The heartbeat on the auto-governed Home, as v4 draws it: the heartbeat bar (cadence, the last
// beat, the next one, Beat now, Pause, connector chips that light as each is read), The world
// right now (a card per region, and every line of one with its source and Undo), and Recent
// beats. Everything comes from /api/heartbeat; nothing here is example data.

import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router";

import { css, cx } from "../css";
import {
  beatSummary,
  clock,
  costLine,
  type HbConnector,
  type HbLine,
  type HbRegion,
  type HbStatus,
  tokens,
  useBeatNow,
  useBeats,
  useHeartbeat,
  useHeartbeatSettings,
  useRegions,
  useUndoLine,
} from "../hooks/heartbeat";
import { Empty, Failure, Loaded, Loading } from "../ui";

const GREEN = "oklch(0.66 0.14 150)";
const AMBER = "oklch(0.74 0.14 80)";
const HUES = [265, 150, 35, 210, 80, 320, 190, 20];
const PILL = "padding:7px 14px;border-radius:99px;border:1px solid var(--line2);background:transparent;font:500 12.5px Geist;color:var(--ink);cursor:pointer";

/** The bar's state in words, for the dot and the line under the title. */
function barLine(s: HbStatus): string {
  if (s.running) {
    const now = s.connectors.find((c) => c.id === s.running?.reading);
    return now ? `Reading ${now.name} through ${now.cli_label}…` : "Beating…";
  }
  if (s.state !== "ready") return s.line;
  const last = s.last_beat;
  const next = s.next_beat_at ? ` · next ${clock(s.next_beat_at)}` : "";
  if (!last) return `No beat yet${next}`;
  if (last.status === "failed") return `The last beat (${clock(last.started_at)}) stopped: ${last.errors[0] ?? "it could not finish"}${next}`;
  const read = `read ${last.connectors_read} ${last.connectors_read === 1 ? "connector" : "connectors"}`;
  return `Last beat ${clock(last.started_at)} · ${read}, ${last.items} ${last.items === 1 ? "item" : "items"}, ${last.changes} ${last.changes === 1 ? "change" : "changes"}${next}`;
}

function chipState(c: HbConnector, s: HbStatus): "off" | "now" | "done" | "wait" | "ok" | "problem" {
  if (!c.enabled || !c.present) return "off";
  if (s.running) {
    if (s.running.reading === c.id) return "now";
    return s.running.read.includes(c.id) ? "done" : "wait";
  }
  return c.status === "ok" ? "ok" : "problem";
}

const CHIP_WORDS: Record<string, string> = {
  off: "off",
  now: "reading now",
  done: "read",
  wait: "waiting to be read",
  ok: "on",
  problem: "needs attention",
};

export function HeartbeatBar() {
  const navigate = useNavigate();
  const status = useHeartbeat();
  const beat = useBeatNow();
  const settings = useHeartbeatSettings();
  if (status.isLoading) return <Loading what="Reading the heartbeat" />;
  if (status.error || !status.data) return <Failure error={status.error} retry={() => void status.refetch()} />;
  const s = status.data;
  const running = Boolean(s.running) || beat.isPending;
  const dot = s.paused ? "var(--faint)" : s.state === "ready" ? (running ? AMBER : GREEN) : running ? AMBER : "oklch(0.68 0.14 35)";
  const said = beat.data?.skipped ? beat.data.line : null;
  return (
    <section
      aria-label="Heartbeat"
      style={css("background:var(--surface);border-radius:22px;box-shadow:var(--shadow);padding:16px 20px;display:flex;flex-direction:column;gap:12px;margin-top:-12px")}
    >
      <div style={css("display:flex;align-items:center;gap:14px;flex-wrap:wrap")}>
        <span
          aria-hidden="true"
          style={css(`width:10px;height:10px;border-radius:50%;flex:none;background:${dot};${s.paused ? "" : `animation:gnDot ${running ? ".6s" : "1.6s"} infinite`}`)}
        />
        <div role="status" style={css("display:flex;flex-direction:column;gap:2px;flex:1;min-width:220px")}>
          <span style={css("font:500 15px Geist")}>Heartbeat · {s.paused ? "paused" : `every ${s.cadence} min`}</span>
          <span style={css("font:400 13px/1.45 Geist;color:var(--muted)")}>{barLine(s)}</span>
        </div>
        {s.in_quiet_hours && !s.paused && !running ? (
          <span style={css("display:inline-flex;align-items:center;gap:8px;flex-wrap:wrap")}>
            <span style={css("padding:7px 14px;border-radius:99px;background:var(--soft);color:var(--muted);font:500 12.5px Geist")}>Quiet hours</span>
            <button type="button" onClick={() => beat.mutate()} style={css("border:0;background:transparent;font:500 12.5px Geist;color:var(--ink);text-decoration:underline;cursor:pointer;padding:0")}>
              Beat once anyway
            </button>
          </span>
        ) : (
          <button
            type="button"
            disabled={running || s.paused}
            title={s.paused ? "The heartbeat is paused. Resume it first." : undefined}
            onClick={() => beat.mutate()}
            style={css(`padding:7px 14px;border-radius:99px;background:var(--ink);color:var(--bg);border:0;font:500 12.5px Geist;cursor:pointer${running || s.paused ? ";opacity:.55" : ""}`)}
          >
            {running ? "Beating…" : "Beat now"}
          </button>
        )}
        <button type="button" disabled={settings.isPending} onClick={() => settings.mutate({ paused: !s.paused })} style={css(PILL)}>
          {s.paused ? "Resume" : "Pause"}
        </button>
        <button type="button" onClick={() => navigate("/settings?tab=approval")} style={css(PILL)}>
          Connectors
        </button>
      </div>
      {s.connectors.length ? (
        <ul aria-label="Connectors" style={css("display:flex;gap:6px;flex-wrap:wrap;margin:0;padding:0;list-style:none")}>
          {s.connectors.map((c) => {
            const st = chipState(c, s);
            return (
              <li
                key={c.id}
                title={c.status_line}
                aria-label={`${c.name}: ${CHIP_WORDS[st]}`}
                style={css(
                  `display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:99px;font:400 12px Geist;color:${st === "off" ? "var(--muted)" : "var(--ink)"};background:${
                    st === "now" ? "oklch(0.74 0.12 80 / .25)" : "var(--soft)"
                  }${st === "off" ? ";text-decoration:line-through" : ""}`,
                )}
              >
                <span
                  aria-hidden="true"
                  style={css(
                    `width:6px;height:6px;border-radius:50%;flex:none;background:${
                      st === "off" || st === "wait" ? "var(--line2)" : st === "now" ? AMBER : st === "problem" ? "oklch(0.68 0.14 35)" : GREEN
                    }`,
                  )}
                />
                {c.name}
              </li>
            );
          })}
        </ul>
      ) : null}
      {said ? <span style={css("font:400 13px Geist;color:var(--ink2)")}>{said}</span> : null}
      {beat.error ? <Failure error={beat.error} /> : null}
      {settings.error ? <Failure error={settings.error} /> : null}
    </section>
  );
}

/** One item a beat read, with every write it made: a region shows the item once, and each write
 * keeps its own undo (an item can move a project's progress and open a task). */
export interface HbItem {
  key: string;
  first: HbLine;
  lines: HbLine[];
  gone: boolean;
  fresh: boolean;
}

export function itemsOf(lines: HbLine[]): HbItem[] {
  const out: HbItem[] = [];
  const found = new Map<string, HbItem>();
  for (const line of lines) {
    const key = `${line.beat_id}|${line.source_id}`;
    const item = found.get(key);
    if (item) item.lines.push(line);
    else {
      const made = { key, first: line, lines: [line], gone: false, fresh: false };
      found.set(key, made);
      out.push(made);
    }
  }
  for (const item of out) {
    item.gone = item.lines.every((l) => l.status === "undone");
    item.fresh = !item.gone && item.lines.some((l) => l.new_this_beat && l.status !== "undone");
  }
  return out;
}

const itemText = (item: HbItem) =>
  cx("font:400 13.5px/1.45 Geist;flex:1;min-width:160px", item.fresh && "font-weight:500", item.gone && "text-decoration:line-through;color:var(--muted)");

function ItemLine({ item }: { item: HbItem }) {
  return (
    <div style={css("display:flex;gap:10px;align-items:baseline;padding:7px 0;border-top:1px solid var(--line);flex-wrap:wrap")}>
      <span style={itemText(item)}>{item.first.text}</span>
      <span style={css("font:400 11.5px Geist;color:var(--muted);white-space:nowrap")}>
        {item.first.connector} · {clock(item.first.at)}
      </span>
    </div>
  );
}

function ItemRow({ item, undoing, onUndo }: { item: HbItem; undoing: string | null; onUndo: (line: HbLine) => void }) {
  const line = item.first;
  return (
    <div style={css("display:flex;flex-direction:column;gap:4px;padding:12px 0;border-top:1px solid var(--line)")}>
      <span style={itemText(item)}>{line.text}</span>
      <span style={css("font:400 12.5px/1.45 Geist;color:var(--muted)")}>{[line.connector, line.how, line.cli_label, clock(line.at)].filter(Boolean).join(" · ")}</span>
      {item.lines.map((w) => {
        const gone = w.status === "undone";
        return (
          <div key={w.id} style={css("display:flex;gap:14px;align-items:flex-start;flex-wrap:wrap")}>
            <div style={css("flex:1;min-width:220px;display:flex;flex-direction:column;gap:2px")}>
              <span style={css("font:400 12.5px/1.45 Geist;color:var(--ink2)")}>{gone ? `Undone. ${w.wrote}` : w.wrote || "Noted, nothing written."}</span>
              {w.reason ? <span style={css("font:400 12px/1.45 Geist;color:var(--muted)")}>Why: {w.reason}</span> : null}
            </div>
            {w.can_undo || gone ? (
              <button
                type="button"
                aria-label={gone ? `Undone: ${w.wrote || w.text}` : `Undo: ${w.wrote || w.text}`}
                disabled={gone || undoing === w.id}
                onClick={() => onUndo(w)}
                style={css("border:0;background:transparent;font:500 12.5px Geist;color:var(--ink2);cursor:pointer")}
              >
                {gone ? "Undone" : undoing === w.id ? "Undoing…" : "Undo"}
              </button>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

export function WorldRightNow() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const regions = useRegions();
  const undo = useUndoLine();
  const [undoing, setUndoing] = useState<string | null>(null);
  const selected = params.get("region");
  const pick = (id: string | null) => {
    const next = new URLSearchParams(params);
    if (id) next.set("region", id);
    else next.delete("region");
    setParams(next, { replace: true });
  };
  const hue = (i: number) => HUES[i % HUES.length];
  return (
    <section id="world" aria-label="The world right now" style={css("display:flex;flex-direction:column;gap:14px")}>
      <div style={css("display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap")}>
        <h2 style={css("margin:0;font:400 30px Newsreader")}>The world right now</h2>
        <button type="button" onClick={() => navigate("/brain")} style={css("border:0;background:transparent;font:400 13px Geist;color:var(--muted);cursor:pointer")}>
          Open Brain →
        </button>
      </div>
      <span style={css("font:400 14.5px/1.5 Geist;color:var(--ink2);max-width:720px;margin-top:-6px")}>
        Each region of your Brain, kept current by the heartbeat through the connectors in your CLIs. Projects sit in the region they belong to. Click a region to see where every line came from.
      </span>
      {undo.error ? <Failure error={undo.error} /> : null}
      <Loaded q={regions} empty={(rows) => (rows.length ? null : <Empty title="No regions yet">Your Brain's areas appear here once it has some.</Empty>)}>
        {(rows: HbRegion[]) => {
          const sel = rows.find((r) => r.id === selected) ?? null;
          return (
            <>
              <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:14px")}>
                {rows.map((rg, i) => {
                  const on = rg.id === selected;
                  const live = rg.lines.filter((l) => l.status !== "undone");
                  const items = itemsOf(rg.lines);
                  return (
                    <div
                      key={rg.id}
                      style={css(
                        `padding:18px 20px;border-radius:20px;background:var(--surface);box-shadow:var(--shadow);display:flex;flex-direction:column;gap:12px;border-top:3px solid oklch(0.68 0.12 ${hue(i)});${on ? "outline:2px solid var(--ink)" : ""}`,
                      )}
                    >
                      <button
                        type="button"
                        aria-expanded={on}
                        onClick={() => pick(on ? null : rg.id)}
                        style={css("display:flex;flex-direction:column;gap:8px;border:0;background:transparent;padding:0;text-align:left;color:var(--ink);cursor:pointer")}
                      >
                        <div style={css("display:flex;align-items:center;gap:8px;width:100%")}>
                          <span aria-hidden="true" style={css(`width:10px;height:10px;border-radius:3px;flex:none;background:oklch(0.68 0.12 ${hue(i)})`)} />
                          <span style={css("font:500 14px Geist")}>{rg.name}</span>
                          {rg.new_this_beat ? (
                            <span style={css("padding:2px 8px;border-radius:99px;font:500 11px Geist;background:oklch(0.62 0.14 150 / .18);color:var(--ink)")}>+{rg.new_this_beat} this beat</span>
                          ) : null}
                          <span style={css("font:400 12px Geist;color:var(--muted);margin-left:auto")}>{clock(rg.updated_at)}</span>
                        </div>
                        <span style={css(`font:400 19px/1.3 Newsreader${rg.headline ? "" : ";color:var(--muted)"}`)}>{rg.headline || (live.length ? "No headline yet." : "Nothing from the heartbeat yet.")}</span>
                      </button>
                      {rg.lines.length ? (
                        <div style={css("display:flex;flex-direction:column")}>
                          {items.slice(0, 3).map((it) => (
                            <ItemLine key={it.key} item={it} />
                          ))}
                        </div>
                      ) : null}
                      {rg.projects.length ? (
                        <div style={css("display:flex;gap:6px;flex-wrap:wrap;margin-top:auto")}>
                          {rg.projects.map((p) => (
                            <button
                              key={p.id}
                              type="button"
                              onClick={() => navigate(`/projects/${encodeURIComponent(p.id)}`)}
                              style={css("padding:5px 11px;border-radius:99px;border:1px solid var(--line2);background:var(--bg);font:500 12px Geist;color:var(--ink);cursor:pointer;text-align:left")}
                            >
                              {p.title}
                              <span style={css("font-weight:400;color:var(--muted)")}> · {p.status}</span>
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
              {sel ? (
                <div
                  role="region"
                  aria-label={`${sel.name}: every line`}
                  style={css("background:var(--surface);border-radius:22px;box-shadow:var(--shadow);padding:20px 22px;display:flex;flex-direction:column;gap:14px;border:2px solid var(--ink)")}
                >
                  <div style={css("display:flex;align-items:flex-start;gap:12px;flex-wrap:wrap")}>
                    <div style={css("display:flex;flex-direction:column;gap:4px;flex:1;min-width:240px")}>
                      <span style={css("font:500 10.5px 'Geist Mono';letter-spacing:.06em;color:var(--muted)")}>
                        REGION · {sel.name.toUpperCase()}
                        {sel.updated_at ? ` · UPDATED ${clock(sel.updated_at).toUpperCase()}` : ""}
                      </span>
                      <span style={css("font:400 24px/1.25 Newsreader")}>{sel.headline || "Nothing from the heartbeat yet."}</span>
                    </div>
                    <button type="button" onClick={() => navigate("/brain?tab=map")} style={css(PILL)}>
                      Open in Brain
                    </button>
                    <button type="button" onClick={() => pick(null)} style={css(PILL)}>
                      Close
                    </button>
                  </div>
                  <div style={css("display:flex;flex-direction:column")}>
                    {sel.lines.length ? (
                      itemsOf(sel.lines).map((it) => (
                        <ItemRow
                          key={it.key}
                          item={it}
                          undoing={undoing}
                          onUndo={(l) => {
                            setUndoing(l.id);
                            undo.mutate(l.id, { onSettled: () => setUndoing(null) });
                          }}
                        />
                      ))
                    ) : (
                      <span style={css("font:400 14px Geist;color:var(--muted);padding:12px 0;border-top:1px solid var(--line)")}>No line in this region yet.</span>
                    )}
                  </div>
                  {sel.projects.length ? (
                    <div style={css("display:flex;flex-direction:column;gap:8px")}>
                      <span style={css("font:500 12px Geist;color:var(--muted)")}>Projects in this region</span>
                      <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:10px")}>
                        {sel.projects.map((p) => (
                          <button
                            key={p.id}
                            type="button"
                            onClick={() => navigate(`/projects/${encodeURIComponent(p.id)}`)}
                            style={css("padding:14px 16px;border-radius:16px;border:1px solid var(--line);background:var(--bg);display:flex;flex-direction:column;gap:4px;text-align:left;color:var(--ink);cursor:pointer")}
                          >
                            <span style={css("font:500 14px Geist")}>{p.title}</span>
                            <span style={css("font:400 13px/1.45 Geist;color:var(--ink2)")}>{p.status}</span>
                            <span style={css("font:400 12px Geist;color:var(--muted)")}>{p.from.length ? `From ${p.from.join(" and ")}` : ""}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </>
          );
        }}
      </Loaded>
    </section>
  );
}

export function RecentBeats() {
  const beats = useBeats(6);
  const status = useHeartbeat();
  const [open, setOpen] = useState<Record<string, boolean>>({});
  return (
    <section aria-label="Recent beats" style={css("background:var(--surface);border-radius:22px;box-shadow:var(--shadow);padding:6px 22px 10px")}>
      <div style={css("display:flex;justify-content:space-between;padding:14px 0 8px;gap:10px;flex-wrap:wrap")}>
        <span style={css("font:500 13px Geist;color:var(--muted)")}>Recent beats</span>
        <span style={css("font:400 12px Geist;color:var(--muted)")}>{costLine(status.data)}</span>
      </div>
      <Loaded
        q={beats}
        empty={(rows) =>
          rows.length ? null : <div style={css("padding:13px 0 16px;border-top:1px solid var(--line);font:400 14px Geist;color:var(--muted)")}>No beats yet. Press Beat now, or wait for the next one.</div>
        }
      >
        {(rows) => (
          <>
            {rows.map((b, i) => {
              const isOpen = open[b.id] ?? i === 0;
              const lines = [...b.details, ...b.errors.map((e) => `Could not read ${e}`)];
              return (
                <div key={b.id} style={css("border-top:1px solid var(--line)")}>
                  <button
                    type="button"
                    aria-expanded={isOpen}
                    onClick={() => setOpen((o) => ({ ...o, [b.id]: !isOpen }))}
                    style={css("display:flex;gap:12px;align-items:baseline;padding:11px 0;border:0;background:transparent;width:100%;text-align:left;color:var(--ink);cursor:pointer;flex-wrap:wrap")}
                  >
                    <span style={css("font:500 12.5px 'Geist Mono';min-width:44px")}>{clock(b.started_at)}</span>
                    <span style={css(`font:400 13.5px Geist;flex:1;min-width:160px;color:${b.nothing_new ? "var(--muted)" : "var(--ink)"}`)}>{beatSummary(b)}</span>
                    <span style={css("font:400 11.5px 'Geist Mono';color:var(--muted)")}>{tokens(b.tokens)}</span>
                    <span aria-hidden="true" style={css("font:400 12px Geist;color:var(--muted)")}>
                      {isOpen ? "▾" : "▸"}
                    </span>
                  </button>
                  {isOpen && lines.length ? (
                    <div style={css("display:flex;flex-direction:column;gap:4px;padding:0 0 12px 56px")}>
                      {lines.map((t, k) => (
                        <span key={k} style={css("font:400 13px/1.45 Geist;color:var(--ink2)")}>
                          {t}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </>
        )}
      </Loaded>
    </section>
  );
}
