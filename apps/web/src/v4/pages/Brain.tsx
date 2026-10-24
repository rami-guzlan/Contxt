// The Brain (Gnomon Prototype v4, slices 10-isBrain, 19-isNote, 32-isLive): what your AI knows,
// in the exact words it receives. Tabs by ?tab=: What it knows (the brain map, long-term
// memory, context sheets, taste), Catch up (its own panel), Try a prompt, Notes, Sheets,
// Files and Questions. A note's page shows the current version against earlier versions kept
// as they were; a sheet's page shows its grid and every cell's history. Every value comes
// from the server; what the server cannot give yet says so.

import {
  type CSSProperties,
  type KeyboardEvent,
  type ReactNode,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import type { BrainArea, BrainEntrySummary, BrainFile, BrainHistoryRecord, InventoryItem, StateColumn, StateRow, StateSheet } from "../../api/types";
import { type TasteEntry, useBrainMap, useForgetLearned, useLearned, useProposals, useProposeTaste, useTaste } from "../api";
import { css } from "../css";
import {
  DERIVED,
  fileUrl,
  type Gap,
  useAddFile,
  useBrainCatalog,
  useBrainEntry,
  useBrainFiles,
  useBrainHistory,
  useBrainInventory,
  useBrainProjects,
  useCellHistory,
  useDerivedSheet,
  useDismissGap,
  useEntryDecide,
  useEntryDetails,
  useEntryUse,
  useEntryVersion,
  useEntryVersions,
  useGaps,
  useGoals,
  useLive,
  usePreview,
  useSheet,
  useSheetAct,
  useTeach,
} from "../hooks/brain";
import { Btn, Empty, Failure, Later, Loaded, Loading, Modal, plural, S, Status, when } from "../ui";
import { LevelChip, LoreShelf, MapCard, SectionAddresses } from "../components/BrainV4";
import { CatchUpPanel } from "./CatchUp";

// ------------------------------------------------------------------ shared bits

const WRAP = "max-width:1120px;margin:0 auto;padding:56px 64px 96px;display:flex;flex-direction:column;gap:32px;box-sizing:border-box";
const TS = (on: boolean) =>
  `padding:7px 14px;border-radius:99px;border:0;white-space:nowrap;font:${on ? 500 : 400} 13px Geist;background:${on ? "var(--ink)" : "transparent"};color:${on ? "var(--bg)" : "var(--ink2)"}`;
const SECTION = "display:flex;flex-direction:column;gap:18px;margin-top:14px;padding-top:34px;border-top:1px solid var(--line)";
const KICKER = "font:500 11px 'Geist Mono';letter-spacing:.06em;color:var(--muted)";
const BIG = "font:400 30px Newsreader";
const BLURB = "font:400 14px/1.5 Geist;color:var(--ink2);max-width:620px";
const AUTO_TAG = "padding:3px 9px;border-radius:99px;background:oklch(0.74 0.12 150 / .18);color:oklch(0.45 0.1 150);font:500 11px Geist";
const ERR = "font:400 13px Geist;color:oklch(0.55 0.17 28)";
const HUES = [80, 265, 150, 320, 35, 210, 60, 25];

function dark(): boolean {
  try {
    const set = document.documentElement.dataset.theme;
    if (set) return set === "dark";
    return Boolean(window.matchMedia?.("(prefers-color-scheme: dark)").matches);
  } catch {
    return false;
  }
}
const tint = (h: number, a?: number) => (dark() ? `oklch(0.74 0.12 ${h} / ${a || 0.22})` : `oklch(${a ? 0.86 : 0.93} ${a ? 0.07 : 0.045} ${h})`);
const solid = (h: number) => `oklch(0.66 0.13 ${h})`;
const ink = (h: number) => (dark() ? `oklch(0.88 0.08 ${h})` : `oklch(0.38 0.09 ${h})`);
const dotStyle = (h: number, size = 8) => `width:${size}px;height:${size}px;border-radius:50%;flex:none;background:${solid(h)}`;
function hueOf(key: string): number {
  let n = 0;
  for (const ch of key) n = (n * 31 + ch.charCodeAt(0)) >>> 0;
  return HUES[n % HUES.length] ?? 80;
}
const errorText = (e: unknown) => (e instanceof Error ? e.message : "Something went wrong. Try again.");

function Chips<T extends string>({ value, options, onChange, label }: { value: T; options: [T, string][]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="group" aria-label={label} style={css(S.wrap)}>
      {options.map(([id, text]) => (
        <button key={id} type="button" aria-pressed={value === id} onClick={() => onChange(id)} style={css(TS(value === id))}>
          {text}
        </button>
      ))}
    </div>
  );
}

function Mistake({ error }: { error: unknown }) {
  return error ? (
    <span role="alert" style={css(ERR)}>
      {errorText(error)}
    </span>
  ) : null;
}

// ------------------------------------------------------------------ the Brain screen

type TabId = "knows" | "catchup" | "try" | "notes" | "sheets" | "files" | "questions";
const TAB_IDS: TabId[] = ["knows", "catchup", "try", "notes", "sheets", "files", "questions"];

export function BrainPage() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab") as TabId | null;
  const tab: TabId = raw && TAB_IDS.includes(raw) ? raw : "knows";
  const go = (id: TabId) => setParams(id === "knows" ? {} : { tab: id });
  const proposals = useProposals();
  const gaps = useGaps();
  const waiting = proposals.data?.length ?? 0;
  const open = gaps.data?.length ?? 0;
  const [nudgeGone, setNudgeGone] = useState(false);
  const [teach, setTeach] = useState(false);

  const tabs: [TabId, string][] = [
    ["knows", "What it knows"],
    ["catchup", waiting ? `Catch up · ${waiting}` : "Catch up"],
    ["try", "Try a prompt"],
    ["notes", "Notes"],
    ["sheets", "Sheets"],
    ["files", "Files"],
    ["questions", gaps.data ? `Questions · ${open}` : "Questions"],
  ];

  return (
    <div className="gn-page" style={css(WRAP)}>
      <div style={css("display:flex;justify-content:space-between;align-items:flex-end;gap:24px;flex-wrap:wrap")}>
        <div style={css("display:flex;flex-direction:column;gap:8px")}>
          <h1 style={css(S.h1)}>What your AI knows</h1>
          <span style={css("font:400 17px Geist;color:var(--ink2)")}>In the exact words it receives. Nothing changes without you.</span>
        </div>
        <Btn kind="primary" onClick={() => setTeach(true)}>
          Teach it something
        </Btn>
      </div>
      <div role="tablist" aria-label="Brain" style={css(S.wrap)}>
        {tabs.map(([id, label]) => (
          <button key={id} role="tab" type="button" aria-selected={tab === id} onClick={() => go(id)} style={css(TS(tab === id))}>
            {label}
          </button>
        ))}
      </div>
      {waiting > 0 && !nudgeGone && tab !== "catchup" ? (
        <div style={css("display:flex;align-items:center;gap:12px;padding:12px 16px;border-radius:16px;border:1px solid var(--line);width:100%;box-sizing:border-box;margin-bottom:-12px")}>
          <span style={css("width:8px;height:8px;border-radius:50%;flex:none;background:oklch(0.62 0.14 150)")} />
          <span style={css("font:400 14px Geist;flex:1")}>
            Your AIs learned {plural(waiting, "new thing")} since you last looked. Look whenever you like.
          </span>
          <button type="button" onClick={() => go("catchup")} style={css("border:0;background:transparent;padding:0;font:500 13px Geist;color:var(--ink)")}>
            Catch up →
          </button>
          <button
            type="button"
            onClick={() => setNudgeGone(true)}
            aria-label="Dismiss"
            title="Dismiss"
            style={css("width:28px;height:28px;border-radius:50%;border:0;background:transparent;color:var(--muted);font:400 18px/1 Geist;padding:0")}
          >
            ×
          </button>
        </div>
      ) : null}
      <div role="tabpanel" aria-label={tabs.find(([id]) => id === tab)?.[1]} style={css("display:flex;flex-direction:column;gap:32px")}>
        {tab === "knows" ? <KnowsTab go={go} /> : null}
        {tab === "catchup" ? <CatchUpPanel /> : null}
        {tab === "try" ? <TryTab /> : null}
        {tab === "notes" ? <NotesTab /> : null}
        {tab === "sheets" ? <SheetsTab /> : null}
        {tab === "files" ? <FilesTab /> : null}
        {tab === "questions" ? <QuestionsTab /> : null}
      </div>
      {teach ? <TeachModal onClose={() => setTeach(false)} /> : null}
    </div>
  );
}

function TeachModal({ onClose }: { onClose: () => void }) {
  const teach = useTeach();
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const done = teach.data;
  return (
    <Modal title="Teach it something" eyebrow="IN YOUR OWN WORDS" onClose={onClose}>
      {done ? (
        <>
          <span style={css("font:400 15px/1.5 Geist")}>{done.message || "Saved. It waits in Catch up for your yes."}</span>
          <Btn kind="primarySm" onClick={onClose}>
            Done
          </Btn>
        </>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!name.trim() || !text.trim()) return;
            teach.mutate({ title: name.trim(), statement: text.trim() });
          }}
          style={css(S.col)}
        >
          <label style={css(S.col)}>
            <span style={css(S.small)}>What it's about</span>
            <input value={name} onChange={(e) => setName(e.target.value)} style={css(S.input)} placeholder="A few words" />
          </label>
          <label style={css(S.col)}>
            <span style={css(S.small)}>What your AI should know</span>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} style={css(S.input + ";resize:vertical")} placeholder="Say it the way you'd tell a colleague" />
          </label>
          <span style={css(S.small)}>It waits in Catch up for your yes, like everything your AIs suggest.</span>
          <Mistake error={teach.error} />
          <div style={css("display:flex;gap:8px")}>
            <Btn kind="primarySm" type="submit" disabled={teach.isPending || !name.trim() || !text.trim()}>
              {teach.isPending ? "Saving…" : "Save"}
            </Btn>
            <Btn onClick={onClose}>Cancel</Btn>
          </div>
        </form>
      )}
    </Modal>
  );
}

// ------------------------------------------------------------------ What it knows

interface RegionItem {
  t: string;
  m: string;
  h: number;
  go: () => void;
}
interface Region {
  id: string;
  name: string;
  part: string;
  h: number;
  real: string;
  holds: string;
  reach: string;
  stat: string;
  items: RegionItem[];
}

/** A count in words once its query has an answer. */
function counted<T>(q: { data?: T; isLoading: boolean; error: unknown }, say: (data: T) => string): string {
  if (q.isLoading) return "Counting…";
  if (q.error || q.data === undefined) return "Couldn't count right now";
  return say(q.data);
}

function KnowsTab({ go }: { go: (id: TabId) => void }) {
  const navigate = useNavigate();
  const catalog = useBrainCatalog();
  const inventory = useBrainInventory();
  const projects = useBrainProjects();
  const live = useLive();
  const files = useBrainFiles();
  const proposals = useProposals();
  const taste = useTaste();
  const map = useBrainMap();
  const goals = useGoals();
  const [area, setArea] = useState<string | null>(null);
  const tasteRef = useRef<HTMLDivElement>(null);
  const memoryRef = useRef<HTMLDivElement>(null);

  const rules = (map.data?.lines ?? []).filter((l) => l.startsWith("rule ")).map((l) => l.slice(5));
  const areas = catalog.data?.areas ?? [];
  const entries = catalog.data?.entries ?? [];
  const byArea = (key: string) => entries.filter((e) => e.area === key).length;
  const principles = taste.data ? [...taste.data.lenses.looks, ...taste.data.lenses.feels, ...taste.data.lenses.works] : [];
  const fileList = [...(files.data?.references ?? []), ...(files.data?.assets ?? [])];
  const openTaste = () => tasteRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  const openArea = (key: string) => {
    setArea(key);
    memoryRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  };

  const regions: Region[] = [
    {
      id: "fr",
      name: "Projects and goals",
      part: "Frontal lobe",
      h: 320,
      real: "Plans ahead, sets goals, and keeps track of what you're working toward.",
      holds: "Every project: where it stands, its packet, what's kept with it, and the goals it serves.",
      reach: "When a request names a project, its packet goes first.",
      stat: counted(projects, (d) => plural(d.length, "project")),
      items: (projects.data ?? []).slice(0, 6).map((p) => ({ t: p.title, m: p.updated ? when(p.updated) : p.status, h: 320, go: () => navigate(`/projects/${encodeURIComponent(p.id)}`) })),
    },
    {
      id: "pf",
      name: "Context sheets",
      part: "Prefrontal cortex",
      h: 150,
      real: "Holds working memory: what's true right now, while you work.",
      holds: "Short-lived context that changes often, like project status and who wants what. Every cell keeps its history.",
      reach: "Current values only. The history stays home.",
      stat: counted(live, (d) => `${plural(d.sheets.length, "sheet")} · ${plural(d.waiting.length, "value")} waiting`),
      items: (live.data?.sheets ?? []).slice(0, 6).map((s) => ({ t: s.title, m: s.scope || "Brain-wide", h: 150, go: () => navigate(`/brain/sheets/${encodeURIComponent(s.id)}`) })),
    },
    {
      id: "pa",
      name: "Capture",
      part: "Parietal lobe",
      h: 35,
      real: "Takes in signals from the senses and makes sense of them.",
      holds: "What comes in: talk, meetings, uploads, and files you bring in.",
      reach: "Nothing here reaches your AI until you keep part of it.",
      stat: counted(proposals, (d) => `${d.length} in Catch up`),
      items: [
        { t: "Meetings and uploads", m: "open Capture", h: 35, go: () => navigate("/capture") },
        { t: "Catch up", m: proposals.data ? `${proposals.data.length} waiting` : "", h: 35, go: () => go("catchup") },
      ],
    },
    {
      id: "oc",
      name: "Files",
      part: "Occipital lobe",
      h: 210,
      real: "Processes what you see.",
      holds: "Documents it can quote, and assets it keeps byte for byte.",
      reach: "Sent as pointers. Opened only when a request needs them.",
      stat: counted(files, (d) => plural(d.references.length + d.assets.length, "file")),
      items: fileList.slice(0, 5).map((f) => ({ t: f.title || f.path, m: f.kind === "asset" ? "asset" : "document", h: 210, go: () => go("files") })),
    },
    {
      id: "lt",
      name: "Long-term memory",
      part: "Temporal lobe and hippocampus",
      h: 80,
      real: "Stores lasting memories: facts, names, how things are.",
      holds: "Notes that rarely change: who you are, how you work, your rules. Sorted into areas.",
      reach: "Matched by meaning to each request. Only what fits is sent.",
      stat: counted(catalog, (d) => `${plural(d.entries.length, "note")} in ${plural(d.areas.length, "area")}`),
      items: areas.map((a) => ({ t: a.label, m: plural(byArea(a.key), "note"), h: hueOf(a.key), go: () => openArea(a.key) })),
    },
    {
      id: "ce",
      name: "Skills and agents",
      part: "Cerebellum",
      h: 265,
      real: "Learns and runs practiced routines, like riding a bike.",
      holds: "Ways of working your AI follows, and roles it can take on.",
      reach: "Used when a request asks for a skill or an agent.",
      stat: counted(files, (d) => plural(d.skills.length, "skill")),
      items: (files.data?.skills ?? []).slice(0, 5).map((s) => ({ t: s.name, m: "skill", h: 265, go: () => navigate("/agents") })),
    },
    {
      id: "bs",
      name: "Must-holds",
      part: "Brainstem",
      h: 60,
      real: "Runs what must always happen, like breathing.",
      holds: "Rules that go with every request, whatever it's about.",
      reach: "Always sent. Changing one waits for your yes, even in Auto mode.",
      stat: counted(map, () => plural(rules.length, "must-hold") + ((map.data?.pages ?? 1) > 1 ? " on the first page of the map" : "")),
      items: rules.map((t) => ({ t, m: "always", h: 60, go: () => navigate("/settings") })),
    },
    {
      id: "ins",
      name: "Taste",
      part: "Insula, deep inside",
      h: 25,
      real: "Where you sense taste, and gut feeling: the quick “this is right” you feel before you can say why.",
      holds: "Your taste: what looks good, feels good and works good. Principles, contrasts and the words for it.",
      reach: "It works underneath everything else. It goes with creative and design requests, and with any agent that starts from your taste.",
      stat: counted(taste, (d) => plural(d.count, "entry", "entries")),
      items: [
        ...principles.slice(0, 3).map((p) => ({ t: p.text, m: p.strength, h: 25, go: openTaste })),
        { t: "Customize your taste", m: "principles, contrasts, words", h: 25, go: openTaste },
      ],
    },
  ];

  return (
    <>
      <div style={css("display:flex;align-items:center;gap:14px;padding:14px 18px;border-radius:18px;border:1px solid var(--line);flex-wrap:wrap")}>
        <span style={css("width:32px;height:32px;border-radius:50%;background:var(--ink);display:flex;align-items:center;justify-content:center;flex:none")}>
          <span style={css("width:2px;height:14px;background:var(--bg);border-radius:2px;transform:rotate(30deg)")} />
        </span>
        <div style={css("flex:1;min-width:240px;display:flex;flex-direction:column;gap:2px")}>
          <span style={css("font:500 14px Geist")}>Your knowledge agent keeps this Brain tidy</span>
          <span style={css("font:400 13px/1.45 Geist;color:var(--ink2)")}>
            It finds repeats, stale notes, drift and gaps, and runs your scheduled checks. Every change it suggests waits for your yes.
          </span>
        </div>
        <Link to="/agents" style={css("font:500 13px Geist;color:var(--ink);text-decoration:none")}>
          Open it in Agents →
        </Link>
      </div>

      <div style={css("display:flex;align-items:center;gap:16px;padding:16px 20px;border-radius:18px;background:var(--soft);margin-bottom:-8px;flex-wrap:wrap")}>
        <span style={css("font:500 11px 'Geist Mono';color:var(--muted);letter-spacing:.04em;white-space:nowrap")}>WHAT IT'S FOR</span>
        <span style={css("font:400 15px/1.5 Geist;flex:1")}>
          {goals.isLoading
            ? "Loading…"
            : goals.error
              ? "Couldn't load what it's for."
              : goals.data?.purpose?.trim() || "Not written yet. Say what this Brain is for, and every AI starts from it."}
        </span>
        <Link to="/settings" style={css("font:500 13px Geist;color:var(--ink2);text-decoration:none")}>
          Edit
        </Link>
      </div>

      <MapCard />

      <BrainMapCard regions={regions} areas={areas} count={byArea} onArea={openArea} />

      <LoreShelf />

      <div ref={memoryRef}>
        <LongTermMemory catalog={catalog} inventory={inventory.data} area={area} setArea={setArea} />
      </div>

      <ContextSheets live={live} map={map.data?.lines ?? []} onNew={() => go("sheets")} />

      <div ref={tasteRef}>
        <TasteSection />
      </div>

      <LearnedSection />
    </>
  );
}

