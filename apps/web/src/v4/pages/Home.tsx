// Home, as v4 draws it: the quick start until it is done or put away (five steps, each true
// from what the app knows), then the day's Home (tell or ask, Today, Jump back in, your Brain),
// or, when the Brain's preset lets changes go in on their own, the auto-governed Home with
// what went in and an Undo for each.

import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";

import { useAiApps, useAiRequests, useBrainCatalog, useBrainCheckpoints, useBrainProjects, useNotes } from "../../api/hooks";
import type { BrainCheckpoint, BrainProject } from "../../api/types";
import { useTalk } from "../../components/Talk";
import { type Policy, useProposals, usePolicy, useSourceStatus, useUndo } from "../api";
import { css, cx } from "../css";
import {
  AUTO_LABEL,
  autoApplied,
  changeTitle,
  changeVerb,
  lastDay,
  type QsId,
  receiptOpened,
  useQuickStartMemory,
  useTell,
} from "../hooks/home";
import { Btn, Empty, Failure, Later, Loaded, Loading, plural, S, when } from "../ui";

/** In Auto mode changes go in on their own, so Home shows what was applied instead of what waits. */
export function isAutoGoverned(policy: Pick<Policy, "mode"> | undefined): boolean {
  return policy?.mode === "auto";
}

export function HomePage() {
  const [params, setParams] = useSearchParams();
  const memory = useQuickStartMemory();
  const policy = usePolicy();
  const { reopen } = memory;

  // Help's "Quick start" opens it again (?quickstart=1), then the address goes back to Home.
  const asked = params.get("quickstart") === "1";
  useEffect(() => {
    if (!asked) return;
    reopen();
    setParams({}, { replace: true });
  }, [asked, reopen, setParams]);

  if (!memory.dismissed || asked) return <QuickStart memory={memory} />;
  if (policy.isLoading) return <Loading what="Opening your Home" />;
  return isAutoGoverned(policy.data) && policy.data ? <AutoHome policy={policy.data} /> : <DayHome />;
}

// ------------------------------------------------------------------ quick start

interface Step {
  id: QsId;
  t: string;
  time: string;
  what: string;
  why: string;
  cta: string;
  to: string;
}

const QS: Step[] = [
  {
    id: "app",
    t: "Connect your AI",
    time: "1 min",
    what: "Pick the AI app you already use: Claude Code, Codex, Cursor or Gemini. You’ll see whether it reaches your Brain, and what it last asked.",
    why: "Distill and Ask run on it. Gnomon never switches provider on its own.",
    cta: "Connect",
    to: "/settings?tab=apps",
  },
  {
    id: "capture",
    t: "Capture one source",
    time: "1 min",
    what: "Paste a few lines, drop in one file, or press Scan now on a folder.",
    why: "It stays private until you keep part of it. Saved isn’t searchable yet.",
    cta: "Open Capture",
    to: "/capture",
  },
  {
    id: "catchup",
    t: "Review what it found",
    time: "1 min",
    what: "Each suggestion shows its source, passage, speaker and where it would go. Keep, edit or skip.",
    why: "Keeping stores it. It doesn’t make it true.",
    cta: "Review",
    to: "/brain/cards",
  },
  { id: "ask", t: "Ask a question", time: "30 sec", what: "Ask about what you just kept.", why: "This is your first useful answer.", cta: "Ask", to: "/ask" },
  {
    id: "evidence",
    t: "Inspect the evidence",
    time: "30 sec",
    what: "Open the receipt under the answer: what was sent, what didn’t fit, and what’s unknown.",
    why: "You see exactly what your AI got, and what it didn’t.",
    cta: "Open Ask",
    to: "/ask",
  },
];

const HOW: [string, string, number, string?, string?, string?][] = [
  ["You bring things in", "Talk, meetings, files, or what your other AIs already know.", 35, "HOW CONTEXT FLOWS"],
  ["Your Brain keeps what matters", "Sorted into notes, projects and sheets you can read and change.", 80],
  ["Every AI reads the part it needs", "Claude, Cursor and others get only the notes that fit the request.", 210],
  ["You approve what it learns", "A minute a day in Catch up. Nothing changes without your yes.", 150],
  [
    "Better output, because you set the standard",
    "Your AI works only from what you’ve approved, plus your taste for what looks, feels and works good. So what it makes is right, and sounds like you, at work and at home.",
    60,
    "WHAT IT DOES FOR YOUR WORK",
    "See your taste",
    "/brain",
  ],
  [
    "Do the work in Projects",
    "Each project has its context and a workspace: boards, docs, skills and agents. Ask your AI to do the work right there, with the project’s packet.",
    320,
    "",
    "Open Projects",
    "/projects",
  ],
  ["Agents that work your way", "Agent profiles carry your taste, your sources and exactly the context they need. Skills do the steps.", 265, "", "See agent profiles", "/agents"],
];

const tint = (h: number) => `oklch(0.74 0.12 ${h} / .2)`;

/** The undo points a person made, not the ones changes made on their own. */
function byPerson(points: BrainCheckpoint[]) {
  return points.filter((p) => p.kind === "decisions" && !p.label.startsWith(AUTO_LABEL));
}

