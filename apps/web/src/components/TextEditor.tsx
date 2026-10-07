// Editing a piece of context in place: its title, its one-line summary and its Markdown text,
// written or previewed. Nothing is saved until the caller acts on what `onSave` hands it.

import { useState } from "react";

import { Markdown } from "./Markdown";
import { Field } from "./ui";

export interface Draft {
  title: string;
  summary: string;
  body: string;
}

export function TextEditor({
  label,
  initial,
  withSummary = true,
  saveLabel = "Keep these edits",
  onSave,
  onCancel,
}: {
  label: string;
  initial: Draft;
  withSummary?: boolean;
  saveLabel?: string;
  onSave: (draft: Draft) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState<Draft>(initial);
  const [preview, setPreview] = useState(false);
  const set = (changes: Partial<Draft>) => setDraft((current) => ({ ...current, ...changes }));
  const lines = draft.body.split("\n").length;
  return (
    <div className="text-editor" role="group" aria-label={label}>
      <Field label="Title">
        <input value={draft.title} onChange={(event) => set({ title: event.target.value })} />
      </Field>
      {withSummary ? (
        <Field label="One-line summary" hint="What a model reads before deciding to open it.">
          <input value={draft.summary} onChange={(event) => set({ summary: event.target.value })} />
        </Field>
      ) : null}
      <div className="editor-tabs" role="tablist" aria-label="Write or preview">
        <button type="button" role="tab" aria-selected={!preview} className={preview ? "tab" : "tab active"} onClick={() => setPreview(false)}>
          Write
        </button>
        <button type="button" role="tab" aria-selected={preview} className={preview ? "tab active" : "tab"} onClick={() => setPreview(true)}>
          Preview
        </button>
      </div>
      {preview ? (
        <div className="document compact">
          <Markdown text={draft.body} />
        </div>
      ) : (
        <textarea
          aria-label="Text"
          value={draft.body}
          rows={Math.min(24, Math.max(6, lines + 2))}
          onChange={(event) => set({ body: event.target.value })}
        />
      )}
      <p className="muted small">Markdown works here: **bold**, lists, links, tables.</p>
      <div className="row">
        <button type="button" className="primary" disabled={!draft.body.trim()} onClick={() => onSave(draft)}>
          {saveLabel}
        </button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

/** Only what the person changed: the fields a decision should carry. */
export function changes(initial: Draft, draft: Draft): Partial<Draft> {
  const out: Partial<Draft> = {};
  if (draft.body.trim() !== initial.body.trim()) out.body = draft.body.trim();
  if (draft.title.trim() && draft.title.trim() !== initial.title.trim()) out.title = draft.title.trim();
  if (draft.summary.trim() && draft.summary.trim() !== initial.summary.trim()) out.summary = draft.summary.trim();
  return out;
}
