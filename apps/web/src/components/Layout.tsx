import {
  Activity,
  Brain,
  BriefcaseBusiness,
  FolderKanban,
  House,
  Inbox,
  ListChecks,
  Mic,
  NotebookPen,
  Plus,
  Radio,
  Settings,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router";

import { useBringIn, useCatchUp, useGoals, useHome, useNewDoc } from "../api/hooks";
import { minutes } from "../lib/catchup";
import { AgentProvider } from "./agent/AgentContext";
import { AgentDock, AgentPanel } from "./agent/AgentPanel";
import { AiWork } from "./AiWork";
import { UploadButton } from "./CaptureParts";
import { TalkButton, TalkProvider, useTalk } from "./Talk";
import { ThemeSwitch } from "./ThemeSwitch";
import { HelpMenu } from "./tour/HelpMenu";
import { TourProvider } from "./tour/Tour";
import { ErrorNote } from "./ui";

// Places named for the person's questions: how am I doing (Home), what did I bring in
// (Capture), what is in motion (Projects), what does my AI know (Brain), how do I put it to use
// (Work: composing, writing, skills, agents, workflows, the library and what they made), what did
// it use and what changed (Activity). Catch up, what needs my yes, is listed only while
// something does, calmly, with the time it takes.
const NAV: { to: string; label: string; icon: LucideIcon; end?: boolean }[] = [
  { to: "/", label: "Home", icon: House, end: true },
  { to: "/capture", label: "Capture", icon: Inbox },
  { to: "/projects", label: "Projects", icon: FolderKanban },
  { to: "/brain", label: "Brain", icon: Brain },
  { to: "/work", label: "Work", icon: BriefcaseBusiness },
  { to: "/activity", label: "Activity", icon: Activity },
];

export const DEMOS = ["knowledge-company", "programmer", "entrepreneur", "personal"];

export function Layout({ children }: { children: ReactNode }) {
  const { data: home } = useHome();
  const { data: plan } = useCatchUp();
  const location = useLocation();
  const showCatchUp = (plan && !plan.caught_up) || location.pathname.startsWith("/catch-up") || location.pathname.startsWith("/review");
  return (
    <TourProvider>
      <TalkProvider>
        <AgentProvider>
        <div className="shell">
          <aside className="sidebar">
            <p className="brand">{home?.workspace.name ?? "Contxt"}</p>
            <nav aria-label="Main" data-tour="nav">
              {NAV.map((item) => (
                <NavLink key={item.to} to={item.to} end={item.end} className="nav-link">
                  <item.icon className="nav-icon" aria-hidden="true" />
                  {item.label}
                </NavLink>
              ))}
              {showCatchUp ? (
                <NavLink to="/catch-up" className="nav-link">
                  <ListChecks className="nav-icon" aria-hidden="true" />
                  Catch up
                  {plan && !plan.caught_up ? <span className="calm-count">{minutes(plan.seconds).replace(/^about /, "")}</span> : null}
                </NavLink>
              ) : null}
            </nav>
            <nav aria-label="Settings" className="sidebar-foot">
              <NavLink to="/settings" className="nav-link">
                <Settings className="nav-icon" aria-hidden="true" />
                Settings
              </NavLink>
              <ThemeSwitch />
            </nav>
          </aside>
          <div className="main">
            <header className="topbar">
              <SearchBox />
              <AiWork />
              <TalkButton />
              <AddMenu />
              <HelpMenu />
            </header>
            <DemoBanner />
            <main>{children}</main>
          </div>
        </div>
        <AgentPanel />
        <AgentDock />
        </AgentProvider>
      </TalkProvider>
    </TourProvider>
  );
}

/** A demo Brain says so, and how to start your own. */
function DemoBanner() {
  const { data: goals } = useGoals();
  const { data: home } = useHome();
  if (!goals?.starter || !DEMOS.includes(goals.starter)) return null;
  return (
    <p className="demo-banner" role="note">
      {home?.workspace.name ?? "This Brain"} is made up: a demo with invented people and numbers. Start your own with{" "}
      <code>uv run contxt setup --brain empty</code>.
    </p>
  );
}

function SearchBox() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  return (
    <form
      role="search"
      className="search"
      data-tour="search"
      onSubmit={(event) => {
        event.preventDefault();
        if (q.trim()) navigate(`/search?q=${encodeURIComponent(q.trim())}`);
      }}
    >
      <input aria-label="Search everything" placeholder="Search the Brain, projects and Capture" value={q} onChange={(event) => setQ(event.target.value)} />
    </form>
  );
}

/** + Add: talk, record or upload (each lands in Capture first), or write (a doc in Work,
 * Workspace). All of it stays private to you. */
function AddMenu() {
  const [open, setOpen] = useState(false);
  const create = useNewDoc();
  const bring = useBringIn();
  const talk = useTalk();
  const navigate = useNavigate();
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("mousedown", away);
    window.addEventListener("keydown", escape);
    return () => {
      window.removeEventListener("mousedown", away);
      window.removeEventListener("keydown", escape);
    };
  }, [open]);
  return (
    <div className="add-menu" ref={box} data-tour="new-note">
      <button type="button" className="primary" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        <Plus className="button-icon" aria-hidden="true" />
        Add
      </button>
      {open ? (
        <div className="add-popover" role="menu" aria-label="Add">
          <button
            type="button"
            role="menuitem"
            disabled={!talk}
            onClick={() => {
              // A tap: it listens until the next press of Talk or Space.
              talk?.press();
              talk?.release();
              setOpen(false);
            }}
          >
            <Mic className="button-icon" aria-hidden="true" />
            Talk <span className="muted small">or hold Space</span>
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              navigate("/capture?record=1");
            }}
          >
            <Radio className="button-icon" aria-hidden="true" />
            Record a meeting
          </button>
          <UploadButton
            busy={bring.isPending}
            onFiles={(files) => {
              setOpen(false);
              const list = Array.from(files);
              void Promise.allSettled(list.map((file) => bring.mutateAsync({ file }))).then((done) => {
                const first = done[0];
                navigate(list.length === 1 && first?.status === "fulfilled" ? `/capture/${encodeURIComponent(first.value.id)}` : "/capture");
              });
            }}
          >
            Upload a file
          </UploadButton>
          <button
            type="button"
            role="menuitem"
            disabled={create.isPending}
            onClick={() =>
              create.mutate(
                { template: "blank" },
                {
                  onSuccess: (doc) => {
                    setOpen(false);
                    navigate(`/work/workspace/${encodeURIComponent(doc.id)}`);
                  },
                },
              )
            }
          >
            <NotebookPen className="button-icon" aria-hidden="true" />
            Write
          </button>
          <Link role="menuitem" to="/move-in" onClick={() => setOpen(false)}>
            Move in from another AI
          </Link>
        </div>
      ) : null}
      <ErrorNote error={create.error ?? bring.error} />
    </div>
  );
}