// ---- the brain map

const CEREBRUM =
  "M52,214 C30,150 70,78 150,52 C215,28 300,22 370,40 C440,58 492,118 488,190 C486,226 470,252 446,262 C410,276 360,286 320,300 C270,318 205,322 170,302 C150,290 146,270 166,256 C140,262 112,262 92,254 C72,246 58,232 52,214 Z";
const CEREB = "M338,292 C342,262 400,250 446,264 C478,274 488,306 468,326 C446,346 382,350 352,334 C336,324 334,304 338,292 Z";
const STEM = "M302,296 C314,302 330,304 344,298 L352,330 C356,350 352,372 348,394 L318,394 C314,372 308,350 304,328 Z";
const INSULA = "M238,224 C246,204 286,188 330,182 C360,178 374,190 362,204 C346,222 300,234 262,236 C246,237 234,232 238,224 Z";
const LOBE: Record<string, string> = {
  pf: "M0,0 L160,0 C150,90 150,170 166,256 L0,400 Z",
  fr: "M160,0 L314,0 C304,70 278,150 252,212 C222,226 190,240 166,256 C150,170 150,90 160,0 Z",
  pa: "M314,0 L440,0 L436,40 C432,90 428,130 426,176 C400,180 372,176 352,168 C344,178 338,186 330,190 C300,198 276,206 252,212 C278,150 304,70 314,0 Z",
  oc: "M440,0 L520,0 L520,400 L430,400 L430,266 C428,230 426,200 426,176 C428,130 432,90 436,40 Z",
  lt: "M0,400 L166,256 C190,240 222,226 252,212 C276,206 300,198 330,190 C338,186 344,178 352,168 C372,176 400,180 426,176 C426,200 428,230 430,266 L430,400 Z",
};
const GYRI = [
  "M70,140 C90,120 112,126 134,108",
  "M64,196 C88,182 114,188 142,176",
  "M84,236 C104,226 124,232 146,222",
  "M120,94 C150,80 180,92 210,82 S262,70 292,62",
  "M114,150 C146,134 178,148 208,136 S252,120 282,110",
  "M150,204 C176,192 200,198 226,186 S246,176 264,168",
  "M290,42 C282,100 260,160 238,208",
  "M342,40 C334,92 314,150 292,196",
  "M330,122 C360,104 392,114 422,100",
  "M360,70 C380,62 400,70 418,60",
  "M372,150 C392,140 408,148 424,138",
  "M196,284 C236,264 284,248 332,228 S392,214 424,222",
  "M228,308 C276,294 324,278 372,264 S412,254 430,252",
  "M448,92 C468,124 472,162 464,202",
  "M442,152 C458,182 458,222 448,252",
];
const BOUND = [
  "M314,10 C304,70 278,150 252,212",
  "M166,256 C190,240 222,226 252,212 C276,206 300,198 330,190 C338,186 344,178 352,168",
  "M436,40 C432,90 428,130 426,176 C426,200 428,230 430,266",
];
const SEQ: [string | null, string][] = [
  ["bs", "1 · Must-holds go out first, with every request."],
  ["fr", "2 · When a request names a project, its packet comes next."],
  ["pf", "3 · Its live sheets add what's true right now."],
  ["ins", "4 · Your taste works underneath, shaping how it's written and designed."],
  ["lt", "5 · Long-term memory fills the gaps, matched by meaning."],
  ["oc", "6 · Files go as pointers, opened only if needed."],
  [null, "Done. See every step for a real request in Try a prompt."],
];
const seqAt = (k: number): [string | null, string] => SEQ[Math.min(k, SEQ.length - 1)] ?? [null, ""];

