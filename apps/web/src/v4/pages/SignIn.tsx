// Sign in, as v4 draws it. The owner pastes the sign-in link `contxt serve` printed, or just
// its key; the page posts the key to /auth/login, which answers with a session cookie, and opens
// Home. The key goes in the request body, never the address, and is never shown, logged or kept.

import { useState } from "react";

import { ApiError, post } from "../../api/client";
import { css } from "../css";

/** The key from a pasted sign-in link ("…/auth/login?token=…"), or the pasted key itself. */
export function keyFrom(pasted: string): string {
  const text = pasted.trim();
  if (!text) return "";
  if (/token=/.test(text)) {
    try {
      const url = new URL(text, window.location.origin);
      const token = url.searchParams.get("token");
      if (token) return token.trim();
    } catch {
      // Not a link after all: treat it as the key.
    }
  }
  return text;
}

function open(path: string) {
  window.location.assign(path);
}

export function SignInPage({ go = open }: { go?: (path: string) => void }) {
  const [pasted, setPasted] = useState("");
  const [sending, setSending] = useState(false);
  const [problem, setProblem] = useState("");
  const key = keyFrom(pasted);

  return (
    <main style={css("min-height:100vh;display:flex;align-items:center;justify-content:center;padding:40px;box-sizing:border-box;background:var(--bg);color:var(--ink)")}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!key) return;
          setSending(true);
          setProblem("");
          post("/auth/login", { token: key }).then(
            () => go("/"),
            (error: unknown) => {
              setSending(false);
              setProblem(
                error instanceof ApiError && error.status === 401
                  ? "That key didn't work. Run uv run contxt token to see the current one, then paste it again."
                  : "Gnomon didn't answer. Check that uv run contxt serve is still running, then try again.",
              );
            },
          );
        }}
        style={css("width:420px;max-width:100%;display:flex;flex-direction:column;align-items:center;gap:20px;text-align:center")}
      >
        <span aria-hidden="true" style={css("width:44px;height:44px;border-radius:50%;background:var(--ink);display:flex;align-items:center;justify-content:center")}>
          <span style={css("width:3px;height:20px;background:var(--bg);border-radius:2px;transform:rotate(30deg)")} />
        </span>
        <h1 style={css("margin:0;font:400 36px Newsreader")}>Sign in to Gnomon</h1>
        <span style={css("font:400 15px/1.55 Geist;color:var(--ink2)")}>Open the link printed when the app started, or paste your sign-in key.</span>
        <input
          type="password"
          aria-label="Sign-in link or key"
          autoComplete="off"
          autoCapitalize="off"
          spellCheck={false}
          autoFocus
          value={pasted}
          onChange={(e) => setPasted(e.target.value)}
          placeholder="Sign-in key"
          style={css("width:100%;box-sizing:border-box;border:1px solid var(--line2);border-radius:12px;padding:11px 14px;outline:none;background:var(--surface);color:var(--ink);font:400 15px Geist")}
        />
        <button
          type="submit"
          disabled={!key || sending}
          style={css("width:100%;padding:10px 18px;border-radius:99px;background:var(--ink);color:var(--bg);border:0;font:500 14px Geist")}
        >
          {sending ? "Signing in…" : "Sign in"}
        </button>
        {problem ? (
          <span role="alert" style={css("font:400 13.5px/1.5 Geist;color:var(--ink)")}>
            {problem}
          </span>
        ) : null}
        <span style={css("font:400 13px/1.5 Geist;color:var(--muted)")}>
          Lost the link? Run <code style={css("font:400 12px 'Geist Mono';color:var(--ink2)")}>uv run contxt token</code> to see it again. It stays on this computer.
        </span>
        <span style={css("font:400 12px 'Geist Mono';color:var(--muted)")}>uv run contxt serve</span>
      </form>
    </main>
  );
}
