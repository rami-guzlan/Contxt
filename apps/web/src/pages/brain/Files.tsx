import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";

import { brainFileUrl, keys, useBrainCatalog, useBrainFiles } from "../../api/hooks";
import type { BrainFile, BrainSkill } from "../../api/types";
import { Markdown } from "../../components/Markdown";
import { Empty, ErrorNote, Loading, Tabs } from "../../components/ui";
import { bytes, label, plural, when } from "../../lib/format";
import { AddFileDialog } from "./AddFile";
import { TypeBadge, entryUrl, fileViewUrl, filesTab, isImage, isText } from "./shared";

type Tab = "references" | "assets";
const TABS: readonly Tab[] = ["references", "assets"];

// Media, fonts and templates: what people open a Brain's files for, wherever they are kept.
// Skills often keep their logos, fonts and deck templates in their own folders.
const ASSET_FILE = /\.(png|jpe?g|gif|webp|svg|ico|ttf|otf|woff2?|mp3|wav|m4a|mp4|mov|webm|pdf|pptx|potx|docx|dotx|xlsx|xltx)$/i;

interface KeptAssets {
  skill: BrainSkill;
  files: BrainFile[];
}

function keptWithSkills(skills: BrainSkill[]): KeptAssets[] {
  return skills
    .map((skill) => ({ skill, files: skill.files.filter((file) => ASSET_FILE.test(file.path)) }))
    .filter((group) => group.files.length > 0);
}

// Files: the documents and assets the Brain holds, each one openable and downloadable. Skills
// have their own place; the media they keep shows under Assets.
export function FilesPage() {
  const { data: files, isLoading, error } = useBrainFiles();
  const { data: catalog } = useBrainCatalog();
  const [params, setParams] = useSearchParams();
  const [adding, setAdding] = useState(false);
  const wanted = params.get("tab") as Tab | null;
  const tab: Tab = wanted && TABS.includes(wanted) ? wanted : "references";
  if (isLoading) return <Loading />;
  if (!files) return <ErrorNote error={error} />;
  const kept = keptWithSkills(files.skills);
  const assetCount = files.assets.length + kept.reduce((n, group) => n + group.files.length, 0);
  return (
    <div className="files">
      <div className="files-head">
        <Tabs
          tabs={[
            { id: "references", label: `References (${files.references.length})` },
            { id: "assets", label: `Assets (${assetCount})` },
          ]}
          active={tab}
          onChange={(id) => setParams({ tab: id }, { replace: true })}
        />
        <button type="button" className="primary" onClick={() => setAdding(true)}>
          Add a file
        </button>
      </div>
      {tab === "references" ? (
        <References files={files.references} titles={new Map((catalog?.entries ?? []).map((e) => [e.id, e.title]))} />
      ) : null}
      {tab === "assets" ? <Assets filed={files.assets} kept={kept} /> : null}
      {adding ? <AddFileDialog onClose={() => setAdding(false)} /> : null}
    </div>
  );
}

/** Which copy a file is, as its card says: "version 3 · sent · 2026-10-03". */
function copyFacts(file: BrainFile): string[] {
  return [
    file.version ? `version ${file.version}` : "",
    file.file_status ?? "",
    file.dated ? file.dated : "",
  ].filter(Boolean);
}

