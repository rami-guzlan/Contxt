// Work, Skills: the procedures your AI follows to make things (a post, a proposal, a deck), each
// with what it loads from the Brain and the files it needs. Every AI you connect finds them; here
// you run them and see what they make, improve them, write new ones, and look back at each version.

import { WandSparkles } from "lucide-react";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { brainFileUrl, useAddBuiltinSkills, useBrainSkill, useBuiltinSkills, useNote, useSkills } from "../../api/hooks";
import type { BrainCheckpoint, SkillCard, SkillVersion } from "../../api/types";
import { Markdown } from "../../components/Markdown";
import {
  ImproveSkill,
  LatestRuns,
  NewSkill,
  RunSkill,
  Saved,
  SkillEditor,
  SkillHistory,
  SkillRuns,
  makesLine,
} from "../../components/SkillWork";
import { FirstVisitTip } from "../../components/Tips";
import { BringInSkill, SkillAboutLine, SkillCopies, SuggestedSkills } from "../../components/work/SkillExtras";
import { Empty, ErrorNote, Loading, Pill, Section, Tabs } from "../../components/ui";
import { bytes, label, plural, when } from "../../lib/format";
import { SKILLS, skillUrl } from "../../lib/links";
import { fileViewUrl } from "../brain/shared";
import { ScopeChip } from "../../components/work/Scope";

/** A skill's description, cut at its first sentence or two: what it does, not every trigger. */
function gist(description: string, limit = 180): string {
  const text = description.replace(/\s+/g, " ").trim();
  const sentences = text.match(/[^.!?]+[.!?]+(\s|$)/g) ?? [text];
  let out = "";
  for (const sentence of sentences) {
    if (out && (out + sentence).length > limit) break;
    out += sentence;
  }
  out = out.trim() || text;
  return out.length > limit ? `${out.slice(0, limit - 1)}…` : out;
}

export function SkillsPage() {
  const { data, isLoading, error } = useSkills();
  const [params, setParams] = useSearchParams();
  const teaching = params.get("capture");
  const { data: capture } = useNote(teaching ?? "");
  const writing = params.get("new") === "1" || !!teaching;
  const [bringing, setBringing] = useState(false);
  if (isLoading) return <Loading />;
  if (!data) return <ErrorNote error={error} />;
  const byCategory = new Map<string, SkillCard[]>();
  for (const skill of data.skills) {
    const category = skill.category || "general";
    byCategory.set(category, [...(byCategory.get(category) ?? []), skill]);
  }
  const startNew = () => setParams({ new: "1" });
  return (
    <div className="work-tab skills">
      <div className="work-intro">
        <p>
          How your AI makes things: each skill is a procedure it follows, with what it loads from the Brain and the files it needs. Run one
          here and see what it makes, or ask for it in any AI you connect.
        </p>
        {!writing ? (
          <div className="row">
            <button type="button" className="primary" onClick={startNew}>
              New skill
            </button>
            <button type="button" aria-expanded={bringing} onClick={() => setBringing(!bringing)}>
              Bring one in
            </button>
          </div>
        ) : null}
      </div>
      {bringing ? <BringInSkill onClose={() => setBringing(false)} /> : null}
      <FirstVisitTip id="skills">
        A skill is how your AI makes something, step by step. Run one here, or just ask for it in any AI you connect: it finds the skill.
      </FirstVisitTip>
      {writing ? (
        <NewSkill
          capture={teaching && capture ? { id: capture.id, title: capture.title } : null}
          initial={params.get("ask") ?? ""}
          onClose={() => setParams({})}
        />
      ) : null}
      {data.skills.some((s) => s.use === "run") ? (
        <section className="skill-panel" aria-label="Run skills">
          <h2>Run skills</h2>
          <p className="muted small">
            Run one or several with a prompt, in the order you pick, with your notes and documents, and see the whole prompt your AI gets
            before it runs.
          </p>
          <Link className="button primary" to="/work/prompts/new?run=1">
            Run skills with a prompt
          </Link>
        </section>
      ) : null}
      <SuggestedSkills onWrite={(ask) => setParams({ new: "1", ask })} />
      <LatestRuns />
      <BuiltIns />
      {data.waiting.length ? (
        <p className="notice small">
          Waiting in <Link to="/review">Review</Link>: {data.waiting.map((w) => `/${w.name}`).join(", ")}. Approve{" "}
          {data.waiting.length === 1 ? "it" : "them"} to put {data.waiting.length === 1 ? "it" : "them"} to work.
        </p>
      ) : null}
      {data.skills.length ? (
        [...byCategory].map(([category, list], index) => (
          <Section key={category} title={label(category)} tour={index === 0 ? "skills-list" : undefined}>
            <ul className="skill-grid">
              {list.map((skill) => (
                <li key={skill.name} className="skill-card">
                  <WandSparkles className="skill-icon" aria-hidden="true" />
                  <Link to={skillUrl(skill.name)} className="skill-card-title">
                    /{skill.name}
                  </Link>
                  <ScopeChip />
                  {skill.description ? <p className="skill-card-text">{gist(skill.description)}</p> : null}
                  {skill.use === "run" && skill.triggers[0] ? (
                    <p className="skill-card-meta muted small" title="Your AI picks it up when you ask like this, in any chat">
                      Ask: “{skill.triggers[0]}”
                    </p>
                  ) : null}
                  {skill.use === "support" ? (
                    <p className="skill-card-meta muted small">
                      Used by other skills ({plural(skill.used_by.length, "skill")}), not run on its own
                    </p>
                  ) : skill.use === "chat" ? (
                    <p className="skill-card-meta muted small">Use it in a chat: /{skill.name}</p>
                  ) : (
                    <>
                      <p className="skill-card-meta muted small">
                        {[makesLine(skill.artifacts, skill.makes_files), skill.last_run ? `ran ${when(skill.last_run.at)}` : ""]
                          .filter(Boolean)
                          .join(" · ") || plural(skill.files, "file")}
                      </p>
                      <Link to={skillUrl(skill.name)} className="button small" aria-label={`Run /${skill.name}`}>
                        Run it here
                      </Link>
                    </>
                  )}
                </li>
              ))}
            </ul>
          </Section>
        ))
      ) : (
        <Empty why="No skills yet. A skill is a procedure your AI follows to make something, like a post or a proposal, with the templates it needs.">
          {!writing ? (
            <button type="button" className="primary" onClick={startNew}>
              Write your first skill
            </button>
          ) : null}
        </Empty>
      )}
    </div>
  );
}

