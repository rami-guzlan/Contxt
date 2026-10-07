// The guided tour's chapters and steps: the six places, and how context moves through them,
// following one recording from Capture to Review to the Brain and into a chat. A step
// highlights the element marked data-tour="<target>" on its route; a step without a target, or
// whose target is not on the page (nothing made yet), shows in the middle.

import type { ReactNode } from "react";

export interface TourPlace {
  /** A project, a capture and a skill, for the steps shown on one. */
  projectId?: string;
  noteId?: string;
  skillName?: string;
}

export interface TourStep {
  id: string;
  chapter: string;
  title: string;
  body: ReactNode;
  /** Where the step is shown; a function picks a project, capture or skill page when there is one. */
  route?: string | ((place: TourPlace) => string | null);
  /** Where to go when `route` finds nothing to show (no project yet, say). */
  fallback?: string;
  /** Said instead of the highlight when the target is not there. */
  missing?: string;
  target?: string;
}

export const CHAPTERS = [
  { id: "basics", label: "Getting around" },
  { id: "home", label: "Home" },
  { id: "capture", label: "Capture" },
  { id: "review", label: "Review" },
  { id: "brain", label: "The Brain" },
  { id: "projects", label: "Projects" },
  { id: "skills", label: "Skills" },
  { id: "connect", label: "Your AI and settings" },
] as const;

const projectPage = ({ projectId }: TourPlace) => (projectId ? `/projects/${encodeURIComponent(projectId)}` : null);
const capturePage = ({ noteId }: TourPlace) => (noteId ? `/capture/${encodeURIComponent(noteId)}` : null);
const skillPage = ({ skillName }: TourPlace) => (skillName ? `/skills/${encodeURIComponent(skillName)}` : null);

