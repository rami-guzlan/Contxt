// Activity (v4 slice 14-isActivity): every question from every app and what it got (each with
// its evidence receipt), what that cost and how well it carried, every change with its undo
// point, and the tasks being handed between you and your AIs. Only real numbers: where the
// server has nothing, the screen says so.

import { type FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router";

import {
  useAiRequests,
  useBrainActivity,
  useBrainCheckpoints,
  useHandOff,
  useHandoffTask,
  useHandoffs,
  useReport,
  useWeekly,
} from "../../api/hooks";
import type { AiRequest, BrainCheckpoint, TaskItem } from "../../api/types";
import { SessionSearch } from "../components/BrainV4";
import { ReceiptView } from "../components/Receipt";
import { css } from "../css";
import { useRecentRequests, type UndoRefusal, undoRefusal, useUndoPoint } from "../hooks/activity";
import { Btn, Empty, Failure, Loaded, Loading, S, plural, when } from "../ui";

type Tab = "requests" | "report" | "changes" | "tasks";
const TABS: [Tab, string][] = [
  ["requests", "Requests"],
  ["report", "Cost and quality"],
  ["changes", "Changes"],
  ["tasks", "Tasks and handoffs"],
];

const TS = (on: boolean) =>
  `padding:7px 14px;border-radius:99px;border:0;white-space:nowrap;font:${on ? 500 : 400} 13px Geist;background:${on ? "var(--ink)" : "transparent"};color:${on ? "var(--bg)" : "var(--ink2)"}`;

const PILL = "padding:4px 10px;border-radius:99px;background:var(--soft);color:var(--ink2);font:500 12px Geist";
const HUES = [265, 150, 35, 80, 210, 320, 120, 10];

function hue(label: string): number {
  let h = 0;
  for (const ch of label) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return HUES[h % HUES.length] ?? 265;
}

const WEEK_MS = 7 * 24 * 3600 * 1000;

function inLastWeek(iso: string): boolean {
  const t = new Date(iso).getTime();
  return !Number.isNaN(t) && Date.now() - t <= WEEK_MS;
}

function dayLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Earlier";
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });
}

function timeOf(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function abbr(app: string): string {
  const words = (app || "?").split(/\s+/).filter(Boolean);
  return (words.length > 1 ? words.slice(0, 2).map((w) => w[0]) : [app.slice(0, 2)]).join("").toUpperCase();
}

function groups(r: AiRequest): { l: string; n: number; tokens: number }[] {
  const out = new Map<string, { l: string; n: number; tokens: number }>();
  for (const p of r.got) {
    const l = p.topic_label || p.topic || p.kind;
    const g = out.get(l) ?? { l, n: 0, tokens: 0 };
    g.n += 1;
    g.tokens += p.tokens || 0;
    out.set(l, g);
  }
  return [...out.values()];
}

function words(action: string): string {
  const t = action.replace(/[_-]+/g, " ").trim();
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : "Changed";
}

export function ActivityPage() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab");
  const tab: Tab = TABS.some(([id]) => id === raw) ? (raw as Tab) : "requests";
  const setTab = (id: Tab) =>
    setParams(
      (p) => {
        p.set("tab", id);
        return p;
      },
      { replace: true },
    );
  return (
    <div className="gn-page" style={css("max-width:1120px;margin:0 auto;padding:56px 64px 96px;display:flex;flex-direction:column;gap:30px;box-sizing:border-box")}>
      <div style={css("display:flex;justify-content:space-between;align-items:flex-end;gap:24px;flex-wrap:wrap")}>
        <div style={css("display:flex;flex-direction:column;gap:8px")}>
          <h1 style={css("margin:0;font:400 44px/1.1 Newsreader;letter-spacing:-.02em")}>Activity</h1>
          <span style={css("font:400 17px Geist;color:var(--ink2)")}>Every question from every app, what it got, and every change, each with undo.</span>
        </div>
        <HeadStats />
      </div>
      <div role="tablist" aria-label="Activity" style={css("display:flex;gap:6px;flex-wrap:wrap")}>
        {TABS.map(([id, label]) => (
          <button key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => setTab(id)} style={css(TS(tab === id))}>
            {label}
          </button>
        ))}
      </div>
      {tab === "requests" ? <Requests /> : null}
      {tab === "report" ? <Report /> : null}
      {tab === "changes" ? <Changes /> : null}
      {tab === "tasks" ? <Tasks /> : null}
    </div>
  );
}