const TABS = [
  { id: "run", label: "Run" },
  { id: "procedure", label: "Procedure" },
  { id: "improve", label: "Improve" },
  { id: "history", label: "History" },
  { id: "files", label: "Files" },
] as const;
type Tab = (typeof TABS)[number]["id"];

// One skill: run it, read and edit its procedure, improve it, its versions and its files.
export function SkillPage() {
  const { name = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const { data: skill, isLoading, error } = useBrainSkill(name);
  const { data: cards } = useSkills();
  // Words to ask for it that the knowledge agent suggested (?add=a|b): the editor opens with
  // them added, for the person to look over and save.
  const added = (params.get("add") ?? "")
    .split("|")
    .map((t) => t.trim())
    .filter(Boolean);
  const [editing, setEditing] = useState<SkillVersion | "current" | null>(added.length ? "current" : null);
  const [saved, setSaved] = useState<BrainCheckpoint | null>(null);
  if (isLoading) return <Loading />;
  if (!skill) return <ErrorNote error={error} />;
  const card = cards?.skills.find((s) => s.name === skill.name);
  // Files other skills build on (fonts, logos) are kept here, not run; the Brain's own
  // housekeeping runs in a conversation, where it has the tools it needs.
  const runs = !card || card.use === "run";
  const tabs = runs ? TABS : TABS.filter((t) => t.id !== "run");
  const first: Tab = runs ? "run" : "procedure";
  const asked = params.get("tab");
  const tab: Tab = tabs.some((t) => t.id === asked) ? (asked as Tab) : first;
  const show = (next: Tab) => setParams(next === first ? {} : { tab: next }, { replace: true });
  const source = procedure(skill.text);
  const makes = makesLine(skill.artifacts ?? [], card?.makes_files ?? false);
  const restore = (version: SkillVersion) => {
    setEditing(version);
    setSaved(null);
    show("procedure");
  };
  return (
    <div className="skill-page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to={SKILLS}>Skills</Link>
        {skill.category ? (
          <>
            <span aria-hidden="true">/</span>
            <span>{label(skill.category)}</span>
          </>
        ) : null}
      </nav>
      <header className="entry-head">
        <h1>/{skill.name}</h1>
        {skill.description ? <p className="lede">{gist(skill.description, 320)}</p> : null}
        {card?.use === "chat" ? (
          <p className="notice small">
            It works on your Brain from a conversation: type <code>/{skill.name}</code> in Claude Code or any AI you connect, where it has
            the Brain's tools.
          </p>
        ) : null}
        {card?.used_by.length ? (
          <p className="muted small">
            {card.use === "support" ? "Other skills use its files: " : "Other skills build on it: "}
            {card.used_by.map((name, index) => (
              <span key={name}>
                {index ? ", " : ""}
                <Link to={skillUrl(name)}>/{name}</Link>
              </span>
            ))}
            {card.use === "support" ? ". It is not run on its own." : "."}
          </p>
        ) : null}
        {runs && (makes || card?.last_run) ? (
          <p className="muted small">
            {makes}
            {makes && card?.last_run ? " · " : ""}
            {card?.last_run ? (
              <>
                last ran {when(card.last_run.at)} <Pill status={card.last_run.status} />
              </>
            ) : null}
          </p>
        ) : null}
        <SkillAboutLine name={skill.name} />
      </header>
      <Tabs tabs={tabs} active={tab} onChange={show} />
      {tab === "run" ? (
        <div className="stack">
          <RunSkill name={skill.name} triggers={skill.triggers ?? []} makesFiles={card?.makes_files ?? false} />
          <Section title="What it made">
            <SkillRuns name={skill.name} kind="run" />
          </Section>
        </div>
      ) : null}
      {tab === "procedure" ? (
        <div className="entry-layout">
          <div className="stack">
            {saved ? <Saved checkpoint={saved} onUndone={() => setSaved(null)} /> : null}
            {editing ? (
              <SkillEditor
                key={editing === "current" ? "current" : editing.ref}
                skill={{
                  name: skill.name,
                  description: skill.description,
                  when_to_use: skill.when_to_use,
                  triggers: [...new Set([...(skill.triggers ?? []), ...(editing === "current" ? added : [])])],
                  body: editing === "current" ? source : (editing.body ?? source),
                }}
                saved={skill.triggers ?? []}
                onDone={(checkpoint) => {
                  setEditing(null);
                  setSaved(checkpoint);
                }}
              />
            ) : (
              <>
                <div className="row">
                  <button type="button" onClick={() => setEditing("current")}>
                    Edit
                  </button>
                  <button type="button" onClick={() => show("improve")}>
                    Ask your AI to improve it
                  </button>
                </div>
                <div className="document">
                  <Markdown text={withoutHeading(source, skill.name)} />
                </div>
              </>
            )}
          </div>
          <aside className="entry-side">
            {skill.when_to_use ? (
              <Section title="When to use it">
                <p>{skill.when_to_use}</p>
              </Section>
            ) : null}
            {skill.triggers?.length ? (
              <Section title="What you say to ask for it">
                <ul className="list">
                  {skill.triggers.map((trigger) => (
                    <li key={trigger}>“{trigger}”</li>
                  ))}
                </ul>
              </Section>
            ) : null}
            {skill.loads.length ? (
              <Section title="What it loads">
                <ul className="list">
                  {skill.loads.map((item) => (
                    <li key={item}>
                      <code>{item}</code>
                    </li>
                  ))}
                </ul>
              </Section>
            ) : null}
            {skill.depends_on?.length ? (
              <Section title="What it builds on">
                <ul className="list">
                  {skill.depends_on.map((item) => (
                    <li key={item}>
                      <Link to={skillUrl(item, "files")}>/{item}</Link>
                    </li>
                  ))}
                </ul>
              </Section>
            ) : null}
          </aside>
        </div>
      ) : null}
      {tab === "improve" ? (
        <div className="stack">
          <ImproveSkill
            key={params.get("example") ?? "none"}
            name={skill.name}
            example={params.get("example")}
            onClearExample={() => setParams({ tab: "improve" }, { replace: true })}
          />
          <Section title="Improvements asked for">
            <SkillRuns name={skill.name} kind="improve" />
          </Section>
        </div>
      ) : null}
      {tab === "history" ? <SkillHistory name={skill.name} onRestore={restore} /> : null}
      {tab === "files" ? (
        <Section title="Files">
          <ul className="list">
            {skill.files.map((file) => (
              <li key={file.path} className="file-line">
                <Link to={fileViewUrl(file.path)}>{file.title}</Link>
                <span className="muted"> · {bytes(file.size)} </span>
                <a href={brainFileUrl(file.path)} download aria-label={`Download ${file.title}`}>
                  Download
                </a>
              </li>
            ))}
          </ul>
          <SkillCopies name={skill.name} />
        </Section>
      ) : null}
    </div>
  );
}

/** The procedure as its file holds it, without the lines the Brain puts above it for models
 * (what it loads, its folder): what an edit starts from. */
function procedure(text: string): string {
  const lines = text.split("\n");
  const folder = lines.findIndex((line) => line.startsWith("Folder: "));
  let body = folder >= 0 && lines[0]?.startsWith("# /") ? lines.slice(folder + 1) : lines;
  while (body.length && !body[0]?.trim()) body = body.slice(1);
  return body.join("\n");
}

/** The procedure to read, without its "# /name" heading (the page says the name). */
function withoutHeading(source: string, name: string): string {
  const lines = source.split("\n");
  return lines[0]?.trim() === `# /${name}` ? lines.slice(1).join("\n") : source;
}

/** The skills every Brain comes with: the knowledge agent, the knowledge check, teaching it,
 * wrapping up a chat and the goals interview. An older Brain can add the ones it lacks. */
function BuiltIns() {
  const { data } = useBuiltinSkills();
  const add = useAddBuiltinSkills();
  if (!data?.skills.length) return null;
  return (
    <Section title="Comes with every Brain">
      <ul className="list builtins">
        {data.skills.map((skill) => (
          <li key={skill.name}>
            {skill.installed ? <Link to={skillUrl(skill.name)}>/{skill.name}</Link> : <span>/{skill.name}</span>}
            <span className="muted small"> · {gist(skill.description, 140)}</span>
            {skill.installed ? null : <span className="chip small">Not in this Brain yet</span>}
          </li>
        ))}
      </ul>
      {data.missing.length ? (
        <button type="button" className="primary" disabled={add.isPending} onClick={() => add.mutate(undefined)}>
          {add.isPending ? "Adding…" : `Add the ${plural(data.missing.length, "missing one")}`}
        </button>
      ) : null}
      <ErrorNote error={add.error} />
    </Section>
  );
}

