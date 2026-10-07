// What the Brain is for, in the person's own words: one question at a time, talked or typed,
// with a follow-up when Claude Code on this computer can ask one, then a playback to edit and
// keep. Everything brought in later is summarized and sifted against these answers. Used by
// the first run and by Settings, Your goals.

import { ArrowLeft, ArrowRight, Check, Mic } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  useBrainProjects,
  useCreateBrainProject,
  useDownloadSpeech,
  useGoalFollowup,
  useGoals,
  useRunners,
  useSetGoals,
  useSpeech,
} from "../api/hooks";
import type { GoalQuestion, Goals } from "../api/types";
import { plural } from "../lib/format";
import { TalkButton, useTalk } from "./Talk";
import { ErrorNote, Loading } from "./ui";

export const SIFT_LINE =
  "Everything you bring in later (meetings, files, notes) is summarized and sifted against what you say here. The clearer you are, the better it picks.";

/** Is Claude Code on this computer ready to ask a follow-up? */
function canFollowUp(runners: { provider: string; installed: boolean; signed_in: boolean | null }[] | undefined): boolean {
  return !!runners?.some((r) => r.provider === "claude-code" && r.installed && r.signed_in !== false);
}

/** "What is in motion", one per line: the projects it could start. */
export function linesOf(text: string | undefined): string[] {
  return (text ?? "")
    .split("\n")
    .map((line) => line.replace(/^[\s*-]+/, "").trim())
    .filter(Boolean);
}

export function GoalsInterview({ onDone, startAt = 0 }: { onDone: (goals: Goals) => void; startAt?: number }) {
  const { data: goals, isLoading, error } = useGoals();
  if (isLoading) return <Loading />;
  if (!goals) return <ErrorNote error={error} />;
  return <Interview goals={goals} onDone={onDone} startAt={startAt} />;
}

function Interview({ goals, onDone, startAt }: { goals: Goals; onDone: (goals: Goals) => void; startAt: number }) {
  const [answers, setAnswers] = useState<Record<string, string>>(() => ({ ...goals.answers }));
  const [index, setIndex] = useState(Math.min(startAt, goals.questions.length - 1));
  const [playback, setPlayback] = useState(false);
  const [followups, setFollowups] = useState<Record<string, string | null>>({});
  const { data: runners } = useRunners();
  const followup = useGoalFollowup();
  const answer = (id: string, text: string) => setAnswers((current) => ({ ...current, [id]: text }));
  const question = goals.questions[index];
  if (!question) return <ErrorNote error="The questions could not be read. Reload the page." />;

  const next = () => {
    if (!question) return;
    const text = (answers[question.id] ?? "").trim();
    const asked = question.id in followups;
    if (text && !asked && canFollowUp(runners) && text !== (goals.answers[question.id] ?? "").trim()) {
      followup.mutate(
        { question: question.question, answer: text },
        {
          onSuccess: (reply) => {
            setFollowups((current) => ({ ...current, [question.id]: reply.followup }));
            if (!reply.followup) advance();
          },
          // No follow-up is no loss: the fixed questions work on their own.
          onError: () => {
            setFollowups((current) => ({ ...current, [question.id]: null }));
            advance();
          },
        },
      );
      return;
    }
    advance();
  };

  const advance = () => {
    if (index + 1 < goals.questions.length) setIndex(index + 1);
    else setPlayback(true);
  };

  if (playback) {
    return <Playback goals={goals} answers={answers} onChange={answer} onBack={() => setPlayback(false)} onDone={onDone} />;
  }
  const required = question.required && !(answers[question.id] ?? "").trim();
  return (
    <div className="interview">
      {index === 0 ? <p className="lede">{SIFT_LINE}</p> : null}
      <p className="interview-progress muted small">
        Question {index + 1} of {goals.questions.length}
        {question.required ? "" : ". You can skip this one."}
      </p>
      <QuestionCard
        question={question}
        value={answers[question.id] ?? ""}
        onChange={(text) => answer(question.id, text)}
        followup={followups[question.id] ?? null}
      />
      <div className="row interview-actions">
        <button type="button" disabled={index === 0 || followup.isPending} onClick={() => setIndex(index - 1)}>
          <ArrowLeft className="button-icon" aria-hidden="true" />
          Back
        </button>
        {!question.required ? (
          <button type="button" className="link" disabled={followup.isPending} onClick={advance}>
            Skip
          </button>
        ) : null}
        <button type="button" className="primary" disabled={required || followup.isPending} onClick={next}>
          {followup.isPending ? "Thinking of one more question…" : index + 1 < goals.questions.length ? "Next" : "See what I heard"}
          {followup.isPending ? null : <ArrowRight className="button-icon" aria-hidden="true" />}
        </button>
        {followup.isPending ? (
          <button
            type="button"
            className="link"
            onClick={() => {
              followup.reset();
              setFollowups((current) => ({ ...current, [question.id]: null }));
              advance();
            }}
          >
            Skip the follow-up
          </button>
        ) : null}
      </div>
    </div>
  );
}

/** One question: why it matters, an example for this kind of Brain, and the answer, talked or
 * typed. While it is on screen, Space and the Talk button write into the answer. */
