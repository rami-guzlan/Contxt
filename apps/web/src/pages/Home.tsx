// Home: how your context flows and where it is stuck, a way to bring something in, the Brain at a
// glance, the projects in motion, what your AI gets for any request, and what came in this week.
// An empty Brain gets a welcome instead of empty panels: what goes where, and three ways to start.

import { FolderKanban, Mic, Upload } from "lucide-react";
import { Link } from "react-router";

import { useBrainActivity, useBrainAttention, useBrainPolicies, useHome, useOnboarding } from "../api/hooks";
import { BrainMap, ProjectStrip } from "../components/BrainMap";
import { BringIn } from "../components/BringIn";
import { ContextFlow } from "../components/ContextFlow";
import { ContextPreview } from "../components/ContextPreview";
import { Empty, ErrorNote, Loading, Section } from "../components/ui";
import { plural } from "../lib/format";
import { EventList } from "./brain/events";
import { Waiting } from "./brain/Week";
import { SetupCard } from "./Setup";

const WEEK = 7 * 86_400_000;

export function HomePage() {
  const { data: home, isLoading, error } = useHome();
  const { data: attention } = useBrainAttention();
  const { data: setup } = useOnboarding();
  if (isLoading) return <Loading />;
  if (!home) return <ErrorNote error={error} />;
  const brain = setup?.brain;
  const empty = !!brain && brain.available && !brain.own_entries && !brain.projects && !brain.files && !home.counts.brain_proposals;
  return (
    <div className="page home">
      <p className="eyebrow">{new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}</p>
      <h1>{home.workspace.name}</h1>
      {empty ? <Welcome /> : <SetupCard />}
      <ContextFlow />
      {empty ? null : (
        <>
          <div className="grid-2">
            <BringIn />
            <Section title="Waiting for you" tour="home-waiting">
              <Waiting waiting={home.counts.brain_proposals} attention={attention} />
            </Section>
          </div>
          <Section
            title="Your Brain at a glance"
            actions={
              <Link className="button" to="/brain">
                Open the map
              </Link>
            }
          >
            <BrainMap compact />
          </Section>
          <Section
            title="Projects in motion"
            actions={
              <Link className="button" to="/projects">
                All projects
              </Link>
            }
          >
            <ProjectStrip />
          </Section>
          <Section title="What your AI gets" tour="home-preview">
            <ContextPreview />
          </Section>
          <Section
            title="What's new this week"
            tour="home-new"
            actions={
              <Link className="button" to="/brain/history">
                Everything
              </Link>
            }
          >
            <WhatsNew />
          </Section>
        </>
      )}
    </div>
  );
}

/** A first look at an empty Brain: how context moves, and three ways to start. */
function Welcome() {
  return (
    <section className="welcome" aria-label="Welcome">
      <h2>Your Brain is ready for its first things</h2>
      <p className="lede">
        What you bring in waits privately in Capture. What should last goes to Review for your yes, then into the Brain, where every AI you connect
        finds it when a chat needs it.
      </p>
      <ul className="welcome-starts">
        <li>
          <Mic className="welcome-icon" aria-hidden="true" />
          <Link to="/settings?tab=start" className="welcome-title">
            Tell it about you
          </Link>
          <span className="muted">Your role, your work, how you like things written. Talk or type.</span>
        </li>
        <li>
          <FolderKanban className="welcome-icon" aria-hidden="true" />
          <Link to="/projects" className="welcome-title">
            Start a project
          </Link>
          <span className="muted">Name what you're working on. Your AI then knows where it stands.</span>
        </li>
        <li>
          <Upload className="welcome-icon" aria-hidden="true" />
          <Link to="/capture" className="welcome-title">
            Bring in a recording or a file
          </Link>
          <span className="muted">A meeting, a proposal, a brief. It stays private until you pull from it.</span>
        </li>
      </ul>
      <p className="small muted">
        Then <Link to="/settings?tab=connections">connect your AI</Link>: Claude Code on this computer and Claude Desktop, one step each.
      </p>
    </section>
  );
}

function WhatsNew() {
  // From the start of the day a week ago: one query a day, not a new one on every render.
  const since = `${new Date(Date.now() - WEEK).toISOString().slice(0, 10)}T00:00:00Z`;
  const { data: events, isLoading, error } = useBrainActivity({ since, limit: 40 });
  const { data: policies } = useBrainPolicies();
  if (isLoading) return <Loading />;
  if (!events) return <ErrorNote error={error} />;
  if (!events.length) return <Empty why="Nothing came in this week. What you and your AI save shows here." />;
  return (
    <>
      <p className="muted small">{plural(events.length, "change")} in the last 7 days, newest first.</p>
      <EventList events={events} approver={policies?.approver} />
    </>
  );
}