function BrainMapCard({ regions, areas, count, onArea }: { regions: Region[]; areas: BrainArea[]; count: (key: string) => number; onArea: (key: string) => void }) {
  const [sel, setSel] = useState("lt");
  const [step, setStep] = useState(-1);
  const timers = useRef<number[]>([]);
  useEffect(() => () => timers.current.forEach((t) => window.clearTimeout(t)), []);
  const running = step >= 0 && step < SEQ.length - 1;
  const lit = step >= 0 ? seqAt(step)[0] : null;
  const selId = running && lit ? lit : sel;
  const region = (id: string): Region => regions.find((g) => g.id === id) ?? (regions[4] as Region);
  const R = region(selId);
  const pick = (id: string) => () => {
    timers.current.forEach((t) => window.clearTimeout(t));
    setStep(-1);
    setSel(id);
  };
  const run = () => {
    timers.current.forEach((t) => window.clearTimeout(t));
    setStep(0);
    timers.current = SEQ.map((_, k) => window.setTimeout(() => setStep(k), k * 1000));
  };
  const kb = (id: string) => ({
    tabIndex: 0,
    role: "button",
    "aria-label": region(id).name,
    onKeyDown: (ev: KeyboardEvent) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        pick(id)();
      }
    },
  });
  const groove = dark() ? "rgba(0,0,0,.42)" : "rgba(70,45,20,.17)";
  const st = (id: string): CSSProperties => {
    const g = region(id);
    const on = selId === id;
    const glow = lit === id;
    return {
      fill: on ? tint(g.h, 0.55) : tint(g.h),
      stroke: on ? ink(g.h) : "none",
      strokeWidth: on ? 2.5 : 0,
      cursor: "pointer",
      transition: "fill .3s, opacity .3s",
      opacity: running && !glow ? 0.4 : 1,
      filter: glow ? `drop-shadow(0 0 10px ${solid(g.h)})` : "none",
    };
  };
  const lab = (id: string, x: number, y: number, sz = 12.5) => {
    const g = region(id);
    return (
      <g key={"l" + id} style={{ pointerEvents: "none" }} aria-hidden="true">
        <text x={x} y={y} textAnchor="middle" style={{ font: `500 ${sz}px Geist`, fill: ink(g.h) }}>
          {g.name}
        </text>
        <text x={x} y={y + 14} textAnchor="middle" style={{ font: "400 10px Geist", fill: ink(g.h), opacity: 0.75 }}>
          {g.part}
        </text>
      </g>
    );
  };
  const insOn = selId === "ins" || lit === "ins";
  return (
    <div style={css("background:var(--surface);border-radius:24px;box-shadow:var(--shadow);padding:22px;display:flex;gap:28px;flex-wrap:wrap;align-items:flex-start")}>
      <div style={css("flex:1 1 520px;min-width:0;display:flex;flex-direction:column;gap:12px")}>
        <div style={css("display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap")}>
          <div style={css("display:flex;flex-direction:column;gap:2px")}>
            <span style={css("font:500 15px Geist")}>How your Brain is organized</span>
            <span style={css("font:400 12.5px/1.45 Geist;color:var(--muted)")}>
              Each region holds one kind of context, like the part of a real brain that does the same job. Click one.
            </span>
          </div>
          <button type="button" onClick={run} disabled={running} style={css("padding:7px 14px;border-radius:99px;background:var(--soft);border:0;font:500 12.5px Geist;color:var(--ink)")}>
            {running ? "Watching…" : "Watch a request move through it"}
          </button>
        </div>
        <div style={css("width:100%;max-width:560px;margin:0 auto")}>
          <svg viewBox="0 0 520 400" role="group" aria-label="The regions of your Brain" style={{ width: "100%", height: "auto", display: "block", overflow: "visible" }}>
            <defs>
              <clipPath id="gnBrainC">
                <path d={CEREBRUM} />
              </clipPath>
              <clipPath id="gnBrainCe">
                <path d={CEREB} />
              </clipPath>
              <radialGradient id="gnTG" cx="57%" cy="54%" r="62%">
                <stop offset="0%" stopColor="oklch(0.75 0.14 25)" stopOpacity={0.38} />
                <stop offset="100%" stopColor="oklch(0.75 0.14 25)" stopOpacity={0} />
              </radialGradient>
            </defs>
            <path d={STEM} onClick={pick("bs")} {...kb("bs")} style={st("bs")} />
            <path d="M318,300 C320,330 326,360 330,392 M334,300 C336,330 340,360 342,392" style={{ fill: "none", stroke: groove, strokeWidth: 1.6, pointerEvents: "none" }} />
            <path d={CEREB} onClick={pick("ce")} {...kb("ce")} style={st("ce")} />
            <g clipPath="url(#gnBrainCe)" style={{ pointerEvents: "none" }}>
              {Array.from({ length: 8 }, (_, i) => (
                <path key={i} d={`M332,${276 + i * 9} C372,${262 + i * 9} 432,${262 + i * 9} 486,${280 + i * 8}`} style={{ fill: "none", stroke: groove, strokeWidth: 1.8 }} />
              ))}
            </g>
            <g clipPath="url(#gnBrainC)">
              {["pf", "fr", "pa", "oc", "lt"].map((id) => (
                <path key={id} d={LOBE[id]} onClick={pick(id)} {...kb(id)} style={st(id)} />
              ))}
            </g>
            <g clipPath="url(#gnBrainC)" style={{ pointerEvents: "none" }}>
              {GYRI.map((d, i) => (
                <path key={"g" + i} d={d} style={{ fill: "none", stroke: groove, strokeWidth: 2.2, strokeLinecap: "round" }} />
              ))}
              {BOUND.map((d, i) => (
                <path key={"b" + i} d={d} style={{ fill: "none", stroke: "var(--surface)", strokeWidth: 4, strokeLinecap: "round" }} />
              ))}
            </g>
            <path d={CEREBRUM} style={{ fill: "none", stroke: dark() ? "#45433e" : "#d8d3c9", strokeWidth: 1.5, pointerEvents: "none" }} />
            {insOn ? <path d={CEREBRUM} style={{ fill: "url(#gnTG)", pointerEvents: "none" }} /> : null}
            <path
              d={INSULA}
              onClick={pick("ins")}
              {...kb("ins")}
              style={{
                fill: insOn ? "oklch(0.72 0.14 25 / .42)" : "oklch(0.72 0.14 25 / .18)",
                stroke: "oklch(0.6 0.15 25)",
                strokeWidth: selId === "ins" ? 2.4 : 1.5,
                strokeDasharray: "5 4",
                cursor: "pointer",
                filter: insOn ? "drop-shadow(0 0 12px oklch(0.72 0.15 25))" : "none",
                opacity: running && lit !== "ins" ? 0.45 : 1,
                transition: "all .3s",
              }}
            />
            <text
              x={304}
              y={205}
              textAnchor="middle"
              aria-hidden="true"
              style={{ font: "italic 400 14px Newsreader", fill: dark() ? "oklch(0.85 0.09 25)" : "oklch(0.42 0.12 25)", pointerEvents: "none" }}
            >
              Taste
            </text>
            {lab("pf", 100, 160, 12)}
            {lab("fr", 226, 116)}
            {lab("pa", 376, 96)}
            {lab("oc", 464, 172, 12)}
            {lab("lt", 300, 258)}
            {lab("ce", 410, 300, 12)}
            <g style={{ cursor: "pointer" }} onClick={pick("bs")} aria-hidden="true">
              <text x={362} y={372} style={{ font: "500 12px Geist", fill: ink(60) }}>
                Must-holds
              </text>
              <text x={362} y={386} style={{ font: "400 10px Geist", fill: ink(60), opacity: 0.75 }}>
                Brainstem
              </text>
            </g>
            {areas.slice(0, 8).map((a, i) => (
              <circle
                key={"d" + a.key}
                cx={240 + i * 21}
                cy={290}
                r={Math.min(8, 4 + count(a.key) / 3)}
                onClick={(ev) => {
                  ev.stopPropagation();
                  onArea(a.key);
                }}
                style={{ fill: solid(hueOf(a.key)), stroke: "var(--surface)", strokeWidth: 2, cursor: "pointer" }}
              >
                <title>{`${a.label} · ${plural(count(a.key), "note")}`}</title>
              </circle>
            ))}
          </svg>
        </div>
        <div aria-live="polite" style={css(`font:400 13.5px/1.5 Geist;text-align:center;min-height:20px;color:${step >= 0 ? "var(--ink)" : "var(--muted)"}`)}>
          {step >= 0 ? seqAt(step)[1] : "Click a region to see what it holds and how it reaches your AI."}
        </div>
        <div role="group" aria-label="Regions" style={css("display:flex;gap:6px;flex-wrap:wrap;justify-content:center")}>
          {regions.map((g) => (
            <button
              key={g.id}
              type="button"
              aria-pressed={selId === g.id}
              onClick={pick(g.id)}
              style={css(
                `padding:5px 11px;border-radius:99px;font:${selId === g.id ? 500 : 400} 12px Geist;cursor:pointer;${selId === g.id ? "background:var(--ink);color:var(--bg);border:1px solid var(--ink)" : "background:transparent;color:var(--ink2);border:1px solid var(--line2)"}`,
              )}
            >
              {g.name}
            </button>
          ))}
        </div>
      </div>
      <div style={css("flex:1 1 280px;min-width:260px;display:flex;flex-direction:column;gap:14px")} aria-live="polite">
        <div style={css("display:flex;align-items:center;gap:10px")}>
          <span style={css(dotStyle(R.h, 10))} />
          <span style={css("font:500 10.5px 'Geist Mono';letter-spacing:.06em;color:var(--muted)")}>{R.part.toUpperCase()}</span>
        </div>
        <span style={css("font:400 28px/1.15 Newsreader")}>{R.name}</span>
        <div style={css("display:flex;flex-direction:column;gap:3px")}>
          <span style={css("font:500 12px Geist;color:var(--muted)")}>In a human brain</span>
          <span style={css("font:400 14px/1.5 Geist;color:var(--ink2)")}>{R.real}</span>
        </div>
        <div style={css("display:flex;flex-direction:column;gap:3px")}>
          <span style={css("font:500 12px Geist;color:var(--muted)")}>In your Brain</span>
          <span style={css("font:400 14px/1.5 Geist")}>{R.holds}</span>
        </div>
        <div style={css("display:flex;flex-direction:column;gap:3px")}>
          <span style={css("font:500 12px Geist;color:var(--muted)")}>How it reaches your AI</span>
          <span style={css("font:400 14px/1.5 Geist")}>{R.reach}</span>
        </div>
        <div style={css("display:flex;flex-direction:column")}>
          <span style={css("font:500 13px Geist;padding-bottom:6px")}>{R.stat}</span>
          {R.items.map((x, i) => (
            <button
              key={x.t + i}
              type="button"
              onClick={x.go}
              className="gn-hover"
              style={css("display:flex;align-items:center;gap:10px;padding:9px 0;border:0;border-top:1px solid var(--line);background:transparent;width:100%;text-align:left;color:var(--ink)")}
            >
              <span style={css(dotStyle(x.h))} />
              <span style={css("font:400 14px Geist;flex:1;min-width:0")}>{x.t}</span>
              <span style={css("font:400 12px Geist;color:var(--muted)")}>{x.m}</span>
              <span aria-hidden="true" style={css("color:var(--muted)")}>
                →
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---- long-term memory

function LongTermMemory({
  catalog,
  inventory,
  area,
  setArea,
}: {
  catalog: ReturnType<typeof useBrainCatalog>;
  inventory: InventoryItem[] | undefined;
  area: string | null;
  setArea: (key: string) => void;
}) {
  const uses = useMemo(() => new Map((inventory ?? []).map((i) => [i.id, i.uses])), [inventory]);
  const level = useMemo(() => new Map((inventory ?? []).map((i) => [i.id, i.level])), [inventory]);
  return (
    <div style={css(SECTION)}>
      <div style={css("display:flex;flex-direction:column;gap:4px")}>
        <span style={css(KICKER)}>LONG-TERM · RARELY CHANGES</span>
        <span style={css(BIG)}>Long-term memory</span>
        <span style={css(BLURB)}>Who you are, how you work, and the rules every AI follows. Sorted into areas.</span>
      </div>
      <Loaded
        q={catalog}
        empty={(d) => (d.areas.length === 0 ? <Empty title="Nothing in long-term memory yet">Teach it something, or keep what your AIs suggest in Catch up.</Empty> : null)}
      >
        {(d) => {
          const count = (key: string) => d.entries.filter((e) => e.area === key).length;
          const sorted = [...d.areas].sort((a, b) => count(b.key) - count(a.key));
          const sel = sorted.find((a) => a.key === area) ?? sorted[0];
          if (!sel) return null;
          const weekUses = (key: string) => d.entries.filter((e) => e.area === key).reduce((n, e) => n + (uses.get(e.id)?.d7 ?? 0), 0);
          const notes = d.entries.filter((e) => e.area === sel.key);
          return (
            <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:40px")}>
              <div style={css("display:flex;flex-direction:column;gap:14px")}>
                <div role="group" aria-label="Areas" style={css("display:grid;grid-template-columns:repeat(3,minmax(0,1fr));grid-auto-rows:110px;gap:6px")}>
                  {sorted.map((a, i) => {
                    const u = weekUses(a.key);
                    const h = hueOf(a.key);
                    const L = u >= 10 ? [0.74, 0.12] : u >= 5 ? [0.82, 0.09] : [0.89, 0.06];
                    const on = a.key === sel.key;
                    const span = i === 0 && sorted.length > 2 ? "grid-column:span 2;grid-row:span 2;" : "";
                    return (
                      <button
                        key={a.key}
                        type="button"
                        aria-pressed={on}
                        onClick={() => setArea(a.key)}
                        style={css(
                          `${span}border:0;border-radius:18px;padding:16px;display:flex;flex-direction:column;justify-content:space-between;align-items:flex-start;text-align:left;cursor:pointer;background:oklch(${L[0]} ${L[1]} ${h});color:oklch(0.25 0.05 ${h});outline:${on ? "2px solid var(--ink)" : "2px solid transparent"};outline-offset:2px;transition:outline-color .15s`,
                        )}
                      >
                        <span style={css("font:500 15px Geist")}>{a.label}</span>
                        <span style={css("font:400 13px Geist;opacity:.85")}>
                          {plural(count(a.key), "note")}
                          {inventory ? ` · ${plural(u, "use")}` : ""}
                        </span>
                      </button>
                    );
                  })}
                </div>
                <span style={css("font:400 13px Geist;color:var(--muted)")}>Bigger holds more. Deeper color means your AIs used it more this week.</span>
              </div>
              <div style={css("display:flex;flex-direction:column;gap:14px")}>
                <div style={css("display:flex;align-items:center;gap:10px")}>
                  <span style={css(dotStyle(hueOf(sel.key), 10))} />
                  <span style={css("font:500 16px Geist")}>{sel.label}</span>
                  <span style={css("margin-left:auto;font:400 13px Geist;color:var(--muted)")}>{plural(notes.length, "note")}</span>
                </div>
                {sel.description ? <span style={css("font:400 13px/1.5 Geist;color:var(--ink2)")}>{sel.description}</span> : null}
                <div style={css("display:flex;flex-direction:column")}>
                  {notes.length === 0 ? <span style={css(S.muted)}>No notes in this area yet.</span> : null}
                  {notes.map((n) => (
                    <AreaNote key={n.id} note={n} uses={uses.get(n.id)} level={level.get(n.id)} known={Boolean(inventory)} />
                  ))}
                </div>
              </div>
            </div>
          );
        }}
      </Loaded>
    </div>
  );
}

function AreaNote({ note, uses, level, known }: { note: BrainEntrySummary; uses?: InventoryItem["uses"]; level?: string; known: boolean }) {
  const unused = known && (uses?.d30 ?? 0) === 0;
  const meta = !known ? note.summary : unused ? "Not used in 30 days · tidy up?" : `Used ${uses?.d7 ?? 0}× this week`;
  return (
    <Link
      to={`/brain/notes/${encodeURIComponent(note.id)}`}
      style={css("padding:14px 0;border-top:1px solid var(--line);display:flex;flex-direction:column;gap:4px;text-align:left;color:var(--ink);text-decoration:none")}
    >
      <span style={css("display:flex;gap:8px;align-items:center;flex-wrap:wrap")}>
        <span style={css(`font:400 15px Geist;color:${unused ? "var(--muted)" : "var(--ink)"}`)}>{note.title}</span>
        <LevelChip level={level} />
      </span>
      <span style={css(`font:400 13px Geist;color:${unused ? "oklch(0.58 0.12 35)" : "var(--muted)"}`)}>{meta}</span>
    </Link>
  );
}

// ---- context sheets

function DerivedNote({ name }: { name: string }) {
  return (
    <div style={css("padding:16px 20px;font:400 13.5px/1.5 Geist;color:var(--ink2)")}>
      {name} is worked out by the Brain from your projects and tasks, fresh for each request. Your AIs read it through the Brain; this page can't show its rows yet.
    </div>
  );
}

function ContextSheets({ live, map, onNew }: { live: ReturnType<typeof useLive>; map: string[]; onNew: () => void }) {
  const status = useDerivedSheet("project-status");
  const derived = map
    .filter((l) => l.startsWith("sheet "))
    .map((l) => {
      const [name, cols] = l.slice(6).split(": ");
      return { name: name ?? "", cols: cols ?? "" };
    })
    .filter((s) => Object.values(DERIVED).includes(s.name));
  const statusCols = derived.find((s) => s.name === DERIVED["project-status"])?.cols;
  return (
    <div style={css(SECTION)}>
      <div style={css("display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap")}>
        <div style={css("display:flex;flex-direction:column;gap:4px")}>
          <span style={css(KICKER)}>SHORT-TERM · CHANGES OFTEN</span>
          <span style={css(BIG)}>Context sheets</span>
          <span style={css(BLURB)}>What's true right now. Your AIs get current values only, and every cell keeps its history. Gnomon keeps the auto sheets up to date for you.</span>
        </div>
        <button type="button" onClick={onNew} style={css("border:0;background:transparent;font:500 13px Geist;color:var(--ink2);padding:0")}>
          Manage sheets →
        </button>
      </div>
      <div style={css("background:var(--surface);border-radius:20px;box-shadow:var(--shadow);overflow:hidden")}>
        <div style={css("display:flex;align-items:center;gap:10px;padding:16px 20px;border-bottom:1px solid var(--line);flex-wrap:wrap")}>
          <span style={css("font:500 15px Geist")}>Project status</span>
          <span style={css(AUTO_TAG)}>Auto · kept by Gnomon</span>
          <span style={css("font:400 12.5px Geist;color:var(--muted);flex:1;min-width:140px")}>{statusCols ? `Columns: ${statusCols}` : ""}</span>
          <Link to="/brain/sheets/project-status" style={css("font:500 13px Geist;color:var(--ink2);text-decoration:none")}>
            Open sheet →
          </Link>
        </div>
        {status.isLoading ? (
          <div style={css("padding:0 20px")}>
            <Loading />
          </div>
        ) : status.data ? (
          <SheetGrid view={status.data} />
        ) : (
          <DerivedNote name="Project status" />
        )}
      </div>
      <Loaded q={live}>
        {(d) => (
          <div style={css("display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px")}>
            {d.sheets.map((s) => (
              <SheetCard key={s.id} sheet={s} waiting={d.waiting.filter((w) => w.sheet === s.id).length} />
            ))}
            {derived
              .filter((s) => s.name !== DERIVED["project-status"])
              .map((s) => (
                <Link
                  key={s.name}
                  to={`/brain/sheets/${Object.keys(DERIVED).find((k) => DERIVED[k] === s.name) ?? ""}`}
                  style={css("padding:18px;border-radius:18px;border:1px solid var(--line);background:var(--surface);display:flex;flex-direction:column;gap:8px;text-align:left;color:var(--ink);text-decoration:none")}
                >
                  <div style={css("display:flex;align-items:center;gap:8px;flex-wrap:wrap")}>
                    <span style={css("font:500 15px Geist")}>{s.name}</span>
                    <span style={css(AUTO_TAG)}>Auto</span>
                  </div>
                  <span style={css("font:400 13px/1.45 Geist;color:var(--ink2)")}>Kept by the Brain, worked out fresh each time.</span>
                  <span style={css("font:400 12px Geist;color:var(--faint)")}>{s.cols}</span>
                </Link>
              ))}
            <button
              type="button"
              onClick={onNew}
              style={css("padding:18px;border-radius:18px;border:1.5px dashed var(--line2);background:transparent;font:500 14px Geist;color:var(--ink2);min-height:120px")}
            >
              + New sheet
            </button>
          </div>
        )}
      </Loaded>
    </div>
  );
}

function SheetCard({ sheet, waiting }: { sheet: StateSheet; waiting: number }) {
  return (
    <Link
      to={`/brain/sheets/${encodeURIComponent(sheet.id)}`}
      style={css("padding:18px;border-radius:18px;border:1px solid var(--line);background:var(--surface);display:flex;flex-direction:column;gap:8px;text-align:left;color:var(--ink);text-decoration:none")}
    >
      <span style={css("font:500 15px Geist")}>{sheet.title}</span>
      {sheet.description ? <span style={css("font:400 13px/1.45 Geist;color:var(--ink2)")}>{sheet.description}</span> : null}
      <span style={css("font:400 12px/1.45 Geist;color:var(--muted)")}>{waiting ? `${plural(waiting, "value")} from your AIs waiting` : "Nothing waiting"}</span>
      <span style={css("font:400 12px Geist;color:var(--faint)")}>
        {plural(sheet.columns.length, "column")} · {sheet.scope || "Brain-wide"}
      </span>
    </Link>
  );
}

// ---- taste

const LENS: ["looks" | "feels" | "works", string, string, number][] = [
  ["looks", "Looks good", "How it should look", 210],
  ["feels", "Feels good", "How it should feel", 320],
  ["works", "Works good", "How it should work", 150],
];
const isPrinciple = (e: TasteEntry) => e.kind !== "pair" && e.kind !== "use" && e.kind !== "avoid";

function tasteMeta(p: TasteEntry): string {
  return `${p.strength === "always" ? "Always" : "Usually"} · ${p.domains.length && !p.domains.includes("all") ? p.domains.join(", ") : "everything"}`;
}

function TasteSection() {
  const taste = useTaste();
  const [adding, setAdding] = useState(false);
  return (
    <div style={css("display:flex;flex-direction:column;gap:16px;margin-top:14px;padding-top:34px;border-top:1px solid var(--line)")}>
      <div style={css("display:flex;flex-direction:column;gap:4px")}>
        <span style={css(KICKER)}>UNDERNEATH · SHAPES EVERYTHING</span>
        <span style={css(BIG)}>Taste profile</span>
        <span style={css(BLURB)}>
          What good means to you: how things should look, feel and work. Your AIs build with it, and it keeps learning from what you keep and change.
        </span>
      </div>
      <div style={css("background:var(--surface);border-radius:22px;box-shadow:var(--shadow);padding:24px;display:flex;flex-direction:column;gap:20px")}>
        <Loaded q={taste}>
          {(t) => {
            const all = [...t.lenses.looks, ...t.lenses.feels, ...t.lenses.works];
            const pairs = all.filter((e) => e.kind === "pair");
            const use = t.words.use ?? [];
            const avoid = t.words.avoid ?? [];
            const principles = all.filter(isPrinciple);
            return (
              <>
                <div style={css("display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap")}>
                  <div style={css("display:flex;flex-direction:column;gap:6px;flex:1;min-width:280px;max-width:680px")}>
                    <span style={css(KICKER)}>YOUR TASTE · WHAT LOOKS, FEELS AND WORKS GOOD</span>
                    <span style={css("font:400 24px/1.3 Newsreader;text-wrap:pretty")}>
                      {t.count ? `${plural(t.count, "thing")} your AIs know about your taste.` : "Your taste isn't written down yet."}
                    </span>
                    <span style={css("font:400 13px/1.5 Geist;color:var(--muted)")}>
                      {plural(principles.length, "principle")} · {plural(pairs.length, "contrast")} · {plural(use.length + avoid.length, "word")} to use or avoid.
                    </span>
                  </div>
                  <div style={css("display:flex;gap:8px;flex-wrap:wrap;align-items:center")}>
                    <Btn onClick={() => setAdding(true)}>Customize</Btn>
                    <Btn kind="primarySm" disabled title="Comes in a later release">
                      This or that
                    </Btn>
                    <Later />
                  </div>
                </div>
                <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr));gap:12px")}>
                  {LENS.map(([id, label, sub, h]) => {
                    const items = t.lenses[id].filter(isPrinciple);
                    return (
                      <div key={id} style={css("padding:16px;border-radius:18px;background:var(--soft);display:flex;flex-direction:column;gap:10px")}>
                        <div style={css("display:flex;align-items:center;gap:8px")}>
                          <span style={css(dotStyle(h, 9))} />
                          <span style={css("font:500 15px Geist")}>{label}</span>
                          <span style={css("font:400 12px Geist;color:var(--muted)")}>{sub}</span>
                        </div>
                        {items.length === 0 ? <span style={css(S.small)}>Nothing yet.</span> : null}
                        {items.map((p) => (
                          <div key={p.id} style={css("display:flex;flex-direction:column;gap:2px;padding-top:8px;border-top:1px solid var(--line2)")}>
                            <span style={css("font:400 14px/1.45 Geist")}>{p.text}</span>
                            <span style={css("font:400 11.5px Geist;color:var(--muted)")}>{tasteMeta(p)}</span>
                          </div>
                        ))}
                      </div>
                    );
                  })}
                </div>
                <div style={css("display:flex;flex-direction:column;gap:8px")}>
                  <span style={css("font:500 12px Geist;color:var(--muted)")}>This, not that</span>
                  <div style={css(S.wrap)}>
                    {pairs.length === 0 ? <span style={css(S.small)}>No contrasts yet.</span> : null}
                    {pairs.map((x) => (
                      <span key={x.id} style={css("padding:6px 12px;border-radius:99px;border:1px solid var(--line2);font:400 13px Geist")}>
                        <b style={css("font-weight:500")}>{x.text}</b>
                        <span style={css("color:var(--muted)")}>, not {x.not_that}</span>
                      </span>
                    ))}
                  </div>
                </div>
                <div style={css("display:flex;gap:24px;flex-wrap:wrap")}>
                  <div style={css("display:flex;flex-direction:column;gap:8px")}>
                    <span style={css("font:500 12px Geist;color:var(--muted)")}>Words for it</span>
                    <div style={css(S.wrap)}>
                      {use.length === 0 ? <span style={css(S.small)}>None yet.</span> : null}
                      {use.map((w) => (
                        <span key={w} style={css("padding:4px 10px;border-radius:99px;background:oklch(0.62 0.14 150 / .14);font:400 13px Geist")}>
                          {w}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div style={css("display:flex;flex-direction:column;gap:8px")}>
                    <span style={css("font:500 12px Geist;color:var(--muted)")}>Steer away from</span>
                    <div style={css(S.wrap)}>
                      {avoid.length === 0 ? <span style={css(S.small)}>None yet.</span> : null}
                      {avoid.map((w) => (
                        <span key={w} style={css("padding:4px 10px;border-radius:99px;background:oklch(0.64 0.17 28 / .12);font:400 13px Geist")}>
                          {w}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </>
            );
          }}
        </Loaded>
        <div style={css("display:flex;flex-direction:column;gap:2px;padding:12px 16px;border-radius:16px;border:1px dashed oklch(0.72 0.15 60)")}>
          <span style={css("font:500 12px Geist;color:oklch(0.55 0.14 60);padding-bottom:4px")}>
            Recently learned · keep it?
            <Later />
          </span>
          <span style={css(S.small)}>Learning your taste from what you keep and change comes in a later release. For now, add what you know with Customize.</span>
        </div>
        <div style={css("display:flex;flex-direction:column;gap:10px")}>
          <span style={css("font:500 12px Geist;color:var(--muted)")}>
            References it learns from
            <Later />
          </span>
          <button
            type="button"
            disabled
            style={css("min-height:90px;border-radius:16px;border:1.5px dashed var(--line2);background:transparent;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;color:var(--ink2)")}
          >
            <span style={css("font:500 13.5px Geist")}>+ Add a reference</span>
            <span style={css("font:400 11.5px Geist;color:var(--muted)")}>Image, link, repo, file, video or text</span>
          </button>
        </div>
        <div style={css("display:flex;align-items:center;gap:10px;padding:12px 14px;border-radius:14px;background:var(--soft);flex-wrap:wrap")}>
          <span style={css("font:500 11px 'Geist Mono';letter-spacing:.05em;color:var(--muted)")}>TEAM BRAINS</span>
          <span style={css("font:400 13px/1.45 Geist;color:var(--ink2);flex:1;min-width:220px")}>
            In a team brain, your taste can roll up into the team's taste, governed like a must-hold, so the whole company's AI builds with a shared point of view.
          </span>
          <Later />
        </div>
      </div>
      {adding ? <TasteModal onClose={() => setAdding(false)} /> : null}
    </div>
  );
}

function TasteModal({ onClose }: { onClose: () => void }) {
  const propose = useProposeTaste();
  const [lens, setLens] = useState("looks");
  const [kind, setKind] = useState("principle");
  const [text, setText] = useState("");
  const [notThat, setNotThat] = useState("");
  const [strength, setStrength] = useState("usually");
  const ready = Boolean(text.trim() && (kind !== "pair" || notThat.trim()));
  return (
    <Modal title="Add to your taste" eyebrow="TASTE PROFILE" onClose={onClose}>
      {propose.data ? (
        <>
          <span role="status" style={css("font:400 15px/1.5 Geist")}>
            {propose.data.message}
          </span>
          <div style={css("display:flex;gap:8px")}>
            <Btn kind="primarySm" onClick={onClose}>
              Done
            </Btn>
            <Btn
              onClick={() => {
                propose.reset();
                setText("");
                setNotThat("");
              }}
            >
              Add another
            </Btn>
          </div>
        </>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!ready) return;
            propose.mutate({ text: text.trim(), lens, kind, strength, not_that: kind === "pair" ? notThat.trim() : undefined });
          }}
          style={css("display:flex;flex-direction:column;gap:12px")}
        >
          <div style={css(S.col)}>
            <span style={css(S.small)}>Which part of good</span>
            <Chips value={lens} onChange={setLens} label="Lens" options={LENS.map(([id, l]) => [id, l] as [string, string])} />
          </div>
          <div style={css(S.col)}>
            <span style={css(S.small)}>What it is</span>
            <Chips
              value={kind}
              onChange={setKind}
              label="Kind"
              options={[
                ["principle", "A principle"],
                ["pair", "This, not that"],
                ["use", "A word to use"],
                ["avoid", "A word to avoid"],
              ]}
            />
          </div>
          <label style={css(S.col)}>
            <span style={css(S.small)}>{kind === "pair" ? "This" : kind === "use" || kind === "avoid" ? "The word" : "In your words"}</span>
            <input value={text} onChange={(e) => setText(e.target.value)} style={css(S.input)} />
          </label>
          {kind === "pair" ? (
            <label style={css(S.col)}>
              <span style={css(S.small)}>Not that</span>
              <input value={notThat} onChange={(e) => setNotThat(e.target.value)} style={css(S.input)} />
            </label>
          ) : null}
          <div style={css(S.col)}>
            <span style={css(S.small)}>How firm</span>
            <Chips
              value={strength}
              onChange={setStrength}
              label="How firm"
              options={[
                ["usually", "Usually"],
                ["always", "Always"],
              ]}
            />
          </div>
          <Mistake error={propose.error} />
          <div style={css("display:flex;gap:8px")}>
            <Btn kind="primarySm" type="submit" disabled={!ready || propose.isPending}>
              {propose.isPending ? "Saving…" : "Add it"}
            </Btn>
            <Btn onClick={onClose}>Cancel</Btn>
          </div>
        </form>
      )}
    </Modal>
  );
}

// ---- learned rules

function LearnedSection() {
  const learned = useLearned();
  const forget = useForgetLearned();
  return (
    <div style={css("display:flex;flex-direction:column;gap:12px;margin-top:14px;padding-top:34px;border-top:1px solid var(--line)")}>
      <div style={css("display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap")}>
        <div style={css("display:flex;flex-direction:column;gap:4px")}>
          <span style={css(KICKER)}>FROM YOUR UNDOS</span>
          <span style={css("font:400 22px Newsreader")}>What it learned to ask about</span>
          <span style={css(BLURB)}>When you undo something that went in on its own, it asks first next time. Forget one to let those through again.</span>
        </div>
        <Link to="/settings" style={css("font:500 13px Geist;color:var(--ink2);text-decoration:none")}>
          Settings →
        </Link>
      </div>
      <Loaded q={learned} empty={(d) => (d.length === 0 ? <span style={css(S.muted)}>Nothing learned from undos yet.</span> : null)}>
        {(rules) => (
          <div style={css("display:flex;flex-direction:column")}>
            {rules.map((r) => (
              <div key={r.id} style={css("display:flex;align-items:center;gap:12px;padding:10px 0;border-top:1px solid var(--line);flex-wrap:wrap")}>
                <span style={css("font:400 14px Geist;flex:1;min-width:200px")}>{r.says}</span>
                <span style={css(S.small)}>{[r.area, r.origin, when(r.at)].filter(Boolean).join(" · ")}</span>
                <Btn onClick={() => forget.mutate(r.id)} disabled={forget.isPending}>
                  Forget
                </Btn>
              </div>
            ))}
            <Mistake error={forget.error} />
          </div>
        )}
      </Loaded>
    </div>
  );
}

// ------------------------------------------------------------------ Try a prompt

const MODE: Record<string, string> = {
  lean: "A short packet",
  standard: "A standard packet",
  micro: "A small packet",
  deep: "A deep packet",
  none: "No packet",
};

interface Step {
  t: string;
  meta: string;
  why: string;
  items: { t: string; src: string; tok?: string; to?: string }[];
}

function TryTab() {
  const [text, setText] = useState("");
  const [asked, setAsked] = useState("");
  const preview = usePreview(asked);
  const [copied, setCopied] = useState(false);
  const p = preview.data;
  const steps: Step[] = p
    ? [
        {
          t: "Read the request",
          meta: MODE[p.mode] ?? p.mode,
          why: p.project ? `It names a project: ${p.project.title}.` : "No project matched, by name or by meaning.",
          items: (p.log ?? []).map((l) => ({ t: l, src: "" })),
        },
        {
          t: "Project memory",
          meta: p.project ? p.project.title : "No project",
          why: p.project ? "The project's packet goes first." : "Nothing project-specific goes in.",
          items: [],
        },
        {
          t: "Always-on rules",
          meta: p.must_holds?.length ? plural(p.must_holds.length, "rule") : "None apply",
          why: "Must-holds in this request's domain go with it, whatever it's about.",
          items: (p.must_holds ?? []).map((m) => ({
            t: m.line || m.title,
            src: m.why || (m.triggers.length ? `brought in by: ${m.triggers.join(", ")}` : ""),
            to: `/brain/notes/${encodeURIComponent(m.id)}`,
          })),
        },
        {
          t: "Your Brain, by meaning",
          meta: `${p.candidates.length} considered → ${p.notes.length}`,
          why: p.notes.length ? "The notes that fit the request best, in the order they go." : "No note fit the request well enough to send.",
          items: p.notes.map((n) => ({
            t: n.title,
            src: [n.topic, n.why].filter(Boolean).join(" · "),
            tok: `match ${Number(n.score ?? 0).toFixed(2)}`,
            to: `/brain/notes/${encodeURIComponent(n.id)}`,
          })),
        },
        {
          t: "Files",
          meta: p.sections.length ? plural(p.sections.length, "part") : "None",
          why: "Parts of documents it can quote, chosen for what the request asks.",
          items: p.sections.map((s) => ({ t: s.title || s.label, src: `${s.file} · ${s.why}`, tok: `match ${Number(s.score ?? 0).toFixed(2)}` })),
        },
        {
          t: "Procedure",
          meta: p.procedure ?? "None",
          why: p.procedure ? (p.skill_included ? "Its steps come in full." : "Named, so your AI can open it if it needs it.") : "No skill fits this request.",
          items: [],
        },
        {
          t: "Fit to budget",
          meta: `${(p.tokens ?? 0).toLocaleString()} tokens`,
          why: p.budget ? `Within a budget of ${p.budget.toLocaleString()} tokens.` : "The preview doesn't report the budget it fit to.",
          items: [],
        },
      ]
    : [];
  return (
    <div style={css("display:flex;flex-direction:column;gap:20px")}>
      <span style={css("font:400 15px/1.5 Geist;color:var(--ink2);max-width:720px")}>
        Ask anything, the way your AI would. See exactly what your Brain sends, in what order, and why. Nothing here is saved or sent.
      </span>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!text.trim()) return;
          setCopied(false);
          setAsked(text.trim());
        }}
        style={css("background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:18px;display:flex;flex-direction:column;gap:12px")}
      >
        <div style={css("display:flex;gap:8px")}>
          <label className="gn-sr" htmlFor="gn-try">
            Your request
          </label>
          <input
            id="gn-try"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Ask about a project, or anything at all"
            style={css("flex:1;min-width:0;border:1px solid var(--line2);border-radius:14px;padding:12px 14px;outline:none;background:var(--bg);color:var(--ink);font:400 15px Geist")}
          />
          <Btn kind="primary" type="submit" disabled={!text.trim() || preview.isFetching}>
            {preview.isFetching ? "Building…" : "Show what it sends"}
          </Btn>
        </div>
        <div style={css("display:flex;gap:6px;flex-wrap:wrap;align-items:center")}>
          <span style={css("font:400 12px Geist;color:var(--muted)")}>The packet is the same for every connected app.</span>
          <span style={css("margin-left:auto;font:400 12px Geist;color:var(--muted)")}>
            {p?.budget ? `Budget: ${p.budget.toLocaleString()} tokens` : "Budget: set by the Brain for each kind of request"}
          </span>
        </div>
      </form>
      {!asked ? (
        <div style={css("padding:40px 24px;border-radius:20px;border:1.5px dashed var(--line2);text-align:center;font:400 14.5px/1.5 Geist;color:var(--muted)")}>
          Type a request above to watch your Brain build what it sends.
        </div>
      ) : preview.isLoading ? (
        <Loading what="Building the packet" />
      ) : preview.error ? (
        <Failure error={preview.error} retry={() => void preview.refetch()} />
      ) : p ? (
        <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,380px),1fr));gap:20px;align-items:start")}>
          <ol aria-label="Steps" style={css("display:flex;flex-direction:column;gap:10px;margin:0;padding:0;list-style:none")}>
            {steps.map((s, i) => (
              <li key={s.t} style={css("background:var(--surface);border-radius:18px;box-shadow:var(--shadow);padding:14px 16px;display:flex;flex-direction:column;gap:6px")}>
                <div style={css("display:flex;align-items:center;gap:10px")}>
                  <span style={css("width:24px;height:24px;border-radius:50%;flex:none;background:var(--soft);display:flex;align-items:center;justify-content:center;font:500 12px Geist")}>{i + 1}</span>
                  <span style={css("font:500 15px Geist")}>{s.t}</span>
                  <span style={css("margin-left:auto;font:400 12px Geist;color:var(--muted);text-align:right")}>{s.meta}</span>
                </div>
                <span style={css("font:400 13.5px/1.55 Geist;color:var(--ink2);padding-left:34px")}>{s.why}</span>
                {s.items.length ? (
                  <div style={css("display:flex;flex-direction:column;padding-left:34px")}>
                    {s.items.map((it, k) => (
                      <div key={it.t + k} style={css("display:flex;gap:10px;align-items:flex-start;padding:8px 0;border-top:1px solid var(--line)")}>
                        <span style={css(dotStyle(hueOf(s.t)) + ";margin-top:6px")} />
                        <div style={css("display:flex;flex-direction:column;gap:1px;flex:1;min-width:0")}>
                          {it.to ? (
                            <Link to={it.to} style={css("font:400 14px Geist;color:var(--ink)")}>
                              {it.t}
                            </Link>
                          ) : (
                            <span style={css("font:400 14px Geist")}>{it.t}</span>
                          )}
                          {it.src ? <span style={css("font:400 12px/1.4 Geist;color:var(--muted)")}>{it.src}</span> : null}
                        </div>
                        {it.tok ? <span style={css("font:400 11.5px 'Geist Mono';color:var(--muted);white-space:nowrap")}>{it.tok}</span> : null}
                      </div>
                    ))}
                  </div>
                ) : null}
              </li>
            ))}
          </ol>
          <div style={css("position:sticky;top:24px;display:flex;flex-direction:column;gap:12px")}>
            <div style={css("background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:18px;display:flex;flex-direction:column;gap:10px")}>
              <div style={css("display:flex;justify-content:space-between;gap:10px")}>
                <span style={css("font:500 14px Geist")}>The packet</span>
                <span style={css("font:400 12px Geist;color:var(--muted)")}>
                  {(p.tokens ?? 0).toLocaleString()} tokens{p.budget ? ` of ${p.budget.toLocaleString()}` : ""}
                </span>
              </div>
              <span style={css(S.small)}>
                {plural(p.notes.length, "note")} · {plural(p.must_holds?.length ?? 0, "rule")} · {plural(p.sections.length, "file part")}
                {p.project ? " · 1 project" : ""}
              </span>
            </div>
            {p.reason ? <span style={css(S.muted)}>{p.reason}</span> : null}
            <div style={css("background:var(--code);border-radius:20px;padding:16px 18px;display:flex;flex-direction:column;gap:10px")}>
              <div style={css("display:flex;align-items:center;gap:10px")}>
                <span style={css("font:500 11px 'Geist Mono';letter-spacing:.05em;color:#8f8c84;flex:1")}>EXACTLY WHAT YOUR AI RECEIVES</span>
                <button
                  type="button"
                  onClick={() => {
                    void navigator.clipboard?.writeText(p.text).then(
                      () => setCopied(true),
                      () => setCopied(false),
                    );
                  }}
                  style={css("padding:4px 12px;border-radius:99px;background:#3a3935;color:#fff;border:0;font:500 12px Geist")}
                >
                  {copied ? "Copied" : "Copy"}
                </button>
              </div>
              <pre style={css("margin:0;font:400 12px/1.65 'Geist Mono';color:#d8d5cd;white-space:pre-wrap;word-break:break-word;max-height:520px;overflow:auto")}>
                {p.text || "Nothing would be sent for this request."}
              </pre>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

// ------------------------------------------------------------------ Notes

type ViewId = "live" | "due" | "unused" | "most" | "week" | "fromai" | "heavy" | "archived";
const DAY = 86_400_000;
const ago = (iso: string | null | undefined) => (iso ? (Date.now() - new Date(iso).getTime()) / DAY : Infinity);
const isDue = (n: InventoryItem) => Boolean(n.stale) || (n.review_due ? ago(n.review_due) >= 0 : false);
const VIEWS: [ViewId, string, (n: InventoryItem) => boolean][] = [
  ["live", "Everything live", (n) => n.live],
  ["due", "Due for a check", (n) => n.live && isDue(n)],
  ["unused", "Unused for 60 days", (n) => n.live && ago(n.uses.last) > 60],
  ["most", "Most used", (n) => n.live && n.uses.d30 > 0],
  ["week", "Changed this week", (n) => n.live && ago(n.updated ?? n.revised ?? n.added) <= 7],
  ["fromai", "From AI, never checked", (n) => n.live && !n.checked && Boolean(n.origin) && n.origin?.kind !== "you"],
  ["heavy", "Heaviest", (n) => n.live],
  ["archived", "Archived", (n) => !n.live],
];

function NotesTab() {
  const inventory = useBrainInventory();
  const [view, setView] = useState<ViewId>("live");
  return (
    <Loaded q={inventory}>
      {(items) => {
        const notes = items.filter((i) => i.type === "note");
        const test = VIEWS.find(([id]) => id === view)?.[2] ?? (() => true);
        let shown = notes.filter(test);
        if (view === "most") shown = [...shown].sort((a, b) => b.uses.d30 - a.uses.d30);
        if (view === "heavy") shown = [...shown].sort((a, b) => b.tokens - a.tokens);
        return (
          <div style={css("display:flex;flex-direction:column;gap:18px")}>
            <Chips value={view} onChange={setView} label="Saved views" options={VIEWS.map(([id, l, t]) => [id, `${l} · ${notes.filter(t).length}`] as [ViewId, string])} />
            <div style={css("background:var(--surface);border-radius:20px;box-shadow:var(--shadow);overflow:auto")}>
              <div style={css("min-width:760px")}>
                <div style={css("display:flex;gap:12px;padding:12px 20px;border-bottom:1px solid var(--line);font:500 12px Geist;color:var(--muted)")}>
                  <span style={css("flex:1")}>Note</span>
                  <span style={css("width:140px")}>Area</span>
                  <span style={css("width:110px")}>Owner</span>
                  <span style={css("width:76px")}>Uses 7/30</span>
                  <span style={css("width:76px")}>Last used</span>
                  <span style={css("width:80px")}>Checked</span>
                  <span style={css("width:56px;text-align:right")}>Tokens</span>
                </div>
                {shown.length === 0 ? (
                  <div style={css("padding:48px;text-align:center;font:400 15px Geist;color:var(--muted)")}>
                    {view === "archived" ? "Nothing here yet. Retired notes land here, kept as history." : notes.length ? "No notes in this view." : "No notes yet. Teach it something, or keep what your AIs suggest."}
                  </div>
                ) : null}
                {shown.map((n) => {
                  const due = isDue(n);
                  return (
                    <Link
                      key={n.id}
                      to={`/brain/notes/${encodeURIComponent(n.id)}`}
                      className="gn-hover"
                      style={css("display:flex;gap:12px;align-items:center;padding:13px 20px;border-bottom:1px solid var(--line);background:transparent;text-align:left;color:var(--ink);text-decoration:none")}
                    >
                      <span style={css("flex:1;font:400 14px Geist;display:flex;gap:10px;align-items:center;min-width:0")}>
                        <span style={css(dotStyle(hueOf(n.area)))} />
                        {n.title}
                        <LevelChip level={n.level} />
                      </span>
                      <span style={css("width:140px;font:400 13px Geist;color:var(--ink2)")}>{n.area_label || n.area}</span>
                      <span style={css("width:110px;font:400 13px Geist;color:var(--ink2)")}>{n.owner || "No owner"}</span>
                      <span style={css("width:76px;font:400 13px Geist;color:var(--muted)")}>
                        {n.uses.d7}/{n.uses.d30}
                      </span>
                      <span style={css("width:76px;font:400 13px Geist;color:var(--muted)")}>{n.uses.last ? when(n.uses.last).split(",")[0] : "Never"}</span>
                      <span style={css(`width:80px;font:400 13px Geist;color:${n.checked ? "oklch(0.5 0.12 150)" : due ? "oklch(0.58 0.12 35)" : "var(--muted)"}`)}>
                        {n.checked ? "Checked" : due ? "Due" : "Not yet"}
                      </span>
                      <span style={css("width:56px;text-align:right;font:400 13px 'Geist Mono';color:var(--muted)")}>{n.tokens}</span>
                    </Link>
                  );
                })}
              </div>
            </div>
          </div>
        );
      }}
    </Loaded>
  );
}

// ------------------------------------------------------------------ Sheets

interface SheetRowView {
  id: string;
  name: string;
  scope: string;
  cols: number;
  waiting: number;
  auto: boolean;
  sheet: StateSheet | null;
}

function SheetsTab() {
  const live = useLive();
  const [sel, setSel] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "yours" | "auto">("all");
  const [making, setMaking] = useState(false);
  return (
    <div style={css("display:flex;flex-direction:column;gap:18px")}>
      <div style={css("display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap")}>
        <span style={css("font:400 15px/1.5 Geist;color:var(--ink2);max-width:620px")}>
          Short-lived context that changes often. Unlike notes, sheets aren't long-term memory: your AIs get the current values, and every cell keeps how it changed.
        </span>
        <div style={css("display:flex;align-items:center;gap:14px")}>
          <span style={css("font:500 13px Geist;color:var(--muted)")}>
            Show archived
            <Later />
          </span>
          <Btn kind="primarySm" onClick={() => setMaking(true)}>
            New sheet
          </Btn>
        </div>
      </div>
      <Chips
        value={filter}
        onChange={setFilter}
        label="Which sheets"
        options={[
          ["all", "All"],
          ["yours", "Kept by you"],
          ["auto", "Auto"],
        ]}
      />
      <Loaded q={live}>
        {(d) => {
          const rows: SheetRowView[] = [
            ...(filter === "auto"
              ? []
              : d.sheets.map((s) => ({ id: s.id, name: s.title, scope: s.scope || "Brain-wide", cols: s.columns.length, waiting: d.waiting.filter((w) => w.sheet === s.id).length, auto: false, sheet: s }))),
            ...(filter === "yours" ? [] : Object.entries(DERIVED).map(([id, name]) => ({ id, name, scope: "Brain-wide", cols: 0, waiting: 0, auto: true, sheet: null }))),
          ];
          const picked = rows.find((r) => r.id === sel) ?? null;
          return (
            <div style={css("display:flex;gap:24px;align-items:flex-start;flex-wrap:wrap")}>
              <div style={css("flex:1 1 520px;min-width:0;background:var(--surface);border-radius:20px;box-shadow:var(--shadow);overflow:hidden")}>
                <div style={css("display:flex;gap:12px;padding:12px 20px;border-bottom:1px solid var(--line);font:500 12px Geist;color:var(--muted)")}>
                  <span style={css("flex:1")}>Sheet</span>
                  <span style={css("width:130px")}>Scope</span>
                  <span style={css("width:64px")}>Columns</span>
                  <span style={css("width:64px")}>Waiting</span>
                  <span style={css("width:110px")}>Sent</span>
                </div>
                {rows.length === 0 ? <div style={css("padding:40px;text-align:center;font:400 14px Geist;color:var(--muted)")}>No sheets here.</div> : null}
                {rows.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    aria-pressed={sel === r.id}
                    onClick={() => setSel(r.id)}
                    style={css(
                      `display:flex;gap:12px;align-items:center;padding:13px 20px;border:0;border-bottom:1px solid var(--line);width:100%;text-align:left;color:var(--ink);background:${sel === r.id ? "var(--soft)" : "transparent"}`,
                    )}
                  >
                    <div style={css("flex:1;min-width:0;display:flex;flex-direction:column;gap:2px")}>
                      <span style={css("font:400 14px Geist")}>{r.name}</span>
                      <span style={css("font:400 12px Geist;color:var(--muted)")}>{r.auto ? "Auto · kept by Gnomon" : "Kept by you and your AIs"}</span>
                    </div>
                    <span style={css("width:130px;display:flex")}>
                      <span style={css("padding:3px 9px;border-radius:99px;background:var(--soft);font:500 11.5px Geist;color:var(--ink2)")}>{r.scope}</span>
                    </span>
                    <span style={css("width:64px;font:400 13px Geist;color:var(--ink2)")}>{r.auto ? "Fixed" : r.cols}</span>
                    <span style={css("width:64px;font:400 13px Geist;color:var(--ink2)")}>{r.auto ? "None" : r.waiting}</span>
                    <span style={css("width:110px;font:400 13px Geist;color:var(--ink2)")}>Current values</span>
                  </button>
                ))}
              </div>
              {picked ? <SheetSide picked={picked} /> : null}
            </div>
          );
        }}
      </Loaded>
      {making ? <NewSheetModal templates={live.data?.templates ?? []} onClose={() => setMaking(false)} /> : null}
    </div>
  );
}

function SheetSide({ picked }: { picked: SheetRowView }) {
  return (
    <div style={css("flex:0 1 360px;min-width:300px;position:sticky;top:24px;background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:22px;display:flex;flex-direction:column;gap:16px")}>
      <div style={css("display:flex;flex-direction:column;gap:6px")}>
        <div style={css("display:flex;gap:6px")}>
          <span style={css("padding:3px 9px;border-radius:99px;background:var(--soft);font:500 11.5px Geist;color:var(--ink2)")}>{picked.scope}</span>
          {picked.auto ? <span style={css(AUTO_TAG)}>Auto</span> : null}
        </div>
        <span style={css("font:400 24px Newsreader")}>{picked.name}</span>
        <span style={css("font:400 13px Geist;color:var(--muted)")}>
          {picked.auto ? "Worked out by the Brain for each request." : `${plural(picked.cols, "column")} · ${plural(picked.waiting, "value")} waiting`}
        </span>
      </div>
      {picked.sheet ? (
        <div style={css("display:flex;flex-direction:column;gap:8px")}>
          <span style={css("font:500 12px Geist;color:var(--muted)")}>Columns</span>
          <div style={css(S.wrap)}>
            {picked.sheet.columns.map((c) => (
              <span key={c.name} style={css("padding:5px 12px;border-radius:99px;background:var(--soft);font:400 12px Geist")}>
                {c.name}
              </span>
            ))}
          </div>
        </div>
      ) : null}
      <div style={css("display:flex;flex-direction:column;gap:4px")}>
        <span style={css("font:500 12px Geist;color:var(--muted)")}>When it's sent</span>
        <span style={css("font:400 13.5px/1.5 Geist")}>Current values only. The history stays home.</span>
      </div>
      <div style={css("display:flex;flex-direction:column;gap:4px")}>
        <span style={css("font:500 12px Geist;color:var(--muted)")}>
          Scope, who keeps it current, review and cell history
          <Later />
        </span>
        <span style={css(S.small)}>Set by the sheet's template for now.</span>
      </div>
      <button type="button" disabled style={css("display:flex;flex-direction:column;gap:2px;padding:12px 14px;border-radius:14px;border:0;background:var(--soft);text-align:left;color:var(--ink)")}>
        <span style={css("font:500 13px Geist")}>
          Settled values → long-term notes
          <Later />
        </span>
        <span style={css("font:400 12px/1.4 Geist;color:var(--ink2)")}>Values that stopped changing can become Brain notes, after your yes.</span>
      </button>
      <div style={css("display:flex;gap:8px;flex-wrap:wrap;border-top:1px solid var(--line);padding-top:14px")}>
        <Link to={`/brain/sheets/${encodeURIComponent(picked.id)}`} style={css(S.primarySm + ";text-decoration:none")}>
          Open sheet
        </Link>
        <Btn disabled title="Comes in a later release">
          Duplicate
        </Btn>
        <Btn disabled title="Comes in a later release">
          Archive
        </Btn>
      </div>
    </div>
  );
}

function NewSheetModal({ templates, onClose }: { templates: { id: string; title: string; columns: string[] }[]; onClose: () => void }) {
  const act = useSheetAct();
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [template, setTemplate] = useState("");
  const [columns, setColumns] = useState("");
  const cols = columns
    .split(",")
    .map((c) => c.trim())
    .filter(Boolean);
  const ready = Boolean(title.trim() && (template || cols.length));
  return (
    <Modal title="New sheet" eyebrow="CONTEXT SHEETS" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!ready) return;
          act.mutate(
            { action: "create_sheet", fields: { title: title.trim(), template, columns: cols.map((name) => ({ name })) } },
            { onSuccess: (done) => (done.sheet?.id ? navigate(`/brain/sheets/${encodeURIComponent(done.sheet.id)}`) : onClose()) },
          );
        }}
        style={css("display:flex;flex-direction:column;gap:12px")}
      >
        <label style={css(S.col)}>
          <span style={css(S.small)}>Name</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} style={css(S.input)} />
        </label>
        <label style={css(S.col)}>
          <span style={css(S.small)}>Start from</span>
          <select value={template} onChange={(e) => setTemplate(e.target.value)} style={css(S.input)}>
            <option value="">No template: my own columns</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.title} ({t.columns.join(", ")})
              </option>
            ))}
          </select>
        </label>
        <label style={css(S.col)}>
          <span style={css(S.small)}>{template ? "More columns (optional), separated by commas" : "Columns, separated by commas"}</span>
          <input value={columns} onChange={(e) => setColumns(e.target.value)} style={css(S.input)} />
        </label>
        <Mistake error={act.error} />
        <div style={css("display:flex;gap:8px")}>
          <Btn kind="primarySm" type="submit" disabled={!ready || act.isPending}>
            {act.isPending ? "Making…" : "Make it"}
          </Btn>
          <Btn onClick={onClose}>Cancel</Btn>
        </div>
      </form>
    </Modal>
  );
}

