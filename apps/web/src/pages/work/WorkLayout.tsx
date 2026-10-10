import { useLibrary, useSkills, useWaitingRuns, useWorkAgents, useWorkflows } from "../../api/hooks";
import { SectionFrame, Stat } from "../../components/SectionFrame";

// Knowledge Work: where you shape what your Brain knows and keep it current. Each tab answers
// one question: what changed and what needs you (Overview), where you think and what your AIs
// keep current (Workspace), what is kept whole (Library), your own words for later (Prompts), the
// procedures the Brain routes (Skills), the roles and the context they point to
// (Agents), the context work on a schedule (Workflows) and what was made (Outputs). Running
// things is an action on these screens, never their subject. The addresses stay /work/...
export function WorkLayout() {
  const { data: skills } = useSkills();
  const { data: library } = useLibrary();
  const { data: agents } = useWorkAgents();
  const { data: workflows } = useWorkflows();
  const { data: waiting } = useWaitingRuns();
  return (
    <SectionFrame
      title="Knowledge Work"
      lede="Shape what your Brain knows and keep it current."
      tour="work-tabs"
      className="work"
      tabs={[
        { to: "/work", label: "Overview", end: true },
        { to: "/work/workspace", label: "Workspace" },
        { to: "/work/library", label: "Library" },
        { to: "/work/prompts", label: "Prompts" },
        { to: "/work/skills", label: "Skills", badge: skills?.waiting.length ?? 0 },
        { to: "/work/agents", label: "Agents" },
        { to: "/work/workflows", label: "Workflows", badge: waiting?.length ?? 0 },
        { to: "/work/outputs", label: "Outputs" },
      ]}
      stats={
        <dl className="stats">
          <Stat label="Skills" value={skills?.skills.length} />
          <Stat label="Agents" value={agents?.length} />
          <Stat label="Workflows" value={workflows?.length} />
          <Stat label="Library" value={library?.filter((item) => item.kind !== "prompt").length} />
        </dl>
      }
    />
  );
}
