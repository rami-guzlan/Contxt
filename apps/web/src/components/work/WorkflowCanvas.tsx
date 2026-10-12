// The workflow canvas (UX 4.7): the same steps as the list, drawn as boxes on React Flow, with
// the node library beside them (each kind of step, grouped, with what it takes and gives) and
// the picked box's settings and last run below. Straight lines for now: each step reads what
// the step before made, and a line turns red when a step cannot take what it is given.

import { Background, Controls, Handle, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { useNodeLibrary } from "../../api/hooks";
import type { NodeLibrary, StepKind, WorkflowStep, WorkflowStepStatus } from "../../api/types";
import { STEP_HINTS, STEP_NAMES, stepWords } from "./WorkflowEditor";

const GAP = 230;

type BoxData = {
  eyebrow: string;
  name: string;
  words: string;
  status?: WorkflowStepStatus;
  picked?: boolean;
  problem?: string;
};

function Box({ data }: NodeProps<Node<BoxData>>) {
  return (
    <div className={`flow-box${data.picked ? " picked" : ""}${data.problem ? " misfit" : ""}`} title={data.problem}>
      <Handle type="target" position={Position.Left} />
      <span className="eyebrow small">{data.eyebrow}</span>
      <strong className="flow-box-name">{data.name}</strong>
      {data.words ? <span className="small muted">{data.words}</span> : null}
      {data.status ? <span className={`pill small status-${data.status}`}>Last run: {data.status}</span> : null}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

const NODE_TYPES = { box: Box };

/** Steps that do not fit the one before: what each takes against what that gives. A step that
 * takes nothing reads nothing before it, so it follows anything. */
export function fitProblems(steps: WorkflowStep[], library: NodeLibrary | undefined): (string | undefined)[] {
  if (!library) return steps.map(() => undefined);
  const kinds = new Map(library.kinds.map((k) => [k.kind, k]));
  let gives = ["none"];
  return steps.map((step) => {
    const kind = kinds.get(step.kind);
    const takes = kind?.takes ?? ["any"];
    const problem =
      takes.includes("any") || takes.includes("none") || takes.some((t) => gives.includes(t))
        ? undefined
        : `${kind?.label ?? step.kind} needs ${takes.join(" or ")}; the step before gives ${gives.join(" and ")}.`;
    if (step.kind !== "check") gives = kind?.gives ?? ["text"];
    return problem;
  });
}

export function WorkflowCanvas({
  steps,
  when,
  output,
  picked,
  statuses,
  onPick,
  onAdd,
}: {
  steps: WorkflowStep[];
  when: string;
  output: string;
  picked: number | null;
  statuses?: WorkflowStepStatus[];
  onPick: (index: number | null) => void;
  onAdd: (kind: StepKind) => void;
}) {
  const { data: library } = useNodeLibrary();
  const problems = fitProblems(steps, library);
  const groups = new Map<string, NodeLibrary["kinds"]>();
  for (const kind of library?.kinds ?? []) groups.set(kind.group, [...(groups.get(kind.group) ?? []), kind]);
  const nodes: Node<BoxData>[] = [
    { id: "start", type: "box", position: { x: 0, y: 0 }, data: { eyebrow: "Starts", name: "When it runs", words: when }, draggable: false },
    ...steps.map((step, index) => ({
      id: `step-${index}`,
      type: "box",
      position: { x: GAP * (index + 1), y: 0 },
      draggable: false,
      data: {
        eyebrow: `Step ${index + 1}`,
        name: STEP_NAMES[step.kind],
        words: stepWords(step),
        status: statuses?.[index],
        picked: picked === index,
        problem: problems[index],
      },
    })),
    { id: "end", type: "box", position: { x: GAP * (steps.length + 1), y: 0 }, data: { eyebrow: "Goes to", name: output, words: "" }, draggable: false },
  ];
  const ids = nodes.map((n) => n.id);
  const edges: Edge[] = ids.slice(1).map((id, n) => {
    const problem = n < problems.length ? problems[n] : undefined;
    return {
      id: `${ids[n]}-${id}`,
      source: ids[n]!,
      target: id,
      animated: false,
      label: problem ? "does not fit" : undefined,
      className: problem ? "misfit" : undefined,
    };
  });
  return (
    <div className="workflow-canvas-wrap">
      <aside className="node-library" aria-label="Node library">
        {[...groups.entries()].map(([group, kinds]) => (
          <section key={group}>
            <h4 className="small-head">{group}</h4>
            {kinds.map((k) => (
              <button
                key={k.kind}
                type="button"
                className="node-library-item"
                title={`${STEP_HINTS[k.kind]} Takes ${k.takes.join(" or ")}; gives ${k.gives.join(" and ")}.`}
                onClick={() => onAdd(k.kind)}
              >
                {STEP_NAMES[k.kind]}
              </button>
            ))}
          </section>
        ))}
        <section>
          <h4 className="small-head">Starts</h4>
          {(library?.triggers ?? []).map((t) => (
            <p key={t.id} className={`small${t.later ? " muted" : ""}`}>
              {t.label}
              {t.later ? " (coming later)" : ""}
            </p>
          ))}
          <p className="small muted">Direct connectors beyond Claude Code's (coming later)</p>
        </section>
      </aside>
      <div className="workflow-canvas" role="region" aria-label="The workflow canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          fitView
          nodesConnectable={false}
          onNodeClick={(_, node) => onPick(node.id.startsWith("step-") ? Number(node.id.slice(5)) : null)}
          onPaneClick={() => onPick(null)}
        >
          <Background />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      {problems.some(Boolean) ? (
        <ul className="warning small" aria-label="Steps that do not fit">
          {problems.map((p, n) => (p ? <li key={n}>Step {n + 1}: {p}</li> : null))}
        </ul>
      ) : null}
    </div>
  );
}
