// Work, Outputs: what your AI made, in the outputs folder beside your Brain. Folders to organize,
// files newest first, a download or a look in place, move and rename (never over another file,
// never a delete), and for each file what it was made from: the skill run and what it was
// handed, the export it came from, or the chat that saved it and what that chat got.

import { Download, Eye, FolderPlus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { outputFileUrl, useBrainProjects, useLinkOutput, useMadeFrom, useMakeOutputFolder, useMoveOutput, useOutputs } from "../../api/hooks";
import type { OutputFile, RequestPiece } from "../../api/types";
import { Empty, ErrorNote, Loading } from "../../components/ui";
import { bytes, plural, when } from "../../lib/format";
import { skillUrl } from "../../lib/links";
import { RequestRow } from "../Activity";
import { entryUrl } from "../brain/shared";
import { ScopeChip } from "../../components/work/Scope";

const KIND_WORDS: Record<string, string> = {
  document: "Document",
  pdf: "PDF",
  slides: "Slides",
  spreadsheet: "Spreadsheet",
  image: "Image",
  page: "Web page",
  data: "Data",
  audio: "Audio",
  video: "Video",
};

export function OutputsPage() {
  const { data, isLoading, error } = useOutputs();
  const { data: projects } = useBrainProjects();
  const [folder, setFolder] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [group, setGroup] = useState<"project" | "folder">("project");
  const [filter, setFilter] = useState({ project: "", entity: "", maker: "", kind: "", q: "" });
  if (isLoading) return <Loading />;
  if (!data) return <ErrorNote error={error} />;
  const titles = new Map((projects ?? []).map((p) => [p.id, p.title]));
  const inFolder = folder === null ? data.files : data.files.filter((f) => f.folder === folder || f.folder.startsWith(`${folder}/`));
  const files = inFolder.filter(
    (f) =>
      (!filter.project || (filter.project === "none" ? !f.project : f.project === filter.project)) &&
      (!filter.entity || f.for === filter.entity) &&
      (!filter.maker || (f.maker ?? "") === filter.maker) &&
      (!filter.kind || f.kind === filter.kind) &&
      (!filter.q || `${f.name} ${f.title ?? ""}`.toLowerCase().includes(filter.q.toLowerCase())),
  );
  const entities = [...new Set(data.files.map((f) => f.for).filter(Boolean))] as string[];
  const makers = [...new Set(data.files.map((f) => f.maker).filter(Boolean))] as string[];
  const kinds = [...new Set(data.files.map((f) => f.kind))];
  const set = (k: keyof typeof filter, v: string) => setFilter({ ...filter, [k]: v });
  const row = (file: OutputFile) => (
    <FileRow key={file.path} file={file} folders={data.folders} open={open === file.path} onOpen={() => setOpen(open === file.path ? null : file.path)} />
  );
  return (
    <div className="work-tab outputs">
      <div className="work-intro">
        <p>
          What your AI made: everything in your outputs folder, newest first, each with what it was made from.{" "}
          <span className="muted small">The folder: {data.root}</span>
        </p>
      </div>
      <div className="outputs-layout">
        <nav className="folders" aria-label="Folders">
          <button type="button" className={folder === null ? "tab active" : "tab"} onClick={() => setFolder(null)}>
            Everything <span className="muted small">{data.files.length}</span>
          </button>
          {data.folders.map((f) => (
            <button key={f} type="button" className={folder === f ? "tab active" : "tab"} onClick={() => setFolder(f)}>
              {f}
            </button>
          ))}
          <NewFolder />
        </nav>
        <div className="files">
          <div className="row wrap output-filters" aria-label="Filters">
            <label className="small">
              Group by{" "}
              <select value={group} onChange={(event) => setGroup(event.target.value as "project" | "folder")}>
                <option value="project">Project, then what it is for</option>
                <option value="folder">Newest first</option>
              </select>
            </label>
            <select aria-label="Project" value={filter.project} onChange={(event) => set("project", event.target.value)}>
              <option value="">Every project</option>
              {[...titles].map(([id, title]) => (
                <option key={id} value={id}>
                  {title}
                </option>
              ))}
              <option value="none">No project</option>
            </select>
            {entities.length ? (
              <select aria-label="For" value={filter.entity} onChange={(event) => set("entity", event.target.value)}>
                <option value="">Anything it is for</option>
                {entities.map((e) => (
                  <option key={e} value={e}>
                    {e.split("/").slice(1).join("/")}
                  </option>
                ))}
              </select>
            ) : null}
            {makers.length > 1 ? (
              <select aria-label="Made by" value={filter.maker} onChange={(event) => set("maker", event.target.value)}>
                <option value="">Anyone</option>
                {makers.map((m) => (
                  <option key={m}>{m}</option>
                ))}
              </select>
            ) : null}
            <select aria-label="Kind" value={filter.kind} onChange={(event) => set("kind", event.target.value)}>
              <option value="">Every kind</option>
              {kinds.map((k) => (
                <option key={k} value={k}>
                  {KIND_WORDS[k] ?? k}
                </option>
              ))}
            </select>
            <input aria-label="Search outputs" placeholder="Search" value={filter.q} onChange={(event) => set("q", event.target.value)} />
          </div>
          {files.length && group === "project" ? (
            <Grouped files={files} titles={titles} row={row} />
          ) : files.length ? (
            <ul className="file-list">{files.map(row)}</ul>
          ) : (
            <Empty why="Nothing here yet. When a skill makes a file, or your AI saves one for you, it lands in this folder." />
          )}
        </div>
      </div>
    </div>
  );
}

/** By project (the default), then by what each is for (an account's bucket), then newest. */
function Grouped({ files, titles, row }: { files: OutputFile[]; titles: Map<string, string>; row: (f: OutputFile) => React.ReactNode }) {
  const projects = [...new Set(files.map((f) => f.project ?? ""))].sort((a, b) => (a ? (b ? a.localeCompare(b) : -1) : 1));
  return (
    <>
      {projects.map((project) => {
        const mine = files.filter((f) => (f.project ?? "") === project);
        const buckets = [...new Set(mine.map((f) => f.for ?? ""))].sort((a, b) => (a ? (b ? a.localeCompare(b) : -1) : 1));
        return (
          <section key={project || "none"} aria-label={project ? (titles.get(project) ?? project) : "No project"}>
            <h3 className="small-head">{project ? (titles.get(project) ?? project) : "No project"}</h3>
            {buckets.map((bucket) => (
              <div key={bucket || "general"}>
                {buckets.length > 1 || bucket ? <h4 className="small muted">{bucket ? bucket.split("/").slice(1).join("/") : "Not for one entity"}</h4> : null}
                <ul className="file-list">{mine.filter((f) => (f.for ?? "") === bucket).map(row)}</ul>
              </div>
            ))}
          </section>
        );
      })}
    </>
  );
}

function LinkFor({ file }: { file: OutputFile }) {
  const link = useLinkOutput();
  const { data: projects } = useBrainProjects();
  const [row, setRow] = useState(file.for ?? "");
  return (
    <div className="row small">
      <select aria-label={`Project for ${file.name}`} value={file.project ?? ""} onChange={(event) => link.mutate({ path: file.path, project: event.target.value })}>
        <option value="">No project</option>
        {(projects ?? []).map((p) => (
          <option key={p.id} value={p.id}>
            {p.title}
          </option>
        ))}
      </select>
      <input aria-label={`What ${file.name} is for`} placeholder="For (sheet/row)" value={row} onChange={(event) => setRow(event.target.value)} />
      <button type="button" className="link small" onClick={() => link.mutate({ path: file.path, row: row.trim() })}>
        Save
      </button>
      <ErrorNote error={link.error} />
    </div>
  );
}

function NewFolder() {
  const make = useMakeOutputFolder();
  const [name, setName] = useState("");
  const [shown, setShown] = useState(false);
  if (!shown) {
    return (
      <button type="button" className="link small" onClick={() => setShown(true)}>
        <FolderPlus className="button-icon" aria-hidden="true" />
        New folder
      </button>
    );
  }
  return (
    <form
      className="stack-tight"
      onSubmit={(event) => {
        event.preventDefault();
        if (name.trim()) make.mutate(name.trim(), { onSuccess: () => { setName(""); setShown(false); } });
      }}
    >
      <label className="sr-only" htmlFor="new-folder">
        Folder name
      </label>
      <input id="new-folder" value={name} placeholder="Folder name" onChange={(event) => setName(event.target.value)} />
      <button type="submit" disabled={!name.trim() || make.isPending}>
        Make it
      </button>
      <ErrorNote error={make.error} />
    </form>
  );
}

function FileRow({ file, folders, open, onOpen }: { file: OutputFile; folders: string[]; open: boolean; onOpen: () => void }) {
  const [moving, setMoving] = useState(false);
  return (
    <li className="file-row">
      <div className="file-main">
        <button type="button" className="link file-title" aria-expanded={open} onClick={onOpen}>
          {file.name}
        </button>
        <ScopeChip />
        <span className="muted small">
          {KIND_WORDS[file.kind] ?? "File"} · {bytes(file.size)} · {when(file.modified)}
          {file.folder ? ` · ${file.folder}` : ""}
        </span>
        {file.from === "skill" ? <span className="chip small">From a skill run</span> : null}
        {file.from === "chat" ? <span className="chip small">From a chat</span> : null}
        <span className="muted small">Made by {file.maker ?? "you"}</span>
        {file.for ? <span className="chip small">For {file.for.split("/").slice(1).join("/")}</span> : null}
        {file.working ? <span className="chip small">Still being made</span> : null}
      </div>
      <div className="file-actions row">
        <a className="button" href={outputFileUrl(file.path)} download>
          <Download className="button-icon" aria-hidden="true" />
          Download
        </a>
        <a className="button" href={outputFileUrl(file.path, false)} target="_blank" rel="noreferrer">
          <Eye className="button-icon" aria-hidden="true" />
          Open
        </a>
        <button type="button" disabled={file.working} onClick={() => setMoving(!moving)}>
          Move or rename
        </button>
      </div>
      {moving ? <Move file={file} folders={folders} onDone={() => setMoving(false)} /> : null}
      {open ? (
        <>
          <LinkFor file={file} />
          <MadeFromPanel path={file.path} />
        </>
      ) : null}
    </li>
  );
}

function Move({ file, folders, onDone }: { file: OutputFile; folders: string[]; onDone: () => void }) {
  const move = useMoveOutput();
  const [target, setTarget] = useState(file.path);
  return (
    <form
      className="inline-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (target.trim() && target.trim() !== file.path) move.mutate({ source: file.path, target: target.trim() }, { onSuccess: onDone });
      }}
    >
      <label className="field-label" htmlFor={`move-${file.path}`}>
        New place and name
      </label>
      <input id={`move-${file.path}`} list={`folders-${file.path}`} value={target} onChange={(event) => setTarget(event.target.value)} />
      <datalist id={`folders-${file.path}`}>
        {folders.map((f) => (
          <option key={f} value={`${f}/${file.name}`} />
        ))}
      </datalist>
      <button type="submit" className="primary" disabled={move.isPending}>
        Move
      </button>
      <button type="button" className="link" onClick={onDone}>
        Cancel
      </button>
      <ErrorNote error={move.error} />
    </form>
  );
}

