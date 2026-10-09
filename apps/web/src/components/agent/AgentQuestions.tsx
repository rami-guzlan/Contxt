// The knowledge agent's questions for the owner, each with the one-tap answers its kind allows:
// a note can be confirmed, retired or marked disputed; a question is answered in a sentence (it
// becomes a suggested note); anything can be set aside.

import { useState } from "react";
import { Link } from "react-router";

import { useAnswerAgentQuestion } from "../../api/hooks";
import type { AgentQuestion } from "../../api/types";
import { ErrorNote } from "../ui";

const ACTION_WORDS: Record<string, string> = {
  "tidy-repeats": "Repeats",
  "check-drift": "Drift",
  "check-alignment": "Alignment",
  "freshen-up": "Freshness",
  "tidy-projects": "Projects",
  "tidy-skills": "Skills",
  "fill-gaps": "Gaps",
};

function targetLink(question: AgentQuestion): string | null {
  const { type, id } = question.target;
  if (type === "note") return `/brain/entries/${encodeURIComponent(id)}`;
  if (type === "project") return `/projects/${encodeURIComponent(id)}`;
  if (type === "skill") return `/skills/${encodeURIComponent(id)}`;
  if (type === "goals") return "/settings?tab=goals";
  return null;
}

export function AgentQuestionCard({ question, compact = false }: { question: AgentQuestion; compact?: boolean }) {
  const answer = useAnswerAgentQuestion();
  const [writing, setWriting] = useState(false);
  const [text, setText] = useState("");
  const link = targetLink(question);
  const note = question.target.type === "note";
  const words = question.target.type === "gap" || question.target.type === "goals" || (note && question.verdict === "ask");
  const act = (what: "verify" | "retire" | "dispute" | "answer" | "done" | "dismiss", said?: string) =>
    answer.mutate({ key: question.key, do: what, text: said });
  if (answer.isSuccess) {
    const done = answer.data;
    return (
      <article className="agent-question done" aria-label={question.ask}>
        <p className="small" role="status">
          {done.do === "answer" ? (
            <>
              Kept as a suggestion: it waits in <Link to="/catch-up">Catch up</Link>.
            </>
          ) : done.do === "retire" ? (
            "Retired. Undo it from Activity, Changes."
          ) : done.do === "dispute" ? (
            "Marked disputed until you settle it."
          ) : done.do === "verify" ? (
            "Confirmed as still true."
          ) : (
            "Done."
          )}
        </p>
      </article>
    );
  }
  return (
    <article className={compact ? "agent-question compact" : "agent-question"} aria-label={question.ask}>
      <p className="agent-question-kind muted small">
        {ACTION_WORDS[question.action] ?? question.action}
        {link ? (
          <>
            {" · "}
            <Link to={link}>{question.target.title}</Link>
          </>
        ) : null}
      </p>
      <p className="agent-question-ask">{question.ask}</p>
      {question.text && question.text !== question.ask ? <p className="agent-question-text">{question.text}</p> : null}
      {question.triggers?.length ? (
        <ul className="chips">
          {question.triggers.map((t) => (
            <li key={t} className="chip">
              {t}
            </li>
          ))}
        </ul>
      ) : null}
      {question.why ? <p className="muted small">{question.why}</p> : null}
      {writing ? (
        <form
          className="stack-tight"
          onSubmit={(event) => {
            event.preventDefault();
            if (text.trim()) act("answer", text.trim());
          }}
        >
          <label className="field">
            <span className="field-label">Your answer</span>
            <textarea rows={2} value={text} onChange={(event) => setText(event.target.value)} />
          </label>
          <div className="row">
            <button type="submit" className="primary" disabled={!text.trim() || answer.isPending}>
              Teach it
            </button>
            <button type="button" className="link" onClick={() => setWriting(false)}>
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <div className="row agent-question-actions">
          {note && question.verdict === "retire" ? (
            <>
              <button type="button" className="primary" disabled={answer.isPending} onClick={() => act("retire")}>
                Retire it
              </button>
              <button type="button" disabled={answer.isPending} onClick={() => act("dismiss")}>
                Keep it
              </button>
            </>
          ) : note && question.verdict === "dispute" ? (
            <>
              <button type="button" className="primary" disabled={answer.isPending} onClick={() => act("dispute")}>
                Mark disputed
              </button>
              <button type="button" disabled={answer.isPending} onClick={() => act("dismiss")}>
                Not now
              </button>
            </>
          ) : note && question.verdict === "ask" ? (
            <>
              <button type="button" className="primary" disabled={answer.isPending} onClick={() => act("verify")}>
                Still true
              </button>
              <button type="button" disabled={answer.isPending} onClick={() => setWriting(true)}>
                It changed
              </button>
              <button type="button" disabled={answer.isPending} onClick={() => act("retire")}>
                Retire it
              </button>
            </>
          ) : words ? (
            <>
              <button type="button" className="primary" disabled={answer.isPending} onClick={() => setWriting(true)}>
                Answer
              </button>
              <button type="button" disabled={answer.isPending} onClick={() => act("dismiss")}>
                Not now
              </button>
            </>
          ) : (
            <>
              {link ? (
                <Link className="button primary" to={link}>
                  Open it
                </Link>
              ) : null}
              <button type="button" disabled={answer.isPending} onClick={() => act("done")}>
                Done
              </button>
              <button type="button" className="link" disabled={answer.isPending} onClick={() => act("dismiss")}>
                Not now
              </button>
            </>
          )}
        </div>
      )}
      <ErrorNote error={answer.error} />
    </article>
  );
}

export function AgentQuestions({ questions, compact = false }: { questions: AgentQuestion[]; compact?: boolean }) {
  if (!questions.length) return <p className="muted small">No questions from the agent right now.</p>;
  return (
    <div className="agent-questions">
      {questions.map((q) => (
        <AgentQuestionCard key={q.key} question={q} compact={compact} />
      ))}
    </div>
  );
}
