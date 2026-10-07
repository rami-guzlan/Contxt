// The Brain's front page: the map of what it knows (areas, then topics, then entries), the
// projects it follows, how to add to it, and the week in its supply chain.

import { Link, Navigate, useSearchParams } from "react-router";

import { AreaMap, BrainMap, ProjectStrip } from "../../components/BrainMap";
import { Section } from "../../components/ui";
import { Week } from "./Week";
import { entryUrl } from "./shared";

export function BrainMapPage() {
  const [params] = useSearchParams();
  // Links from before the map: an entry, or a filtered list of entries.
  const entry = params.get("entry");
  if (entry) return <Navigate to={entryUrl(entry)} replace />;
  if (["topic", "kind", "show", "view"].some((key) => params.get(key))) {
    return <Navigate to={`/brain/entries?${params.toString()}`} replace />;
  }
  const area = params.get("area");
  if (area) {
    return (
      <div className="brain-overview">
        <AreaMap areaKey={area} />
      </div>
    );
  }
  return (
    <div className="brain-overview">
      <Section title="What it knows">
        <BrainMap />
        <p className="small muted">Bigger tiles hold more; darker ones went to more chats this week. Open an area for its topics.</p>
      </Section>
      <Section
        title="Projects it follows"
        actions={
          <Link className="button" to="/projects">
            All projects
          </Link>
        }
      >
        <ProjectStrip />
      </Section>
      <Section title="Add to it">
        <ul className="list">
          <li>
            <Link to="/capture">Talk, upload a recording or a file, or write a note</Link>
            <span className="muted"> · it stays private in Capture until you pull it in or file it</span>
          </li>
          <li>
            <Link to="/brain/files">Add a document to a project</Link>
            <span className="muted"> · your AI quotes the part a request is about</span>
          </li>
          <li>
            <Link to="/projects">Start a project</Link>
            <span className="muted"> · your AI then knows where it stands whenever you mention it</span>
          </li>
          <li>
            <Link to="/review">Review what your AI suggested</Link>
            <span className="muted"> · rules and preferences wait for your yes</span>
          </li>
        </ul>
      </Section>
      <Week />
    </div>
  );
}