function References({ files, titles }: { files: BrainFile[]; titles: Map<string, string> }) {
  if (!files.length) {
    return (
      <Empty why="No documents yet. Add a proposal, brief, deck or guide: your AI quotes the part a request is about." />
    );
  }
  // Work files by project first (what you are working on), then everything else.
  const groups = new Map<string, { title: string; files: BrainFile[] }>();
  for (const file of files) {
    const key = file.project ?? "";
    const group = groups.get(key) ?? { title: file.project_title ?? "Guides and other documents", files: [] };
    group.files.push(file);
    groups.set(key, group);
  }
  const ordered = [...groups.entries()].sort(([a, ga], [b, gb]) =>
    a === "" ? 1 : b === "" ? -1 : ga.title.localeCompare(gb.title),
  );
  return (
    <>
      {ordered.map(([key, group]) => (
        <section key={key || "other"} className="file-group" aria-label={group.title}>
          <h3>{group.title}</h3>
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
          <TypeBadge name={file.original ?? file.path} />
          <div className="file-main">
            <Link to={fileViewUrl(file.path)} className="file-title">
              {file.title}
            </Link>
            {copyFacts(file).length ? <span className="file-copy">{copyFacts(file).join(" · ")}</span> : null}
            {file.description ? <p className="snippet">{file.description}</p> : null}
            <p className="file-meta">
              {file.sections ? `${plural(file.sections, "part")} your AI can quote · ` : ""}
              {file.path} · {bytes(file.size)}
              {file.updated ? ` · updated ${when(file.updated)}` : ""}
              {file.original ? ` · from ${file.original}` : ""}
              {file.entry_id ? (
                <>
                  {" · models find it through "}
                  <Link to={entryUrl(file.entry_id)}>{titles.get(file.entry_id) ?? "its entry"}</Link>
                </>
              ) : (
                <span className="unrouted" title="Models reach it only when a task pins it or they search for it">
                  {" · no entry points models here yet"}
                </span>
              )}
            </p>
          </div>
          <div className="file-actions">
            <a className="button" href={brainFileUrl(file.path)} download aria-label={`Download ${file.title}`}>
              Download
            </a>
            {file.original ? (
              <a
                className="button"
                href={brainFileUrl(file.path, true)}
                download
                aria-label={`Download the original, ${file.original}`}
              >
                Original
              </a>
            ) : null}
          </div>
        </li>
      ))}
    </ul>
  );
}

function Assets({ filed, kept }: { filed: BrainFile[]; kept: KeptAssets[] }) {
  if (!filed.length && !kept.length) {
    return (
      <Empty why="No assets yet. Logos, images, fonts and data files you add are kept byte for byte, with an entry that tells models where they are." />
    );
  }
  return (
    <>
      {filed.length ? (
        <section className="asset-group">
          <h3>Filed in the Brain</h3>
          <AssetGrid files={filed} />
        </section>
      ) : null}
      {kept.map(({ skill, files }) => (
        <section key={skill.name} className="asset-group">
          <h3>
            Kept with <Link to={`/skills/${encodeURIComponent(skill.name)}`}>/{skill.name}</Link>
          </h3>
          <AssetGrid files={files} />
        </section>
      ))}
    </>
  );
}

function AssetGrid({ files }: { files: BrainFile[] }) {
  return (
    <ul className="asset-grid">
      {files.map((file) => (
        <li key={file.path} className="asset-card">
          <Link to={fileViewUrl(file.path)} className={isImage(file.mime) ? "thumb checker" : "thumb"} aria-label={`Open ${file.title}`}>
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
            {file.entry_id ? <Link to={entryUrl(file.entry_id)}>Its entry</Link> : null}
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

// One file: a reference read in place, an image shown, anything else offered as a download.
export function FileViewPage() {
  const [params] = useSearchParams();
  const path = params.get("path") ?? "";
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
            <Link to="/skills">Skills</Link>
            <span aria-hidden="true">/</span>
            <Link to={`/skills/${encodeURIComponent(skill.name)}`}>/{skill.name}</Link>
          </>
        ) : (
          <>
            <Link to="/brain/files">Files</Link>
            <span aria-hidden="true">/</span>
            <Link to={`/brain/files?tab=${tab}`}>{label(tab)}</Link>
          </>
        )}
      </nav>
      <header className="entry-head">
        <h1>{file?.title ?? name}</h1>
        <div className="row">
          <a className="button primary" href={brainFileUrl(path)} download>
            Download
          </a>
          {file?.original ? (
            <a className="button" href={brainFileUrl(path, true)} download>
              Download the original ({file.original})
            </a>
          ) : null}
          {file?.entry_id ? (
            <Link className="button" to={entryUrl(file.entry_id)}>
              Open its entry
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