function Pieces({ pieces }: { pieces: RequestPiece[] }) {
  if (!pieces.length) return <p className="muted small">Nothing from the Brain was recorded for it.</p>;
  return (
    <ul className="preview-why">
      {pieces.map((p) => (
        <li key={`${p.kind}:${p.id}`}>
          <span className="why-kind">{p.kind === "note" ? "Note" : p.kind === "section" ? "From a file" : p.kind}</span>
          <span>
            {p.kind === "note" ? <Link to={entryUrl(p.id)}>{p.title ?? p.id}</Link> : (p.title ?? p.id)}
            {p.why ? <span className="muted"> ({p.why})</span> : null}
          </span>
        </li>
      ))}
    </ul>
  );
}

function MadeFromPanel({ path }: { path: string }) {
  const { data, isLoading, error } = useMadeFrom(path);
  if (isLoading) return <Loading />;
  if (!data) return <ErrorNote error={error} />;
  return (
    <div className="made-from">
      <h3>Made from</h3>
      {data.how === "skill" && data.skill_run ? (
        <>
          <p>
            The skill <Link to={skillUrl(data.skill_run.skill)}>/{data.skill_run.skill}</Link>, asked: “{data.skill_run.ask}”
            {data.skill_run.project ? ` for ${data.skill_run.project}` : ""}, {when(data.skill_run.created_at)}.
          </p>
          {data.skill_run.capture ? (
            <p className="small">
              From <Link to={`/capture/${encodeURIComponent(data.skill_run.capture.id)}`}>{data.skill_run.capture.title}</Link>
            </p>
          ) : null}
          {(data.given ?? []).map((run) => (
            <div key={run.id}>
              <p className="small muted">What {plural(run.pieces.length, "piece")} of your Brain it was handed:</p>
              <Pieces pieces={run.pieces} />
            </div>
          ))}
        </>
      ) : null}
      {data.how === "export" && data.export ? (
        <>
          <p>
            Exported from “{data.export.title}” ({data.export.type}, version {data.export.version}), {when(data.export.exported_at)}.
          </p>
          {(data.given ?? []).map((run) => (
            <Pieces key={run.id} pieces={run.pieces} />
          ))}
        </>
      ) : null}
      {data.how === "chat" && data.chat ? (
        <>
          <p>
            Saved by {data.chat.app} in a chat{data.chat.title ? `: ${data.chat.title}` : ""}
            {data.chat.at ? `, ${when(data.chat.at)}` : ""}. What that chat asked and got:
          </p>
          <ul className="requests">
            {data.chat.requests.map((r) => (
              <RequestRow key={r.id} request={r} brainTokens={0} />
            ))}
          </ul>
        </>
      ) : null}
      {data.how === "unknown" ? (
        <p className="muted small">
          Made outside the app, or by an AI that did not say. Your connected AIs are asked to record each file they save, with the chat it was made
          in; files they save from now on show it here.
        </p>
      ) : null}
    </div>
  );
}
