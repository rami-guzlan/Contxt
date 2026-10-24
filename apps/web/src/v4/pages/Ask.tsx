// Ask (v4 slice 01-isAsk, Release 1 plan M10): a conversation with the Brain. Each question
// goes to the person's chosen AI (Claude Code in Release 1) with only the Brain's tools; each
// answer shows the notes it cites, one evidence receipt per request the AI made, and who
// answered and where the data went. The conversation lives in this page (and sessionStorage,
// for this viewer only); nothing here is kept in the Brain.

import { Fragment, type KeyboardEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { ApiError } from "../../api/client";
import { useCatchUp } from "../../api/hooks";
import { type AskAnswer, type ProviderCard, useAsk } from "../api";
import { ReceiptView } from "../components/Receipt";
import { css } from "../css";
import { Btn, plural } from "../ui";

type TurnState = "asking" | "answered" | "failed" | "interrupted";

interface Turn {
  id: string;
  question: string;
  at: string;
  state: TurnState;
  answer?: AskAnswer;
  error?: { status: number; code: string; message: string };
}

const KEY = "contxt.v4.ask.thread";
const CITED = /(\[[a-z0-9][a-z0-9-]{1,80}\])/g;
const ONE_CITE = /^\[([a-z0-9][a-z0-9-]{1,80})\]$/;

function loadThread(): Turn[] {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    const turns = raw ? (JSON.parse(raw) as Turn[]) : [];
    if (!Array.isArray(turns)) return [];
    // A question still being answered when the page closed has no answer to come back to.
    return turns.map((t) => (t.state === "asking" ? { ...t, state: "interrupted" as const } : t));
  } catch {
    return [];
  }
}

function saveThread(turns: Turn[]) {
  try {
    if (turns.length) window.sessionStorage.setItem(KEY, JSON.stringify(turns));
    else window.sessionStorage.removeItem(KEY);
  } catch {
    // Storage can be blocked; the conversation still works in this page.
  }
}