// ------------------------------------------------------------------ Files

function sizeOf(bytes: number): string {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function FilesTab() {
  const files = useBrainFiles();
  const add = useAddFile();
  const [which, setWhich] = useState<"all" | "documents" | "assets">("all");
  const input = useRef<HTMLInputElement>(null);
  return (
    <div style={css("display:flex;flex-direction:column;gap:18px")}>
      <div style={css("display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap")}>
        <Chips
          value={which}
          onChange={setWhich}
          label="Which files"
          options={[
            ["all", "Everything"],
            ["documents", "Documents"],
            ["assets", "Assets"],
          ]}
        />
        <div>
          <input
            ref={input}
            type="file"
            aria-label="Choose a file to add"
            className="gn-sr"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) add.mutate(file);
              e.target.value = "";
            }}
          />
          <Btn onClick={() => input.current?.click()} disabled={add.isPending}>
            {add.isPending ? "Adding…" : "Add a file"}
          </Btn>
        </div>
      </div>
      {add.data ? (
        <span role="status" style={css(S.muted)}>
          {add.data.message || (add.data.status === "pending" ? "It waits in Catch up for your yes." : "Filed.")}
        </span>
      ) : null}
      <Mistake error={add.error} />
      <Loaded q={files}>
        {(d) => {
          const list: BrainFile[] = which === "documents" ? d.references : which === "assets" ? d.assets : [...d.references, ...d.assets];
          if (!list.length)
            return (
              <Empty title={which === "assets" ? "No assets yet" : which === "documents" ? "No documents yet" : "No files yet"}>
                Add a file to keep it in your Brain. Documents can be quoted; assets are kept byte for byte.
              </Empty>
            );
          return (
            <div style={css("display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px")}>
              {list.map((x) => {
                const ext = (x.path.split(".").pop() ?? "").toUpperCase().slice(0, 5);
                return (
                  <a
                    key={x.path}
                    href={fileUrl(x.path)}
                    download
                    title="Download"
                    style={css("padding:20px;border-radius:18px;background:var(--surface);border:0;box-shadow:var(--shadow);display:flex;flex-direction:column;gap:14px;text-align:left;color:var(--ink);text-decoration:none")}
                  >
                    <span
                      style={css(
                        "width:46px;height:56px;border-radius:10px;background:var(--soft);display:flex;align-items:flex-end;justify-content:center;padding-bottom:8px;box-sizing:border-box;font:500 10px 'Geist Mono';color:var(--muted)",
                      )}
                    >
                      {ext}
                    </span>
                    <span style={css("font:400 15px Geist;word-break:break-word")}>{x.title || x.path}</span>
                    <span style={css("font:400 13px Geist;color:var(--muted)")}>
                      {[x.kind === "asset" ? "Asset" : "Document", x.project_title, sizeOf(x.size), x.updated ? when(x.updated) : ""].filter(Boolean).join(" · ")}
                    </span>
                  </a>
                );
              })}
            </div>
          );
        }}
      </Loaded>
      <span style={css("font:400 13px Geist;color:var(--muted)")}>Documents are quoted in the part a request is about. Assets are kept byte for byte. Click one to download it.</span>
    </div>
  );
}

