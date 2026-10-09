// Skills, upgraded: bring one in (a zip, a folder, a GitHub repository), skills worth writing
// down (asks repeated with no skill to follow, prompts run often), and on each skill's page what
// uses it, when it was edited and used, what it loads that changed since, and its copies in
// Claude Code with how far behind each is.

import { Download, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router";

import {
  skillExportUrl,
  useBringInSkill,
  useBringInSkillFromGit,
  useDismissSuggestion,
  usePushSkill,
  useSkillAbout,
  useSkillSuggestions,
} from "../../api/hooks";
import type { SkillBroughtIn } from "../../api/types";
import { when } from "../../lib/format";
import { skillUrl } from "../../lib/links";
import { ErrorNote, Field, Section } from "../ui";

// ---------------------------------------------------------------- bringing one in

export function BringInSkill({ onClose }: { onClose: () => void }) {
  const bring = useBringInSkill();
  const fromGit = useBringInSkillFromGit();
  const zip = useRef<HTMLInputElement>(null);
  const folder = useRef<HTMLInputElement>(null);
  const [url, setUrl] = useState("");
  const [done, setDone] = useState<SkillBroughtIn | null>(null);
  const busy = bring.isPending || fromGit.isPending;
  const took = (made: SkillBroughtIn) => setDone(made);
  return (
    <section className="skill-panel" aria-label="Bring a skill in">
      <h2>Bring a skill in</h2>
      <p className="muted small">
        A skill is a folder with a SKILL.md (Contxt's, or the Agent Skills format), beside its scripts, assets and references. It goes in at
        once, with an undo point, like your own edits.
      </p>
      <div className="row">
        <button type="button" disabled={busy} onClick={() => zip.current?.click()}>
          <Upload className="button-icon" aria-hidden="true" /> A zip
        </button>
        <button type="button" disabled={busy} onClick={() => folder.current?.click()}>
          <Upload className="button-icon" aria-hidden="true" /> A folder
        </button>
        <input
          ref={zip}
          type="file"
          hidden
          accept=".zip,application/zip"
          aria-label="A skill as a zip"
          onChange={(event) => {
            const picked = event.target.files?.[0];
            if (picked) bring.mutate({ zip: picked }, { onSuccess: took });
            event.target.value = "";
          }}
        />
        <input
          ref={folder}
          type="file"
          hidden
          multiple
          aria-label="A skill's folder"
          // A folder picker: the browser sends each file with its path inside the folder.
          {...{ webkitdirectory: "" }}
          onChange={(event) => {
            const picked = Array.from(event.target.files ?? []);
            if (picked.length) bring.mutate({ files: picked }, { onSuccess: took });
            event.target.value = "";
          }}
        />
      </div>
      <form
        className="inline-form"
        onSubmit={(event) => {
          event.preventDefault();
          fromGit.mutate({ url: url.trim() }, { onSuccess: took });
        }}
      >
        <Field label="Or from GitHub" hint="The repository, or the skill's folder in it. Private ones use this computer's own git sign-in.">
          <input type="url" value={url} placeholder="https://github.com/owner/name/tree/main/skills/brand-voice" onChange={(event) => setUrl(event.target.value)} />
        </Field>
        <button type="submit" disabled={!url.trim() || busy}>
          {fromGit.isPending ? "Fetching…" : "Bring it in"}
        </button>
      </form>
      <ErrorNote error={bring.error ?? fromGit.error} />
      {done ? (
        <div className="notice small" role="status">
          <p>
            <Link to={skillUrl(done.name)}>/{done.name}</Link> {done.replaced ? "has its new version" : "is in"}, with {done.files} file
            {done.files === 1 ? "" : "s"} beside its SKILL.md.
          </p>
          {done.skipped.length ? (
            <>
              <p>Left out:</p>
              <ul>
                {done.skipped.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      ) : null}
      <div className="row">
        <button type="button" onClick={onClose}>
          Close
        </button>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- worth writing down

export function SuggestedSkills({ onWrite }: { onWrite: (ask: string) => void }) {
  const { data } = useSkillSuggestions();
  const dismiss = useDismissSuggestion();
  const found = data?.suggestions ?? [];
  if (!found.length) return null;
  return (
    <Section title="Worth writing down">
      <p className="muted small">
        {data?.matched_by === "meaning"
          ? "Asks your AIs got again and again with no skill to follow (alike by meaning), and prompts you run often."
          : "Asks your AIs got again and again with no skill to follow (alike by their words, until the Brain's local model is downloaded), and prompts you run often."}
      </p>
      <ul className="workspace-list" aria-label="Skills worth writing down">
        {found.map((s) => (
          <li key={s.key} className="workspace-row">
            <span className="kind-chip kind-guide">{s.count}×</span>
            <div className="workspace-row-main">
              <strong>{s.kind === "prompt" ? `Your prompt “${s.title}”` : s.title}</strong>
              {s.kind === "asks" ? (
                <ul className="small muted">
                  {s.examples.slice(1, 3).map((e) => (
                    <li key={e}>“{e}”</li>
                  ))}
                </ul>
              ) : null}
              <p className="muted small">
                {s.kind === "prompt" ? `Run ${s.count} times` : `Asked ${s.count} times${s.apps.length ? ` in ${s.apps.join(", ")}` : ""}`}
                {s.last ? `, last ${when(s.last)}` : ""}
              </p>
              <div className="row small">
                <button type="button" className="primary" onClick={() => onWrite(s.ask)}>
                  Write it as a skill
                </button>
                <button type="button" disabled={dismiss.isPending} onClick={() => dismiss.mutate(s.key)}>
                  Not now
                </button>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </Section>
  );
}

// ---------------------------------------------------------------- one skill

export function SkillAboutLine({ name }: { name: string }) {
  const { data } = useSkillAbout(name);
  if (!data) return null;
  const fresh = data.freshness;
  const users = data.used_by;
  return (
    <div className="stack-tight skill-about">
      <p className="muted small">
        {fresh.last_edited ? `Last edited ${when(fresh.last_edited)}` : "Never edited here"}
        {" · "}
        {fresh.last_used ? `last used ${when(fresh.last_used)}` : "not used yet"}
        {users.agents.length || users.workflows.length ? " · used by " : ""}
        {users.agents.map((agent, index) => (
          <span key={agent}>
            {index ? ", " : ""}
            <Link to={`/work/agents/${encodeURIComponent(agent)}`}>{agent}</Link>
          </span>
        ))}
        {users.agents.length && users.workflows.length ? ", " : ""}
        {users.workflows.map((workflow, index) => (
          <span key={workflow.id}>
            {index ? ", " : ""}
            <Link to={`/work/workflows/${encodeURIComponent(workflow.id)}`}>{workflow.name}</Link>
          </span>
        ))}
      </p>
      {fresh.changed.length ? (
        <p className="notice small">
          What it loads changed after its last edit: {fresh.changed.map((c) => `${c.title} (${when(c.at)})`).join(", ")}. Read it again, or{" "}
          <Link to={`${skillUrl(name)}?tab=improve`}>ask your AI to bring it up to date</Link>.
        </p>
      ) : null}
    </div>
  );
}

export function SkillCopies({ name }: { name: string }) {
  const { data } = useSkillAbout(name);
  const push = usePushSkill();
  const [project, setProject] = useState("");
  const [other, setOther] = useState(false);
  const copies = data?.pushed ?? [];
  const mine = copies.find((c) => c.user);
  return (
    <section className="skill-panel" aria-label="Elsewhere">
      <h2>Take it elsewhere</h2>
      <p className="muted small">
        Any AI connected to your Brain reads the current version itself (get_skill). A copy is for tools that need the files on disk.
      </p>
      <div className="row">
        <a className="button" href={skillExportUrl(name)} download>
          <Download className="button-icon" aria-hidden="true" /> Export as a zip
        </a>
        <button type="button" disabled={push.isPending} onClick={() => push.mutate({ name })}>
          {mine ? "Update the copy in Claude Code" : "Copy it into Claude Code"}
        </button>
        <button type="button" className="link small" aria-expanded={other} onClick={() => setOther(!other)}>
          Into a project instead
        </button>
      </div>
      {other ? (
        <form
          className="inline-form"
          onSubmit={(event) => {
            event.preventDefault();
            push.mutate({ name, projectDir: project.trim() });
          }}
        >
          <Field label="The project's folder" hint="It goes in .claude/skills inside it.">
            <input value={project} placeholder="C:\\Users\\you\\code\\project" onChange={(event) => setProject(event.target.value)} />
          </Field>
          <button type="submit" disabled={!project.trim() || push.isPending}>
            Copy it there
          </button>
        </form>
      ) : null}
      {copies.length ? (
        <ul className="list compact-list" aria-label="Its copies">
          {copies.map((copy) => (
            <li key={copy.place}>
              <span className="small">{copy.user ? "Claude Code (yours)" : copy.place}</span>
              <span className={copy.behind ? "notice small" : "muted small"}>
                {" · "}
                {copy.behind === 0
                  ? "current"
                  : copy.behind === null
                    ? "older than the history kept: update it"
                    : `${copy.behind} version${copy.behind === 1 ? "" : "s"} behind: update it`}
                {copy.pushed_at ? ` · copied ${when(copy.pushed_at)}` : ""}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      <ErrorNote error={push.error} />
    </section>
  );
}
