// See the difference: the same request answered twice by the same model, once with nothing and
// once with what your Brain hands over, side by side, each difference linked to the note that
// caused it. Without Claude Code on this computer: the two prompts to paste into any AI. A demo
// Brain's own before and after pairs show what good looks like.

import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { useBrainPreview, useBrainProjects, useDifference, useExamples, useRunners, useStartDifference } from "../api/hooks";
import type { Comparison, DifferenceExample, DifferencePiece } from "../api/types";
import { entryUrl } from "../pages/brain/shared";
import { CopyBlock, ErrorNote, Loading } from "./ui";

const STEPS: Record<Comparison["step"], string> = {
  without: "Answering without your Brain…",
  with: "Answering with it…",
  differences: "Comparing the two…",
  done: "Done",
};

export const FAIR = "Same model, same request, same settings. The only difference is what your Brain handed over.";

function pieceUrl(piece: DifferencePiece | undefined, id: string): string | null {
  if (!id) return null;
  if (piece?.kind === "project" || piece?.kind === "focus") return `/projects/${encodeURIComponent(id)}`;
  if (piece?.kind === "section" || piece?.kind === "reference") return null;
  return entryUrl(id);
}

/** "It got 640 tokens, about a tenth of your Brain." */
export function costLine(tokens: number, brainTokens: number, kernelTokens: number): string {
  const share = brainTokens ? tokens / brainTokens : 0;
  const part =
    share <= 0
      ? ""
      : share < 0.05
        ? ", a small slice of your Brain"
        : share < 0.15
          ? ", about a tenth of your Brain"
          : `, ${Math.round(share * 100)}% of your Brain`;
  const kernel = kernelTokens ? ` Every chat also gets the short startup note once (${kernelTokens.toLocaleString()} tokens).` : "";
  return `It got ${tokens.toLocaleString()} tokens${part}.${kernel}`;
}