function greeting(): string {
  const hour = new Date().getHours();
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

const SUGGESTIONS = ["What's out of date?", "What did I decide most recently?", "What does my Brain know about my current projects?"];

export function AskPage() {
  const ask = useAsk();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [thread, setThread] = useState<Turn[]>(loadThread);
  const [draft, setDraft] = useState("");
  const asking = thread.some((t) => t.state === "asking");
  const started = useRef(false);

  useEffect(() => saveThread(thread), [thread]);

  const update = (id: string, change: Partial<Turn>) => setThread((all) => all.map((t) => (t.id === id ? { ...t, ...change } : t)));

  const send = (text?: string) => {
    const question = (text ?? draft).trim();
    if (!question || asking) return;
    const id = `t${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
    setThread((all) => [...all, { id, question, at: new Date().toISOString(), state: "asking" }]);
    if (text === undefined) setDraft("");
    ask.mutate(question, {
      onSuccess: (answer) => update(id, { state: "answered", answer }),
      onError: (error) =>
        update(id, {
          state: "failed",
          error: {
            status: error instanceof ApiError ? error.status : 0,
            code: error instanceof ApiError ? error.code : "error",
            message: error instanceof Error ? error.message : "Something went wrong.",
          },
        }),
    });
  };
  const sendRef = useRef(send);
  sendRef.current = send;

  // ?q= fills the question in and sends it, once.
  useEffect(() => {
    const q = params.get("q");
    if (!q || started.current) return;
    started.current = true;
    setParams(
      (p) => {
        p.delete("q");
        return p;
      },
      { replace: true },
    );
    sendRef.current(q);
  }, [params, setParams]);

  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const retry = (t: Turn) => {
    setThread((all) => all.filter((x) => x.id !== t.id));
    send(t.question);
  };

  return (
    <div style={css("min-height:100%;display:flex;flex-direction:column;align-items:center;padding:0 40px;box-sizing:border-box")}>
      {thread.length === 0 ? (
        <div style={css("width:720px;max-width:100%;display:flex;flex-direction:column;align-items:center;gap:32px;padding:13vh 0 64px")}>
          <div style={css("display:flex;flex-direction:column;align-items:center;gap:14px")}>
            <span style={css("font:400 15px Geist;color:var(--muted)")}>{greeting()}</span>
            <h1 style={css("margin:0;font:400 46px/1.1 Newsreader;letter-spacing:-.02em;text-align:center")}>What should your Brain know?</h1>
          </div>
          <div style={css("width:100%;background:var(--surface);border-radius:24px;padding:18px 20px 14px;box-shadow:var(--shadow2);display:flex;flex-direction:column;gap:14px;box-sizing:border-box")}>
            <textarea
              aria-label="Your question"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKey}
              placeholder="Ask what your Brain knows, or what your AI would get…"
              rows={2}
              style={css("border:0;outline:none;resize:none;background:transparent;color:var(--ink);font:400 17px/1.5 Geist")}
            />
            <div style={css("display:flex;align-items:center;gap:8px;flex-wrap:wrap")}>
              <button
                type="button"
                onClick={() => navigate("/capture")}
                style={css("padding:6px 12px;border-radius:99px;border:1px solid var(--line2);background:transparent;font:400 13px Geist;color:var(--ink2)")}
              >
                + File
              </button>
              <button
                type="button"
                onClick={() => navigate("/capture?record=1")}
                style={css("padding:6px 12px;border-radius:99px;border:1px solid var(--line2);background:transparent;font:400 13px Geist;color:var(--ink2)")}
              >
                Record
              </button>
              <span style={css("margin-left:auto;font:400 12px Geist;color:var(--faint)")}>Enter to send</span>
              <SendButton onClick={() => send()} disabled={!draft.trim()} />
            </div>
          </div>
          <span style={css("font:400 13px/1.5 Geist;color:var(--muted);text-align:center;max-width:560px;margin-top:-16px")}>
            Ask answers from your Brain alone. To tell it something new, add a file or a recording: it goes to Capture, and you decide what is kept.
          </span>
          <div style={css("display:flex;gap:8px;flex-wrap:wrap;justify-content:center")}>
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => send(s)}
                style={css("padding:8px 14px;border-radius:99px;background:var(--soft);border:0;font:400 14px Geist;color:var(--ink2)")}
              >
                {s}
              </button>
            ))}
          </div>
          <CheckIn />
        </div>
      ) : (
        <>
          <div style={css("width:720px;max-width:100%;display:flex;flex-direction:column;gap:26px;padding:56px 0 40px;flex:1")}>
            <div style={css("display:flex;justify-content:space-between;align-items:center")}>
              <span style={css("font:500 14px Geist;color:var(--muted)")}>Talking with your Brain</span>
              <button
                type="button"
                disabled={asking}
                onClick={() => setThread([])}
                style={css("border:0;background:transparent;font:400 13px Geist;color:var(--muted)")}
              >
                New chat
              </button>
            </div>
            {thread.map((t) => (
              <div key={t.id} style={css("display:flex;flex-direction:column;gap:12px")}>
                <div style={css("align-self:flex-end;max-width:70%;padding:12px 16px;border-radius:18px 18px 4px 18px;background:var(--soft);font:400 15px/1.5 Geist;white-space:pre-wrap")}>
                  {t.question}
                </div>
                <BrainTurn turn={t} onRetry={() => retry(t)} canRetry={!asking} />
              </div>
            ))}
          </div>
          <div style={css("position:sticky;bottom:0;width:720px;max-width:100%;padding:16px 0 28px;background:linear-gradient(transparent,var(--bg) 30%)")}>
            <div style={css("background:var(--surface);border-radius:22px;padding:12px 14px 12px 20px;display:flex;align-items:center;gap:10px;box-shadow:var(--shadow2)")}>
              <input
                aria-label="Your question"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={onKey}
                placeholder={asking ? "Wait for the answer, then ask the next thing…" : "Ask a follow-up, or something new…"}
                style={css("flex:1;border:0;outline:none;background:transparent;color:var(--ink);font:400 16px Geist")}
              />
              <SendButton onClick={() => send()} disabled={asking || !draft.trim()} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function SendButton({ onClick, disabled }: { onClick: () => void; disabled: boolean }) {
  return (
    <button
      type="button"
      aria-label="Send"
      onClick={onClick}
      disabled={disabled}
      style={css(`width:34px;height:34px;border-radius:50%;background:var(--ink);color:var(--bg);border:0;font:500 16px Geist;${disabled ? "opacity:.45" : ""}`)}
    >
      ↑
    </button>
  );
}

/** The weekly check-in, when Catch up has something waiting. */
function CheckIn() {
  const q = useCatchUp();
  const navigate = useNavigate();
  const plan = q.data;
  if (!plan || plan.caught_up || !plan.counts) return null;
  const n = (plan.counts.judgment ?? 0) + (plan.counts.quick_items ?? 0) + (plan.counts.upkeep ?? 0);
  if (n <= 0) return null;
  return (
    <div style={css("width:100%;display:flex;align-items:center;gap:18px;padding:20px 22px;border-radius:20px;border:1px solid var(--line);background:var(--surface);box-sizing:border-box;margin-top:8px")}>
      <span style={css("width:44px;height:44px;border-radius:14px;background:oklch(0.94 0.035 35);flex:none;display:flex;align-items:center;justify-content:center;font:400 20px Newsreader;color:oklch(0.42 0.09 35)")}>
        {n}
      </span>
      <div style={css("flex:1;display:flex;flex-direction:column;gap:2px")}>
        <span style={css("font:500 15px Geist")}>Weekly check-in</span>
        <span style={css("font:400 14px Geist;color:var(--ink2)")}>
          {plural(n, "thing")} wait{n === 1 ? "s" : ""} for you{plan.minutes ? `, about ${plural(plan.minutes, "minute")}` : ""}.
        </span>
      </div>
      <Btn kind="primary" onClick={() => navigate("/brain/catch-up")}>
        Start
      </Btn>
    </div>
  );
}

function Mark() {
  return (
    <span aria-hidden="true" style={css("width:26px;height:26px;border-radius:50%;background:var(--ink);flex:none;display:flex;align-items:center;justify-content:center;margin-top:3px")}>
      <span style={css("width:2px;height:12px;background:var(--bg);border-radius:2px;transform:rotate(30deg)")} />
    </span>
  );
}

function BrainTurn({ turn, onRetry, canRetry }: { turn: Turn; onRetry: () => void; canRetry: boolean }) {
  return (
    <div style={css("display:flex;gap:14px;align-items:flex-start;max-width:88%")}>
      <Mark />
      <div style={css("display:flex;flex-direction:column;gap:12px;min-width:0;flex:1")}>
        {turn.state === "asking" ? <Working since={turn.at} /> : null}
        {turn.state === "answered" && turn.answer ? <Answer answer={turn.answer} /> : null}
        {turn.state === "failed" && turn.error ? <AskFailed error={turn.error} onRetry={onRetry} canRetry={canRetry} /> : null}
        {turn.state === "interrupted" ? (
          <div style={css("display:flex;flex-direction:column;gap:8px;align-items:flex-start")}>
            <span style={css("font:400 15px/1.5 Geist;color:var(--ink2)")}>
              The page closed while this was being answered, so the answer did not come back here. Ask it again.
            </span>
            <Btn kind="ghostSm" onClick={onRetry} disabled={!canRetry}>
              Ask again
            </Btn>
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** Honest progress: the AI is working, how long so far, and that it can take a minute. */
function Working({ since }: { since: string }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const seconds = Math.max(0, Math.round((now - new Date(since).getTime()) / 1000));
  return (
    <div role="status" aria-live="polite" style={css("display:flex;flex-direction:column;gap:4px")}>
      <span style={css("display:flex;gap:5px;padding:12px 0 4px")} aria-hidden="true">
        <span style={css("width:6px;height:6px;border-radius:50%;background:var(--muted);animation:gnDot 1s infinite")} />
        <span style={css("width:6px;height:6px;border-radius:50%;background:var(--muted);animation:gnDot 1s .2s infinite")} />
        <span style={css("width:6px;height:6px;border-radius:50%;background:var(--muted);animation:gnDot 1s .4s infinite")} />
      </span>
      <span style={css("font:400 13px Geist;color:var(--muted)")}>
        Your chosen AI is reading your Brain and writing the answer{seconds >= 1 ? `, ${seconds} s so far` : ""}. This can take a minute.
      </span>
    </div>
  );
}

function AnswerText({ text, cited }: { text: string; cited: string[] }) {
  const held = new Set(cited);
  const parts = text.split(CITED);
  return (
    <span style={css("font:400 20px/1.5 Newsreader;text-wrap:pretty;white-space:pre-wrap")}>
      {parts.map((part, i) => {
        const id = ONE_CITE.exec(part)?.[1];
        if (id && held.has(id)) {
          return (
            <Link key={i} to={`/brain/notes/${encodeURIComponent(id)}`} style={css("font:400 13px 'Geist Mono';color:var(--ink2);text-decoration:underline")}>
              [{id}]
            </Link>
          );
        }
        return <Fragment key={i}>{part}</Fragment>;
      })}
    </span>
  );
}

function Answer({ answer }: { answer: AskAnswer }) {
  const text = answer.answer.trim();
  return (
    <>
      {text ? (
        <AnswerText text={text} cited={answer.cited} />
      ) : (
        <span style={css("font:400 15px Geist;color:var(--ink2)")}>The AI finished without writing an answer.</span>
      )}
      {!answer.asked_brain ? (
        <span role="note" style={css("padding:10px 14px;border-radius:14px;background:oklch(0.78 0.11 70 / .2);font:400 14px/1.5 Geist;color:var(--ink)")}>
          The AI answered without asking the Brain, so nothing in this answer comes from your notes and there is no receipt.
        </span>
      ) : null}
      {answer.asked_brain || answer.cited.length ? (
        <div style={css("display:flex;flex-direction:column;gap:10px;padding:16px 18px;border-radius:18px;background:var(--surface);border:1px solid var(--line)")}>
          <span style={css("font:500 13px Geist")}>Notes it cites</span>
          {answer.cited.length ? (
            <div style={css("display:flex;gap:6px;flex-wrap:wrap")}>
              {answer.cited.map((id) => (
                <Link
                  key={id}
                  to={`/brain/notes/${encodeURIComponent(id)}`}
                  style={css("padding:4px 10px;border-radius:99px;background:var(--soft);color:var(--ink2);font:500 12px Geist;text-decoration:none")}
                >
                  {id}
                </Link>
              ))}
            </div>
          ) : (
            <span style={css("font:400 13px Geist;color:var(--ink2)")}>It cites no note from your Brain.</span>
          )}
          <span style={css("font:400 13px Geist;color:var(--muted)")}>
            {plural(answer.cited.length, "note")} cited · {plural(answer.receipts.length, "request")} to the Brain
          </span>
        </div>
      ) : null}
      {answer.receipts.map((id) => (
        <ReceiptView key={id} id={id} />
      ))}
      {answer.provider ? <Provider card={answer.provider} /> : null}
    </>
  );
}

function Provider({ card }: { card: ProviderCard }) {
  const model = card.model ? card.model : "model not named";
  const rows: [string, string][] = [
    ["Provider and model", `${card.label}, ${card.vendor}, ${model}${card.model_from ? ` (${card.model_from})` : ""}`],
    ["Where data goes", card.data],
  ];
  if (card.switches) rows.push(["If it fails", card.switches]);
  return (
    <div role="group" aria-label="Who answered" style={css("display:flex;flex-direction:column;padding:4px 16px;border-radius:16px;border:1px solid var(--line)")}>
      {rows.map(([k, v], i) => (
        <div key={k} style={css(`display:flex;gap:14px;padding:9px 0;${i ? "border-top:1px solid var(--line);" : ""}font:400 13px/1.5 Geist;flex-wrap:wrap`)}>
          <span style={css("width:130px;flex:none;color:var(--muted)")}>{k}</span>
          <span style={css("flex:1;min-width:200px;color:var(--ink2)")}>{v}</span>
        </div>
      ))}
    </div>
  );
}

function AskFailed({ error, onRetry, canRetry }: { error: NonNullable<Turn["error"]>; onRetry: () => void; canRetry: boolean }) {
  const blocked = error.status === 409;
  return (
    <div role="alert" style={css("padding:16px 18px;border-radius:16px;background:oklch(0.64 0.17 28 / .1);display:flex;flex-direction:column;gap:8px;align-items:flex-start")}>
      <span style={css("font:500 14px Geist")}>{blocked ? "Ask can't run right now" : "The answer didn't come back"}</span>
      <span style={css("font:400 14px/1.5 Geist;color:var(--ink2)")}>{error.message}</span>
      {blocked ? (
        <span style={css("font:400 14px/1.5 Geist;color:var(--ink2)")}>
          To fix it: in Agents, choose Claude Code as the AI that answers, and make sure it is signed in on this computer. Then ask again.
        </span>
      ) : null}
      <div style={css("display:flex;gap:8px;flex-wrap:wrap")}>
        {blocked ? (
          <Link to="/agents" style={css("padding:8px 14px;border-radius:99px;background:var(--ink);color:var(--bg);font:500 13px Geist;text-decoration:none")}>
            Open Agents
          </Link>
        ) : null}
        <Btn kind="ghostSm" onClick={onRetry} disabled={!canRetry}>
          Ask again
        </Btn>
      </div>
    </div>
  );
}