// ------------------------------------------------------------------ Questions

function gapLine(g: Gap): string {
  if (g.kind === "flagged") return "Your AI flagged it: the Brain didn't hold what this needed";
  if (g.kind === "searched") return `Your AI had to search for ${g.entry_title ? `“${g.entry_title}”` : "a note"}: the packet didn't bring it`;
  return g.close.length ? `Nothing matched. Closest: ${g.close.map((c) => c.title).join(", ")}` : "Your Brain had nothing for it";
}

function QuestionsTab() {
  const gaps = useGaps();
  const dismiss = useDismissGap();
  const teach = useTeach();
  const [open, setOpen] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [answered, setAnswered] = useState<Record<string, string>>({});
  return (
    <div style={css("display:flex;flex-direction:column;gap:14px;max-width:760px")}>
      <span style={css("font:400 15px/1.55 Geist;color:var(--ink2)")}>Your AIs asked these and your Brain had nothing. Answer once and every app knows.</span>
      <Loaded q={gaps} empty={(d) => (d.length === 0 ? <Empty title="No questions">Your Brain had something for every request in the last 30 days.</Empty> : null)}>
        {(list) => (
          <>
            {list.map((g) => (
              <div key={g.key} style={css("background:var(--surface);border-radius:20px;padding:22px 24px;box-shadow:var(--shadow);display:flex;flex-direction:column;gap:12px")}>
                <span style={css("font:400 22px/1.35 Newsreader")}>“{g.request || "A request with no words"}”</span>
                <span style={css("font:400 13px Geist;color:var(--muted)")}>
                  {gapLine(g)} · {when(g.at)}
                </span>
                {g.kind === "searched" && g.entry ? (
                  <Link to={`/brain/notes/${encodeURIComponent(g.entry)}`} style={css("font:500 13px Geist;color:var(--ink2)")}>
                    Open the note it found
                  </Link>
                ) : null}
                {answered[g.key] ? (
                  <span role="status" style={css("font:400 14px Geist;color:oklch(0.5 0.12 150)")}>
                    Answered: {answered[g.key]}. It waits in Catch up for your yes.
                  </span>
                ) : open === g.key ? (
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      const answer = text.trim();
                      if (!answer) return;
                      teach.mutate(
                        { title: (g.request || "An answer").slice(0, 120), statement: answer },
                        {
                          onSuccess: () => {
                            setAnswered((a) => ({ ...a, [g.key]: answer }));
                            setOpen(null);
                            setText("");
                          },
                        },
                      );
                    }}
                    style={css("display:flex;flex-direction:column;gap:6px")}
                  >
                    <div style={css("display:flex;gap:8px")}>
                      <input
                        aria-label="Your answer"
                        value={text}
                        onChange={(e) => setText(e.target.value)}
                        placeholder="Type the answer in your own words"
                        style={css("flex:1;border:1px solid var(--line2);border-radius:12px;padding:10px 14px;outline:none;background:var(--bg);color:var(--ink);font:400 15px Geist")}
                      />
                      <Btn kind="primarySm" type="submit" disabled={!text.trim() || teach.isPending}>
                        {teach.isPending ? "Saving…" : "Save"}
                      </Btn>
                    </div>
                    <Mistake error={teach.error} />
                  </form>
                ) : (
                  <div style={css("display:flex;gap:12px;align-items:center")}>
                    <button
                      type="button"
                      onClick={() => {
                        teach.reset();
                        setText("");
                        setOpen(g.key);
                      }}
                      style={css("padding:8px 14px;border-radius:99px;background:var(--soft);border:0;font:500 13px Geist;color:var(--ink)")}
                    >
                      Answer it
                    </button>
                    <button
                      type="button"
                      disabled={dismiss.isPending}
                      onClick={() => dismiss.mutate(g.key)}
                      style={css("border:0;background:transparent;padding:0;font:500 13px Geist;color:var(--muted)")}
                    >
                      Not needed
                    </button>
                  </div>
                )}
              </div>
            ))}
            <Mistake error={dismiss.error} />
          </>
        )}
      </Loaded>
    </div>
  );
}

