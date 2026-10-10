// Knowledge Work, Library: everything the Brain keeps whole. Guides to follow, references to read
// whole, influences whose taste to borrow, and assets kept byte for byte (images, fonts, sheets),
// each with where it came from and its scope. Add one by upload, by writing it here, from a web
// page or from a GitHub repository; a fetched one can be fetched again by hand or on a schedule.
// Skills, agents and workflows point to them, so they always read the current version. Every
// file in Brain > Files opens its page here.

import { BookOpen, RefreshCw } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";

import {
  brainFileUrl,
  useFetchToLibrary,
  useLibrary,
  useLibraryItem,
  useLinkRepo,
  useRefreshLibraryItem,
  useUpdateLibraryItem,
  useUploadToLibrary,
  useWriteToLibrary,
} from "../../api/hooks";
import type { LibraryFiled, LibraryItem, LibraryKind, LibraryRefresh } from "../../api/types";
import { Markdown } from "../../components/Markdown";
import { Empty, ErrorNote, Field, Loading, Section, Tabs } from "../../components/ui";
import { ScopeChip } from "../../components/work/Scope";
import { plural, when } from "../../lib/format";
import { skillUrl } from "../../lib/links";
import { originLine, SETTABLE_ORIGINS } from "../../lib/origins";
import { entryUrl, libraryItemUrl } from "../brain/shared";

export const KIND_WORDS: Record<LibraryKind, { one: string; many: string; what: string }> = {
  guide: { one: "Guide", many: "Guides", what: "to follow: rules and conventions, read whole" },
  reference: { one: "Reference", many: "References", what: "to read whole: specs, contracts, product sheets" },
  influence: { one: "Influence", many: "Influences", what: "whose taste to borrow: a repository, a site, a writer" },
  asset: { one: "Asset", many: "Assets", what: "kept byte for byte: images, fonts, sheets, recordings" },
};
const KINDS: LibraryKind[] = ["guide", "reference", "influence", "asset"];
const DOCUMENT_KINDS: LibraryKind[] = ["guide", "reference", "influence"];
const ASSET_ACCEPT = ".png,.jpg,.jpeg,.gif,.webp,.svg,.ttf,.otf,.woff,.woff2,.csv,.json,.xlsx,.mp3,.wav,.m4a,.mp4,.mov,.webm";
const REFRESH_WORDS: Record<LibraryRefresh, string> = { never: "Only when I say", weekly: "Every week", monthly: "Every month" };

// One page per item, shared with Brain > Files.
export { libraryItemUrl };

