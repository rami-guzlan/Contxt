// Goals and projects (v4 isProjects): the projects the Brain follows, a nudge for one that has
// gone quiet, New project, and the to-dos from meetings and uploads across all of them. Goals
// are a later phase: shown, never pretended to work.

import { useCallback, useState } from "react";
import { useNavigate } from "react-router";

import type { BrainProject, TaskItem } from "../../api/types";
import { css } from "../css";
import { flatTasks, useBrainProjects, useCreateBrainProject, useHandOff, useProjectTasks, useUpdateProject } from "../hooks/projects";
import { Btn, Chip, Empty, Failure, Later, Loading, Modal, S, Status } from "../ui";

const DAY = 86_400_000;

function daysSince(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? null : Math.floor((Date.now() - t) / DAY);
}

export function ago(iso: string | null | undefined): string {
  const days = daysSince(iso);
  if (days === null) return "No updates yet";
  if (days <= 0) return "Active today";
  if (days === 1) return "Active yesterday";
  return `Active ${days} days ago`;
}

const STATUS_WORDS: Record<string, [string, string]> = {
  active: ["confirmed", "Active"],
  paused: ["tentative", "Paused"],
  blocked: ["disputed", "Blocked"],
  done: ["captured", "Done"],
};

export function ProjectStatus({ status }: { status: string }) {
  const [kind, words] = STATUS_WORDS[status] ?? ["captured", status || "Active"];
  return <Status kind={kind}>{words}</Status>;
}

export function ProjectsPage() {
  const navigate = useNavigate();
  const projects = useBrainProjects();
  const tasks = useProjectTasks();
  const [making, setMaking] = useState(false);
  // A stable close keeps the dialog from taking focus back whenever the lists refresh.
  const close = useCallback(() => setMaking(false), []);
  const all = flatTasks(tasks.data);
  const open = all.filter((t) => t.status !== "done" && t.status !== "dropped");
  const list = projects.data ?? [];
  const quiet = list.find((p) => p.active && (daysSince(p.updated) ?? 0) >= 7);

  return (
    <div className="gn-page" style={css("max-width:1080px;margin:0 auto;padding:56px 64px 96px;display:flex;flex-direction:column;gap:36px;box-sizing:border-box")}>
      <div style={css("display:flex;flex-direction:column;gap:8px")}>
        <h1 style={css(S.h1)}>Goals and projects</h1>
        <span style={css("font:400 17px Geist;color:var(--ink2)")}>What's in motion. Your AI knows where each one stands.</span>
      </div>

      <div style={css("display:flex;flex-direction:column;gap:14px")}>
        <span style={css("font:500 15px Geist")}>
          Goals
          <Later />
        </span>
        <span style={css(S.muted)}>Goals with measures are a later phase. Projects below work now.</span>
      </div>

      {quiet ? <QuietNudge project={quiet} /> : null}

      <div style={css("display:flex;justify-content:space-between;align-items:center;margin-bottom:-18px")}>
        <span style={css("font:500 15px Geist")}>Projects</span>
        <Btn kind="primarySm" onClick={() => setMaking(true)}>
          New project
        </Btn>
      </div>

      {projects.isLoading ? (
        <Loading what="Loading projects" />
      ) : projects.error ? (
        <Failure error={projects.error} retry={() => void projects.refetch()} />
      ) : (
        <div style={css("display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,300px),1fr));gap:16px")}>
          {list.map((p) => (
            <ProjectCard
              key={p.id}
              p={p}
              open={open.filter((t) => t.project === p.id).length}
              tasksKnown={Boolean(tasks.data)}
              onOpen={() => navigate(`/projects/${encodeURIComponent(p.id)}`)}
            />
          ))}
          <button
            type="button"
            onClick={() => setMaking(true)}
            style={css("border-radius:22px;border:1.5px dashed var(--line2);background:transparent;padding:20px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;min-height:220px;color:var(--ink2)")}
          >
            <span style={css("font:400 30px Newsreader")}>+</span>
            <span style={css("font:500 14px Geist")}>New project</span>
            <span style={css("font:400 12px Geist;color:var(--muted)")}>
              {list.length === 0 ? "No projects yet. Start one here." : "Name it and say what it's chasing"}
            </span>
          </button>
        </div>
      )}

      <div style={css("display:flex;flex-direction:column;gap:10px")}>
        <div style={css("display:flex;justify-content:space-between;align-items:baseline")}>
          <span style={css("font:500 15px Geist")}>To-dos from meetings and uploads</span>
          <span style={css("font:400 13px Geist;color:var(--muted)")}>{tasks.data ? `${open.length} open` : ""}</span>
        </div>
        {tasks.isLoading ? (
          <Loading what="Loading to-dos" />
        ) : tasks.error ? (
          <Failure error={tasks.error} retry={() => void tasks.refetch()} />
        ) : open.length === 0 ? (
          <Empty title="No open to-dos">Pull them from a meeting in Capture, or add one in a project's Tasks.</Empty>
        ) : (
          <div style={css("background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:4px 20px")}>
            {open.map((t) => (
              <TodoRow key={t.id} t={t} projectName={list.find((p) => p.id === t.project)?.title ?? "No project"} />
            ))}
          </div>
        )}
      </div>

      {making ? <NewProject onClose={close} onMade={(id) => navigate(`/projects/${encodeURIComponent(id)}`)} /> : null}
    </div>
  );
}

