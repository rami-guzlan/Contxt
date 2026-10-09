// Work's overview: its parts and what each is for, what waits for you, and what ran last. The
// way in for someone new is the ladder from doing to delegating: show it once (Compose), write it
// down (a skill), hand it off (an agent with a schedule).

import { Link } from "react-router";

import { useOutputs, useSkills } from "../../api/hooks";
import { LatestRuns } from "../../components/SkillWork";
import { Section } from "../../components/ui";
import { plural } from "../../lib/format";
import { OUTPUTS, SKILLS } from "../../lib/links";

interface Part {
  title: string;
  question: string;
  text: string;
  to?: string;
  count?: string;
}

export function WorkOverviewPage() {
  const { data: skills } = useSkills();
  const { data: outputs } = useOutputs();
  const parts: Part[] = [
    {
      title: "Compose",
      question: "How you ask",
      text: "A prompt box with your skills, agents, docs and library to pick from. See the whole prompt, improve it and save it.",
    },
    {
      title: "Workspace",
      question: "Where you think",
      text: "Your own docs, plans and links, by project. Private until you share them; your AI drafts from them when you ask.",
    },
    {
      title: "Skills",
      question: "How it makes things",
      text: "Procedures your AI follows, with their files. Run one here, or ask for it in any AI you connect.",
      to: SKILLS,
      count: skills ? plural(skills.skills.length, "skill") : undefined,
    },
    {
      title: "Agents",
      question: "Who does the work",
      text: "Roles written like a job description, pointing to the skills, references and context they need.",
    },
    {
      title: "Workflows",
      question: "When it runs",
      text: "Steps that run on a schedule, with a button or from any AI, and wait for your yes before anything that matters.",
    },
    {
      title: "Library",
      question: "What good looks like",
      text: "Guides to follow, references to read whole, and influences whose taste to borrow, kept current.",
    },
    {
      title: "Outputs",
      question: "What it made",
      text: "Every file your AI made, with what it was made from.",
      to: OUTPUTS,
      count: outputs ? plural(outputs.files.length, "file") : undefined,
    },
  ];
  const waiting = skills?.waiting ?? [];
  return (
    <div className="work-tab work-overview">
      <p className="work-ladder">
        <strong>Show it</strong> once in Compose, <strong>write it down</strong> as a skill, <strong>hand it off</strong> to an agent with a
        schedule. Each part reads from your Brain, so the work stays current.
      </p>
      {waiting.length ? (
        <Section title="Waiting for you">
          <p className="notice small">
            {plural(waiting.length, "skill")} waiting in <Link to="/review">Review</Link>: {waiting.map((w) => `/${w.name}`).join(", ")}.
          </p>
        </Section>
      ) : null}
      <ul className="work-parts" aria-label="The parts of Work">
        {parts.map((part) => (
          <li key={part.title} className="work-part">
            <p className="work-part-question">{part.question}</p>
            <h2>{part.to ? <Link to={part.to}>{part.title}</Link> : part.title}</h2>
            <p>{part.text}</p>
            {part.count ? <p className="muted small">{part.count}</p> : null}
          </li>
        ))}
      </ul>
      <LatestRuns />
    </div>
  );
}
