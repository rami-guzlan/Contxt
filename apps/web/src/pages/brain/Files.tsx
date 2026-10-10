import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router";

import { brainFileUrl, keys, useBrainCatalog, useBrainFiles } from "../../api/hooks";
import type { BrainFile, BrainSkill } from "../../api/types";
import { Markdown } from "../../components/Markdown";
import { KnowledgeCheck, PullWhatMatters } from "../../components/Pull";
import { Empty, ErrorNote, Loading } from "../../components/ui";
import { ScopeChip } from "../../components/work/Scope";
import { bytes, label, plural, when } from "../../lib/format";
import { ORIGIN_GROUPS, originGroup, originLine, type OriginGroup } from "../../lib/origins";
import { AddFileDialog } from "./AddFile";
import { TypeBadge, entryUrl, filesTab, isImage, isText, libraryItemUrl } from "./shared";

// Media, fonts and templates: what people open a Brain's files for, wherever they are kept.
// Skills often keep their logos, fonts and deck templates in their own folders.
const ASSET_FILE = /\.(png|jpe?g|gif|webp|svg|ico|ttf|otf|woff2?|mp3|wav|m4a|mp4|mov|webm|pdf|pptx|potx|docx|dotx|xlsx|xltx)$/i;

type Show = "all" | "documents" | "assets";
const SHOWS: { id: Show; label: string }[] = [
  { id: "all", label: "Everything" },
  { id: "documents", label: "Documents" },
  { id: "assets", label: "Assets" },
];

interface KeptAssets {
  skill: BrainSkill;
  files: BrainFile[];
}

function keptWithSkills(skills: BrainSkill[]): KeptAssets[] {
  return skills
    .map((skill) => ({ skill, files: skill.files.filter((file) => ASSET_FILE.test(file.path)) }))
    .filter((group) => group.files.length > 0);
}

// Files: everything the Brain holds, grouped by where it came from (Capture, projects, the
// Library, runs, Moving in, your uploads, your AIs, swept folders, or not known yet). Every
// document and asset opens its one page in the Library; a file a skill keeps opens with its
// skill.
export function FilesPage() {
  const { data: files, isLoading, error } = useBrainFiles();
  const { data: catalog } = useBrainCatalog();
  const [params, setParams] = useSearchParams();
  const [adding, setAdding] = useState(false);
  const show = (SHOWS.find((s) => s.id === params.get("show"))?.id ?? "all") as Show;
  if (isLoading) return <Loading />;
  if (!files) return <ErrorNote error={error} />;
  const titles = new Map((catalog?.entries ?? []).map((e) => [e.id, e.title]));
  const filed = [
    ...(show === "assets" ? [] : files.references),
    ...(show === "documents" ? [] : files.assets),
  ];
  const groups = new Map<OriginGroup, BrainFile[]>();
  for (const file of filed) {
    const group = originGroup(file.origin);
    groups.set(group, [...(groups.get(group) ?? []), file]);
  }
  const kept = show === "documents" ? [] : keptWithSkills(files.skills);
  return (
    <div className="files">
      <div className="files-head">
        <p className="muted small">Every file your Brain holds, by where it came from. Each opens its page in the Library.</p>
        <button type="button" className="primary" onClick={() => setAdding(true)}>
          Add a file
        </button>
      </div>
      <div className="chips" role="group" aria-label="Show">
        {SHOWS.map((s) => (
          <button
            key={s.id}
            type="button"
            className={show === s.id ? "chip active" : "chip"}
            aria-pressed={show === s.id}
            onClick={() => setParams(s.id === "all" ? {} : { show: s.id }, { replace: true })}
          >
            {s.label}
          </button>
        ))}
      </div>
      {!filed.length && !kept.length ? (
        <Empty why="No files yet. Add a proposal, a brief, a deck, a guide or a logo: your AI quotes the part a request is about." />
      ) : null}
      {ORIGIN_GROUPS.filter((g) => groups.has(g.id)).map((group) => (
        <section key={group.id} className="file-group" aria-label={group.label}>
          <h3>
            {group.label} <span className="muted small">{group.what}</span>
          </h3>
          {group.id === "project" ? (
            <ByProject files={groups.get(group.id) ?? []} titles={titles} />
          ) : (
            <FileRows files={groups.get(group.id) ?? []} titles={titles} />
          )}
        </section>
      ))}
      {kept.length ? (
        <section className="file-group" aria-label="Skills">
          <h3>
            Skills <span className="muted small">Logos, fonts and templates a skill keeps in its own folder</span>
          </h3>
          {kept.map(({ skill, files: members }) => (
            <div key={skill.name} className="asset-group">
              <h4>
                Kept with <Link to={`/work/skills/${encodeURIComponent(skill.name)}`}>/{skill.name}</Link>
              </h4>
              <AssetGrid files={members} />
            </div>
          ))}
        </section>
      ) : null}
      {adding ? <AddFileDialog onClose={() => setAdding(false)} /> : null}
    </div>
  );
}