function ProjectCard({ p, open, tasksKnown, onOpen }: { p: BrainProject; open: number; tasksKnown: boolean; onOpen: () => void }) {
  const meta = [`${p.files} ${p.files === 1 ? "file" : "files"}`, `${p.updates} ${p.updates === 1 ? "update" : "updates"}`];
  if (tasksKnown) meta.push(`${open} ${open === 1 ? "to-do" : "to-dos"} open`);
  return (
    <button
      type="button"
      onClick={onOpen}
      className="gn-hover"
      style={css("background:var(--surface);border:0;border-radius:22px;box-shadow:var(--shadow);padding:18px;display:flex;flex-direction:column;gap:12px;text-align:left;color:var(--ink)")}
    >
      <div style={css("display:flex;align-items:center;gap:8px;flex-wrap:wrap")}>
        <ProjectStatus status={p.status} />
        <span style={css("font:400 12px Geist;color:var(--muted)")}>{ago(p.updated)}</span>
      </div>
      <span style={css("font:400 22px/1.25 Newsreader")}>{p.title}</span>
      <span style={css("font:400 13.5px/1.5 Geist;color:var(--ink2)")}>{p.current || p.summary || "Where it stands isn't recorded yet."}</span>
      <span style={css("font:400 12px Geist;color:var(--muted);margin-top:auto")}>{meta.join(" · ")}</span>
    </button>
  );
}

/** A project that has not moved for a week: ask where it is. Each answer is a progress update. */
function QuietNudge({ project }: { project: BrainProject }) {
  const update = useUpdateProject(project.id);
  const days = daysSince(project.updated) ?? 7;
  const answers: [string, string, Record<string, string>][] = [
    ["Still active", "Still active.", {}],
    ["Paused", "Paused for now.", { status: "paused" }],
    ["Done", "Done.", { status: "done" }],
  ];
  if (update.isSuccess) return null;
  return (
    <div style={css("display:flex;align-items:center;gap:10px;padding:16px 20px;border-radius:18px;background:var(--soft);flex-wrap:wrap")}>
      <span style={css("font:400 15px Geist;flex:1;min-width:240px")}>
        {project.title} hasn't moved in {days} days. Where is it?
      </span>
      {answers.map(([label, summary, state]) => (
        <button
          key={label}
          type="button"
          disabled={update.isPending}
          onClick={() => update.mutate({ summary, state })}
          style={css("padding:7px 14px;border-radius:99px;border:1px solid var(--line2);background:var(--surface);font:500 13px Geist;color:var(--ink)")}
        >
          {label}
        </button>
      ))}
      {update.error ? (
        <span role="alert" style={css("flex-basis:100%;font:400 13px Geist;color:oklch(0.55 0.17 28)")}>
          {(update.error as Error).message}
        </span>
      ) : null}
    </div>
  );
}

