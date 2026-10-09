import { useAgent, useBrainCatalog, useBrainFiles, useBrainGaps } from "../../api/hooks";
import { SectionFrame, Stat } from "../../components/SectionFrame";

// The Brain: what every AI you use can know, in the words it receives; its notes in full; its
// files; and the questions it could not answer, each one a thing to teach it. Its history lives
// in Activity, Changes.
export function BrainLayout() {
  const { data: catalog } = useBrainCatalog();
  const { data: files } = useBrainFiles();
  const { data: gaps } = useBrainGaps(30);
  const { data: agent } = useAgent();
  const fileCount = files ? files.references.length + files.assets.length : undefined;
  return (
    <SectionFrame
      title="Brain"
      lede="What every AI you use can know. Nothing changes without you."
      tour="brain-tabs"
      className="brain"
      tabs={[
        { to: "/brain", label: "What it knows", end: true },
        { to: "/brain/entries", label: "Notes" },
        { to: "/brain/files", label: "Files" },
        { to: "/brain/questions", label: "Questions", badge: gaps?.length ?? 0 },
        { to: "/brain/agent", label: "Knowledge agent", badge: agent?.questions.length ?? 0 },
      ]}
      stats={
        <dl className="stats">
          <Stat label="Notes" value={catalog?.entries.length} />
          <Stat label="Files" value={fileCount} />
          <Stat label="Skills" value={files?.skills.length} />
        </dl>
      }
    />
  );
}
