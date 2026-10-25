// Settings, Approval, the Heartbeat block: the first, onboarding beat. Each CLI on this computer
// reads what it keeps on the person (its memory, what they said in its chats, and what it
// remembers from its own other apps) and turns it into context packets for the Brain. Memory
// from an AI app no CLI can reach comes in pasted.

import { useState } from "react";

import { css } from "../css";
import { type HbConnector, useOnboard, useRescan } from "../hooks/heartbeat";
import { Failure } from "../ui";

const SURFACES: Record<string, string> = {
  claude: "Claude on the web, desktop and phone",
  codex: "ChatGPT",
  gemini: "the Gemini app",
};

export const ASK_OTHER_APP =
  "List everything you remember about me: who I am, my work and projects, my preferences and rules for how to work with me, and the people I work with. Plain lines, with dates where you know them.";

const button = "padding:8px 16px;border-radius:99px;border:1px solid var(--ink);background:var(--ink);color:var(--bg);font:500 13px Geist;cursor:pointer";
const quiet = "padding:7px 14px;border-radius:99px;border:1px solid var(--line2);background:transparent;font:500 12.5px Geist;color:var(--ink);cursor:pointer";
const field = "font:400 13px/1.45 Geist;padding:8px 10px;border-radius:10px;border:1px solid var(--line2);background:var(--surface);color:var(--ink);width:100%;box-sizing:border-box";

export function Onboarding({ connectors }: { connectors: HbConnector[] }) {
  const sources = connectors.filter((c) => c.how === "memory" && c.present);
  const read = sources.some((c) => c.last_read_at);
  const [chosen, setChosen] = useState<string[] | null>(null);
  const [pasted, setPasted] = useState("");
  const [ask, setAsk] = useState("");
  const [copied, setCopied] = useState(false);
  const onboard = useOnboard();
  const rescan = useRescan();
  const picked = chosen ?? sources.map((c) => c.cli);
  const copy = () => {
    void navigator.clipboard?.writeText(ASK_OTHER_APP).then(() => setCopied(true), () => setCopied(false));
  };
  return (
    <div role="region" aria-label="Start with what your AI apps know" style={css("display:flex;flex-direction:column;gap:10px;padding:14px 16px;border-radius:14px;background:var(--surface)")}>
      <span style={css("font:500 14px Geist")}>{read ? "Read your AI apps again" : "Start with what your AI apps already know"}</span>
      <span style={css("font:400 13px/1.5 Geist;color:var(--ink2);max-width:640px")}>
        Each AI app here reads what it keeps on you: its memory, what you said in its chats, and what it remembers from its own other apps. It turns that into context packets, and the heartbeat files them into your Brain. After that, it reads what is new once a day.
      </span>
      {sources.length ? (
        <div role="group" aria-label="AI apps to read" style={css("display:flex;flex-direction:column;gap:6px")}>
          {sources.map((c) => (
            <label key={c.id} style={css("display:flex;gap:8px;align-items:flex-start;font:400 13px/1.45 Geist")}>
              <input
                type="checkbox"
                checked={picked.includes(c.cli)}
                onChange={(e) => setChosen(e.target.checked ? [...picked, c.cli] : picked.filter((x) => x !== c.cli))}
              />
              <span>
                <span style={css("font-weight:500")}>{c.cli_label}</span>: its memory, your chats with it, and what it remembers from {SURFACES[c.cli] ?? "its other apps"}
                {c.last_read_at ? <span style={css("color:var(--muted)")}> · read before</span> : null}
              </span>
            </label>
          ))}
        </div>
      ) : (
        <span style={css("display:flex;gap:10px;align-items:center;flex-wrap:wrap;font:400 13px Geist;color:var(--muted)")}>
          No AI app found here yet.
          <button type="button" disabled={rescan.isPending} onClick={() => rescan.mutate()} style={css(quiet)}>
            {rescan.isPending ? "Looking…" : "Find my AI apps"}
          </button>
        </span>
      )}
      <details>
        <summary style={css("font:500 12.5px Geist;cursor:pointer")}>Add memory from another AI app</summary>
        <div style={css("display:flex;flex-direction:column;gap:8px;padding-top:8px")}>
          <span style={css("font:400 12.5px/1.5 Geist;color:var(--ink2)")}>
            For an app no AI app here can read (ChatGPT, Gemini, Claude on the web), ask it this, then paste its answer below.
          </span>
          <span style={css("display:flex;gap:8px;align-items:flex-start;flex-wrap:wrap")}>
            <code style={css("flex:1;min-width:220px;font:400 12.5px/1.5 Geist;padding:8px 10px;border-radius:10px;border:1px solid var(--line)")}>{ASK_OTHER_APP}</code>
            <button type="button" onClick={copy} style={css(quiet)}>
              {copied ? "Copied" : "Copy"}
            </button>
          </span>
          <textarea aria-label="What another AI app remembers about you" rows={4} value={pasted} onChange={(e) => setPasted(e.target.value)} style={css(field)} />
        </div>
      </details>
      <input aria-label="Anything to look for, in your words (optional)" placeholder="Anything to look for, in your words (optional)" value={ask} onChange={(e) => setAsk(e.target.value)} style={css(field)} />
      <span style={css("display:flex;gap:10px;align-items:center;flex-wrap:wrap")}>
        <button
          type="button"
          disabled={onboard.isPending || !picked.length}
          onClick={() => onboard.mutate({ clis: picked, ...(ask.trim() ? { ask: ask.trim() } : {}), ...(pasted.trim() ? { pasted: pasted.trim() } : {}) })}
          style={css(button)}
        >
          {onboard.isPending ? "Starting…" : read ? "Read them again" : "Build my Brain from them"}
        </button>
        <span style={css("font:400 12px Geist;color:var(--muted)")}>Read-only. One run of each app, so it costs tokens once.</span>
      </span>
      {onboard.data?.reading ? (
        <span role="status" style={css("font:400 13px Geist;color:var(--ink2)")}>
          Reading {onboard.data.reading.join(", ")}. Recent beats shows each one as it is read.
        </span>
      ) : onboard.data?.line ? (
        <span role="status" style={css("font:400 13px Geist;color:var(--ink2)")}>{onboard.data.line}</span>
      ) : null}
      {onboard.error ? <Failure error={onboard.error} /> : null}
      {rescan.error ? <Failure error={rescan.error} /> : null}
    </div>
  );
}