// ------------------------------------------------------------------ a note's page

type NoteTab = "about" | "versions" | "use" | "history";
const NOTE_TABS: [NoteTab, string][] = [
  ["about", "About"],
  ["versions", "Versions"],
  ["use", "Use"],
  ["history", "History"],
];
const WHEN_OPTS: [string, string, string][] = [
  ["standing", "Always", "In every session's startup context."],
  ["domain", "Whenever its area comes up", "Any request about its area."],
  ["on-demand", "When relevant", "When a request is about it."],
  ["manual", "Only when asked for", "Opened by name or found by a search, never sent on its own."],
];
const STATEMENT = {
  confirmed: ["confirmed", "Confirmed by you"],
  disputed: ["disputed", "Disputed: something says otherwise"],
  tentative: ["tentative", "Tentative: it was said with a hedge"],
  conditional: ["conditional", "Conditional: it holds only under a condition"],
  stated: ["captured", "Kept as said, not confirmed"],
} satisfies Record<string, [string, string]>;

type Entry = NonNullable<ReturnType<typeof useBrainEntry>["data"]> & { said_by?: string | null; as_of?: string | null };

function statementOf(meta: Record<string, unknown> | undefined, entry: Entry, checked?: boolean): [string, string] {
  if (entry.confidence === "disputed" || meta?.disputed) return STATEMENT.disputed;
  if (checked || entry.confidence === "confirmed") return STATEMENT.confirmed;
  const said = String(meta?.statement_status ?? "");
  return (STATEMENT as Record<string, [string, string]>)[said] ?? STATEMENT.stated;
}

function Row({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div style={css("display:flex;align-items:flex-start;gap:14px;padding:13px 0;border-top:1px solid var(--line);color:var(--ink);width:100%;flex-wrap:wrap")}>
      <span style={css("font:400 14px Geist;color:var(--muted);width:200px")}>{k}</span>
      <span style={css("font:400 15px/1.45 Geist;flex:1;min-width:160px")}>{children}</span>
    </div>
  );
}