/** Where each step stands, from what the app knows. */
function useQuickStartState() {
  const apps = useAiApps();
  const notes = useNotes();
  const points = useBrainCheckpoints();
  const proposals = useProposals();
  const requests = useAiRequests({ limit: 1 });
  const queries = [apps, notes, points, proposals, requests];
  const loading = queries.some((q) => q.isLoading);
  const failed = queries.find((q) => q.error);
  const connected = (apps.data ?? []).filter((a) => a.connected).map((a) => a.label);
  const decided = byPerson(points.data ?? []).some((p) => p.decisions.some((d) => ["approved", "edited", "rejected"].includes(d.action)));
  const waiting = proposals.data?.length ?? 0;
  const captured = notes.data?.length ?? 0;
  const asked = (requests.data?.requests.length ?? 0) > 0;
  const opened = receiptOpened();
  const real: Record<QsId, boolean> = { app: connected.length > 0, capture: captured > 0, catchup: decided, ask: asked, evidence: opened };
  const now: Record<QsId, string> = {
    app: connected.length ? `Connected now: ${connected.join(", ")}.` : "No AI app reaches your Brain yet.",
    capture: captured ? `${plural(captured, "capture")} so far.` : "Nothing captured yet.",
    catchup: decided
      ? "You’ve decided on what it found."
      : waiting
        ? `${plural(waiting, "suggestion")} waiting for you now.`
        : "Nothing waits yet. Capture something first.",
    ask: asked ? "Your Brain has been asked before." : "No questions yet.",
    evidence: opened ? "You’ve opened a receipt on this computer." : "Not opened yet on this computer.",
  };
  return { loading, failed, real, now, retry: () => queries.forEach((q) => void q.refetch()) };
}