function TodoRow({ t, projectName }: { t: TaskItem; projectName: string }) {
  const handOff = useHandOff();
  const done = t.status === "done";
  return (
    <div style={css("display:flex;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid var(--line);flex-wrap:wrap")}>
      <button
        type="button"
        role="checkbox"
        aria-checked={done}
        aria-label={`Mark ${t.task} done`}
        disabled={done || handOff.isPending}
        onClick={() => handOff.mutate({ task: t.id, status: "done" })}
        style={css(
          "width:22px;height:22px;flex:none;border-radius:50%;padding:0;display:flex;align-items:center;justify-content:center;font:500 11px Geist;" +
            (done ? "background:var(--ink);color:var(--bg);border:0" : "border:1.5px solid var(--line2);background:transparent;color:transparent"),
        )}
      >
        ✓
      </button>
      <span style={css("font:400 15px Geist;flex:1;min-width:180px;" + (done ? "color:var(--muted);text-decoration:line-through" : "color:var(--ink)"))}>{t.task}</span>
      <span style={css("font:400 13px Geist;color:var(--muted)")}>{projectName}</span>
      <span style={css("font:400 12px Geist;color:var(--muted)")}>
        {t.id} · {t.status_words || t.status} · {t.owner_label || t.owner}
      </span>
      {handOff.error ? (
        <span role="alert" style={css("flex-basis:100%;font:400 13px Geist;color:oklch(0.55 0.17 28)")}>
          {(handOff.error as Error).message}
        </span>
      ) : null}
    </div>
  );
}

/** New project: its name, the output it's chasing (it opens every brief), and other names. */
export function NewProject({ onClose, onMade }: { onClose: () => void; onMade: (id: string) => void }) {
  const create = useCreateBrainProject();
  const [name, setName] = useState("");
  const [objective, setObjective] = useState("");
  const [aliases, setAliases] = useState("");
  const ready = name.trim().length > 0 && objective.trim().length > 0;

  function save() {
    if (!ready) return;
    const goal = objective.trim();
    create.mutate(
      {
        name: name.trim(),
        summary: goal.slice(0, 300),
        objective: goal,
        aliases: aliases
          .split(",")
          .map((a) => a.trim())
          .filter(Boolean),
      },
      { onSuccess: (p) => onMade(p.id) },
    );
  }

  const field = "border:1px solid var(--line2);border-radius:12px;padding:11px 14px;outline:none;background:var(--surface);color:var(--ink);font:400 15px Geist";
  return (
    <Modal title="New project" onClose={onClose}>
      <input aria-label="Project name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Name, e.g. Spring webinar series" style={css(field)} />
      <div style={css("display:flex;flex-direction:column;gap:8px")}>
        <span style={css("font:500 13px Geist")}>
          What kind of project?
          <Later />
        </span>
        <span style={css("font:400 12px/1.45 Geist;color:var(--muted)")}>
          Templates are a later phase. Every project starts with Context, Tasks, Files and Outputs.
        </span>
      </div>
      <textarea
        aria-label="Objective"
        value={objective}
        onChange={(e) => setObjective(e.target.value)}
        rows={2}
        placeholder="The output it's chasing. This opens every brief in it."
        style={css(field + ";resize:none;line-height:1.5")}
      />
      <div style={css("display:flex;flex-direction:column;gap:8px")}>
        <span style={css("font:500 13px Geist")}>
          Which goals does it serve?
          <Later />
        </span>
        <div style={css(S.wrap)}>
          <Chip>Goals are a later phase</Chip>
        </div>
      </div>
      <input
        aria-label="Other names"
        value={aliases}
        onChange={(e) => setAliases(e.target.value)}
        placeholder="Other names you'll call it, comma separated"
        style={css(field)}
      />
      {create.error ? (
        <span role="alert" style={css("font:400 13px Geist;color:oklch(0.55 0.17 28)")}>
          {(create.error as Error).message}
        </span>
      ) : null}
      <div style={css("display:flex;gap:8px;justify-content:flex-end;align-items:center")}>
        {!ready ? <span style={css(S.small + ";margin-right:auto")}>Give it a name and an objective.</span> : null}
        <Btn kind="ghost" onClick={onClose}>
          Cancel
        </Btn>
        <Btn kind="primary" onClick={save} disabled={!ready || create.isPending}>
          {create.isPending ? "Creating…" : "Create"}
        </Btn>
      </div>
    </Modal>
  );
}
