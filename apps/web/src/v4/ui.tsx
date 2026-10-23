// Shared parts of the v4 screens, in the design's own styles (css.ts). Every screen builds from
// these, so loading, empty, failure and "later phase" read the same everywhere.

import { type ReactNode, useEffect, useRef } from "react";

import { ApiError } from "../api/client";
import { css, cx } from "./css";

export const S = {
  page: "max-width:1040px;margin:0 auto;padding:56px 48px 96px;display:flex;flex-direction:column;gap:28px;box-sizing:border-box",
  narrow: "max-width:920px;margin:0 auto;padding:72px 48px 96px;display:flex;flex-direction:column;gap:40px;box-sizing:border-box",
  eyebrow: "font:500 11px 'Geist Mono';letter-spacing:.06em;color:var(--muted)",
  h1: "margin:0;font:400 44px/1.1 Newsreader;letter-spacing:-.02em",
  h2: "margin:0;font:400 26px Newsreader",
  h3: "font:400 22px/1.25 Newsreader",
  lead: "margin:0;font:400 15px/1.5 Geist;color:var(--ink2)",
  muted: "font:400 13px Geist;color:var(--muted)",
  small: "font:400 12px Geist;color:var(--muted)",
  card: "padding:22px;border-radius:20px;background:var(--surface);box-shadow:var(--shadow);display:flex;flex-direction:column;gap:10px",
  row: "display:flex;align-items:center;gap:14px;padding:13px 0;border:0;border-top:1px solid var(--line);background:transparent;text-align:left;color:var(--ink);width:100%",
  primary: "padding:10px 18px;border-radius:99px;background:var(--ink);color:var(--bg);border:0;font:500 14px Geist",
  primarySm: "padding:8px 14px;border-radius:99px;background:var(--ink);color:var(--bg);border:0;font:500 13px Geist",
  ghost: "padding:10px 16px;border-radius:99px;border:1px solid var(--line2);background:transparent;color:var(--ink);font:500 14px Geist",
  ghostSm: "padding:8px 14px;border-radius:99px;border:1px solid var(--line2);background:transparent;color:var(--ink);font:500 13px Geist",
  soft: "padding:7px 14px;border-radius:99px;background:var(--soft);border:0;font:500 13px Geist;color:var(--ink)",
  link: "align-self:flex-start;border:0;background:transparent;padding:0;font:400 14px Geist;color:var(--muted)",
  wrap: "display:flex;gap:6px;flex-wrap:wrap",
  col: "display:flex;flex-direction:column;gap:8px",
  input: "border:1px solid var(--line2);border-radius:12px;padding:10px 12px;background:var(--bg);color:var(--ink);font:400 15px Geist;outline:none",
};

type Kind = "primary" | "primarySm" | "ghost" | "ghostSm" | "soft" | "link";

export function Btn({
  kind = "ghostSm",
  onClick,
  children,
  disabled,
  type = "button",
  title,
  style,
}: {
  kind?: Kind;
  onClick?: () => void;
  children: ReactNode;
  disabled?: boolean;
  type?: "button" | "submit";
  title?: string;
  style?: string;
}) {
  return (
    <button type={type} onClick={onClick} disabled={disabled} title={title} style={cx(S[kind], style)}>
      {children}
    </button>
  );
}

export function Page({ children, narrow = false }: { children: ReactNode; narrow?: boolean }) {
  return (
    <div className="gn-page" style={css(narrow ? S.narrow : S.page)}>
      {children}
    </div>
  );
}

export function Head({ eyebrow, title, lead, right }: { eyebrow?: string; title: ReactNode; lead?: ReactNode; right?: ReactNode }) {
  return (
    <div style={css("display:flex;justify-content:space-between;align-items:flex-end;gap:20px;flex-wrap:wrap")}>
      <div style={css("display:flex;flex-direction:column;gap:10px;max-width:760px")}>
        {eyebrow ? <span style={css(S.eyebrow)}>{eyebrow}</span> : null}
        <h1 style={css(S.h1)}>{title}</h1>
        {lead ? <p style={css(S.lead)}>{lead}</p> : null}
      </div>
      {right}
    </div>
  );
}

