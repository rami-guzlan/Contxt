// "What your AI gets": type a request the way you would ask any AI, and see the context the
// Brain would hand it, piece by piece with why each is there, then the context itself.
// Nothing is recorded: a preview is not a conversation.

import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { useBrainPreview, useBrainProjects } from "../api/hooks";
import type { BrainPreview } from "../api/types";
import { entryUrl, fileViewUrl } from "../pages/brain/shared";
import { Markdown } from "./Markdown";
import { ErrorNote, Loading } from "./ui";

const EXAMPLE = "Tighten the LinkedIn part of the campaign proposal";

export function ContextPreview({ project, example = EXAMPLE }: { project?: string; example?: string }) {
  const [draft, setDraft] = useState("");
  const [asked, setAsked] = useState("");
  const [scope, setScope] = useState(project ?? "");
  const { data: projects } = useBrainProjects();
  const { data, isFetching, error } = useBrainPreview(asked, scope);

  function submit(event: FormEvent) {
    event.preventDefault();
    setAsked(draft.trim());
  }

  return (
    <div className="preview" data-tour="brain-preview">
      <form className="preview-ask" onSubmit={submit}>
        <label className="sr-only" htmlFor="preview-request">
          What you would ask your AI
        </label>
        <input
          id="preview-request"
          value={draft}
          placeholder={`Ask as you would ask your AI: "${example}"`}
          onChange={(event) => setDraft(event.target.value)}
        />
        {project === undefined && (projects?.length ?? 0) > 0 ? (
          <select aria-label="Project" value={scope} onChange={(event) => setScope(event.target.value)}>
            <option value="">Any project</option>
            {(projects ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </select>
        ) : null}
        <button type="submit" className="primary" disabled={!draft.trim()}>
          Show what it gets
        </button>
      </form>
      {isFetching ? <Loading /> : null}
      <ErrorNote error={error} />
      {data && asked && !isFetching ? <PreviewResult preview={data} /> : null}
    </div>
  );
}

function PreviewResult({ preview }: { preview: BrainPreview }) {
  const nothing =
    !preview.project && !preview.procedure && !preview.notes.length && !preview.sections.length;
  return (
    <div className="preview-result" aria-live="polite">
      {nothing ? (
        <p className="muted">
          Nothing in your Brain fits this request, so your AI would answer from general knowledge and say so.
        </p>
      ) : (
        <ul className="preview-why">
          {preview.project ? (
            <li>
              <span className="why-kind">Project</span>
              <span>
                {preview.project.title} <span className="muted">(where it stands, its latest progress, its files)</span>
              </span>
            </li>
          ) : null}
          {preview.sections.map((part) => (
            <li key={part.id}>
              <span className="why-kind">From a file</span>
              <span>
                <Link to={fileViewUrl(part.file)}>{part.title}</Link>: {part.label}{" "}
                <span className="muted">({part.why})</span>
              </span>
            </li>
          ))}
          {preview.notes.map((note) => (
            <li key={note.id}>
              <span className="why-kind">Note</span>
              <span>
                <Link to={entryUrl(note.id)}>{note.title}</Link> <span className="muted">({note.why})</span>
              </span>
            </li>
          ))}
          {preview.procedure ? (
            <li>
              <span className="why-kind">Procedure</span>
              <span>/{preview.procedure}</span>
            </li>
          ) : null}
        </ul>
      )}
      <details className="preview-text">
        <summary>The context itself, about {preview.tokens.toLocaleString()} tokens</summary>
        <Markdown text={preview.text} />
      </details>
    </div>
  );
}
