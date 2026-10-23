"""Activity > Tasks and handoffs (goals plan 6.9 and 6.13): who has what, and who did what.

Tasks live in the Brain's Tasks sheet and move only through `todos_update` (brainkit/handoff.py);
this service is the app's door to the same function, so the composer, a goal's rail and any AI
chat are validated once. "Now" is the Tasks sheet as lanes by status; "Timeline" draws each
owner's lane from the tasks' cell logs: handoffs as arrows between lanes, saves as dots,
claims and finishes as marks.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from workspace_core.clock import iso, parse_iso
from workspace_core.domain.policy import Principal
from workspace_core.errors import ValidationFailed

from .runtime import Runtime

UNCLAIMED_HOURS = 24
LANES = ("waiting_for_you", "handed_off", "working", "blocked", "open")


class Handoffs:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt
        # Knowledge Work's agents (set once Agents exists): a task handed to one starts its run.
        self.agents: Any = None

    def now(self, who: Principal, **filters: Any) -> dict[str, Any]:
        """The board, filtered by goal, project, owner or tool: open tasks by lane, the ones
        handed off and not claimed for a day, and what was done this week."""
        who.require("brain.read")
        found = self.rt.brain.tasks(**{k: v for k, v in filters.items() if v})
        if filters.get("tool"):
            found = [t for t in found if t.get("tool") == filters["tool"]]
        moment = self.rt.clock.now()
        week = iso(moment - timedelta(days=7))
        lanes: dict[str, list[dict[str, Any]]] = {lane: [] for lane in LANES}
        done: list[dict[str, Any]] = []
        for task in found:
            if task["status"] == "done":
                if (task.get("updated") or "") >= week:
                    done.append(task)
                continue
            if task["status"] in lanes:
                updated = task.get("updated")
                task["unclaimed"] = bool(
                    task["status"] == "handed_off"
                    and updated
                    and moment - parse_iso(updated) >= timedelta(hours=UNCLAIMED_HOURS)
                )
                lanes[task["status"]].append(task)
        return {"lanes": lanes, "done_this_week": done, "count": len(found)}

    def timeline(self, who: Principal, *, days: int = 7) -> dict[str, Any]:
        """Each owner's lane over the last `days`: events from the tasks' logs."""
        who.require("brain.read")
        since = iso(self.rt.clock.now() - timedelta(days=max(1, min(int(days), 60))))
        events: list[dict[str, Any]] = []
        for summary in self.rt.brain.tasks():
            task = self.rt.brain.task(summary["id"])
            owner = "you"
            for event in reversed(task.get("log") or []):  # oldest first
                at = str(event.get("at") or "")
                column = event.get("column")
                value = event.get("value")
                if column == "Owner":
                    previous, owner = owner, str(value or "you")
                    kind = "handoff"
                    detail = {"from": previous, "to": owner}
                elif column == "Status" and value in ("working", "done", "dropped", "blocked"):
                    kind = {"working": "claim", "done": "finish"}.get(str(value), str(value))
                    detail = {}
                elif column == "Card":
                    kind, detail = "save", {}
                elif event.get("kind") == "row":
                    kind, detail = "open", {}
                else:
                    continue
                if at >= since:
                    events.append(
                        {
                            "at": at,
                            "task": task["id"],
                            "title": task["task"],
                            "owner": owner,
                            "kind": kind,
                            **detail,
                        }
                    )
        events.sort(key=lambda e: e["at"])
        owners = list(dict.fromkeys(e["owner"] for e in events))
        return {"since": since, "owners": owners, "events": events}

    def task(self, who: Principal, task_id: str) -> dict[str, Any]:
        who.require("brain.read")
        return self.rt.brain.task(task_id)

    def hand_off(self, who: Principal, fields: dict[str, Any]) -> dict[str, Any]:
        """The composer and every button: the same function as the tool, as you."""
        who.require("brain.govern")
        allowed = {
            "task",
            "new_task",
            "goal",
            "to",
            "claim",
            "status",
            "done_so_far",
            "next_step",
            "done_when",
            "decisions",
            "open_questions",
            "load",
            "evidence",
            "goal_note",
            "reason",
        }
        unknown = sorted(set(fields) - allowed)
        if unknown:
            raise ValidationFailed(f"Unknown field {unknown[0]!r}.", field=unknown[0])
        done = self.rt.brain.hand_off(**{k: v for k, v in fields.items() if v not in (None, "")})
        task = done.get("task") or {}
        run = self._start_agent(who, task) if fields.get("to") else None
        if run is not None:
            done["run"] = run
        with self.rt.write() as tx:
            tx.emit(
                "task.changed",
                actor_id=who.actor_id,
                subject_type="task",
                subject_id=str(task.get("id") or "task"),
                data={
                    "status": task.get("status"),
                    "owner": task.get("owner"),
                    "move": "pass" if fields.get("to") else "save",
                },
            )
        return done

    def _start_agent(self, who: Principal, task: dict[str, Any]) -> str | None:
        """A task handed to one of Knowledge Work's agents starts that agent's run, with the
        card as its call to action (goals plan 5.6)."""
        owner = str(task.get("owner") or "")
        if self.agents is None or not owner.startswith("agent:"):
            return None
        name = owner.split(":", 1)[1]
        if name == "knowledge-agent" or self.rt.brain.agent(name) is None:
            return None
        card = self.rt.brain.task(str(task["id"])).get("rendered") or ""
        run = self.agents.run(
            who,
            name,
            ask=f"Pick up {task['id']}: claim it with todos_update, work from its card, save "
            f"progress, and pass it on or finish it.\n\n{card}",
            project=task.get("project") or None,
            handoff=str(task["id"]),
        )
        return str(run.id)

    def take_back(self, who: Principal, task_id: str) -> dict[str, Any]:
        """A handoff nobody claimed comes back to you, with its card."""
        task = self.task(who, task_id)
        card = task.get("card") or {}
        return self.hand_off(
            who,
            {
                "task": task_id,
                "to": "you",
                "done_when": card.get("done_when") or "As the card says",
                "next_step": card.get("next_step") or "Decide who should take it",
            },
        )