export function Card({ children, style }: { children: ReactNode; style?: string }) {
  return <div style={cx(S.card, style)}>{children}</div>;
}

/** The design's mono label in capitals. */
export function Eyebrow({ children }: { children: ReactNode }) {
  return <span style={css(S.eyebrow)}>{children}</span>;
}

/** Marks what belongs to a later phase: shown, never pretended to work. */
export function Later({ what = "Later" }: { what?: string }) {
  return (
    <span
      style={css(
        "margin-left:8px;font:500 10px 'Geist Mono';letter-spacing:.05em;padding:2px 7px;border-radius:6px;background:var(--soft);color:var(--ink2);vertical-align:middle;text-transform:uppercase",
      )}
    >
      {what}
    </span>
  );
}

export function Tabs<T extends string>({ value, options, onChange, label }: { value: T; options: [T, string][]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="tablist" aria-label={label} style={css("align-self:flex-start;display:flex;gap:4px;padding:4px;border-radius:99px;background:var(--nav);flex-wrap:wrap")}>
      {options.map(([id, text]) => (
        <button
          key={id}
          role="tab"
          aria-selected={value === id}
          onClick={() => onChange(id)}
          style={css(
            `padding:8px 16px;border-radius:99px;border:0;font:${value === id ? 500 : 400} 13.5px Geist;background:${value === id ? "var(--surface)" : "transparent"};color:var(--ink);${value === id ? "box-shadow:0 1px 2px rgba(30,25,15,.08)" : ""}`,
          )}
        >
          {text}
        </button>
      ))}
    </div>
  );
}

export function Loading({ what = "Loading" }: { what?: string }) {
  return (
    <div role="status" style={css("display:flex;align-items:center;gap:8px;padding:18px 0;font:400 14px Geist;color:var(--muted)")}>
      <span style={css("width:6px;height:6px;border-radius:50%;background:var(--muted);animation:gnDot 1.2s infinite")} />
      {what}…
    </div>
  );
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div style={css("padding:28px;border-radius:20px;border:1px dashed var(--line2);display:flex;flex-direction:column;gap:8px;align-items:flex-start")}>
      <span style={css("font:500 15px Geist")}>{title}</span>
      {children ? <span style={css("font:400 14px/1.5 Geist;color:var(--ink2)")}>{children}</span> : null}
      {action}
    </div>
  );
}

/** Says what went wrong in plain words, and what to do next. */
export function Failure({ error, retry }: { error: unknown; retry?: () => void }) {
  const status = error instanceof ApiError ? error.status : 0;
  const text = error instanceof Error ? error.message : String(error ?? "Something went wrong.");
  const title = status === 403 ? "You can't open this here" : status === 404 ? "Not found" : status === 409 ? "That can't be done right now" : "Something went wrong";
  return (
    <div role="alert" style={css("padding:16px 18px;border-radius:16px;background:oklch(0.64 0.17 28 / .1);display:flex;flex-direction:column;gap:6px;align-items:flex-start")}>
      <span style={css("font:500 14px Geist")}>{title}</span>
      <span style={css("font:400 14px/1.5 Geist;color:var(--ink2)")}>{text}</span>
      {retry ? (
        <Btn kind="ghostSm" onClick={retry}>
          Try again
        </Btn>
      ) : null}
    </div>
  );
}