function host(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

/** Where an item came from, in a few words. */
function sourceLine(item: LibraryItem): string {
  const from = item.source_repo
    ? item.source_repo.replace(/^https:\/\/(www\.)?github\.com\//, "")
    : item.source_url
      ? host(item.source_url)
      : "";
  return [
    from ? `from ${from}` : "",
    item.fetched_at ? `fetched ${when(item.fetched_at)}` : "",
    item.refresh !== "never" && from ? REFRESH_WORDS[item.refresh].toLowerCase() : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

function usedLine(item: LibraryItem): string {
  const count = item.used_by.skills.length + (item.used_by.agents?.length ?? 0) + (item.used_by.workflows?.length ?? 0);
  return count ? `used by ${plural(count, "skill or agent", "skills and agents")}` : "";
}

export function LibraryPage() {
  const { data: items, isLoading, error } = useLibrary();
  const [params, setParams] = useSearchParams();
  const shown = (params.get("kind") as LibraryKind | null) ?? null;
  const [adding, setAdding] = useState(params.get("add") === "1");
  if (isLoading) return <Loading />;
  if (!items) return <ErrorNote error={error} />;
  const list = shown ? items.filter((i) => i.kind === shown) : items;
  const count = (kind: LibraryKind) => items.filter((i) => i.kind === kind).length;
  return (
    <div className="work-tab library">
      <div className="work-intro">
        <p>
          Everything your Brain keeps whole: guides to follow, references to read whole, influences whose taste to borrow, and assets.
          Skills, agents and workflows point to them, so they always read the current version.
        </p>
        {!adding ? (
          <button type="button" className="primary" onClick={() => setAdding(true)}>
            Add to the Library
          </button>
        ) : null}
      </div>
      {adding ? <AddToLibrary onClose={() => setAdding(false)} /> : null}
      <div className="chips library-filter" role="group" aria-label="Show">
        <button type="button" className={shown === null ? "chip active" : "chip"} aria-pressed={shown === null} onClick={() => setParams({})}>
          Everything <span className="muted small">{items.length}</span>
        </button>
        {KINDS.map((kind) => (
          <button
            key={kind}
            type="button"
            className={shown === kind ? "chip active" : "chip"}
            aria-pressed={shown === kind}
            onClick={() => setParams({ kind })}
          >
            {KIND_WORDS[kind].many} <span className="muted small">{count(kind)}</span>
          </button>
        ))}
      </div>
      {list.length ? (
        <ul className="library-list" aria-label="Library">
          {list.map((item) => (
            <li key={item.path} className="library-item">
              <span className={`kind-chip kind-${item.kind}`}>{KIND_WORDS[item.kind]?.one ?? item.kind}</span>
              <div className="library-item-main">
                <Link to={libraryItemUrl(item.path)} className="library-item-title">
                  {item.title}
                </Link>
                <ScopeChip scope={item.scope} />
                {item.summary ? <p className="muted small">{item.summary}</p> : null}
                <p className="muted small">
                  {[
                    `from ${originLine(item.origin).toLowerCase()}`,
                    sourceLine(item),
                    usedLine(item),
                    item.project_title ? `in ${item.project_title}` : "",
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <Empty
          why={
            shown
              ? `No ${KIND_WORDS[shown].many.toLowerCase()} yet: ${KIND_WORDS[shown].what}.`
              : "Nothing kept whole yet. Add a style guide you follow, a spec to read whole, or a repository whose taste you want your AI to borrow."
          }
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------- adding

const WAYS = [
  { id: "url", label: "From a web page" },
  { id: "repo", label: "From GitHub" },
  { id: "upload", label: "Upload a file" },
  { id: "write", label: "Write a guide" },
] as const;
type Way = (typeof WAYS)[number]["id"];

function KindPicker({
  value,
  onChange,
  kinds = DOCUMENT_KINDS,
}: {
  value: LibraryKind;
  onChange: (kind: LibraryKind) => void;
  kinds?: LibraryKind[];
}) {
  return (
    <Field label="What it is">
      <select value={value} onChange={(event) => onChange(event.target.value as LibraryKind)}>
        {kinds.map((kind) => (
          <option key={kind} value={kind}>
            {KIND_WORDS[kind].one}: {KIND_WORDS[kind].what}
          </option>
        ))}
      </select>
    </Field>
  );
}

function RefreshPicker({ value, onChange }: { value: LibraryRefresh; onChange: (refresh: LibraryRefresh) => void }) {
  return (
    <Field label="Fetch it again" hint="A change found on a schedule waits for your yes; one you ask for goes in with an undo point.">
      <select value={value} onChange={(event) => onChange(event.target.value as LibraryRefresh)}>
        {(Object.keys(REFRESH_WORDS) as LibraryRefresh[]).map((refresh) => (
          <option key={refresh} value={refresh}>
            {REFRESH_WORDS[refresh]}
          </option>
        ))}
      </select>
    </Field>
  );
}

function Outcome({ result }: { result: LibraryFiled }) {
  if (result.status === "applied" && result.path) {
    return (
      <p className="notice small" role="status">
        Kept. <Link to={libraryItemUrl(result.path)}>Open it</Link>. Undo it from Activity, Changes.
      </p>
    );
  }
  return (
    <p className="notice small" role="status">
      {result.status === "pending" ? (
        <>
          It waits in <Link to="/review">Review</Link> for your yes.
        </>
      ) : (
        result.message
      )}
    </p>
  );
}

export function AddToLibrary({ onClose }: { onClose: () => void }) {
  const [way, setWay] = useState<Way>("url");
  const [result, setResult] = useState<LibraryFiled | null>(null);
  return (
    <section className="skill-panel library-add" aria-label="Add to the Library">
      <div className="row space-between">
        <h2>Add to the Library</h2>
        <button type="button" className="link" onClick={onClose}>
          Close
        </button>
      </div>
      <Tabs tabs={WAYS} active={way} onChange={(next) => { setWay(next); setResult(null); }} />
      {way === "url" ? <FromPage onDone={setResult} /> : null}
      {way === "repo" ? <FromRepo onDone={setResult} /> : null}
      {way === "upload" ? <Upload onDone={setResult} /> : null}
      {way === "write" ? <Write onDone={setResult} /> : null}
      {result ? <Outcome result={result} /> : null}
    </section>
  );
}

function FromPage({ onDone }: { onDone: (result: LibraryFiled) => void }) {
  const fetchPage = useFetchToLibrary();
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<LibraryKind>("reference");
  const [refresh, setRefresh] = useState<LibraryRefresh>("never");
  return (
    <form
      className="stack"
      onSubmit={(event) => {
        event.preventDefault();
        fetchPage.mutate({ url: url.trim(), title: title.trim() || undefined, kind, refresh }, { onSuccess: onDone });
      }}
    >
      <Field label="The page's address" hint="It is fetched once now and kept as text. Only https:// addresses.">
        <input type="url" required value={url} placeholder="https://" onChange={(event) => setUrl(event.target.value)} />
      </Field>
      <Field label="Title (optional)" hint="The page's own title when left empty.">
        <input value={title} onChange={(event) => setTitle(event.target.value)} />
      </Field>
      <div className="skill-inputs">
        <KindPicker value={kind} onChange={setKind} />
        <RefreshPicker value={refresh} onChange={setRefresh} />
      </div>
      <div className="row">
        <button type="submit" className="primary" disabled={!url.trim() || fetchPage.isPending}>
          {fetchPage.isPending ? "Fetching…" : "Fetch and keep"}
        </button>
      </div>
      <ErrorNote error={fetchPage.error} />
    </form>
  );
}

function FromRepo({ onDone }: { onDone: (result: LibraryFiled) => void }) {
  const link = useLinkRepo();
  const [url, setUrl] = useState("");
  const [paths, setPaths] = useState("");
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<LibraryKind>("influence");
  const [refresh, setRefresh] = useState<LibraryRefresh>("monthly");
  const picked = paths
    .split(/\r?\n/)
    .map((p) => p.trim())
    .filter(Boolean);
  return (
    <form
      className="stack"
      onSubmit={(event) => {
        event.preventDefault();
        link.mutate({ url: url.trim(), paths: picked, title: title.trim() || undefined, kind, refresh }, { onSuccess: onDone });
      }}
    >
      <Field label="The repository" hint="Fetched with git on this computer, with your own sign-in for a private one. Contxt never keeps a token.">
        <input type="url" required value={url} placeholder="https://github.com/owner/name" onChange={(event) => setUrl(event.target.value)} />
      </Field>
      <Field label="Files to include (optional)" hint="One path per line, up to 20, such as CONTRIBUTING.md or src/components/Button.tsx. The README and the folder tree always come along.">
        <textarea rows={3} value={paths} onChange={(event) => setPaths(event.target.value)} />
      </Field>
      <Field label="Title (optional)" hint="owner/name when left empty.">
        <input value={title} onChange={(event) => setTitle(event.target.value)} />
      </Field>
      <div className="skill-inputs">
        <KindPicker value={kind} onChange={setKind} />
        <RefreshPicker value={refresh} onChange={setRefresh} />
      </div>
      <div className="row">
        <button type="submit" className="primary" disabled={!url.trim() || link.isPending}>
          {link.isPending ? "Fetching…" : "Link the repository"}
        </button>
      </div>
      <ErrorNote error={link.error} />
    </form>
  );
}

function Upload({ onDone }: { onDone: (result: LibraryFiled) => void }) {
  const upload = useUploadToLibrary();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<LibraryKind>("reference");
  return (
    <form
      className="stack"
      onSubmit={(event) => {
        event.preventDefault();
        if (file) upload.mutate({ file, title: title.trim() || undefined, kind }, { onSuccess: onDone });
      }}
    >
      <KindPicker value={kind} onChange={setKind} kinds={KINDS} />
      {kind === "asset" ? (
        <Field label="The asset" hint="An image, a font, a sheet, a recording or a video, up to 10 MB, kept byte for byte.">
          <input type="file" accept={ASSET_ACCEPT} onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
        </Field>
      ) : (
        <Field label="The document" hint="PDF, Word, PowerPoint, HTML, Markdown or text, up to 10 MB. It is kept whole, as text.">
          <input type="file" accept=".pdf,.docx,.pptx,.html,.htm,.md,.txt" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
        </Field>
      )}
      <Field label="Title (optional)">
        <input value={title} onChange={(event) => setTitle(event.target.value)} />
      </Field>
      <div className="row">
        <button type="submit" className="primary" disabled={!file || upload.isPending}>
          {upload.isPending ? "Keeping…" : "Keep it"}
        </button>
      </div>
      <ErrorNote error={upload.error} />
    </form>
  );
}

function Write({ onDone }: { onDone: (result: LibraryFiled) => void }) {
  const write = useWriteToLibrary();
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [kind, setKind] = useState<LibraryKind>("guide");
  return (
    <form
      className="stack"
      onSubmit={(event) => {
        event.preventDefault();
        write.mutate({ title: title.trim(), text, kind }, { onSuccess: onDone });
      }}
    >
      <Field label="Title">
        <input required value={title} placeholder="For example: How we write release notes" onChange={(event) => setTitle(event.target.value)} />
      </Field>
      <Field label="The guide" hint="Markdown. Write it the way you would brief a new colleague.">
        <textarea rows={10} value={text} onChange={(event) => setText(event.target.value)} />
      </Field>
      <KindPicker value={kind} onChange={setKind} />
      <div className="row">
        <button type="submit" className="primary" disabled={!title.trim() || !text.trim() || write.isPending}>
          {write.isPending ? "Keeping…" : "Keep it"}
        </button>
      </div>
      <ErrorNote error={write.error} />
    </form>
  );
}

// ---------------------------------------------------------------- one item

export function LibraryItemPage() {
  const [params] = useSearchParams();
  const path = params.get("path") ?? "";
  const { data: item, isLoading, error } = useLibraryItem(path);
  const update = useUpdateLibraryItem();
  const refresh = useRefreshLibraryItem();
  if (isLoading) return <Loading />;
  if (!item) return <ErrorNote error={error} />;
  const fetched = !!(item.source_url || item.source_repo);
  const asset = item.file_kind === "asset";
  return (
    <div className="library-item-page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/work/library">Library</Link> · <Link to="/brain/files">Brain, Files</Link>
      </nav>
      <header className="entry-head">
        <h1>
          <BookOpen className="title-icon" aria-hidden="true" /> {item.title}
        </h1>
        <ScopeChip scope={item.scope} />
        {item.summary ? <p className="lede">{item.summary}</p> : null}
      </header>
      <div className="entry-layout">
        <div className="document">
          {item.text !== null ? (
            <Markdown text={item.text} />
          ) : item.mime.startsWith("image/") ? (
            <img className="asset-preview" src={brainFileUrl(item.path)} alt={item.title} />
          ) : (
            <p>
              <a href={brainFileUrl(item.path)} download>
                Download {item.path.split("/").pop()}
              </a>{" "}
              <span className="muted small">({item.mime}, kept byte for byte)</span>
            </p>
          )}
        </div>
        <aside className="entry-side">
          <Section title="What it is">
            <div className="stack">
              <Field label="Kind">
                <select
                  value={item.kind}
                  disabled={update.isPending || !item.entry_id || asset}
                  onChange={(event) => update.mutate({ path: item.path, kind: event.target.value as LibraryKind })}
                >
                  {(asset ? (["asset"] as LibraryKind[]) : DOCUMENT_KINDS).map((kind) => (
                    <option key={kind} value={kind}>
                      {KIND_WORDS[kind].one}
                    </option>
                  ))}
                </select>
              </Field>
              {fetched ? (
                <Field label="Fetch it again">
                  <select
                    value={item.refresh}
                    disabled={update.isPending || !item.entry_id}
                    onChange={(event) => update.mutate({ path: item.path, refresh: event.target.value as LibraryRefresh })}
                  >
                    {(Object.keys(REFRESH_WORDS) as LibraryRefresh[]).map((value) => (
                      <option key={value} value={value}>
                        {REFRESH_WORDS[value]}
                      </option>
                    ))}
                  </select>
                </Field>
              ) : null}
              <ErrorNote error={update.error} />
            </div>
          </Section>
          <Section title="Where it came from">
            <p className="small">
              {originLine(item.origin)}
              {item.origin_inferred ? <span className="muted"> (read from its card)</span> : null}
            </p>
            {(!item.origin || item.origin_inferred) && item.entry_id ? (
              <Field label="Set where it came from" hint="It was filed before the Brain kept this. One undo point.">
                <select
                  value=""
                  disabled={update.isPending}
                  onChange={(event) => event.target.value && update.mutate({ path: item.path, origin: event.target.value })}
                >
                  <option value="">Choose…</option>
                  {SETTABLE_ORIGINS.map((origin) => (
                    <option key={origin.value} value={origin.value}>
                      {origin.label}
                    </option>
                  ))}
                </select>
              </Field>
            ) : null}
          </Section>
          {fetched ? (
            <Section title="Where it comes from">
              <p className="small">
                <a href={item.source_repo ?? item.source_url ?? "#"} target="_blank" rel="noreferrer">
                  {item.source_repo ?? item.source_url}
                </a>
              </p>
              {item.source_paths.length ? <p className="muted small">With {item.source_paths.join(", ")}</p> : null}
              <p className="muted small">
                {item.fetched_at ? `Fetched ${when(item.fetched_at)}` : ""}
                {item.checked_at ? ` · checked ${when(item.checked_at)}` : ""}
              </p>
              <button type="button" disabled={refresh.isPending} onClick={() => refresh.mutate(item.path)}>
                <RefreshCw className="button-icon" aria-hidden="true" />
                {refresh.isPending ? "Fetching…" : "Fetch it again now"}
              </button>
              {refresh.data ? (
                <p className="notice small" role="status">
                  {refresh.data.status === "unchanged" ? "Nothing changed since it was fetched." : refresh.data.message}
                </p>
              ) : null}
              <ErrorNote error={refresh.error} />
            </Section>
          ) : null}
          <Section title="Used by">
            {item.used_by.skills.length ? (
              <ul className="list">
                {item.used_by.skills.map((name) => (
                  <li key={name}>
                    <Link to={skillUrl(name)}>/{name}</Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted small">Nothing points to it yet. A skill that loads it, or an agent that points to it, shows here.</p>
            )}
          </Section>
          <Section title="Its history">
            <p className="small">
              {item.entry_id ? <Link to={entryUrl(item.entry_id)}>Its card in the Brain</Link> : null}
              {item.entry_id && item.original ? " · " : ""}
              {item.original ? (
                <a href={brainFileUrl(item.path, true)} download>
                  Download the original
                </a>
              ) : null}
            </p>
            <p className="muted small">Every version is kept; the card's page lists them.</p>
          </Section>
        </aside>
      </div>
    </div>
  );
}