export function NotePage() {
  const { noteId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const raw = params.get("view") as NoteTab | null;
  const tab: NoteTab = raw && NOTE_TABS.some(([id]) => id === raw) ? raw : "about";
  const entry = useBrainEntry(noteId);
  const details = useEntryDetails(noteId);
  const current = useEntryVersion(noteId, "current");
  return (
    <div className="gn-page" style={css("max-width:1080px;margin:0 auto;padding:48px 64px 96px;display:flex;flex-direction:column;gap:26px;box-sizing:border-box")}>
      <Link to="/brain?tab=notes" style={css("align-self:flex-start;font:400 14px Geist;color:var(--muted);text-decoration:none")}>
        ← Brain
      </Link>
      <Loaded q={entry}>
        {(found) => {
          const e = found as Entry;
          const d = details.data;
          const [kind, words] = statementOf(current.data?.meta, e, d?.checked);
          const h = hueOf(d?.area ?? e.scope ?? "");
          const archived = d ? !d.live : e.status === "archived";
          return (
            <>
              <div style={css("display:flex;flex-direction:column;gap:12px")}>
                <div style={css("display:flex;gap:8px;flex-wrap:wrap;align-items:center")}>
                  <span style={css(`padding:4px 11px;border-radius:99px;font:500 12px Geist;background:${tint(h)};color:${ink(h)}`)}>{d?.area_label || d?.area || "Brain"}</span>
                  <Status kind={kind}>{words}</Status>
                  <LevelChip level={d?.level} />
                  {archived ? <Status kind="excluded">Archived: your AIs don't receive it</Status> : null}
                  {e.stale ? <Status kind="analysis">Due for a check{e.stale_reason ? `: ${e.stale_reason}` : ""}</Status> : null}
                </div>
                <h1 style={css(S.h1)}>{e.title}</h1>
              </div>
              <div role="tablist" aria-label="Note" style={css(S.wrap)}>
                {NOTE_TABS.map(([id, l]) => (
                  <button key={id} role="tab" type="button" aria-selected={tab === id} onClick={() => setParams(id === "about" ? {} : { view: id })} style={css(TS(tab === id))}>
                    {l}
                  </button>
                ))}
              </div>
              <SectionAddresses id={noteId} />
              {tab === "about" ? <NoteAbout id={noteId} entry={e} details={details} meta={current.data?.meta} archived={archived} /> : null}
              {tab === "versions" ? <NoteVersions id={noteId} /> : null}
              {tab === "use" ? <NoteUse id={noteId} /> : null}
              {tab === "history" ? <NoteHistory id={noteId} /> : null}
            </>
          );
        }}
      </Loaded>
    </div>
  );
}

function NoteAbout({
  id,
  entry,
  details,
  meta,
  archived,
}: {
  id: string;
  entry: Entry;
  details: ReturnType<typeof useEntryDetails>;
  meta: Record<string, unknown> | undefined;
  archived: boolean;
}) {
  const decide = useEntryDecide();
  const [editing, setEditing] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const d = details.data;
  const load = d?.load ?? "";
  const sourceId = String(meta?.source_id ?? "").replace(/^context_item:/, "");
  const captureId = sourceId || (d?.origin?.kind === "capture" ? d.origin.ref : "");
  const version = meta?.source_version ? String(meta.source_version) : "";
  const firstResult = decide.data?.results?.[0];
  return (
    <div style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));gap:40px")}>
      <div style={css("display:flex;flex-direction:column;gap:22px")}>
        <div style={css("display:flex;flex-direction:column;gap:10px")}>
          <span style={css("font:500 15px Geist")}>When it's sent</span>
          <div role="group" aria-label="When it's sent" style={css("display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px")}>
            {WHEN_OPTS.map(([value, l, hint]) => {
              const on = load === value;
              return (
                <button
                  key={value}
                  type="button"
                  aria-pressed={on}
                  disabled={!d || decide.isPending || archived}
                  onClick={() => {
                    if (!on) decide.mutate([{ action: "update", entry_id: id, fields: { load: value } }]);
                  }}
                  style={css(
                    `padding:14px 16px;border-radius:14px;display:flex;flex-direction:column;gap:3px;text-align:left;cursor:pointer;${on ? "background:var(--ink);color:var(--bg);border:1px solid var(--ink)" : "background:var(--surface);color:var(--ink);border:1px solid var(--line2)"}`,
                  )}
                >
                  <span style={css("font:500 14px Geist")}>{l}</span>
                  <span style={css("font:400 12px/1.4 Geist;opacity:.75")}>{hint}</span>
                </button>
              );
            })}
          </div>
          {details.error ? <span style={css(S.small)}>Couldn't read how it's sent right now.</span> : null}
        </div>
        <div style={css("display:flex;flex-direction:column;gap:8px")}>
          <span style={css("font:500 13px Geist;color:var(--muted)")}>Exactly what your AI receives{d ? ` · ${d.tokens} tokens` : ""} · the current version</span>
          <pre style={css("margin:0;padding:16px;border-radius:14px;background:var(--code);color:#d8d5cd;font:400 12px/1.6 'Geist Mono';white-space:pre-wrap;word-break:break-word")}>{entry.text}</pre>
        </div>
      </div>
      <div style={css("display:flex;flex-direction:column")}>
        <Row k="Kind">{d?.role || entry.kind || "Not set"}</Row>
        <Row k="Owner">{d?.owner || "No owner set"}</Row>
        <Row k="Where it came from">
          <span style={css("display:flex;flex-direction:column;gap:6px")}>
            <span>{d?.origin?.label || entry.source || "Not recorded"}</span>
            {meta?.source_excerpt ? (
              <span style={css("font:400 13.5px/1.5 Geist;color:var(--ink2)")}>
                “{String(meta.source_excerpt)}”{meta.source_speaker ? ` · said by ${String(meta.source_speaker)}` : ""}
                {meta.source_locator ? ` · ${String(meta.source_locator)}` : ""}
              </span>
            ) : null}
            {captureId ? (
              <Link to={`/capture/${encodeURIComponent(captureId)}${version ? `?version=${encodeURIComponent(version)}` : ""}`} style={css("font:500 13px Geist;color:var(--ink)")}>
                Open original{version ? ` at version ${version}, the one cited` : ""}
              </Link>
            ) : (
              <span style={css(S.small)}>No source to open: it wasn't brought in from a capture.</span>
            )}
          </span>
        </Row>
        <Row k="Statement">{statementOf(meta, entry, d?.checked)[1]}</Row>
        {entry.said_by ? <Row k="Said by">{entry.said_by}</Row> : null}
        {entry.as_of ? <Row k="True as of">{entry.as_of}</Row> : null}
        <Row k="Sensitivity">{d?.classification || "Normal"}</Row>
        <Row k="Next check">{d?.review_due ? when(d.review_due) : "Not scheduled"}</Row>
        <div style={css("display:flex;gap:8px;padding-top:16px;flex-wrap:wrap")}>
          <Btn onClick={() => setEditing(true)} disabled={archived}>
            Edit in your words
          </Btn>
          {archived ? (
            <Btn onClick={() => decide.mutate([{ action: "unarchive", entry_id: id }])} disabled={decide.isPending}>
              Bring it back
            </Btn>
          ) : (
            <Btn onClick={() => setArchiving(true)}>Archive</Btn>
          )}
        </div>
        {firstResult && !firstResult.ok ? (
          <span role="alert" style={css(ERR + ";padding-top:8px")}>
            {firstResult.message}
          </span>
        ) : null}
        {firstResult?.ok ? (
          <span role="status" style={css(S.small + ";padding-top:8px")}>
            {firstResult.message || "Saved. One undo point."}
          </span>
        ) : null}
        <Mistake error={decide.error} />
      </div>
      {editing ? <EditNote id={id} text={entry.text} onClose={() => setEditing(false)} /> : null}
      {archiving ? (
        <ArchiveNote
          busy={decide.isPending}
          onClose={() => setArchiving(false)}
          onArchive={(reason) => decide.mutate([{ action: "archive", entry_id: id, reason: reason || undefined }], { onSuccess: () => setArchiving(false) })}
        />
      ) : null}
    </div>
  );
}

function EditNote({ id, text, onClose }: { id: string; text: string; onClose: () => void }) {
  const decide = useEntryDecide();
  const [body, setBody] = useState(text);
  const [minor, setMinor] = useState(false);
  const failed = decide.data?.results?.find((r) => !r.ok);
  return (
    <Modal title="Say it your way" eyebrow="EDIT THIS NOTE" onClose={onClose} width={640}>
      <span style={css(S.muted)}>This changes the note itself. The version your AI receives now is kept exactly as it was, in Versions.</span>
      <label style={css(S.col)}>
        <span className="gn-sr">The note's text</span>
        <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={10} style={css(S.input + ";font:400 14px/1.5 Geist;resize:vertical")} />
      </label>
      <label style={css("display:flex;gap:8px;align-items:center;font:400 13px Geist")}>
        <input type="checkbox" checked={minor} onChange={(e) => setMinor(e.target.checked)} />
        Just a typo or cleanup, not new knowledge
      </label>
      {failed ? (
        <span role="alert" style={css(ERR)}>
          {failed.message}
        </span>
      ) : null}
      <Mistake error={decide.error} />
      <div style={css("display:flex;gap:8px")}>
        <Btn
          kind="primarySm"
          disabled={!body.trim() || body === text || decide.isPending}
          onClick={() =>
            decide.mutate([{ action: "edit", entry_id: id, body, minor: minor || undefined }], {
              onSuccess: (out) => {
                if (out.results.every((r) => r.ok)) onClose();
              },
            })
          }
        >
          {decide.isPending ? "Saving…" : "Save"}
        </Btn>
        <Btn onClick={onClose}>Cancel</Btn>
      </div>
    </Modal>
  );
}

function ArchiveNote({ busy, onClose, onArchive }: { busy: boolean; onClose: () => void; onArchive: (reason: string) => void }) {
  const [reason, setReason] = useState("");
  return (
    <Modal title="Archive this note?" onClose={onClose}>
      <span style={css(S.muted)}>Your AIs stop receiving it. It stays in Notes under Archived, with every version, and you can bring it back.</span>
      <label style={css(S.col)}>
        <span style={css(S.small)}>Why (optional)</span>
        <input value={reason} onChange={(e) => setReason(e.target.value)} style={css(S.input)} />
      </label>
      <div style={css("display:flex;gap:8px")}>
        <Btn kind="primarySm" disabled={busy} onClick={() => onArchive(reason.trim())}>
          {busy ? "Archiving…" : "Archive"}
        </Btn>
        <Btn onClick={onClose}>Cancel</Btn>
      </div>
    </Modal>
  );
}

