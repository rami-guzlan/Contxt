import { Brain, FolderKanban, House, Inbox, ListChecks, NotebookPen, Settings, WandSparkles, type LucideIcon } from "lucide-react";
import { useState, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router";

import { useBrainAttention, useCreateNote, useHome } from "../api/hooks";
import { AiWork } from "./AiWork";
import { TalkButton, TalkProvider } from "./Talk";
import { ThemeSwitch } from "./ThemeSwitch";
import { HelpMenu } from "./tour/HelpMenu";
import { TourProvider } from "./tour/Tour";
import { ErrorNote } from "./ui";

// Six places, in the order context moves: Home shows the flow and the map; Capture holds what
// you bring in (talk, recordings, transcripts, files, notes) before it becomes Brain knowledge;
// Projects, the work your AI follows; Brain, everything it knows; Skills, how it makes things;
// Review, what waits for your yes (listed only while something does). Settings at the foot.
const NAV: { to: string; label: string; icon: LucideIcon; end?: boolean }[] = [
  { to: "/", label: "Home", icon: House, end: true },
  { to: "/capture", label: "Capture", icon: Inbox },
  { to: "/projects", label: "Projects", icon: FolderKanban },
  { to: "/brain", label: "Brain", icon: Brain },
  { to: "/skills", label: "Skills", icon: WandSparkles },
  { to: "/review", label: "Review", icon: ListChecks },
];

export function Layout({ children }: { children: ReactNode }) {
  const { data: home } = useHome();
  const { data: attention } = useBrainAttention();
  const location = useLocation();
  const waiting = home?.counts.brain_proposals ?? 0;
  const checks = attention ? attention.clashes.length + attention.twins.length + attention.flagged.length + attention.recheck.length : 0;
  const showReview = waiting > 0 || checks > 0 || location.pathname.startsWith("/review");
  return (
    <TourProvider>
      <TalkProvider>
      <div className="shell">
        <aside className="sidebar">
          <p className="brand">{home?.workspace.name ?? "Contxt"}</p>
          <nav aria-label="Main" data-tour="nav">
            {NAV.filter((item) => item.to !== "/review" || showReview).map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} className="nav-link">
                <item.icon className="nav-icon" aria-hidden="true" />
                {item.label}
                {item.to === "/review" && waiting > 0 ? (
                  <span className="badge" aria-label={`${waiting} waiting for you`}>
                    {waiting}
                  </span>
                ) : null}
              </NavLink>
            ))}
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
            <NewNote />
            <HelpMenu />
          </header>
          <main>{children}</main>
        </div>
      </div>
      </TalkProvider>
    </TourProvider>
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
      <input
        aria-label="Search everything"
        placeholder="Search the Brain, projects and your notes"
        value={q}
        onChange={(event) => setQ(event.target.value)}
      />
    </form>
  );
}

/** A new note in one click: the quickest way to put something down. */
function NewNote() {
  const create = useCreateNote();
  const navigate = useNavigate();
  return (
    <>
      <button
        type="button"
        className="primary"
        data-tour="new-note"
        disabled={create.isPending}
        onClick={() => create.mutate({}, { onSuccess: (note) => navigate(`/capture/${note.id}`) })}
      >
        <NotebookPen className="button-icon" aria-hidden="true" />
        New note
      </button>
      <ErrorNote error={create.error} />
    </>
  );
}