/** Asks this week (the server's weekly count) and how many of this week's requests got
 * something from the Brain (from the latest requests). Hidden until both are known. */
function HeadStats() {
  const weekly = useWeekly(1);
  const recent = useRecentRequests();
  const week = weekly.data?.[weekly.data.length - 1];
  const mine = (recent.data?.requests ?? []).filter((r) => inLastWeek(r.at));
  const answered = mine.length ? Math.round((mine.filter((r) => !r.nothing).length / mine.length) * 100) : null;
  if (!week && answered === null) return null;
  return (
    <div style={css("display:flex;gap:28px")}>
      {week ? (
        <div style={css("display:flex;flex-direction:column;align-items:flex-end")}>
          <span style={css("font:400 32px Newsreader")}>{week.packets.toLocaleString()}</span>
          <span style={css("font:400 13px Geist;color:var(--muted)")}>asks this week</span>
        </div>
      ) : null}
      {answered !== null ? (
        <div style={css("display:flex;flex-direction:column;align-items:flex-end")}>
          <span style={css("font:400 32px Newsreader")}>{answered}%</span>
          <span style={css("font:400 13px Geist;color:var(--muted)")}>got something from your Brain</span>
        </div>
      ) : null}
    </div>
  );
}

// ------------------------------------------------------------------ Requests

function Requests() {
  const [params, setParams] = useSearchParams();
  const app = params.get("app") ?? "";
  const [limit, setLimit] = useState(50);
  const [seenApps, setSeenApps] = useState<string[]>([]);
  const q = useAiRequests({ limit, app: app || undefined });
  const [picked, setPicked] = useState<string | null>(null);
  const apps = [...new Set([...seenApps, ...(q.data?.apps ?? []), ...(app ? [app] : [])])];
  if (q.data && q.data.apps.some((a) => !seenApps.includes(a))) setSeenApps(apps);
  const setApp = (a: string) => {
    setPicked(null);
    setParams(
      (p) => {
        if (a) p.set("app", a);
        else p.delete("app");
        return p;
      },
      { replace: true },
    );
  };
  return (
    <div style={css("display:flex;flex-direction:column;gap:18px")}>
      {apps.length ? (
        <div role="group" aria-label="Filter by app" style={css("display:flex;gap:6px;flex-wrap:wrap")}>
          <button type="button" aria-pressed={!app} onClick={() => setApp("")} style={css(TS(!app))}>
            All apps
          </button>
          {apps.map((a) => (
            <button key={a} type="button" aria-pressed={app === a} onClick={() => setApp(a)} style={css(TS(app === a))}>
              {a}
            </button>
          ))}
        </div>
      ) : null}
      <SessionSearch />
      <Loaded
        q={q}
        empty={(d) =>
          d.requests.length ? null : (
            <Empty title={app ? `No requests from ${app} yet` : "No requests yet"}>
              When an AI app asks your Brain for context, each request shows here with what it got and its receipt. Connect an app in Agents.
            </Empty>
          )
        }
      >
        {(d) => {
          const sel = d.requests.find((r) => r.id === picked) ?? d.requests[0];
          const days: { day: string; items: AiRequest[] }[] = [];
          for (const r of d.requests) {
            const day = dayLabel(r.at);
            const last = days[days.length - 1];
            if (last && last.day === day) last.items.push(r);
            else days.push({ day, items: [r] });
          }
          return (
            <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));gap:32px;align-items:start")}>
              <div style={css("display:flex;flex-direction:column;gap:22px")}>
                {days.map((g) => (
                  <div key={g.day} style={css("display:flex;flex-direction:column;gap:10px")}>
                    <span style={css("font:500 13px Geist;color:var(--muted)")}>{g.day}</span>
                    <div style={css("background:var(--surface);border-radius:20px;padding:4px 8px;box-shadow:var(--shadow)")}>
                      {g.items.map((r) => (
                        <RequestRow key={r.id} r={r} on={r.id === sel?.id} onClick={() => setPicked(r.id)} />
                      ))}
                    </div>
                  </div>
                ))}
                {d.requests.length >= limit ? (
                  <Btn kind="ghostSm" onClick={() => setLimit((n) => n + 50)} disabled={q.isFetching}>
                    {q.isFetching ? "Loading more…" : "Show older requests"}
                  </Btn>
                ) : null}
              </div>
              {sel ? <RequestPanel key={sel.id} r={sel} /> : null}
            </div>
          );
        }}
      </Loaded>
    </div>
  );
}