/** Which copy a file is, as its card says: "version 3 · sent · 2026-10-03". */
function copyFacts(file: BrainFile): string[] {
  return [file.version ? `version ${file.version}` : "", file.file_status ?? "", file.dated ? file.dated : ""].filter(Boolean);
}

/** Files filed for a project, by project. */
function ByProject({ files, titles }: { files: BrainFile[]; titles: Map<string, string> }) {
  const groups = new Map<string, { title: string; files: BrainFile[] }>();
  for (const file of files) {
    const key = file.project ?? "";
    const group = groups.get(key) ?? { title: file.project_title ?? "A project", files: [] };
    group.files.push(file);
    groups.set(key, group);
  }
  return (
    <>
      {[...groups.entries()]
        .sort(([, a], [, b]) => a.title.localeCompare(b.title))
        .map(([key, group]) => (
          <section key={key || "other"} className="file-subgroup" aria-label={group.title}>
            <h4>{group.title}</h4>
            <FileRows files={group.files} titles={titles} />
          </section>
        ))}
    </>
  );
}

function FileRows({ files, titles }: { files: BrainFile[]; titles: Map<string, string> }) {
  return (
    <ul className="file-list">
      {files.map((file) => (
        <li key={file.path} className="file-row">
          {file.kind === "asset" && isImage(file.mime) ? (
            <Link to={libraryItemUrl(file.path)} className="thumb checker small-thumb" aria-label={`Open ${file.title}`}>
              <img src={brainFileUrl(file.path)} alt="" loading="lazy" />
            </Link>
          ) : (
            <TypeBadge name={file.original ?? file.path} />
          )}
          <div className="file-main">
            <Link to={libraryItemUrl(file.path)} className="file-title">
              {file.title}
            </Link>
            <ScopeChip scope={file.scope} />
            {copyFacts(file).length ? <span className="file-copy">{copyFacts(file).join(" · ")}</span> : null}
            {file.description ? <p className="snippet">{file.description}</p> : null}
            <p className="file-meta">
              {file.origin && originGroup(file.origin) !== "project" ? `${originLine(file.origin)} · ` : ""}
              {file.sections ? `${plural(file.sections, "part")} your AI can quote · ` : ""}
              {file.path} · {bytes(file.size)}
              {file.updated ? ` · updated ${when(file.updated)}` : ""}
              {file.original ? ` · from ${file.original}` : ""}
              {file.library === "prompt" ? (
                " · a prompt: your AIs use it only when you name it"
              ) : file.entry_id ? (
                <>
                  {" · models find it through "}
                  <Link to={entryUrl(file.entry_id)}>{titles.get(file.entry_id) ?? "its note"}</Link>
                </>
              ) : (
                <span className="unrouted" title="Models reach it only when a task pins it or they search for it">
                  {" · no note points your AI here yet"}
                </span>
              )}
            </p>
          </div>
          <div className="file-actions">
            <a className="button" href={brainFileUrl(file.path)} download aria-label={`Download ${file.title}`}>
              Download
            </a>
            {file.original ? (
              <a className="button" href={brainFileUrl(file.path, true)} download aria-label={`Download the original, ${file.original}`}>
                Original
              </a>
            ) : null}
            {file.kind === "reference" ? (
              <>
                <PullWhatMatters paths={[file.path]} />
                <KnowledgeCheck title={file.title} path={file.path} />
              </>
            ) : null}
          </div>
        </li>
      ))}
    </ul>
  );
}

function AssetGrid({ files }: { files: BrainFile[] }) {
  return (
    <ul className="asset-grid">
      {files.map((file) => (
        <li key={file.path} className="asset-card">
          <Link
            to={`/brain/files/view?path=${encodeURIComponent(file.path)}`}
            className={isImage(file.mime) ? "thumb checker" : "thumb"}
            aria-label={`Open ${file.title}`}
          >
            {isImage(file.mime) ? <img src={brainFileUrl(file.path)} alt={file.title} loading="lazy" /> : <TypeBadge name={file.path} />}
          </Link>
          <div className="asset-body">
            <strong>{file.title}</strong>
            <span className="muted">
              {bytes(file.size)} · {file.path.split(".").pop()?.toUpperCase()}
            </span>
          </div>
          <div className="row small">
            <a className="button" href={brainFileUrl(file.path)} download aria-label={`Download ${file.title}`}>
              Download
            </a>
          </div>
        </li>
      ))}
    </ul>
  );
}