export const STEPS: TourStep[] = [
  // ---------------------------------------------------------------- getting around
  {
    id: "welcome",
    chapter: "basics",
    route: "/",
    title: "Welcome to your Brain",
    body: (
      <>
        <p>
          This is where every AI you use gets its context: who you are, your rules and preferences, your projects, your files and
          the skills it follows. You bring things in, your AI suggests what should last, you say yes, and every AI you connect
          works from it.
        </p>
        <p>
          The tour follows one recording through all of it, in a few minutes. Use <kbd>→</kbd> and <kbd>←</kbd> or the buttons,
          and leave whenever you like: the <strong>?</strong> at the top right brings it back, chapter by chapter.
        </p>
      </>
    ),
  },
  {
    id: "nav",
    chapter: "basics",
    route: "/",
    target: "nav",
    title: "Six places",
    body: (
      <ul>
        <li>
          <strong>Home</strong>: how context moves, and your Brain at a glance.
        </li>
        <li>
          <strong>Capture</strong>: what you bring in (talk, recordings, transcripts, files, notes) before it becomes knowledge.
        </li>
        <li>
          <strong>Projects</strong>: the work your AI follows.
        </li>
        <li>
          <strong>Brain</strong>: everything it knows, with where each piece came from.
        </li>
        <li>
          <strong>Skills</strong>: how your AI makes things.
        </li>
        <li>
          <strong>Review</strong>: what waits for your yes. It shows in the menu only while something waits.
        </li>
      </ul>
    ),
  },
  {
    id: "talk",
    chapter: "basics",
    route: "/",
    target: "talk",
    title: "Talk to your Brain",
    body: (
      <p>
        Hold <kbd>Space</kbd> anywhere, or this button, and say what is on your mind. It becomes text on this computer, privately,
        and waits in Capture.
      </p>
    ),
  },
  {
    id: "search",
    chapter: "basics",
    route: "/",
    target: "search",
    title: "Search everything",
    body: <p>Search the Brain, your projects and what you brought in, at once.</p>,
  },
  {
    id: "help",
    chapter: "basics",
    route: "/",
    target: "help",
    title: "Help, any time",
    body: <p>The tour, chapter by chapter, and the first-time setup live here.</p>,
  },
  // ---------------------------------------------------------------- home
  {
    id: "home-flow",
    chapter: "home",
    route: "/",
    target: "home-flow",
    title: "How context moves",
    body: (
      <p>
        From Capture, through Review, into the Brain, out to your AI: each step with its count. Open any of them; a count that
        keeps growing shows where things are stuck.
      </p>
    ),
  },
  {
    id: "home-bring-in",
    chapter: "home",
    route: "/",
    target: "home-bring-in",
    title: "Bring something in",
    body: <p>Talk, upload a recording, a meeting's transcript or a document, or write. Let's follow a recording.</p>,
  },
  {
    id: "home-map",
    chapter: "home",
    route: "/",
    target: "brain-map",
    missing: "The map fills in as your Brain does.",
    title: "Your Brain at a glance",
    body: (
      <p>
        Each area is a tile, sized by what it holds and tinted by how much your AI used it this week. A flag means something to
        check, like two entries that clash. Open a tile to see its topics.
      </p>
    ),
  },
  // ---------------------------------------------------------------- capture
  {
    id: "capture-actions",
    chapter: "capture",
    route: "/capture",
    target: "capture-actions",
    title: "Record, upload or write",
    body: (
      <p>
        Record a meeting in the room, upload audio or a transcript from Teams or Zoom, drop a document, or write a note. Audio
        becomes text on this computer; nothing leaves it.
      </p>
    ),
  },
  {
    id: "capture-list",
    chapter: "capture",
    route: "/capture",
    target: "capture-list",
    missing: "What you bring in will be listed here.",
    title: "Everything you brought in",
    body: (
      <p>
        Newest first, each with the first line of its summary. It stays private to you: your AI sees it only when you ask it to
        work with it.
      </p>
    ),
  },
  {
    id: "capture-panel",
    chapter: "capture",
    route: capturePage,
    fallback: "/capture",
    missing: "Bring something in to see this panel.",
    target: "notes-panel",
    title: "What it says, and what to keep",
    body: (
      <ul>
        <li>
          <strong>Summary</strong>: its key points, each marked <em>New</em>, <em>Repeats</em>, <em>Updates</em> or{" "}
          <em>Clashes</em> against what your Brain holds now.
        </li>
        <li>
          <strong>Pull into the Brain</strong>: say what to keep in your own words; your AI suggests the entries.
        </li>
        <li>
          <strong>Teach a skill from it</strong>: when it shows how something should be made.
        </li>
      </ul>
    ),
  },
  // ---------------------------------------------------------------- review
  {
    id: "review",
    chapter: "review",
    route: "/review",
    target: "review",
    missing: "Nothing waits for you right now.",
    title: "Your yes, in batches",
    body: (
      <p>
        What your AI suggested from that recording waits here, beside whatever it would change. Approve the clear ones together;
        every decision is an undo point. A new version of a skill shows next to the skill as it is now.
      </p>
    ),
  },
  // ---------------------------------------------------------------- the brain
  {
    id: "brain",
    chapter: "brain",
    route: "/brain",
    target: "brain-tabs",
    title: "Everything it knows",
    body: (
      <p>
        Once approved, the recording's points are entries here: each with its versions, where it came from and every chat it
        went to. Your files, the history of decisions, and the gaps (what your AI asked that the Brain could not answer) are here
        too.
      </p>
    ),
  },
  // ---------------------------------------------------------------- projects
  {
    id: "projects-list",
    chapter: "projects",
    route: "/projects",
    target: "projects-list",
    missing: "Your projects will be listed here.",
    title: "The work your AI follows",
    body: (
      <p>
        Each project has what it is for, where it stands and its files. Start one here, or just tell your AI in a chat what you
        are starting.
      </p>
    ),
  },
  {
    id: "project-state",
    chapter: "projects",
    route: projectPage,
    fallback: "/projects",
    missing: "Start a project to see its page.",
    target: "project-state",
    title: "Where it stands",
    body: <p>Its status, what is happening now and next, and every update as a timeline. Your AI records progress here too.</p>,
  },
  {
    id: "project-files",
    chapter: "projects",
    route: projectPage,
    fallback: "/projects",
    missing: "Start a project to see its files.",
    target: "project-files",
    title: "Its files",
    body: <p>Drop drafts and documents here. A file named like one already there becomes its new version; your AI quotes the current one.</p>,
  },
  // ---------------------------------------------------------------- skills
  {
    id: "skills-list",
    chapter: "skills",
    route: "/skills",
    target: "skills-list",
    missing: "Write your first skill with New skill.",
    title: "How your AI makes things",
    body: (
      <p>
        Each skill is a procedure your AI follows to make something, like a post or a proposal deck. Ask for it in any chat with
        the words on its card, or run it here.
      </p>
    ),
  },
  {
    id: "skill-run",
    chapter: "skills",
    route: skillPage,
    fallback: "/skills",
    missing: "Add or write a skill to run one here.",
    target: "skill-run",
    title: "Run it, and see what it made",
    body: (
      <p>
        Say what you need, add the recording or a project if it helps, and press Run. Claude Code on this computer follows the
        skill while you watch each step. What it made lands below: copy it, save it as a note, file it in a project, or teach the
        skill from it.
      </p>
    ),
  },
  {
    id: "ai-work",
    chapter: "skills",
    route: "/",
    target: "ai-work",
    missing: "Once your AI runs something on this computer, it shows at the top of every page.",
    title: "What your AI is doing",
    body: <p>What runs on this computer right now, live, and what finished, each with the page its work belongs to.</p>,
  },
  // ---------------------------------------------------------------- your ai and settings
  {
    id: "settings",
    chapter: "connect",
    route: "/settings",
    target: "settings-tabs",
    title: "Connect your AI",
    body: (
      <p>
        Claude Code on this computer runs work from here with one click; Claude Desktop and your other AI apps get your Brain in
        every chat. Here you also turn summaries on or off and choose what saves straight in.
      </p>
    ),
  },
  {
    id: "to-a-chat",
    chapter: "connect",
    route: "/",
    target: "brain-preview",
    title: "And into a chat",
    body: (
      <p>
        Ask here the way you would ask your AI, and see exactly what the Brain would hand it, and why. The recording you approved
        is part of the answer now, in every AI you connect. That is the whole loop.
      </p>
    ),
  },
];
