"""State machines. Only the transitions listed here are possible, whoever asks.

Services check permission (who may move a record) and preconditions (a lease, a due time);
this module only answers whether a move exists at all.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from workspace_core.errors import InvalidTransition


class StateMachine:
    def __init__(
        self,
        name: str,
        transitions: Mapping[str, Iterable[str]],
        initial: str,
        active: Iterable[str] = (),
    ) -> None:
        self.name = name
        self.transitions = {state: frozenset(targets) for state, targets in transitions.items()}
        self.initial = initial
        self.active = frozenset(active)
        missing = {t for targets in self.transitions.values() for t in targets} - set(
            self.transitions
        )
        if missing or initial not in self.transitions:
            raise ValueError(f"{name}: undeclared states {sorted(missing) or [initial]}")

    @property
    def states(self) -> frozenset[str]:
        return frozenset(self.transitions)

    def can(self, current: str, target: str) -> bool:
        return target in self.transitions.get(current, ())

    def check(self, current: str, target: str) -> None:
        if not self.can(current, target):
            allowed = sorted(self.transitions.get(current, ()))
            raise InvalidTransition(
                f"A {self.name} cannot go from {current} to {target}"
                + (f"; from {current} it can go to {', '.join(allowed)}." if allowed else "."),
                current=current,
                target=target,
                allowed=allowed,
            )

    def is_terminal(self, state: str) -> bool:
        return state in self.transitions and not self.transitions[state]

    def is_active(self, state: str) -> bool:
        return state in self.active


# Draft -> ready -> claimed -> in progress -> review -> done, with blocked, failed, cancelled
# and archived branches (spec section 10). `ready` means "claimable once due".
TASK = StateMachine(
    "task",
    {
        "draft": {"ready", "cancelled", "archived"},
        "ready": {"claimed", "draft", "cancelled", "archived"},
        "claimed": {"in_progress", "review", "done", "blocked", "failed", "ready", "cancelled"},
        "in_progress": {"review", "done", "blocked", "failed", "ready", "cancelled"},
        "review": {"done", "ready", "failed", "cancelled"},
        "blocked": {"ready", "cancelled", "archived"},
        "failed": {"ready", "cancelled", "archived"},
        "done": {"ready", "archived"},
        "cancelled": {"draft", "archived"},
        "archived": {"draft"},
    },
    initial="draft",
    active={"claimed", "in_progress"},
)

# One run is one claim: it ends exactly once, and its end releases the lease.
RUN = StateMachine(
    "run",
    {
        "claimed": {
            "in_progress",
            "completed",
            "failed",
            "blocked",
            "expired",
            "released",
            "cancelled",
        },
        "in_progress": {"completed", "failed", "blocked", "expired", "released", "cancelled"},
        "completed": set(),
        "failed": set(),
        "blocked": set(),
        "expired": set(),
        "released": set(),
        "cancelled": set(),
    },
    initial="claimed",
    active={"claimed", "in_progress"},
)

# Draft -> in review -> approved -> exported (spec section 11). A new version returns an
# artifact to draft: an approval covers one version, never the next.
ARTIFACT = StateMachine(
    "artifact",
    {
        "draft": {"in_review", "approved", "rejected", "archived"},
        "in_review": {"approved", "rejected", "draft", "archived"},
        "approved": {"exported", "draft", "archived"},
        "rejected": {"draft", "archived"},
        "exported": {"draft", "archived"},
        "archived": {"draft"},
    },
    initial="draft",
)

APPROVAL = StateMachine(
    "approval",
    {
        "pending": {"approved", "rejected", "changes_requested", "cancelled"},
        "approved": set(),
        "rejected": set(),
        "changes_requested": set(),
        "cancelled": set(),
    },
    initial="pending",
)

# The light lifecycle of an idea in a workspace (spec section 07).
IDEA = StateMachine(
    "idea",
    {
        "captured": {"developing", "promoted", "archived"},
        "developing": {"captured", "promoted", "archived"},
        "promoted": {"archived"},
        "archived": {"captured"},
    },
    initial="captured",
)

PROJECT = StateMachine(
    "project",
    {
        "active": {"paused", "completed", "archived"},
        "paused": {"active", "completed", "archived"},
        "completed": {"active", "archived"},
        "archived": {"active"},
    },
    initial="active",
)

# One run of a project's agent orchestrator (services/orchestrators.py): it runs until it has
# its final output, waits while a gate (spend, post, customer-facing) needs the owner's yes,
# and ends done or stopped. A waiting run goes back to running once every gate is decided and
# the final is still to come.
ORCHESTRATOR_RUN = StateMachine(
    "orchestrator run",
    {
        "running": {"waiting", "done", "stopped"},
        "waiting": {"running", "done", "stopped"},
        "done": set(),
        "stopped": set(),
    },
    initial="running",
    active={"running", "waiting"},
)

# One agent in one orchestrator run: queued until spawned, working on its CLI (or waiting for
# the owner to start a CLI that runs from a copied prompt), then reported. A reported agent
# works again only to do an action the owner said yes to.
ORCHESTRATOR_AGENT = StateMachine(
    "orchestrator agent",
    {
        "queued": {"working", "waiting", "stopped"},
        "waiting": {"working", "stopped"},
        "working": {"reported", "stopped"},
        "reported": {"working", "waiting", "stopped"},
        "stopped": {"working"},
    },
    initial="queued",
    active={"working", "waiting"},
)

# One heartbeat beat: it runs, then it is done (its record says what it read and wrote) or it
# failed (its record says why). A beat ends exactly once.
BEAT = StateMachine(
    "beat",
    {"running": {"done", "failed"}, "done": set(), "failed": set()},
    initial="running",
    active={"running"},
)

# One line a beat wrote into a region. A line that only notes an item, or whose write went in,
# waits, was held back or refused, can be undone once; an undone line stays undone, and the
# next beat does not write it again.
HEARTBEAT_LINE = StateMachine(
    "heartbeat line",
    {
        "noted": {"undone"},
        "applied": {"undone"},
        "waiting": {"undone", "applied"},
        "held": {"undone"},
        "refused": {"undone"},
        "undone": set(),
    },
    initial="noted",
)