export function SideBySide({
  without,
  withContext,
  differences,
  pieces,
}: {
  without: string;
  withContext: string;
  differences: { what: string; item: string }[];
  pieces: DifferencePiece[];
}) {
  const byId = new Map(pieces.map((p) => [p.id, p]));
  return (
    <div className="difference">
      <div className="compare">
        <div className="compare-side">
          <p className="compare-label">Without your Brain</p>
          <div className="prewrap">{without}</div>
        </div>
        <div className="compare-side with">
          <p className="compare-label">With your Brain</p>
          <div className="prewrap">{withContext}</div>
        </div>
      </div>
      {differences.length ? (
        <>
          <h3>What changed, and why</h3>
          <ul className="list differences">
            {differences.map((d) => {
              const piece = byId.get(d.item);
              const url = pieceUrl(piece, d.item);
              return (
                <li key={d.what}>
                  {d.what}
                  {piece ? (
                    <span className="muted">
                      {" "}
                      · {url ? <Link to={url}>{piece.title}</Link> : piece.title}
                    </span>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </>
      ) : null}
    </div>
  );
}

export function SeeTheDifference({ suggestions = [] }: { suggestions?: string[] }) {
  const { data: runners, isLoading } = useRunners();
  const { data: examples } = useExamples();
  // Which way it runs decides the whole panel: wait to know, rather than swap under the person.
  if (isLoading) return <Loading />;
  const ready = !!runners?.some((r) => r.provider === "claude-code" && r.installed && r.signed_in !== false);
  return (
    <div className="see-difference">
      {ready ? <Live suggestions={suggestions} /> : <Paste suggestions={suggestions} />}
      {examples?.length ? <Examples examples={examples} /> : null}
    </div>
  );
}

function Asker({ suggestions, onAsk, busy, label }: { suggestions: string[]; onAsk: (request: string, project: string) => void; busy: boolean; label: string }) {
  const [draft, setDraft] = useState("");
  const [project, setProject] = useState("");
  const { data: projects } = useBrainProjects();
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (draft.trim()) onAsk(draft.trim(), project);
  };
  return (
    <form className="preview-ask" onSubmit={submit}>
      <label className="sr-only" htmlFor="difference-request">
        A request to try both ways
      </label>
      <input
        id="difference-request"
        value={draft}
        placeholder="Type a request, or pick one below"
        onChange={(event) => setDraft(event.target.value)}
      />
      {(projects?.length ?? 0) > 0 ? (
        <select aria-label="Project" value={project} onChange={(event) => setProject(event.target.value)}>
          <option value="">Any project</option>
          {(projects ?? []).filter((p) => p.active).map((p) => (
            <option key={p.id} value={p.id}>
              {p.title}
            </option>
          ))}
        </select>
      ) : null}
      <button type="submit" className="primary" disabled={!draft.trim() || busy}>
        {label}
      </button>
      {suggestions.length ? (
        <div className="chips">
          {suggestions.map((s) => (
            <button key={s} type="button" className="chip-button" onClick={() => setDraft(s)}>
              {s}
            </button>
          ))}
        </div>
      ) : null}
    </form>
  );
}

function Live({ suggestions }: { suggestions: string[] }) {
  const start = useStartDifference();
  const [id, setId] = useState<string | null>(null);
  const { data: comparison } = useDifference(id);
  return (
    <>
      <Asker
        suggestions={suggestions}
        busy={start.isPending || comparison?.status === "running"}
        label="Run it both ways"
        onAsk={(request, project) => start.mutate({ request, project: project || undefined }, { onSuccess: (made) => setId(made.id) })}
      />
      <p className="muted small">{FAIR} It runs on Claude Code on this computer and takes a minute or two.</p>
      <ErrorNote error={start.error} />
      {comparison ? <ComparisonView comparison={comparison} /> : null}
    </>
  );
}

function ComparisonView({ comparison }: { comparison: Comparison }) {
  if (comparison.status === "failed") return <p className="error">{comparison.error ?? "It could not finish. Try again."}</p>;
  if (comparison.status === "running") {
    return (
      <p className="muted" role="status">
        {STEPS[comparison.step]}
      </p>
    );
  }
  return (
    <>
      <SideBySide without={comparison.without} withContext={comparison.with_context} differences={comparison.differences} pieces={comparison.pieces} />
      <p className="small muted">{costLine(comparison.tokens, comparison.brain_tokens, comparison.kernel_tokens)}</p>
    </>
  );
}

/** No runner here: what to paste into any AI, without and with the Brain. */
function Paste({ suggestions }: { suggestions: string[] }) {
  const [asked, setAsked] = useState("");
  const [project, setProject] = useState("");
  const { data: preview, isFetching, error } = useBrainPreview(asked, project);
  return (
    <>
      <Asker
        suggestions={suggestions}
        busy={isFetching}
        label="Show both prompts"
        onAsk={(request, scope) => {
          setAsked(request);
          setProject(scope);
        }}
      />
      <p className="muted small">
        Paste each into the same AI, in two new chats, and compare. {FAIR} With Claude Code on this computer, the app runs both for you (Settings, On
        this computer).
      </p>
      {isFetching ? <Loading /> : null}
      <ErrorNote error={error} />
      {preview && asked && !isFetching ? (
        <div className="compare">
          <CopyBlock label="Without your Brain" text={asked} />
          <CopyBlock label={`With your Brain (${preview.tokens.toLocaleString()} tokens of context)`} text={`${preview.text}\n\n---\n\n${asked}`} />
        </div>
      ) : null}
    </>
  );
}

function Examples({ examples }: { examples: DifferenceExample[] }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="examples">
      <h3>From this Brain, made earlier</h3>
      {examples.map((example) => (
        <details key={example.id} open={open === example.id} onToggle={(event) => setOpen((event.target as HTMLDetailsElement).open ? example.id : null)}>
          <summary>“{example.request}”</summary>
          <SideBySide without={example.without} withContext={example.with_context} differences={example.differences} pieces={example.pieces} />
          <p className="small muted">
            {costLine(example.tokens, example.brain_tokens, example.kernel_tokens)} {example.note}
          </p>
        </details>
      ))}
    </div>
  );
}
