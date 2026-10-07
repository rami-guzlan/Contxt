import { cloneElement, isValidElement, useId, useState, type ReactNode } from "react";

import { ApiError } from "../api/client";
import { label } from "../lib/format";

export function Pill({ status }: { status: string }) {
  return <span className={`pill pill-${status}`}>{label(status)}</span>;
}

export function Section({ title, actions, children, tour }: { title: string; actions?: ReactNode; children: ReactNode; tour?: string }) {
  return (
    <section className="section" data-tour={tour}>
      <header className="section-head">
        <h2>{title}</h2>
        {actions ? <div className="section-actions">{actions}</div> : null}
      </header>
      {children}
    </section>
  );
}

export function Empty({ why, children }: { why: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <p>{why}</p>
      {children ? <div className="empty-actions">{children}</div> : null}
    </div>
  );
}

export function Loading() {
  return <p className="muted">Loading…</p>;
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof ApiError ? error.message : error instanceof Error ? error.message : String(error);
  return (
    <p className="error" role="alert">
      {message}
    </p>
  );
}

// A labelled control. The hint describes the control (aria-describedby) without becoming
// part of its name, so screen readers announce "Prompt", then the hint.
export function Field({ label: text, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  const id = useId();
  const hintId = `${id}-hint`;
  const control = isValidElement<{ id?: string; "aria-describedby"?: string }>(children)
    ? cloneElement(children, { id, "aria-describedby": hint ? hintId : undefined })
    : children;
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>
        {text}
      </label>
      {control}
      {hint ? (
        <span id={hintId} className="field-hint">
          {hint}
        </span>
      ) : null}
    </div>
  );
}

export function Tabs<T extends string>({
  tabs,
  active,
  onChange,
  tour,
}: {
  tabs: readonly { id: T; label: string }[];
  active: T;
  onChange: (id: T) => void;
  /** Marks it for the guided tour (data-tour). */
  tour?: string;
}) {
  return (
    <nav className="tabs" role="tablist" data-tour={tour}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          role="tab"
          aria-selected={tab.id === active}
          className={tab.id === active ? "tab active" : "tab"}
          data-tour={tour ? `${tour}-${tab.id}` : undefined}
          onClick={() => onChange(tab.id)}
          type="button"
        >
          {tab.label}
        </button>
      ))}
    </nav>
  );
}

export function CopyBlock({ text, label: title, prose = false }: { text: string; label?: string; prose?: boolean }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className={prose ? "copy-block prose" : "copy-block"}>
      <div className="copy-head">
        <span>{title}</span>
        <button
          type="button"
          className="link"
          onClick={() => {
            void navigator.clipboard?.writeText(text).then(() => setCopied(true));
          }}
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre>{text}</pre>
    </div>
  );
}

export function KeyValues({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="kv">
      {rows
        .filter(([, value]) => value !== null && value !== undefined && value !== "")
        .map(([key, value]) => (
          <div key={key}>
            <dt>{key}</dt>
            <dd>{value}</dd>
          </div>
        ))}
    </dl>
  );
}
