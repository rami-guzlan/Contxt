import { useSkills } from "../../api/hooks";
import { SectionFrame, Stat } from "../../components/SectionFrame";

// Work: where the Brain gets put to use. Each tab answers one question: how you ask (Compose),
// where you think (Workspace), how it makes things (Skills), who does the work (Agents), when it
// runs (Workflows), what good looks like (Library) and what it made (Outputs). Every part reads
// from the Brain, and what it makes waits for your yes.
export function WorkLayout() {
  const { data: skills } = useSkills();
  return (
    <SectionFrame
      title="Work"
      lede="Where your Brain gets put to use. Everything here reads from the Brain, and what it makes waits for your yes."
      tour="work-tabs"
      className="work"
      tabs={[
        { to: "/work", label: "Overview", end: true },
        { to: "/work/skills", label: "Skills", badge: skills?.waiting.length ?? 0 },
        { to: "/work/outputs", label: "Outputs" },
      ]}
      stats={
        <dl className="stats">
          <Stat label="Skills" value={skills?.skills.length} />
        </dl>
      }
    />
  );
}