function NoteVersions({ id }: { id: string }) {
  const versions = useEntryVersions(id);
  const decide = useEntryDecide();
  const [open, setOpen] = useState<string | null>(null);
  const [restoring, setRestoring] = useState<string | null>(null);
  return (
    <div style={css("display:flex;flex-direction:column;gap:12px")}>
      <span style={css("font:400 13.5px/1.5 Geist;color:var(--ink2)")}>The current version is the one your AI receives. Earlier versions are kept exactly as they were.</span>
      <Loaded q={versions} empty={(d) => (d.length === 0 ? <Empty title="No versions yet" /> : null)}>
        {(list) => (
          <>
            {list.map((v) => (
              <div key={v.ref} style={css("background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:18px 22px;display:flex;align-items:center;gap:16px;flex-wrap:wrap")}>
                <span style={css("font:500 13px Geist;width:110px")}>{v.current ? "Current" : "Kept as it was"}</span>
                <div style={css("flex:1;min-width:200px;display:flex;flex-direction:column;gap:2px")}>
                  <span style={css("font:400 15px Geist")}>{v.message || v.title}</span>
                  <span style={css(S.small)}>{[v.author, v.text_changed ? `${v.chars} characters` : "Only its details changed"].filter(Boolean).join(" · ")}</span>
                </div>
                <span style={css("font:400 13px Geist;color:var(--muted)")}>{when(v.at)}</span>
                <Btn kind="soft" onClick={() => setOpen(v.ref)}>
                  Open as it was
                </Btn>
                {!v.current ? (
                  <Btn kind="soft" onClick={() => setRestoring(v.ref)}>
                    Bring back
                  </Btn>
                ) : null}
              </div>
            ))}
          </>
        )}
      </Loaded>
      {open ? <VersionModal id={id} at={open} onClose={() => setOpen(null)} /> : null}
      {restoring ? (
        <Modal title="Bring this version back?" onClose={() => setRestoring(null)}>
          <span style={css(S.muted)}>It becomes the current version your AI receives. The one it replaces is kept too.</span>
          <Mistake error={decide.error} />
          <div style={css("display:flex;gap:8px")}>
            <Btn kind="primarySm" disabled={decide.isPending} onClick={() => decide.mutate([{ action: "restore", entry_id: id, ref: restoring }], { onSuccess: () => setRestoring(null) })}>
              {decide.isPending ? "Bringing back…" : "Bring it back"}
            </Btn>
            <Btn onClick={() => setRestoring(null)}>Cancel</Btn>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}

function VersionModal({ id, at, onClose }: { id: string; at: string; onClose: () => void }) {
  const version = useEntryVersion(id, at);
  return (
    <Modal title="This version, as it was" eyebrow={at === "current" ? "CURRENT" : `VERSION ${at.slice(0, 7)}`} onClose={onClose} width={680}>
      <Loaded q={version}>
        {(v) => (
          <>
            <span style={css(S.small)}>{[when(v.at), v.author, v.message].filter(Boolean).join(" · ")}</span>
            <pre style={css("margin:0;padding:16px;border-radius:14px;background:var(--code);color:#d8d5cd;font:400 12px/1.6 'Geist Mono';white-space:pre-wrap;word-break:break-word;max-height:60vh;overflow:auto")}>
              {v.body ?? "This version's text isn't available."}
            </pre>
          </>
        )}
      </Loaded>
      <Btn onClick={onClose}>Close</Btn>
    </Modal>
  );
}

const VIA: Record<string, string> = { packet: "Sent in a packet", opened: "Opened by your AI", work: "Read by AI work" };

function NoteUse({ id }: { id: string }) {
  const use = useEntryUse(id);
  return (
    <Loaded q={use}>
      {(u) => {
        const days = u.daily.slice(-30);
        const max = Math.max(1, ...days.map((x) => x.conversations));
        return (
          <div style={css("display:flex;flex-direction:column;gap:18px")}>
            <div style={css("background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:22px;display:flex;flex-direction:column;gap:14px")}>
              <div style={css("display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px")}>
                <span style={css("font:500 15px Geist")}>Last 30 days</span>
                <span style={css("font:400 13px Geist;color:var(--muted)")}>
                  {plural(u.totals.d7 ?? 0, "use")} this week · {plural(u.totals.d30 ?? 0, "use")} in 30 days
                </span>
              </div>
              {days.length === 0 ? (
                <span style={css(S.muted)}>Not sent to any AI in this time.</span>
              ) : (
                <div role="img" aria-label={`Uses per day over ${days.length} days`} style={css("display:flex;align-items:flex-end;gap:4px;height:80px")}>
                  {days.map((x) => (
                    <span
                      key={x.day}
                      title={`${x.day}: ${plural(x.conversations, "conversation")}`}
                      style={css(`flex:1;min-width:3px;border-radius:4px 4px 2px 2px;height:${Math.max(3, Math.round((x.conversations / max) * 80))}px;background:${x.conversations ? solid(150) : "var(--gray)"}`)}
                    />
                  ))}
                </div>
              )}
            </div>
            <div style={css("display:flex;flex-direction:column")}>
              {u.recent.length === 0 ? <span style={css(S.muted)}>No recent handouts.</span> : null}
              {u.recent.map((r) => (
                <div key={r.packet_id + r.at} style={css("display:flex;align-items:center;gap:14px;padding:13px 0;border-top:1px solid var(--line);flex-wrap:wrap")}>
                  <span style={css("font:400 15px Geist;flex:1;min-width:200px")}>{r.work?.title || r.request || "A request with no words"}</span>
                  <span style={css("font:400 13px Geist;color:var(--muted)")}>
                    {VIA[r.via] ?? r.via} · {r.tokens} tokens · {when(r.at)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        );
      }}
    </Loaded>
  );
}

const ACTION: Record<string, string> = {
  approve: "Kept",
  approved: "Kept",
  edit: "Edited",
  edited: "Edited",
  archive: "Archived",
  archived: "Archived",
  unarchive: "Brought back from the archive",
  restore: "An earlier version brought back",
  restored: "An earlier version brought back",
  verify: "Checked",
  verified: "Checked",
  mark: "Marked",
  update: "Details changed",
  updated: "Details changed",
};

function historyLine(h: BrainHistoryRecord): string {
  const base = ACTION[h.action] ?? h.action.replace(/_/g, " ");
  return [base, h.state ? `as ${h.state}` : ""].filter(Boolean).join(" ") + (h.reason ? `: ${h.reason}` : "");
}

function NoteHistory({ id }: { id: string }) {
  const history = useBrainHistory(id);
  return (
    <div style={css("display:flex;flex-direction:column")}>
      <span style={css("font:400 13.5px/1.5 Geist;color:var(--ink2);padding-bottom:12px")}>
        The current version is the one your AI receives. Earlier versions are kept exactly as they were, and sources open at the version they were cited from.
      </span>
      <Loaded q={history} empty={(d) => (d.length === 0 ? <span style={css(S.muted)}>No changes recorded yet.</span> : null)}>
        {(list) => (
          <>
            {list.map((h, i) => (
              <div key={h.at + i} style={css("display:flex;align-items:center;gap:14px;padding:13px 0;border-top:1px solid var(--line);flex-wrap:wrap")}>
                <span style={css("font:400 15px Geist;flex:1;min-width:200px")}>{historyLine(h)}</span>
                <span style={css("font:400 13px Geist;color:var(--muted)")}>{[h.by || h.proposer, when(h.at)].filter(Boolean).join(" · ")}</span>
              </div>
            ))}
          </>
        )}
      </Loaded>
    </div>
  );
}

// ------------------------------------------------------------------ a sheet's page

type SheetData = NonNullable<ReturnType<typeof useSheet>["data"]>;

const cellValue = (row: StateRow, col: StateColumn) => {
  if (col.formula) return row.computed?.[col.name] ?? null;
  return row.cells?.[col.name]?.value ?? null;
};
const show = (v: unknown, none = "") => (v === null || v === undefined || v === "" ? none : String(v));

function SheetGrid({ view, sel, onPick }: { view: SheetData; sel?: { row: string; column: string } | null; onPick?: (row: string, column: string) => void }) {
  const cols = view.sheet.columns.filter((c) => c.name !== view.sheet.key);
  if (!view.rows.length) return <div style={css("padding:28px 20px;font:400 14px Geist;color:var(--muted)")}>No rows yet.</div>;
  return (
    <div style={css("overflow:auto")}>
      <div role="table" aria-label={view.sheet.title} style={css("min-width:max-content")}>
        <div role="row" style={css("display:flex;background:var(--soft);border-bottom:1px solid var(--line)")}>
          <span role="columnheader" style={css("flex:1 0 150px;width:150px;padding:11px 12px;font:500 12px Geist;color:var(--muted)")}>
            {view.sheet.key || "Row"}
          </span>
          {cols.map((c) => (
            <span key={c.name} role="columnheader" style={css("flex:1 0 170px;width:170px;padding:11px 12px;font:500 12px Geist;color:var(--muted);border-left:1px solid var(--line)")}>
              {c.name}
            </span>
          ))}
        </div>
        {view.rows.map((r) => (
          <div key={r.id} role="row" style={css("display:flex;border-bottom:1px solid var(--line)")}>
            <span role="rowheader" style={css("flex:1 0 150px;width:150px;padding:12px;font:500 14px Geist")}>
              {r.key}
            </span>
            {cols.map((c) => {
              const waits = r.pending?.some((p) => p.column === c.name);
              const cell = r.cells?.[c.name];
              const on = sel?.row === r.id && sel?.column === c.name;
              const content = (
                <>
                  <span style={css("flex:1;min-width:0")}>{show(cellValue(r, c))}</span>
                  {waits ? (
                    <span title="A suggestion waits here" style={css("flex:none;width:8px;height:8px;margin-top:5px;border-radius:50%;background:oklch(0.72 0.15 60);box-shadow:0 0 0 3px oklch(0.72 0.15 60 / .22)")}>
                      <span className="gn-sr">A suggestion waits here</span>
                    </span>
                  ) : null}
                  {cell?.stale ? <span style={css("flex:none;margin-top:3px;padding:1px 6px;border-radius:99px;background:oklch(0.74 0.12 80 / .25);font:500 10px Geist")}>old</span> : null}
                </>
              );
              const style = `flex:1 0 170px;width:170px;padding:12px;border:0;border-left:1px solid var(--line);display:flex;gap:6px;align-items:flex-start;text-align:left;font:400 14px Geist;color:var(--ink);background:${on ? "var(--soft)" : "transparent"}`;
              return onPick ? (
                <button
                  key={c.name}
                  role="cell"
                  type="button"
                  aria-pressed={on}
                  aria-label={`${r.key}, ${c.name}: ${show(cellValue(r, c), "empty")}`}
                  onClick={() => onPick(r.id, c.name)}
                  className="gn-hover"
                  style={css(style)}
                >
                  {content}
                </button>
              ) : (
                <span key={c.name} role="cell" style={css(style)}>
                  {content}
                </span>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

export function SheetPage() {
  const { sheetId = "" } = useParams();
  const derivedName = DERIVED[sheetId];
  const derived = useDerivedSheet(sheetId, Boolean(derivedName));
  const sheet = useSheet(derivedName ? "" : sheetId);
  const back = (
    <Link to="/brain?tab=sheets" style={css("align-self:flex-start;font:400 14px Geist;color:var(--muted);text-decoration:none")}>
      ← Sheets
    </Link>
  );
  const wrap = "max-width:1240px;margin:0 auto;padding:48px 56px 96px;display:flex;flex-wrap:wrap;gap:32px;align-items:flex-start;box-sizing:border-box";
  if (derivedName) {
    return (
      <div className="gn-page" style={css(wrap)}>
        <div style={css("flex:1 1 600px;min-width:0;display:flex;flex-direction:column;gap:18px")}>
          {back}
          <div style={css("display:flex;flex-direction:column;gap:8px")}>
            <span style={css(AUTO_TAG + ";align-self:flex-start")}>Auto · kept by Gnomon</span>
            <h1 style={css("margin:0;font:400 40px/1.15 Newsreader;letter-spacing:-.015em")}>{derivedName}</h1>
          </div>
          {derived.isLoading ? (
            <Loading />
          ) : derived.data ? (
            <div style={css("background:var(--surface);border-radius:20px;box-shadow:var(--shadow);overflow:hidden")}>
              <SheetGrid view={derived.data} />
            </div>
          ) : (
            <div style={css("padding:18px 20px;border-radius:18px;background:var(--soft);display:flex;flex-direction:column;gap:6px")}>
              <span style={css("font:500 14px Geist")}>Worked out by the Brain, not stored here</span>
              <span style={css("font:400 14px/1.5 Geist;color:var(--ink2)")}>
                {derivedName} is worked out fresh from your projects and tasks each time an AI asks. Your AIs read it through the Brain; this page can't show its rows yet. Change it by changing the
                projects and tasks it comes from.
              </span>
            </div>
          )}
        </div>
      </div>
    );
  }
  return (
    <div className="gn-page" style={css(wrap)}>
      <Loaded q={sheet}>{(view) => <LiveSheet view={view} back={back} />}</Loaded>
    </div>
  );
}

function LiveSheet({ view, back }: { view: SheetData; back: ReactNode }) {
  const [sel, setSel] = useState<{ row: string; column: string } | null>(null);
  const [adding, setAdding] = useState(false);
  const act = useSheetAct();
  const sheetId = view.sheet.id;
  const waiting = view.rows.reduce((n, r) => n + (r.pending?.length ?? 0), 0);
  return (
    <>
      <div style={css("flex:1 1 600px;min-width:0;display:flex;flex-direction:column;gap:18px")}>
        {back}
        <div style={css("display:flex;flex-direction:column;gap:8px")}>
          <div style={css("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
            <span style={css(AUTO_TAG)}>Live context sheet</span>
            <span style={css("font:400 13px Geist;color:var(--muted)")}>
              {plural(view.rows.length, "row")} · {view.sheet.scope || "Brain-wide"}
            </span>
          </div>
          <h1 style={css("margin:0;font:400 40px/1.15 Newsreader;letter-spacing:-.015em")}>{view.sheet.title}</h1>
          {view.sheet.description ? <span style={css("font:400 16px Geist;color:var(--ink2)")}>{view.sheet.description}</span> : null}
        </div>
        <div style={css("display:flex;align-items:center;gap:12px;padding:12px 16px;border-radius:14px;background:var(--soft);flex-wrap:wrap")}>
          <span style={css("font:400 14px Geist;flex:1")}>
            {waiting ? `${plural(waiting, "value")} from your AIs ${waiting === 1 ? "waits" : "wait"} for your yes.` : "Your AIs suggest changes; each one waits for your yes."}
            <Later what="Auto-update later" />
          </span>
          <span style={css("font:400 12px Geist;color:var(--muted)")}>Your AIs get current values only.</span>
        </div>
        <div style={css("background:var(--surface);border-radius:20px;box-shadow:var(--shadow);overflow:hidden")}>
          <SheetGrid view={view} sel={sel} onPick={(row, column) => setSel({ row, column })} />
        </div>
        <div style={css("display:flex;gap:10px;align-items:center;flex-wrap:wrap")}>
          <Btn kind="soft" onClick={() => setAdding(true)}>
            + Row
          </Btn>
          <span style={css("font:400 13px Geist;color:var(--muted)")}>Click any cell to see how it changed.</span>
        </div>
      </div>
      <div style={css("flex:0 1 340px;min-width:280px;position:sticky;top:24px;background:var(--surface);border-radius:20px;box-shadow:var(--shadow);padding:22px;display:flex;flex-direction:column;gap:14px")}>
        {sel ? (
          <CellPanel view={view} row={sel.row} column={sel.column} />
        ) : (
          <>
            <span style={css("font:500 15px Geist")}>Cell history</span>
            {waiting ? (
              <span style={css("display:flex;align-items:center;gap:8px;font:400 13px/1.45 Geist;color:oklch(0.5 0.13 60)")}>
                <span style={css("width:8px;height:8px;border-radius:50%;flex:none;background:oklch(0.72 0.15 60)")} />
                {plural(waiting, "suggestion")} {waiting === 1 ? "waits" : "wait"} in the marked cells.
              </span>
            ) : null}
            <span style={css("font:400 14px/1.55 Geist;color:var(--ink2)")}>Pick a cell to see every value it's had, where each came from, and bring an old one back.</span>
          </>
        )}
      </div>
      {adding ? (
        <AddRow
          keyName={view.sheet.key || "Row"}
          busy={act.isPending}
          error={act.error}
          onClose={() => setAdding(false)}
          onAdd={(key) => act.mutate({ action: "add_row", fields: { sheet: sheetId, key, values: {} } }, { onSuccess: () => setAdding(false) })}
        />
      ) : null}
    </>
  );
}

function AddRow({ keyName, busy, error, onClose, onAdd }: { keyName: string; busy: boolean; error: unknown; onClose: () => void; onAdd: (key: string) => void }) {
  const [key, setKey] = useState("");
  return (
    <Modal title="Add a row" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (key.trim()) onAdd(key.trim());
        }}
        style={css("display:flex;flex-direction:column;gap:12px")}
      >
        <label style={css(S.col)}>
          <span style={css(S.small)}>{keyName}</span>
          <input value={key} onChange={(e) => setKey(e.target.value)} style={css(S.input)} />
        </label>
        <Mistake error={error} />
        <div style={css("display:flex;gap:8px")}>
          <Btn kind="primarySm" type="submit" disabled={!key.trim() || busy}>
            {busy ? "Adding…" : "Add"}
          </Btn>
          <Btn onClick={onClose}>Cancel</Btn>
        </div>
      </form>
    </Modal>
  );
}

function CellPanel({ view, row, column }: { view: SheetData; row: string; column: string }) {
  const r = view.rows.find((x) => x.id === row);
  const col = view.sheet.columns.find((c) => c.name === column);
  const history = useCellHistory(view.sheet.id, row, column);
  const act = useSheetAct();
  const [edit, setEdit] = useState("");
  useEffect(() => setEdit(""), [row, column]);
  if (!r || !col) return <span style={css(S.muted)}>That cell isn't in this sheet anymore.</span>;
  const now = cellValue(r, col);
  const pending = (r.pending ?? []).filter((p) => p.column === column);
  const write = (value: string | number | null | undefined) =>
    act.mutate({ action: "write", fields: { sheet: view.sheet.id, row, values: { [column]: value ?? "" } } }, { onSuccess: () => setEdit("") });
  const decide = (event: string | undefined, accept: boolean) => act.mutate({ action: "decide", fields: { sheet: view.sheet.id, row, event, accept } });
  const locked = Boolean(col.formula) || col.friction === "locked";
  const changes = (history.data ?? []).filter((h) => !h.column || h.column === column);
  return (
    <>
      <span style={css("font:500 12px Geist;color:var(--muted)")}>
        {r.key} · {column}
      </span>
      <span style={css("font:400 20px/1.35 Newsreader")}>{show(now, "Empty")}</span>
      {pending.map((p, i) => (
        <div key={p.id ?? i} style={css("padding:14px;border-radius:14px;border:1px dashed oklch(0.72 0.15 60);display:flex;flex-direction:column;gap:6px")}>
          <span style={css("font:500 10.5px 'Geist Mono';letter-spacing:.05em;color:oklch(0.55 0.14 60)")}>SUGGESTED CHANGE</span>
          <span style={css("font:400 15px/1.45 Geist")}>{show(p.value, "Empty")}</span>
          <span style={css("font:400 12px Geist;color:var(--muted)")}>{[p.said_by || p.by, p.source ? `from ${p.source}` : "", when(p.at)].filter(Boolean).join(" · ")}</span>
          <div style={css("display:flex;gap:8px;padding-top:4px")}>
            <Btn disabled={act.isPending} onClick={() => decide(p.event ?? p.id, false)}>
              Toss
            </Btn>
            <Btn kind="primarySm" disabled={act.isPending} onClick={() => decide(p.event ?? p.id, true)}>
              Keep
            </Btn>
          </div>
        </div>
      ))}
      {locked ? (
        <span style={css(S.small)}>{col.formula ? `Worked out: ${col.formula_words || col.formula}` : "This column is locked."}</span>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (edit.trim()) write(edit.trim());
          }}
          style={css("display:flex;gap:6px")}
        >
          <input
            aria-label={`Update ${column}`}
            value={edit}
            onChange={(e) => setEdit(e.target.value)}
            placeholder="Update this cell"
            style={css("flex:1;min-width:0;border:1px solid var(--line2);border-radius:12px;padding:10px 12px;outline:none;background:var(--bg);color:var(--ink);font:400 14px Geist")}
          />
          <Btn kind="primarySm" type="submit" disabled={!edit.trim() || act.isPending}>
            Save
          </Btn>
        </form>
      )}
      <Mistake error={act.error} />
      <Loaded q={history} empty={() => (changes.length === 0 ? <span style={css(S.muted)}>No changes recorded for this cell yet.</span> : null)}>
        {() => (
          <div style={css("display:flex;flex-direction:column")}>
            {changes.map((h, i) => {
              const isNow = i === 0 && !h.pending;
              return (
                <div key={(h.id ?? "") + h.at + i} style={css("display:flex;gap:12px;padding:12px 0;border-top:1px solid var(--line)")}>
                  <div style={css("display:flex;flex-direction:column;align-items:center;padding-top:5px")}>
                    <span style={css("width:8px;height:8px;border-radius:50%;background:oklch(0.62 0.12 265)")} />
                  </div>
                  <div style={css("flex:1;display:flex;flex-direction:column;gap:3px")}>
                    <div style={css("display:flex;justify-content:space-between;gap:8px;font:500 12px Geist;color:var(--muted)")}>
                      <span>{isNow ? "Now" : h.pending ? "Waiting" : h.ai ? "From an AI" : "Earlier"}</span>
                      <span style={css("font-weight:400")}>{when(h.at)}</span>
                    </div>
                    <span style={css("font:400 14px/1.45 Geist")}>{show(h.value, "Empty")}</span>
                    <span style={css("font:400 12px Geist;color:var(--muted)")}>from {h.source || h.said_by || h.by || "unknown"}</span>
                    {!isNow && !h.pending && !locked ? (
                      <button
                        type="button"
                        disabled={act.isPending}
                        onClick={() => write(h.value)}
                        style={css("align-self:flex-start;margin-top:4px;border:0;background:transparent;padding:0;font:500 12px Geist;color:var(--ink2)")}
                      >
                        Bring this back
                      </button>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Loaded>
    </>
  );
}