function QuickStart({ memory }: { memory: ReturnType<typeof useQuickStartMemory> }) {
  const navigate = useNavigate();
  const state = useQuickStartState();
  const done = (id: QsId) => Boolean(state.real[id] || memory.marked[id]);
  const count = QS.filter((q) => done(q.id)).length;
  const all = !state.loading && count === QS.length;
  const [open, setOpen] = useState<QsId | null | undefined>(undefined);
  const current = open !== undefined ? open : (QS.find((q) => !done(q.id))?.id ?? null);

  return (
    <div className="gn-page" style={css("max-width:1120px;margin:0 auto;padding:56px 64px 96px;display:flex;flex-direction:column;gap:40px;box-sizing:border-box")}>
      <div style={css("display:flex;flex-direction:column;gap:12px;max-width:700px")}>
        <span style={css("font:400 14px Geist;color:var(--muted)")}>Welcome to Gnomon</span>
        <h1 style={css("margin:0;font:400 48px/1.08 Newsreader;letter-spacing:-.02em")}>Let’s set up your Brain.</h1>
        <span style={css("font:400 18px/1.55 Geist;color:var(--ink2);text-wrap:pretty")}>
          Your Brain is one place that remembers who you are, how you work and what you’re working on. Every AI you use reads from it, so none of them start
          from zero. Five short steps, about four minutes. Goals, organizing, tuning and the tour are optional, any time.
        </span>
      </div>
      <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,380px),1fr));gap:28px;align-items:start")}>
        {all ? (
          <div style={css("background:var(--ink);color:var(--bg);border-radius:22px;padding:30px;display:flex;flex-direction:column;gap:12px")}>
            <span style={css("font:500 12px 'Geist Mono';letter-spacing:.06em;opacity:.7")}>ALL FIVE DONE</span>
            <span style={css("font:400 34px/1.15 Newsreader")}>You’re set up. Your AIs know you now.</span>
            <span style={css("font:400 15px/1.55 Geist;opacity:.8")}>From here, most days take a minute: a few yeses in Catch up, and the occasional capture.</span>
            <button
              type="button"
              onClick={memory.dismiss}
              style={css("align-self:flex-start;margin-top:6px;padding:10px 18px;border-radius:99px;background:var(--bg);color:var(--ink);border:0;font:500 14px Geist")}
            >
              Go to my Home
            </button>
          </div>
        ) : (
          <section aria-label="Quick start" style={css("background:var(--surface);border-radius:22px;box-shadow:var(--shadow);padding:6px 20px 8px;display:flex;flex-direction:column")}>
            <div style={css("display:flex;flex-direction:column;gap:10px;padding:18px 4px 16px")}>
              <div style={css("display:flex;justify-content:space-between;align-items:baseline")}>
                <span style={css("font:500 17px Geist")}>Quick start</span>
                <span style={css("font:400 13px Geist;color:var(--muted)")}>{state.loading ? "Checking…" : `${count} of ${QS.length} done`}</span>
              </div>
              <div
                role="progressbar"
                aria-label="Quick start progress"
                aria-valuemin={0}
                aria-valuemax={QS.length}
                aria-valuenow={count}
                style={css("height:6px;border-radius:99px;background:var(--line2)")}
              >
                <div style={css(`height:6px;border-radius:99px;width:${(count / QS.length) * 100}%;background:oklch(0.62 0.13 150);transition:width .4s`)} />
              </div>
            </div>
            {state.failed ? (
              <div style={css("padding:0 4px 14px")}>
                <Failure error={state.failed.error} retry={state.retry} />
              </div>
            ) : null}
            {QS.map((q, i) => {
              const isDone = done(q.id);
              const isOpen = current === q.id;
              return (
                <div key={q.id} style={css("border-top:1px solid var(--line)")}>
                  <button
                    type="button"
                    aria-expanded={isOpen}
                    onClick={() => setOpen(isOpen ? null : q.id)}
                    style={css("display:flex;align-items:center;gap:14px;padding:14px 4px;border:0;background:transparent;width:100%;text-align:left;color:var(--ink);cursor:pointer")}
                  >
                    <span
                      aria-hidden="true"
                      style={css(
                        `width:28px;height:28px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;font:500 12px Geist;box-sizing:border-box;${
                          isDone ? "background:oklch(0.62 0.13 150);color:#fff" : isOpen ? "background:var(--ink);color:var(--bg)" : "border:1.5px solid var(--line2);color:var(--muted)"
                        }`,
                      )}
                    >
                      {isDone ? "✓" : String(i + 1)}
                    </span>
                    <span style={css(`flex:1;font:${isOpen ? 500 : 400} 15px Geist;${isDone && !isOpen ? "color:var(--muted);text-decoration:line-through" : ""}`)}>
                      {q.t}
                      {isDone ? <span style={css("position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)")}> (done)</span> : null}
                    </span>
                    <span style={css("font:400 12px Geist;color:var(--muted)")}>{q.time}</span>
                  </button>
                  {isOpen ? (
                    <div style={css("display:flex;flex-direction:column;gap:12px;padding:0 4px 18px 46px")}>
                      <span style={css("font:400 15px/1.55 Geist;color:var(--ink);text-wrap:pretty")}>{q.what}</span>
                      <span style={css("font:400 13px Geist;color:var(--muted)")}>{state.loading ? "Checking where this stands…" : state.now[q.id]}</span>
                      <div style={css("display:flex;gap:10px;padding:12px 14px;border-radius:14px;background:var(--soft)")}>
                        <span style={css("font:500 12px Geist;color:var(--muted);padding-top:1px")}>Why</span>
                        <span style={css("font:400 13.5px/1.5 Geist;color:var(--ink2)")}>{q.why}</span>
                      </div>
                      <div style={css("display:flex;gap:12px;align-items:center;flex-wrap:wrap")}>
                        <Btn kind="primary" onClick={() => navigate(q.to)}>
                          {q.cta}
                        </Btn>
                        {!isDone ? (
                          <button
                            type="button"
                            onClick={() => {
                              memory.mark(q.id);
                              setOpen(undefined);
                            }}
                            style={css("border:0;background:transparent;font:400 13px Geist;color:var(--muted)")}
                          >
                            Mark as done
                          </button>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                </div>
              );
            })}
          </section>
        )}
        <div style={css("display:flex;flex-direction:column;gap:18px;padding:24px;border-radius:22px;border:1px solid var(--line)")}>
          <span style={css("font:500 17px Geist")}>How Gnomon works</span>
          {HOW.map(([t, d, h, sec, goL, to], i) => (
            <div key={t} style={css("display:flex;flex-direction:column;gap:18px")}>
              {sec ? <span style={css("font:500 10.5px 'Geist Mono';letter-spacing:.06em;color:var(--muted);padding-top:4px")}>{sec}</span> : null}
              <div style={css("display:flex;gap:14px;align-items:flex-start")}>
                <span
                  aria-hidden="true"
                  style={css(
                    `width:32px;height:32px;border-radius:10px;flex:none;display:flex;align-items:center;justify-content:center;font:500 13px Geist;background:${tint(h)};color:var(--ink)`,
                  )}
                >
                  {i + 1}
                </span>
                <div style={css("display:flex;flex-direction:column;gap:2px")}>
                  <span style={css("font:500 15px Geist")}>{t}</span>
                  <span style={css("font:400 13.5px/1.5 Geist;color:var(--ink2)")}>{d}</span>
                  {goL && to ? (
                    <button
                      type="button"
                      onClick={() => navigate(to)}
                      style={css("align-self:flex-start;border:0;background:transparent;padding:4px 0 0;font:500 12.5px Geist;color:var(--ink)")}
                    >
                      {goL} →
                    </button>
                  ) : null}
                </div>
              </div>
            </div>
          ))}
          <div style={css("display:flex;gap:8px;flex-wrap:wrap;align-items:center;padding-top:2px")}>
            <Btn kind="ghostSm" disabled title="The tour is a later phase.">
              Take the 1-minute tour
            </Btn>
            <Later />
          </div>
        </div>
      </div>
      <button type="button" onClick={memory.dismiss} style={css(S.link)}>
        I’ve done this before. Skip to my Home →
      </button>
    </div>
  );
}

// ------------------------------------------------------------------ the tell or ask box

function greeting(now = new Date()): string {
  const h = now.getHours();
  return h < 12 ? "Good morning." : h < 18 ? "Good afternoon." : "Good evening.";
}

function today(now = new Date()): string {
  return now.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
}

function TellAsk({ projects }: { projects: BrainProject[] }) {
  const navigate = useNavigate();
  const talk = useTalk();
  const tell = useTell();
  const [mode, setMode] = useState<"tell" | "ask">("tell");
  const [text, setText] = useState("");
  const ask = mode === "ask";
  const send = () => {
    const said = text.trim();
    if (!said || tell.isPending) return;
    if (ask) {
      navigate(`/ask?q=${encodeURIComponent(said)}`);
      return;
    }
    tell.mutate(said, { onSuccess: () => setText("") });
  };
  const suggestions = ask ? projects.slice(0, 3).map((p) => `Where does ${p.title} stand?`) : [];
  const live = talk?.state === "listening";
  const saved = tell.data;

  return (
    <div style={css("display:flex;flex-direction:column;gap:12px;margin-top:-16px")}>
      <div style={css("background:var(--surface);border-radius:24px;box-shadow:var(--shadow2);padding:18px 18px 12px;display:flex;flex-direction:column;gap:10px")}>
        <textarea
          aria-label={ask ? "Ask your Brain" : "Tell your Brain"}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          rows={2}
          placeholder={ask ? "Ask your Brain anything" : "Tell your Brain something to remember"}
          style={css("border:0;outline:none;resize:none;background:transparent;color:var(--ink);font:400 17px/1.5 Geist;padding:4px 6px")}
        />
        <div style={css("display:flex;align-items:center;gap:8px;flex-wrap:wrap")}>
          <div role="group" aria-label="Tell or ask" style={css("display:flex;gap:2px;padding:3px;border-radius:99px;background:var(--soft)")}>
            {(
              [
                ["tell", "Tell it"],
                ["ask", "Ask it"],
              ] as const
            ).map(([id, l]) => {
              const on = mode === id;
              return (
                <button
                  key={id}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setMode(id)}
                  style={css(
                    `padding:6px 12px;border-radius:99px;border:0;font:${on ? 500 : 400} 12.5px Geist;background:${on ? "var(--surface)" : "transparent"};color:${
                      on ? "var(--ink)" : "var(--ink2)"
                    };${on ? "box-shadow:var(--shadow)" : ""}`,
                  )}
                >
                  {l}
                </button>
              );
            })}
          </div>
          <span style={css("font:400 12px Geist;color:var(--muted);flex:1;min-width:140px")}>
            {ask ? "Answers come from your Brain, with sources" : "Goes to Capture. Your knowledge agent sorts it."}
          </span>
          <button
            type="button"
            aria-label={live ? "Stop talking" : "Talk"}
            aria-pressed={live}
            title={talk ? "Hold to talk, or tap to start and tap again to send." : "Talking isn’t available here."}
            disabled={!talk}
            onPointerDown={(e) => {
              if (!talk || e.button !== 0) return;
              e.preventDefault();
              talk.press();
            }}
            onPointerUp={() => talk?.release()}
            onKeyDown={(e) => {
              if (!talk || (e.key !== "Enter" && e.key !== " ")) return;
              e.preventDefault();
              if (!e.repeat) talk.press();
            }}
            onKeyUp={(e) => {
              if (!talk || (e.key !== "Enter" && e.key !== " ")) return;
              e.preventDefault();
              talk.release();
            }}
            style={css(
              `width:34px;height:34px;border-radius:50%;border:1px solid var(--line2);background:${live ? "oklch(0.64 0.17 28 / .2)" : "transparent"};display:flex;align-items:center;justify-content:center;padding:0`,
            )}
          >
            <span style={css("width:8px;height:14px;border-radius:5px;border:1.5px solid var(--ink2);box-sizing:border-box")} />
          </button>
          <button
            type="button"
            aria-label={ask ? "Ask" : "Save to Capture"}
            onClick={send}
            disabled={!text.trim() || tell.isPending}
            style={css("width:34px;height:34px;border-radius:50%;background:var(--ink);color:var(--bg);border:0;font:500 15px Geist")}
          >
            ↑
          </button>
        </div>
      </div>
      {tell.isPending ? <Loading what="Saving to Capture" /> : null}
      {tell.error ? <Failure error={tell.error} /> : null}
      {saved && !tell.isPending ? (
        <div role="status" style={css("display:flex;gap:10px;align-items:center;justify-content:center;flex-wrap:wrap;font:400 14px Geist;color:var(--ink2)")}>
          <span>Saved to Capture as “{saved.title || "Untitled"}”. It stays private until you keep part of it.</span>
          <button type="button" onClick={() => navigate(`/capture/${encodeURIComponent(saved.id)}`)} style={css("border:0;background:transparent;padding:0;font:500 14px Geist;color:var(--ink)")}>
            Open it →
          </button>
        </div>
      ) : null}
      {suggestions.length ? (
        <div style={css("display:flex;gap:8px;flex-wrap:wrap;justify-content:center")}>
          {suggestions.map((l) => (
            <button
              key={l}
              type="button"
              className="gn-hover"
              onClick={() => setText(l)}
              style={css("padding:7px 13px;border-radius:99px;border:1px solid var(--line);background:transparent;font:400 13px Geist;color:var(--ink2)")}
            >
              {l}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

// ------------------------------------------------------------------ your Brain, as a bar

const HUES = [35, 80, 150, 210, 265, 320];

interface AreaShare {
  key: string;
  label: string;
  hue: number;
  count: number;
}

function useBrainShape() {
  const catalog = useBrainCatalog();
  const shape = useMemo(() => {
    const data = catalog.data;
    if (!data) return null;
    const areas: AreaShare[] = data.areas.map((a, i) => ({
      key: a.key,
      label: a.label,
      hue: HUES[i % HUES.length] ?? 210,
      count: data.entries.filter((e) => e.area === a.key).length,
    }));
    const stale = data.entries.filter((e) => e.stale_reason).length;
    const line = `${plural(data.entries.length, "note")} in ${plural(data.areas.length, "area")}${stale ? ` · ${stale} need a look` : ""}`;
    return { areas, line, entries: data.entries.length };
  }, [catalog.data]);
  return { catalog, shape };
}

function AreaBar({ areas, height }: { areas: AreaShare[]; height: number }) {
  return (
    <div aria-hidden="true" style={css(`display:flex;height:${height}px;border-radius:99px;overflow:hidden;gap:3px;width:100%`)}>
      {areas
        .filter((a) => a.count > 0)
        .map((a) => (
          <span key={a.key} title={`${a.label}: ${a.count}`} style={css(`flex:${a.count};background:oklch(0.74 0.12 ${a.hue})`)} />
        ))}
    </div>
  );
}

// ------------------------------------------------------------------ the day's Home

const TO_DISTILL = new Set(["captured", "analysis_pending", "retrying", "awaiting_review"]);

function DayHome() {
  const navigate = useNavigate();
  const proposals = useProposals();
  const notes = useNotes();
  const ids = useMemo(() => (notes.data ?? []).slice(0, 50).map((n) => n.id), [notes.data]);
  const statuses = useSourceStatus(ids);
  const requests = useAiRequests({ limit: 50 });
  const projects = useBrainProjects();
  const { catalog, shape } = useBrainShape();
  const active = (projects.data ?? []).filter((p) => p.active);

  const pend = proposals.data?.length ?? 0;
  const mins = Math.max(1, Math.round(pend * 0.6));
  const line = proposals.isLoading
    ? "Looking at what waits for you…"
    : proposals.error
      ? "Couldn’t check what waits for you."
      : pend
        ? `${plural(pend, "thing")} your AIs learned ${pend === 1 ? "is" : "are"} waiting for you. About ${plural(mins, "minute")}.`
        : "You’re all caught up. Your Brain is in order.";

  const toDistill = Object.values(statuses.data ?? {}).filter((s) => TO_DISTILL.has(s.status));
  const byLabel = new Map<string, number>();
  for (const s of toDistill) byLabel.set(s.label, (byLabel.get(s.label) ?? 0) + 1);
  const capLine = [...byLabel.entries()].map(([l, n]) => `${n} ${l.toLowerCase()}`).join(" · ");
  const capLoading = notes.isLoading || (ids.length > 0 && statuses.isLoading);
  const capError = notes.error || statuses.error;

  const todayAsks = (requests.data?.requests ?? []).filter((r) => lastDay(r.at));
  const latest = requests.data?.requests[0];

  const cards = [
    {
      n: proposals.isLoading ? "…" : proposals.error ? "?" : String(pend),
      t: pend === 1 ? "thing to catch up on" : "things to catch up on",
      d: proposals.error ? "Couldn’t check right now" : pend ? `About ${mins} min` : "Nothing waits for you",
      cta: "Catch up",
      to: "/brain/cards",
      dark: true,
    },
    {
      n: capLoading ? "…" : capError ? "?" : String(toDistill.length),
      t: toDistill.length === 1 ? "capture to distill" : "captures to distill",
      d: capError ? "Couldn’t check right now" : capLine || ((notes.data?.length ?? 0) ? "Everything captured has been read" : "Nothing captured yet"),
      cta: "Open Capture",
      to: "/capture",
      dark: false,
    },
    {
      n: requests.isLoading ? "…" : requests.error ? "?" : String(todayAsks.length),
      t: todayAsks.length === 1 ? "AI request today" : "AI requests today",
      d: requests.error ? "Couldn’t check right now" : latest ? `Latest from ${latest.app}, ${when(latest.at)}` : "No AI has asked your Brain yet",
      cta: "See them",
      to: "/activity",
      dark: false,
    },
  ];

  return (
    <div className="gn-page" style={css("max-width:920px;margin:0 auto;padding:72px 48px 96px;display:flex;flex-direction:column;gap:48px;box-sizing:border-box")}>
      <div style={css("display:flex;flex-direction:column;align-items:center;gap:10px;text-align:center")}>
        <span style={css("font:400 14px Geist;color:var(--muted)")}>{today()}</span>
        <h1 style={css("margin:0;font:400 46px/1.1 Newsreader;letter-spacing:-.02em")}>{greeting()}</h1>
        <span style={css("font:400 17px/1.5 Geist;color:var(--ink2)")}>{line}</span>
      </div>
      <TellAsk projects={active} />
      <section aria-label="Today" style={css("display:flex;flex-direction:column;gap:14px")}>
        <h2 style={css("margin:0;font:400 26px Newsreader")}>Today</h2>
        <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px")}>
          {cards.map((c) => (
            <button
              key={c.to}
              type="button"
              onClick={() => navigate(c.to)}
              style={css(
                `padding:20px;border-radius:20px;display:flex;flex-direction:column;gap:4px;text-align:left;min-height:150px;cursor:pointer;${
                  c.dark ? "border:0;background:var(--ink);color:var(--bg)" : "border:0;background:var(--surface);box-shadow:var(--shadow);color:var(--ink)"
                }`,
              )}
            >
              <span style={css("font:400 40px/1 Newsreader;margin-bottom:6px")}>{c.n}</span>
              <span style={css("font:500 15px Geist")}>{c.t}</span>
              <span style={css("font:400 13px Geist;opacity:.68")}>{c.d}</span>
              <span style={css("font:500 13px Geist;margin-top:auto;padding-top:12px")}>{c.cta} →</span>
            </button>
          ))}
        </div>
      </section>
      <section aria-label="Jump back in" style={css("display:flex;flex-direction:column;gap:14px")}>
        <div style={css("display:flex;justify-content:space-between;align-items:baseline")}>
          <h2 style={css("margin:0;font:400 26px Newsreader")}>Jump back in</h2>
          <button type="button" onClick={() => navigate("/projects")} style={css("border:0;background:transparent;font:400 13px Geist;color:var(--muted)")}>
            All projects →
          </button>
        </div>
        <Loaded
          q={projects}
          empty={() =>
            active.length ? null : (
              <Empty title="No active projects yet" action={<Btn onClick={() => navigate("/projects?new=1")}>New project</Btn>}>
                A project keeps its own context, so your AI starts from where you left off.
              </Empty>
            )
          }
        >
          {() => (
            <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px")}>
              {active.slice(0, 3).map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => navigate(`/projects/${encodeURIComponent(p.id)}`)}
                  style={css("background:var(--surface);border:0;border-radius:20px;box-shadow:var(--shadow);padding:16px;display:flex;flex-direction:column;gap:10px;text-align:left;color:var(--ink)")}
                >
                  <div style={css("display:flex")}>
                    <span style={css(`padding:3px 9px;border-radius:99px;font:500 11.5px Geist;white-space:nowrap;background:${tint(320)};color:var(--ink)`)}>
                      {p.status || "Active"}
                    </span>
                  </div>
                  <span style={css("font:400 19px/1.25 Newsreader")}>{p.title}</span>
                  <span style={css("font:400 13px/1.5 Geist;color:var(--ink2)")}>{p.current || p.summary || "Nothing recorded about where it stands yet."}</span>
                  {p.updated ? <span style={css(S.small)}>Updated {when(p.updated)}</span> : null}
                </button>
              ))}
            </div>
          )}
        </Loaded>
      </section>
      {catalog.error ? (
        <Failure error={catalog.error} retry={() => void catalog.refetch()} />
      ) : (
        <button
          type="button"
          onClick={() => navigate("/brain")}
          style={css("display:flex;flex-direction:column;gap:12px;padding:20px 22px;border-radius:20px;border:1px solid var(--line);background:transparent;text-align:left;color:var(--ink)")}
        >
          <div style={css("display:flex;justify-content:space-between;align-items:baseline;width:100%;gap:12px;flex-wrap:wrap")}>
            <span style={css("font:500 15px Geist")}>Your Brain</span>
            <span style={css("font:400 13px Geist;color:var(--muted)")}>{shape ? (shape.entries ? shape.line : "Empty so far") : "Loading…"} →</span>
          </div>
          {shape ? <AreaBar areas={shape.areas} height={10} /> : null}
        </button>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ the auto-governed Home

const KH: Record<string, number> = { Added: 150, Updated: 210, Retired: 35, Changed: 265 };

function AutoHome({ policy }: { policy: Policy }) {
  const navigate = useNavigate();
  const proposals = useProposals();
  const points = useBrainCheckpoints();
  const projects = useBrainProjects();
  const { catalog, shape } = useBrainShape();
  const undo = useUndo();
  const [undoing, setUndoing] = useState<string | null>(null);

  const cap = policy.auto_daily_cap;
  const done = policy.auto_applied_today;
  const paused = done >= cap;
  const auto = autoApplied(points.data ?? []);
  const lastAt = auto[0]?.at;
  const waiting = proposals.data ?? [];
  const need = waiting[0];
  const active = (projects.data ?? []).filter((p) => p.active);
  const dayAuto = auto.filter((p) => lastDay(p.at));
  const counts = ["Added", "Updated", "Retired"].map((k) => ({ k, n: dayAuto.filter((p) => changeVerb(p) === k).length }));

  const status = paused ? `Paused: ${done} changes went in on their own today, the cap is ${cap}` : `${done} of ${cap} today${lastAt ? ` · last change ${when(lastAt)}` : ""}`;
  const waits = proposals.isLoading ? "" : waiting.length ? ` ${plural(waiting.length, "change")} ${waiting.length === 1 ? "waits" : "wait"} for you.` : " Nothing waits for you.";
  const sub = `${plural(done, "change")} went in on ${done === 1 ? "its" : "their"} own in the last 24 hours.${waits}${
    paused ? " Until the cap resets, new changes wait in Catch up." : ""
  }`;

  return (
    <div className="gn-page" style={css("max-width:1080px;margin:0 auto;padding:40px 64px 96px;display:flex;flex-direction:column;gap:44px;box-sizing:border-box")}>
      <div style={css("display:flex;flex-direction:column;align-items:center;gap:10px;text-align:center;padding-top:16px")}>
        <span style={css("font:400 14px Geist;color:var(--muted)")}>{today()}</span>
        <h1 style={css("margin:0;font:400 46px/1.1 Newsreader;letter-spacing:-.02em")}>{greeting()}</h1>
        <span style={css("font:400 17px/1.5 Geist;color:var(--ink2);max-width:640px")}>{paused ? "Auto-governance is paused." : "Your Brain is keeping itself."}</span>
      </div>
      <TellAsk projects={active} />
      <div
        role="status"
        style={css("display:flex;align-items:center;gap:12px;padding:10px 12px 10px 16px;border-radius:99px;background:var(--surface);box-shadow:var(--shadow);align-self:center;flex-wrap:wrap")}
      >
        <span
          aria-hidden="true"
          style={css(`width:8px;height:8px;border-radius:50%;flex:none;background:${paused ? "var(--faint)" : "oklch(0.7 0.14 150)"};${paused ? "" : "animation:gnDot 1.6s infinite"}`)}
        />
        <span style={css("font:500 13px Geist")}>Auto-governed</span>
        <span style={css("font:400 13px Geist;color:var(--muted)")}>{status}</span>
        <button
          type="button"
          disabled
          title="Pausing by hand isn’t available yet. Auto pauses on its own at the daily cap."
          style={css("padding:5px 12px;border-radius:99px;border:1px solid var(--line2);background:transparent;font:500 12px Geist;color:var(--ink);opacity:.55")}
        >
          Pause
        </button>
        <button type="button" onClick={() => navigate("/settings?tab=approval")} style={css("border:0;background:transparent;font:400 12px Geist;color:var(--muted);padding:0 4px")}>
          Settings
        </button>
      </div>
      <span style={css("font:400 15px/1.55 Geist;color:var(--ink2);text-align:center;max-width:680px;align-self:center;margin-top:-24px")}>{sub}</span>
      {proposals.error ? <Failure error={proposals.error} retry={() => void proposals.refetch()} /> : null}
      {need ? (
        <button
          type="button"
          onClick={() => navigate("/brain/cards")}
          style={css("display:flex;align-items:center;gap:16px;padding:18px 22px;border-radius:20px;border:1px dashed oklch(0.68 0.14 35);background:var(--surface);text-align:left;color:var(--ink);margin-top:-16px")}
        >
          <span aria-hidden="true" style={css("width:36px;height:36px;border-radius:12px;flex:none;display:flex;align-items:center;justify-content:center;background:oklch(0.74 0.12 35 / .2);font:500 15px Geist")}>
            !
          </span>
          <div style={css("flex:1;display:flex;flex-direction:column;gap:2px")}>
            <span style={css("font:500 15px Geist")}>“{need.title || need.summary}”</span>
            <span style={css("font:400 13px Geist;color:var(--muted)")}>{need.reason || need.note_summary || "Waits for your yes in Catch up."}</span>
          </div>
          <span style={css("font:500 13px Geist")}>Decide →</span>
        </button>
      ) : null}
      <section aria-label="Goals" style={css("display:flex;flex-direction:column;gap:14px")}>
        <div style={css("display:flex;justify-content:space-between;align-items:baseline")}>
          <h2 style={css("margin:0;font:400 30px Newsreader")}>
            Goals
            <Later />
          </h2>
          <button type="button" disabled style={css("border:0;background:transparent;font:400 13px Geist;color:var(--muted);opacity:.55")}>
            All goals →
          </button>
        </div>
        <Empty title="Goals are a later phase">When they arrive, each goal shows how far along it is and what moved it.</Empty>
      </section>
      <section aria-label="Projects" style={css("display:flex;flex-direction:column;gap:14px")}>
        <div style={css("display:flex;justify-content:space-between;align-items:baseline")}>
          <h2 style={css("margin:0;font:400 30px Newsreader")}>Projects</h2>
          <button type="button" onClick={() => navigate("/projects")} style={css("border:0;background:transparent;font:400 13px Geist;color:var(--muted)")}>
            All projects →
          </button>
        </div>
        <Loaded q={projects} empty={() => (active.length ? null : <Empty title="No active projects yet" />)}>
          {() => (
            <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px")}>
              {active.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => navigate(`/projects/${encodeURIComponent(p.id)}`)}
                  style={css("padding:20px;border-radius:20px;border:1px solid var(--line);background:transparent;display:flex;flex-direction:column;gap:10px;text-align:left;color:var(--ink)")}
                >
                  <span style={css("font:500 15px Geist")}>{p.title}</span>
                  <span style={css("font:400 14px/1.5 Geist;color:var(--ink2)")}>{p.current || p.summary || "Nothing recorded about where it stands yet."}</span>
                  <span style={css("font:400 12px Geist;color:var(--muted);margin-top:auto")}>{p.updated ? `Updated ${when(p.updated)}` : p.status}</span>
                </button>
              ))}
            </div>
          )}
        </Loaded>
      </section>
      <section aria-label="Your Brain" style={css("display:flex;flex-direction:column;gap:18px")}>
        <div style={css("display:flex;justify-content:space-between;align-items:baseline")}>
          <h2 style={css("margin:0;font:400 30px Newsreader")}>Your Brain</h2>
          <button type="button" onClick={() => navigate("/brain")} style={css("border:0;background:transparent;font:400 13px Geist;color:var(--muted)")}>
            Open Brain →
          </button>
        </div>
        {catalog.error ? <Failure error={catalog.error} retry={() => void catalog.refetch()} /> : shape ? <AreaBar areas={shape.areas} height={14} /> : <Loading />}
        {shape ? <span style={css(S.muted)}>{shape.entries ? shape.line : "Your Brain is empty so far."}</span> : null}
        <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px")}>
          {counts.map((c) => (
            <div key={c.k} style={css(`padding:14px 16px;border-radius:16px;background:${tint(KH[c.k] ?? 265)};display:flex;flex-direction:column;gap:2px`)}>
              <span style={css("font:400 28px Newsreader;color:var(--ink)")}>{points.isLoading ? "…" : c.n}</span>
              <span style={css("font:400 13px Geist;color:var(--ink2)")}>{c.k} today</span>
            </div>
          ))}
        </div>
        <div style={css("background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:6px 22px")}>
          <div style={css("display:flex;justify-content:space-between;padding:14px 0 8px")}>
            <span style={css("font:500 13px Geist;color:var(--muted)")}>What went in on its own, and why</span>
            <button type="button" onClick={() => navigate("/activity?tab=changes")} style={css("border:0;background:transparent;font:400 12px Geist;color:var(--muted)")}>
              Full log →
            </button>
          </div>
          {undo.error ? (
            <div style={css("padding-bottom:12px")}>
              <Failure error={undo.error} />
            </div>
          ) : null}
          <Loaded
            q={points}
            empty={() =>
              auto.length ? null : <div style={css("padding:13px 0 16px;border-top:1px solid var(--line);font:400 14px Geist;color:var(--muted)")}>Nothing has gone in on its own yet.</div>
            }
          >
            {() => (
              <>
                {auto.slice(0, 8).map((p) => {
                  const k = changeVerb(p);
                  const gone = Boolean(p.undone_by);
                  const can = !gone && p.undoable !== false;
                  const title = changeTitle(p);
                  return (
                    <div key={p.id} style={css("display:flex;gap:14px;align-items:flex-start;padding:13px 0;border-top:1px solid var(--line)")}>
                      <span style={css(`padding:2px 8px;border-radius:99px;font:500 11px Geist;white-space:nowrap;background:${tint(KH[k] ?? 265)};color:var(--ink)`)}>{k}</span>
                      <div style={css("flex:1;min-width:0;display:flex;flex-direction:column;gap:3px")}>
                        <span style={cx("font:400 14px/1.45 Geist", gone && "text-decoration:line-through;color:var(--muted)")}>{title}</span>
                        <div style={css("display:flex;gap:8px;align-items:center;font:400 12px Geist;color:var(--muted)")}>
                          {p.by ? `From ${p.by}` : "Went in on its own"}
                          {gone ? " · undone" : p.blocked?.length ? " · later changes touch it" : ""}
                        </div>
                      </div>
                      <span style={css("font:400 12px Geist;color:var(--muted);white-space:nowrap")}>{when(p.at)}</span>
                      <button
                        type="button"
                        aria-label={gone ? `Undone: ${title}` : `Undo: ${title}`}
                        disabled={!can || undo.isPending}
                        onClick={() => {
                          setUndoing(p.id);
                          undo.mutate(p.id, { onSettled: () => setUndoing(null) });
                        }}
                        style={css("border:0;background:transparent;font:500 12px Geist;color:var(--ink2);min-width:52px;text-align:right")}
                      >
                        {gone ? "Undone" : undoing === p.id ? "Undoing…" : "Undo"}
                      </button>
                    </div>
                  );
                })}
              </>
            )}
          </Loaded>
        </div>
        <span style={css("font:400 13px/1.5 Geist;color:var(--muted)")}>Guardrails: must-holds and private notes still wait for you. Every change is an undo point.</span>
      </section>
    </div>
  );
}