function RequestRow({ r, on, onClick }: { r: AiRequest; on: boolean; onClick: () => void }) {
  const chips = groups(r);
  const sub = r.nothing ? "Nothing on this · teach it" : r.saved.length ? `Saved ${plural(r.saved.length, "proposal")}` : "";
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={on}
      style={css(
        `display:flex;align-items:center;gap:16px;padding:14px 16px;border:0;border-radius:14px;width:100%;text-align:left;color:var(--ink);background:${on ? "var(--soft)" : "transparent"}`,
      )}
    >
      <span
        aria-hidden="true"
        style={css(
          `width:36px;height:36px;border-radius:12px;flex:none;display:flex;align-items:center;justify-content:center;font:500 11px Geist;background:${r.nothing ? "transparent" : "var(--soft)"};color:var(--ink2);${r.nothing ? "border:1px dashed var(--line2);box-sizing:border-box" : ""}`,
        )}
      >
        {abbr(r.app)}
      </span>
      <div style={css("flex:1;display:flex;flex-direction:column;gap:8px;min-width:0")}>
        <span style={css("font:400 15px Geist;overflow-wrap:anywhere")}>“{r.request}”</span>
        {chips.length ? (
          <div style={css("display:flex;gap:6px;flex-wrap:wrap")}>
            {chips.map((c) => (
              <span key={c.l} style={css(PILL)}>
                {c.l}
                {c.n > 1 ? ` · ${c.n}` : ""}
              </span>
            ))}
          </div>
        ) : null}
        {sub ? <span style={css(`font:400 13px Geist;color:${r.nothing ? "oklch(0.58 0.12 35)" : "var(--muted)"}`)}>{sub}</span> : null}
      </div>
      <span style={css("font:400 13px Geist;color:var(--muted);white-space:nowrap")}>
        <span style={css("position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)")}>{r.app}, </span>
        {timeOf(r.at)}
      </span>
    </button>
  );
}

function RequestPanel({ r }: { r: AiRequest }) {
  const chips = groups(r);
  return (
    <div style={css("position:sticky;top:24px;background:var(--surface);border-radius:22px;padding:26px;box-shadow:var(--shadow);display:flex;flex-direction:column;gap:18px")}>
      <span style={css("font:500 12px 'Geist Mono';color:var(--muted);letter-spacing:.04em")}>
        {r.app.toUpperCase()} · {when(r.at)}
      </span>
      <span style={css("font:400 22px/1.35 Newsreader;overflow-wrap:anywhere")}>“{r.request}”</span>
      {r.nothing ? (
        <>
          <span style={css("font:400 14px/1.5 Geist;color:var(--ink2)")}>Nothing in your Brain matched, so the app answered without it.</span>
          <Link to="/brain?tab=questions" style={css(S.primarySm + ";align-self:flex-start;text-decoration:none")}>
            Teach it the answer
          </Link>
        </>
      ) : (
        <>
          <div style={css("display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap")}>
            <span style={css("font:400 26px Newsreader")}>{plural(r.got.length, "piece")} sent</span>
            <span style={css("font:400 13px Geist;color:var(--muted)")}>{r.tokens.toLocaleString()} tokens</span>
          </div>
          {chips.length ? (
            <div aria-hidden="true" style={css("display:flex;height:30px;gap:3px;border-radius:10px;overflow:hidden")}>
              {chips.map((c) => (
                <span key={c.l} style={css(`flex:${Math.max(1, c.tokens || c.n)};background:oklch(0.74 0.12 ${hue(c.l)})`)} />
              ))}
            </div>
          ) : null}
          <div style={css("display:flex;flex-direction:column")}>
            {r.got.map((p, i) => (
              <div key={`${p.id}-${i}`} style={css("display:flex;gap:12px;align-items:center;padding:11px 0;border-bottom:1px solid var(--line)")}>
                <span aria-hidden="true" style={css(`width:9px;height:9px;border-radius:50%;flex:none;background:oklch(0.74 0.12 ${hue(p.topic_label || p.topic || p.kind)})`)} />
                <span style={css("font:400 14px Geist;flex:1;min-width:0;overflow-wrap:anywhere")}>{p.title || p.id}</span>
                <span style={css("font:400 13px Geist;color:var(--muted);text-align:right")}>{p.why || `${p.tokens} tok`}</span>
              </div>
            ))}
          </div>
          <span style={css("font:400 13px Geist;color:var(--muted)")}>
            {r.share !== null && r.share !== undefined
              ? `${Math.max(r.share > 0 ? 1 : 0, Math.round(r.share * 100))}% of your Brain went out. Only what this request is about goes out.`
              : "Only what this request is about goes out."}
            {r.kernel ? " It got the startup context too." : ""}
          </span>
        </>
      )}
      {r.saved.length ? (
        <div style={css("display:flex;flex-direction:column;gap:6px")}>
          <span style={css("font:500 13px Geist")}>It saved</span>
          {r.saved.map((s) => (
            <span key={s.id} style={css("font:400 13px Geist;color:var(--ink2)")}>
              {s.title || s.id} · {s.status.replace(/_/g, " ")}
            </span>
          ))}
        </div>
      ) : null}
      {r.old_engine ? (
        <span style={css("font:400 13px/1.5 Geist;color:var(--ink2)")}>{r.app} runs older engine code: restart it to pick up the new version.</span>
      ) : null}
      <ReceiptView id={r.id} />
    </div>
  );
}

