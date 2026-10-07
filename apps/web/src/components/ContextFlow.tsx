// How context moves, with the live count at each stage: what you brought in, what waits for your
// yes, what the Brain holds, and what your AI took from it this week. Each stage opens its place,
// so the strip both explains the system and shows where something is stuck.

import { Brain, ChevronRight, Inbox, ListChecks, MessagesSquare } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { useBrainCatalog, useBrainFiles, useBrainFlow, useHome, useNotes } from "../api/hooks";
import { plural } from "../lib/format";

interface Stage {
  to: string;
  icon: ReactNode;
  name: string;
  count: string;
  detail: string;
  lit?: boolean;
}

export function ContextFlow() {
  const { data: home } = useHome();
  const { data: notes } = useNotes();
  const { data: catalog } = useBrainCatalog();
  const { data: files } = useBrainFiles();
  const { data: flow } = useBrainFlow(7);
  const waiting = home?.counts.brain_proposals ?? 0;
  const captured = notes?.length ?? 0;
  const entries = catalog?.entries.length ?? 0;
  const chats = flow?.delivery.conversations ?? 0;
  const stages: Stage[] = [
    {
      to: "/capture",
      icon: <Inbox aria-hidden="true" />,
      name: "Capture",
      count: String(captured),
      detail: captured ? "brought in, private to you" : "talk, upload or write",
    },
    {
      to: "/review",
      icon: <ListChecks aria-hidden="true" />,
      name: "Review",
      count: String(waiting),
      detail: waiting ? "wait for your yes" : "nothing waits",
      lit: waiting > 0,
    },
    {
      to: "/brain",
      icon: <Brain aria-hidden="true" />,
      name: "Brain",
      count: String(entries),
      detail: files
        ? `${entries === 1 ? "entry" : "entries"}, ${plural(files.references.length, "file")}, ${plural(files.skills.length, "skill")}`
        : "entries",
    },
    {
      to: "/brain/entries?view=most",
      icon: <MessagesSquare aria-hidden="true" />,
      name: "Your AI",
      count: String(chats),
      detail: `${chats === 1 ? "chat" : "chats"} used it this week`,
    },
  ];
  return (
    <nav className="flow-strip" aria-label="How your context flows" data-tour="home-flow">
      {stages.map((stage, index) => (
        <div key={stage.name} className="flow-step-wrap">
          {index ? <ChevronRight className="flow-arrow" aria-hidden="true" /> : null}
          <Link to={stage.to} className={stage.lit ? "flow-step lit" : "flow-step"}>
            <span className="flow-icon">{stage.icon}</span>
            <span className="flow-name">{stage.name}</span>
            <span className="flow-count">{stage.count}</span>
            <span className="flow-detail">{stage.detail}</span>
          </Link>
        </div>
      ))}
    </nav>
  );
}