async function fetchText(url: string): Promise<string> {
  const response = await fetch(url, { credentials: "same-origin" });
  if (!response.ok) throw new Error(`Could not open the file (${response.status}).`);
  return response.text();
}

// One file. A document or an asset has one page, in the Library: its old address goes there. A
// file a skill keeps is read in place, an image shown, anything else offered as a download.
export function FileViewPage() {
  const [params] = useSearchParams();
  const path = params.get("path") ?? "";
  if (path.startsWith("references/") || path.startsWith("assets/")) return <Navigate to={libraryItemUrl(path)} replace />;
  return <SkillFileView path={path} />;
}

function SkillFileView({ path }: { path: string }) {
  const { data: files } = useBrainFiles();
  const all = files ? [...files.references, ...files.assets, ...files.skills.flatMap((s) => s.files)] : [];
  const file = all.find((f) => f.path === path);
  const textual = isText(path);
  const { data: text, error } = useQuery({
    queryKey: [...keys.brain, "file", path],
    queryFn: () => fetchText(brainFileUrl(path)),
    enabled: !!path && textual,
  });
  const tab = filesTab(path);
  const name = path.split("/").pop() ?? path;
  // A file a skill keeps belongs to the skill: its breadcrumb leads there.
  const skill = tab === "skills" ? files?.skills.find((s) => s.files.some((f) => f.path === path)) : undefined;
  return (
    <div className="file-view">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        {skill ? (
          <>
            <Link to="/work/skills">Skills</Link>
            <span aria-hidden="true">/</span>
            <Link to={`/work/skills/${encodeURIComponent(skill.name)}`}>/{skill.name}</Link>
          </>
        ) : (
          <>
            <Link to="/brain/files">Files</Link>
            <span aria-hidden="true">/</span>
            <span>{label(tab)}</span>
          </>
        )}
      </nav>
      <header className="entry-head">
        <h1>{file?.title ?? name}</h1>
        <div className="row">
          <a className="button primary" href={brainFileUrl(path)} download>
            Download
          </a>
          {file?.entry_id ? (
            <Link className="button" to={entryUrl(file.entry_id)}>
              Open its note
            </Link>
          ) : null}
        </div>
      </header>
      <p className="file-meta">
        <code>{path}</code>
        {file ? ` · ${bytes(file.size)}` : ""}
        {file?.updated ? ` · updated ${when(file.updated)}` : ""}
      </p>
      {file && isImage(file.mime) ? (
        <div className="preview checker">
          <img src={brainFileUrl(path)} alt={file.title} />
        </div>
      ) : textual ? (
        text !== undefined ? (
          /\.(md|markdown)$/i.test(path) ? (
            <div className="document">
              <Markdown text={documentBody(text, file?.title ?? "")} />
            </div>
          ) : (
            <pre className="document code-view">{text}</pre>
          )
        ) : error ? (
          <ErrorNote error={error} />
        ) : (
          <Loading />
        )
      ) : (
        <Empty why="This kind of file has no preview here.">
          <a className="button" href={brainFileUrl(path)} download>
            Download it
          </a>
        </Empty>
      )}
    </div>
  );
}

/** A document without what the page already shows: its title, and the note the Brain adds
 * when it files a document ("> Source: ..."), since the download buttons carry that. */
export function documentBody(text: string, title: string): string {
  let lines = text.replace(/\r\n?/g, "\n").split("\n");
  const trim = () => {
    while (lines.length && !lines[0]?.trim()) lines = lines.slice(1);
  };
  const heading = `# ${title}`.trim().toLowerCase();
  trim();
  if (title && lines[0]?.trim().toLowerCase() === heading) lines = lines.slice(1);
  trim();
  if (lines[0]?.startsWith("> Source: ")) {
    while (lines.length && lines[0]?.startsWith(">")) lines = lines.slice(1);
    trim();
    if (title && lines[0]?.trim().toLowerCase() === heading) lines = lines.slice(1);
    trim();
  }
  return lines.join("\n");
}