// ------------------------------------------------------------------ Cost and quality

function Stat({ n, l }: { n: string; l: string }) {
  return (
    <div style={css("padding:18px;border-radius:18px;background:var(--soft);display:flex;flex-direction:column;gap:2px")}>
      <span style={css("font:400 30px Newsreader")}>{n}</span>
      <span style={css("font:400 13px Geist;color:var(--ink2)")}>{l}</span>
    </div>
  );
}

function pct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

function Report() {
  const report = useReport(7, false);
  const recent = useRecentRequests();
  return (
    <Loaded q={report}>
      {(rep) => {
        const days = rep.spend?.days ?? [];
        const sent = days.reduce((a, d) => a + (d.brief_tokens || 0), 0);
        const packets = days.reduce((a, d) => a + (d.packets || 0), 0);
        const week = (recent.data?.requests ?? []).filter((r) => inLastWeek(r.at));
        const shares = week.map((r) => r.share).filter((s): s is number => typeof s === "number" && s > 0);
        const share = shares.length ? shares.reduce((a, s) => a + s, 0) / shares.length : null;
        const max = Math.max(0, ...days.map((d) => d.brief_tokens || 0));
        const byApp = new Map<string, number>();
        for (const r of week) byApp.set(r.app, (byApp.get(r.app) ?? 0) + (r.tokens || 0));
        const apps = [...byApp.entries()].sort((a, b) => b[1] - a[1]);
        const top = apps[0]?.[1] ?? 0;
        const quality = rep.eval?.all;
        return (
          <div style={css("display:flex;flex-direction:column;gap:24px")}>
            <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px")}>
              <Stat n={sent.toLocaleString()} l={`tokens sent in the last ${plural(rep.days, "day")}`} />
              <Stat n={packets ? Math.round(sent / packets).toLocaleString() : "None yet"} l="per request, on average" />
              <Stat n={share ? `1 in ${Math.max(1, Math.round(1 / share))}` : "Not known yet"} l="of your Brain, per request" />
              <Stat
                n={rep.eval_set.cases ? `${rep.eval_set.labeled} / ${rep.eval_set.cases}` : "None yet"}
                l="requests you labeled for your private eval"
              />
            </div>
            <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:20px")}>
              <div style={css("background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:24px;display:flex;flex-direction:column;gap:16px")}>
                <span style={css("font:500 15px Geist")}>Tokens by day</span>
                {days.length && max > 0 ? (
                  <div role="img" aria-label={days.map((d) => `${d.day}: ${(d.brief_tokens || 0).toLocaleString()} tokens`).join(", ")} style={css("display:flex;align-items:flex-end;gap:10px;height:150px")}>
                    {days.map((d) => (
                      <div key={d.day} style={css("flex:1;display:flex;flex-direction:column;align-items:center;gap:6px;justify-content:flex-end;height:100%")}>
                        <span
                          title={`${(d.brief_tokens || 0).toLocaleString()} tokens`}
                          style={css(
                            `width:100%;height:${Math.max(2, ((d.brief_tokens || 0) / max) * 120)}px;border-radius:6px;background:${d.brief_tokens === max ? "oklch(0.74 0.12 265)" : "var(--gray)"}`,
                          )}
                        />
                        <span style={css("font:400 11px Geist;color:var(--muted)")}>
                          {new Date(`${d.day}T12:00:00`).toLocaleDateString(undefined, { weekday: "narrow" })}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <span style={css(S.muted)}>No context was sent in these days.</span>
                )}
                {rep.per_day_usd ? (
                  <span style={css("font:400 13px/1.5 Geist;color:var(--muted)")}>
                    About ${rep.per_day_usd.toFixed(2)} a day, estimated{rep.spend?.model ? ` at ${rep.spend.model} prices` : ""}.
                  </span>
                ) : null}
              </div>
              <div style={css("background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:24px;display:flex;flex-direction:column;gap:14px")}>
                <span style={css("font:500 15px Geist")}>By app</span>
                {recent.isLoading ? <Loading /> : null}
                {recent.error ? <Failure error={recent.error} retry={() => void recent.refetch()} /> : null}
                {recent.data && !apps.length ? <span style={css(S.muted)}>No app asked in the last 7 days.</span> : null}
                {apps.map(([l, n]) => (
                  <div key={l} style={css("display:flex;flex-direction:column;gap:6px")}>
                    <div style={css("display:flex;justify-content:space-between;font:400 14px Geist")}>
                      <span>{l}</span>
                      <span style={css("color:var(--muted)")}>{n.toLocaleString()}</span>
                    </div>
                    <div style={css(`height:8px;border-radius:99px;width:${top ? (n / top) * 100 : 0}%;background:oklch(0.74 0.12 ${hue(l)})`)} />
                  </div>
                ))}
                {apps.length ? (
                  <span style={css("font:400 13px/1.5 Geist;color:var(--muted);padding-top:6px")}>
                    Tokens from the latest {plural(week.length, "request")} in the last 7 days.
                  </span>
                ) : null}
              </div>
            </div>
            <div style={css("background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:24px;display:flex;flex-direction:column;gap:10px")}>
              <span style={css("font:500 15px Geist")}>How well briefs carry what a task needs</span>
              {quality && quality.cases ? (
                <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px")}>
                  <Stat n={pct(quality.must_recall)} l="of what a task needed was sent" />
                  <Stat n={pct(quality.precision)} l="of what was sent was useful" />
                  <Stat n={pct(quality.noise_share)} l="was noise" />
                  <Stat n={plural(quality.cases, "request")} l="measured, from your labels" />
                </div>
              ) : (
                <span style={css("font:400 14px/1.5 Geist;color:var(--ink2)")}>
                  Not measured yet. Label a few requests (which notes they needed, which helped) and this shows how well briefs carry what a task needs.
                </span>
              )}
            </div>
          </div>
        );
      }}
    </Loaded>
  );
}

// ------------------------------------------------------------------ Changes and undo points

function Changes() {
  const [sub, setSub] = useState<"events" | "undo">("events");
  return (
    <div style={css("display:flex;flex-direction:column;gap:18px")}>
      <div role="tablist" aria-label="Changes" style={css("display:flex;gap:6px;flex-wrap:wrap")}>
        {(
          [
            ["events", "Everything that happened"],
            ["undo", "Undo points"],
          ] as const
        ).map(([id, label]) => (
          <button key={id} type="button" role="tab" aria-selected={sub === id} onClick={() => setSub(id)} style={css(TS(sub === id))}>
            {label}
          </button>
        ))}
      </div>
      {sub === "events" ? <Events /> : <UndoPoints />}
    </div>
  );
}

function Events() {
  const q = useBrainActivity({ limit: 100 });
  return (
    <Loaded q={q} empty={(d) => (d.length ? null : <Empty title="Nothing has changed yet">Changes to your Brain show here as they happen.</Empty>)}>
      {(events) => (
        <div style={css("display:flex;flex-direction:column")}>
          {events.map((e, i) => (
            <div key={`${e.at}-${i}`} style={css(S.row)}>
              <span aria-hidden="true" style={css("width:9px;height:9px;border-radius:50%;flex:none;background:var(--gray)")} />
              <div style={css("flex:1;display:flex;flex-direction:column;gap:2px;min-width:0")}>
                <span style={css("font:400 15px Geist;overflow-wrap:anywhere")}>
                  {words(e.action)}
                  {e.title ? `: ${e.title}` : ""}
                </span>
                {e.by || e.reason ? (
                  <span style={css("font:400 13px Geist;color:var(--muted)")}>{[e.by, e.reason].filter(Boolean).join(" · ")}</span>
                ) : null}
              </div>
              <span style={css("font:400 13px Geist;color:var(--muted);white-space:nowrap")}>{when(e.at)}</span>
            </div>
          ))}
        </div>
      )}
    </Loaded>
  );
}

function UndoPoints() {
  const q = useBrainCheckpoints();
  const undo = useUndoPoint();
  const [refused, setRefused] = useState<{ id: string; r: UndoRefusal } | null>(null);
  const [done, setDone] = useState("");
  const [working, setWorking] = useState<string | null>(null);
  const run = (point: BrainCheckpoint, together = false) => {
    setDone("");
    setWorking(point.id);
    undo.mutate(
      { id: point.id, together },
      {
        onSuccess: () => {
          setRefused(null);
          setDone(`Undid “${point.label}”${together ? " and the changes after it" : ""}. That's an undo point too.`);
        },
        onError: (error) => {
          const r = undoRefusal(error);
          setRefused(r ? { id: point.id, r } : null);
        },
        onSettled: () => setWorking(null),
      },
    );
  };
  const otherError = undo.error && !undoRefusal(undo.error) ? undo.error : null;
  return (
    <div style={css("position:relative;display:flex;flex-direction:column;min-height:120px")}>
      <span style={css("font:400 14px/1.5 Geist;color:var(--ink2);padding-bottom:10px")}>
        Every change to your Brain makes an undo point in its git history. Undoing makes one too.
      </span>
      {done ? (
        <span role="status" style={css("padding:10px 14px;border-radius:14px;background:oklch(0.62 0.14 150 / .14);font:400 14px Geist;margin-bottom:10px")}>
          {done}
        </span>
      ) : null}
      {otherError ? <Failure error={otherError} /> : null}
      <Loaded q={q} empty={(d) => (d.length ? null : <Empty title="No undo points yet">Each time you keep, edit or archive something, an undo point shows here.</Empty>)}>
        {(points) => (
          <>
            {points.map((u) => (
              <div key={u.id} style={css("display:flex;flex-direction:column;border-top:1px solid var(--line)")}>
                <div style={css("display:flex;align-items:center;gap:14px;padding:13px 0;flex-wrap:wrap")}>
                  <div style={css("flex:1;display:flex;flex-direction:column;gap:2px;min-width:200px")}>
                    <span style={css("font:400 15px Geist")}>{u.label || u.id}</span>
                    {u.blocked?.length && !u.undone_by ? (
                      <span style={css("font:400 13px Geist;color:var(--muted)")}>
                        Changed since: {u.blocked.slice(0, 3).map((b) => b.what).join(", ")}
                        {u.blocked.length > 3 ? ` and ${u.blocked.length - 3} more` : ""}
                      </span>
                    ) : null}
                  </div>
                  <span style={css("font:400 13px Geist;color:var(--muted);width:110px")}>{when(u.at)}</span>
                  {u.undone_by ? (
                    <span style={css("font:400 13px Geist;color:var(--faint)")}>Undone already</span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => run(u)}
                      disabled={undo.isPending}
                      aria-label={`${u.kind === "undo" ? "Redo" : "Undo"} ${u.label || u.id}`}
                      style={css("padding:7px 14px;border-radius:99px;background:var(--soft);border:0;font:500 13px Geist;color:var(--ink)")}
                    >
                      {working === u.id ? "Undoing…" : u.kind === "undo" ? "Redo" : "Undo"}
                    </button>
                  )}
                </div>
                {refused?.id === u.id ? (
                  <Refused
                    r={refused.r}
                    pending={undo.isPending}
                    onTogether={() => run(u, true)}
                    onLeave={() => {
                      setRefused(null);
                      undo.reset();
                    }}
                  />
                ) : null}
              </div>
            ))}
          </>
        )}
      </Loaded>
    </div>
  );
}

function Refused({ r, pending, onTogether, onLeave }: { r: UndoRefusal; pending: boolean; onTogether: () => void; onLeave: () => void }) {
  return (
    <div role="alert" style={css("margin:0 0 14px;padding:14px 16px;border-radius:16px;background:oklch(0.78 0.11 70 / .2);display:flex;flex-direction:column;gap:8px;align-items:flex-start")}>
      <span style={css("font:400 14px/1.5 Geist")}>{r.message}</span>
      {r.dependents.length ? (
        <>
          <span style={css("font:500 13px Geist")}>Undoing them together also undoes</span>
          <ul style={css("margin:0;padding-left:18px;display:flex;flex-direction:column;gap:2px;font:400 13px/1.5 Geist;color:var(--ink2)")}>
            {r.dependents.map((d) => (
              <li key={d.id}>
                {d.label}
                {d.at ? ` · ${when(d.at)}` : ""}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      <div style={css("display:flex;gap:8px;flex-wrap:wrap")}>
        {r.dependents.length ? (
          <Btn kind="primarySm" onClick={onTogether} disabled={pending}>
            {pending ? "Undoing…" : "Undo them together"}
          </Btn>
        ) : null}
        <Btn kind="ghostSm" onClick={onLeave} disabled={pending}>
          Leave it
        </Btn>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Tasks and handoffs

function Tasks() {
  const q = useHandoffs();
  const [sel, setSel] = useState<string | null>(null);
  return (
    <Loaded
      q={q}
      empty={(d) =>
        d.count || d.done_this_week.length ? null : (
          <Empty title="No tasks yet">Tasks show here when you or an AI opens one, or hands work on. Open one from a project's Tasks.</Empty>
        )
      }
    >
      {(d) => {
        const lanes: [string, TaskItem[]][] = [
          ["To do", d.lanes.open ?? []],
          ["Doing", [...(d.lanes.working ?? []), ...(d.lanes.handed_off ?? [])]],
          ["Waiting", [...(d.lanes.waiting_for_you ?? []), ...(d.lanes.blocked ?? [])]],
          ["Done", d.done_this_week ?? []],
        ];
        const all = lanes.flatMap(([l, items]) => items.map((x) => ({ l, x })));
        const chosen = all.find((a) => a.x.id === sel) ?? all[0];
        return (
          <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:24px;align-items:start")}>
            <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;grid-column:1 / -1")}>
              {lanes.map(([l, items]) => (
                <div key={l} role="group" aria-label={l} style={css("padding:14px;border-radius:18px;background:var(--soft);display:flex;flex-direction:column;gap:10px;min-height:280px")}>
                  <span style={css("font:500 13px Geist;color:var(--muted)")}>
                    {l} · {items.length}
                  </span>
                  {items.map((x) => (
                    <button
                      key={x.id}
                      type="button"
                      aria-pressed={chosen?.x.id === x.id}
                      onClick={() => setSel(x.id)}
                      style={css(
                        `padding:14px;border-radius:14px;border:0;text-align:left;display:flex;flex-direction:column;gap:6px;color:var(--ink);width:100%;cursor:pointer;background:var(--surface);${chosen?.x.id === x.id ? "outline:2px solid var(--ink)" : "box-shadow:var(--shadow)"}`,
                      )}
                    >
                      <span style={css("font:400 14px/1.35 Geist")}>{x.task}</span>
                      <span style={css("font:400 12px Geist;color:var(--muted)")}>
                        {x.owner_label} · {x.project ?? "No project"} · {x.status_words}
                      </span>
                    </button>
                  ))}
                </div>
              ))}
            </div>
            {chosen ? <TaskPanel key={chosen.x.id} item={chosen.x} lane={chosen.l} /> : null}
          </div>
        );
      }}
    </Loaded>
  );
}

function TaskPanel({ item, lane }: { item: TaskItem; lane: string }) {
  const detail = useHandoffTask(item.id);
  const handOff = useHandOff();
  const [form, setForm] = useState<"" | "handoff" | "finish">("");
  const [to, setTo] = useState("");
  const [doneWhen, setDoneWhen] = useState(item.card?.done_when ?? "");
  const [next, setNext] = useState(item.card?.next_step ?? "");
  const [evidence, setEvidence] = useState("");
  const [said, setSaid] = useState("");
  const closed = item.status === "done" || item.status === "dropped";
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const body =
      form === "handoff"
        ? { task: item.id, to: to.trim(), done_when: doneWhen.trim(), next_step: next.trim() }
        : { task: item.id, status: "done", evidence: [evidence.trim()] };
    handOff.mutate(body, {
      onSuccess: () => {
        setSaid(form === "handoff" ? `Passed to ${to.trim()}.` : "Marked done.");
        setForm("");
      },
    });
  };
  const log = detail.data?.log ?? [];
  return (
    <div style={css("position:sticky;top:24px;background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:24px;display:flex;flex-direction:column;gap:14px")}>
      <span style={css("font:500 11px 'Geist Mono';color:var(--muted);letter-spacing:.04em")}>
        {lane.toUpperCase()} · {(item.project ?? "No project").toUpperCase()}
      </span>
      <span style={css("font:400 22px/1.3 Newsreader")}>{item.task}</span>
      <span style={css("font:400 14px Geist;color:var(--ink2)")}>
        With {item.owner_label} · {item.status_words}
        {item.due ? ` · due ${item.due}` : ""}
      </span>
      {item.card?.next_step ? <span style={css("font:400 13px/1.5 Geist;color:var(--ink2)")}>Next step: {item.card.next_step}</span> : null}
      <div style={css("display:flex;flex-direction:column")}>
        {detail.isLoading ? <Loading what="Reading its history" /> : null}
        {detail.error ? <Failure error={detail.error} retry={() => void detail.refetch()} /> : null}
        {detail.data && !log.length ? <span style={css(S.small)}>No history yet.</span> : null}
        {log.map((g, i) => (
          <div key={`${g.at}-${i}`} style={css("display:flex;gap:12px;padding:10px 0;border-top:1px solid var(--line);font:400 13px Geist")}>
            <span style={css("flex:1;overflow-wrap:anywhere")}>
              {words(g.kind)}
              {g.column ? `: ${g.column}` : ""}
              {g.value !== undefined && g.value !== null && g.value !== "" ? ` ${String(g.value)}` : ""}
              {g.by ? ` · ${g.by}` : ""}
            </span>
            <span style={css("color:var(--muted);white-space:nowrap")}>{when(g.at)}</span>
          </div>
        ))}
      </div>
      {said ? (
        <span role="status" style={css("font:400 13px/1.5 Geist;color:var(--ink2)")}>
          {said}
        </span>
      ) : null}
      {!closed ? (
        <div style={css("display:flex;gap:8px;flex-wrap:wrap")}>
          <Btn kind="primarySm" onClick={() => setForm(form === "handoff" ? "" : "handoff")}>
            Hand off
          </Btn>
          <Btn kind="ghostSm" onClick={() => setForm(form === "finish" ? "" : "finish")}>
            Finish
          </Btn>
        </div>
      ) : null}
      {form ? (
        <form onSubmit={submit} style={css("display:flex;flex-direction:column;gap:8px;padding:12px 14px;border-radius:14px;background:var(--soft)")}>
          {form === "handoff" ? (
            <>
              <Field label="Pass it to" value={to} onChange={setTo} placeholder="you, or an app such as Claude Code" />
              <Field label="Done when" value={doneWhen} onChange={setDoneWhen} placeholder="What finished looks like" />
              <Field label="Next step" value={next} onChange={setNext} placeholder="Where the next owner starts" />
            </>
          ) : (
            <Field label="Evidence" value={evidence} onChange={setEvidence} placeholder="An output's id, or a decided proposal's id" />
          )}
          <div style={css("display:flex;gap:8px")}>
            <Btn
              kind="primarySm"
              type="submit"
              disabled={handOff.isPending || (form === "handoff" ? !to.trim() || !doneWhen.trim() || !next.trim() : !evidence.trim())}
            >
              {handOff.isPending ? "Saving…" : form === "handoff" ? "Pass it on" : "Mark done"}
            </Btn>
            <Btn kind="ghostSm" onClick={() => setForm("")}>
              Cancel
            </Btn>
          </div>
          {handOff.error ? <Failure error={handOff.error} /> : null}
        </form>
      ) : null}
      <span style={css("font:400 12px/1.5 Geist;color:var(--muted)")}>Nothing reaches Done without evidence, and nothing changes owner without a card.</span>
    </div>
  );
}

function Field({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <label style={css("display:flex;flex-direction:column;gap:4px;font:500 12px Geist;color:var(--muted)")}>
      {label}
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} style={css(S.input + ";font:400 14px Geist;padding:8px 10px")} />
    </label>
  );
}