function QuestionCard({
  question,
  value,
  onChange,
  followup,
}: {
  question: GoalQuestion;
  value: string;
  onChange: (text: string) => void;
  followup: string | null;
}) {
  const talk = useTalk();
  const { data: speech } = useSpeech();
  const download = useDownloadSpeech();
  const setTarget = talk?.setTarget;
  // What was said is added to the answer as it reads when the words come back.
  const latest = useRef({ value, onChange });
  latest.current = { value, onChange };
  useEffect(() => {
    if (!setTarget) return;
    setTarget({
      label: "your answer",
      add: (text) => {
        const { value: now, onChange: change } = latest.current;
        change(now.trim() ? `${now.trim()} ${text}` : text);
      },
    });
    return () => setTarget(null);
  }, [setTarget, question.id]);
  const id = `goal-${question.id}`;
  return (
    <div className="question-card">
      <label htmlFor={id} className="question-title">
        {question.question}
      </label>
      <p className="muted">{question.why}</p>
      <textarea
        id={id}
        rows={question.id === "in_motion" ? 5 : 4}
        value={value}
        placeholder={`For example: ${question.example.split("\n").join(", ")}`}
        onChange={(event) => onChange(event.target.value)}
      />
      {followup ? (
        <p className="followup" role="status">
          <strong>One more thing:</strong> {followup} <span className="muted">Add it above, or go on.</span>
        </p>
      ) : null}
      <div className="row small">
        {talk ? <TalkButton /> : null}
        <span className="muted">
          <Mic className="button-icon" aria-hidden="true" /> Hold Space to talk (outside the box), or type.
        </span>
        {speech && speech.installed && !speech.ready ? (
          <button type="button" className="link" disabled={speech.downloading || download.isPending} onClick={() => download.mutate()}>
            {speech.downloading || download.isPending ? "Downloading the speech model…" : `Set up talking (${speech.about_mb} MB, once)`}
          </button>
        ) : null}
      </div>
    </div>
  );
}

/** "Here is what I heard": the purpose, the answers, what to leave out, and the projects to
 * start; edited, then kept as one undo point. */
function Playback({
  goals,
  answers,
  onChange,
  onBack,
  onDone,
}: {
  goals: Goals;
  answers: Record<string, string>;
  onChange: (id: string, text: string) => void;
  onBack: () => void;
  onDone: (goals: Goals) => void;
}) {
  const save = useSetGoals();
  const start = useCreateBrainProject();
  const { data: projects } = useBrainProjects();
  const known = useMemo(() => {
    const names = new Set<string>();
    for (const p of projects ?? []) {
      names.add(p.title.toLowerCase());
      for (const alias of p.aliases) names.add(alias.toLowerCase());
    }
    return names;
  }, [projects]);
  const motion = linesOf(answers.in_motion);
  const fresh = motion.filter((name) => !known.has(name.toLowerCase()));
  const [chosen, setChosen] = useState<string[]>(fresh);
  const [failed, setFailed] = useState<string[]>([]);
  const [saved, setSaved] = useState<Goals | null>(null);

  const keep = async () => {
    const result = await save.mutateAsync(answers);
    const left: string[] = [];
    for (const name of chosen) {
      try {
        await start.mutateAsync({ name, summary: `${name}, from your goals: what is in motion.`, aliases: [] });
      } catch {
        left.push(name);
      }
    }
    setFailed(left);
    setSaved(result);
  };

  if (saved) {
    return (
      <div className="interview playback" role="status">
        <h2>
          <Check className="button-icon" aria-hidden="true" /> Your goals are kept
        </h2>
        <p>
          From now on, everything you bring in is sifted against this. Change it any time in Settings, Your goals.
          {chosen.length - failed.length ? ` ${plural(chosen.length - failed.length, "project")} started.` : ""}
        </p>
        {failed.length ? <p className="warning small">Not started: {failed.join(", ")}. Start them from Projects.</p> : null}
        <button type="button" className="primary" onClick={() => onDone(saved)}>
          Continue
        </button>
      </div>
    );
  }
  const shown = goals.questions.filter((q) => q.id !== "purpose" && q.id !== "in_motion" && (answers[q.id] ?? "").trim());
  return (
    <div className="interview playback">
      <h2>Here is what I heard</h2>
      <label className="field">
        <span className="field-label">What your Brain is for</span>
        <textarea rows={2} value={answers.purpose ?? ""} onChange={(event) => onChange("purpose", event.target.value)} />
      </label>
      {shown.map((q) => (
        <label className="field" key={q.id}>
          <span className="field-label">{q.question}</span>
          <textarea rows={2} value={answers[q.id] ?? ""} onChange={(event) => onChange(q.id, event.target.value)} />
        </label>
      ))}
      {motion.length ? (
        <fieldset className="field">
          <legend className="field-label">Projects to start</legend>
          {motion.map((name) => {
            const exists = known.has(name.toLowerCase());
            return (
              <label key={name} className="check">
                <input
                  type="checkbox"
                  disabled={exists}
                  checked={exists || chosen.includes(name)}
                  onChange={(event) => setChosen((current) => (event.target.checked ? [...current, name] : current.filter((n) => n !== name)))}
                />{" "}
                {name}
                {exists ? <span className="muted small"> · already a project</span> : null}
              </label>
            );
          })}
        </fieldset>
      ) : null}
      <p className="muted small">Your own words go straight in, with an undo point. Nothing from here waits for review.</p>
      <ErrorNote error={save.error} />
      <div className="row">
        <button type="button" onClick={onBack}>
          <ArrowLeft className="button-icon" aria-hidden="true" />
          Back
        </button>
        <button type="button" className="primary" disabled={save.isPending || !(answers.purpose ?? "").trim()} onClick={() => void keep()}>
          {save.isPending ? "Keeping…" : "Keep my goals"}
        </button>
      </div>
    </div>
  );
}