/** One query's states: loading, failure (with retry) and empty, then its content. */
export function Loaded<T>({
  q,
  empty,
  children,
}: {
  q: { data?: T; isLoading: boolean; error: unknown; refetch?: () => unknown };
  empty?: (data: T) => ReactNode | null;
  children: (data: T) => ReactNode;
}) {
  if (q.isLoading) return <Loading />;
  if (q.error) return <Failure error={q.error} retry={q.refetch ? () => void q.refetch?.() : undefined} />;
  if (q.data === undefined) return null;
  const nothing = empty ? empty(q.data) : null;
  return <>{nothing ?? children(q.data)}</>;
}

const TONE: Record<string, string> = {
  review: "background:oklch(0.74 0.12 35 / .24)",
  awaiting_review: "background:oklch(0.74 0.12 35 / .24)",
  analysis: "background:oklch(0.74 0.12 80 / .25)",
  analysis_pending: "background:oklch(0.74 0.12 80 / .25)",
  retrying: "background:oklch(0.74 0.12 80 / .25)",
  nothing: "background:var(--soft)",
  nothing_kept: "background:var(--soft)",
  captured: "background:var(--soft)",
  accepted: "box-shadow:inset 0 0 0 1.5px oklch(0.62 0.14 150)",
  indexing: "background:oklch(0.72 0.09 250 / .24)",
  partial: "background:oklch(0.72 0.09 250 / .24)",
  searchable: "background:oklch(0.62 0.14 150 / .22)",
  excluded: "box-shadow:inset 0 0 0 1px var(--line2);color:var(--ink2)",
  skipped: "box-shadow:inset 0 0 0 1px var(--line2);color:var(--ink2)",
  failed: "background:oklch(0.64 0.17 28 / .2)",
  disputed: "background:oklch(0.78 0.11 70 / .3)",
  tentative: "background:oklch(0.78 0.11 70 / .2)",
  conditional: "background:oklch(0.78 0.11 70 / .2)",
  confirmed: "background:oklch(0.62 0.14 150 / .22)",
};

/** A status in words (never color alone), toned like the design. */
export function Status({ kind, children }: { kind: string; children: ReactNode }) {
  return (
    <span
      style={css(
        "display:inline-flex;align-items:center;padding:3px 10px;border-radius:99px;font:500 12px Geist;white-space:nowrap;color:var(--ink);" +
          (TONE[kind] ?? "background:var(--soft)"),
      )}
    >
      {children}
    </span>
  );
}

export function Chip({ children, on = false, onClick }: { children: ReactNode; on?: boolean; onClick?: () => void }) {
  const style = `padding:6px 13px;border-radius:99px;font:${on ? 500 : 400} 12.5px Geist;${
    on ? "background:var(--ink);color:var(--bg);border:1px solid var(--ink)" : "background:transparent;color:var(--ink);border:1px solid var(--line2)"
  }`;
  return onClick ? (
    <button type="button" aria-pressed={on} onClick={onClick} style={css(style)}>
      {children}
    </button>
  ) : (
    <span style={css(style)}>{children}</span>
  );
}

/** A dialog: focus moves into it, Esc closes it, the page behind is covered. */
export function Modal({ title, eyebrow, onClose, children, width = 560 }: { title: string; eyebrow?: string; onClose: () => void; children: ReactNode; width?: number }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    box.current?.focus();
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [onClose]);
  return (
    <div onClick={onClose} style={css("position:fixed;inset:0;background:var(--scrim);z-index:60;display:flex;align-items:center;justify-content:center;padding:20px")}>
      <div
        ref={box}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        style={css(`width:${width}px;max-width:100%;max-height:90vh;overflow:auto;background:var(--surface);border-radius:24px;padding:26px;display:flex;flex-direction:column;gap:14px;box-shadow:var(--shadow2);outline:none`)}
      >
        {eyebrow ? <span style={css(S.eyebrow)}>{eyebrow}</span> : null}
        <span style={css("font:400 26px Newsreader")}>{title}</span>
        {children}
      </div>
    </div>
  );
}

/** Plain words for when something happened ("Oct 21, 10:04"). */
export function when(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return String(iso);
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}
