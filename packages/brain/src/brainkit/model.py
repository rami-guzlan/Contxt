"""The records a brain is made of. Plain dataclasses built by `vault.py`, read everywhere."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import frontmatter as fm
from . import util

LIVE = "approved"
CONFIDENCE = ("confirmed", "inferred", "disputed", "unknown")
# How a note reaches a model: in every session (standing), whenever its domain comes up
# (domain: a must-hold), when a request is relevant to it (on-demand), or only when asked for
# by id or found by a search (manual).
LOADS = ("standing", "domain", "on-demand", "manual")
MUST_HOLD = "domain"
MAX_CRITICAL = 3               # must-holds the startup context shows in full, at most


def listish(value) -> list[str]:
    """A front-matter list that may also be written as one comma-separated line."""
    out: list[str] = []
    for item in fm.as_list(value):
        out += [part.strip() for part in item.split(",") if part.strip()]
    return out
# Older vaults filed notes by kind ("layer"); a layer name implies the kind of its notes.
LEGACY_KINDS = {"identity": "identity", "rules": "rule", "facts": "fact", "state": "state"}


@dataclass
class Note:
    """One governed note.

    WHERE IT IS FILED and WHAT IT IS are separate. `area/topic` is where it lives (an area of
    the work such as brand or sales, then a topic inside it); `kind` is how it is used
    (identity, rule, fact, state, or focus for a project's live state). Older vaults used a
    `layer` in place of the area, and the layer implied the kind.
    """

    id: str
    area: str
    topic: str
    scope: str
    status: str
    load: str
    body: str
    path: str                      # vault-relative
    meta: dict = field(default_factory=dict)

    @property
    def layer(self) -> str:
        """The older name for `area`."""
        return self.area

    @property
    def route_key(self) -> str:
        return f"{self.area}/{self.topic}"

    @property
    def kind(self) -> str:
        value = str(self.meta.get("kind") or "").strip().lower()
        return value or LEGACY_KINDS.get(self.area, "fact")

    @property
    def statement_kind(self) -> str:
        """Its kind in the one vocabulary (statements.py): a `state` note is a value, a
        `focus` a project."""
        from . import statements
        return statements.kind(self.kind)

    @property
    def tier(self) -> str:
        """alignment, state or knowledge (statements.tier)."""
        from . import statements
        return statements.tier(self.kind, self.load)

    @property
    def title(self) -> str:
        value = str(self.meta.get("title") or "").strip()
        return value or util.excerpt(self.index_line, 90)

    @property
    def added(self) -> str:
        return str(self.meta.get("added") or "").strip()[:10]

    @property
    def live(self) -> bool:
        return self.status == LIVE

    # ---------------------------------------------------------------- freshness (spec 05)

    @property
    def confidence(self) -> str | None:
        """confirmed, inferred, disputed or unknown; None when the note does not say."""
        value = str(self.meta.get("confidence") or "").strip().lower()
        return value if value in CONFIDENCE else None

    @property
    def verified(self) -> str:
        """When this was last checked: `verified`, else when it was approved or added."""
        for key in ("verified", "affirmed", "approved_at", "added"):
            value = str(self.meta.get(key) or "").strip()[:10]
            if value:
                return value
        return ""

    @property
    def as_of(self) -> str:
        """The day a changing value was true (`as_of`, YYYY-MM-DD), or ""."""
        found = util.parse_date(self.meta.get("as_of"))
        return found.isoformat() if found else ""

    @property
    def valid_until(self) -> str:
        """The last day a value holds (`valid_until`), or ""."""
        found = util.parse_date(self.meta.get("valid_until"))
        return found.isoformat() if found else ""

    @property
    def dated(self) -> str:
        """When what it says was true: `as_of`, else when its text last changed, else when
        it was added."""
        return self.as_of or util.day_text(self.meta.get("revised")) or self.added

    def stale_reason(self, today, default_days: int = 0) -> str | None:
        """Why this note is stale on `today`, or None. Stale notes stay, ranked lower.

        `default_days` is the cadence policy gives a note that sets none of its own
        (`Config.review_days_for` resolves both)."""
        if str(self.meta.get("stale") or "").strip().lower() in ("true", "yes", "1"):
            return "marked stale"
        until = util.parse_date(self.meta.get("valid_until"))
        if until and until < today:
            return f"valid until {until.isoformat()}, now past"
        review_by = util.parse_date(self.meta.get("review_by"))
        if review_by and review_by < today:
            return f"review was due {review_by.isoformat()}"
        every = self.review_due_days(default_days)
        checked = util.parse_date(self.verified)
        if every > 0 and checked and (today - checked).days > every:
            return f"not verified since {checked.isoformat()}"
        return None

    def review_due_days(self, default_days: int = 0) -> int:
        """Days between checks: the note's own `review_days` (not the older `review_every`,
        which counted review cycles), else `default_days`."""
        try:
            every = int(str(self.meta.get("review_days") or "0").strip() or 0)
        except ValueError:
            every = 0
        return every if every > 0 else max(0, int(default_days or 0))

    def review_due(self, default_days: int = 0):
        """The date this note is next due for a check, or None without a cadence or date."""
        import datetime as dt
        review_by = util.parse_date(self.meta.get("review_by"))
        every = self.review_due_days(default_days)
        checked = util.parse_date(self.verified)
        due = checked + dt.timedelta(days=every) if every > 0 and checked else None
        if review_by and (due is None or review_by < due):
            return review_by
        return due

    # ---------------------------------------------------------------- stewardship

    @property
    def owner(self) -> str:
        """Who answers for this note, when it says (`owner`); callers fall back to policy."""
        return str(self.meta.get("owner") or "").strip()

    @property
    def origin(self) -> str:
        """Where this note came from, as `<kind>:<reference>`, when it says (`origin`)."""
        return str(self.meta.get("origin") or "").strip()

    @property
    def standing(self) -> bool:
        return self.load == "standing"

    # ---------------------------------------------------------------- must-holds
    @property
    def must_hold(self) -> bool:
        """A constraint that goes into every brief whenever its domain comes up, whatever
        the request's relevance to it (`load: domain`)."""
        return self.load == MUST_HOLD

    @property
    def applies_to(self) -> list[str]:
        """The domains a must-hold covers: areas (`food`), topics (`food/diet`), project ids,
        or `*` for every task. A must-hold that names none covers its own area."""
        return listish(self.meta.get("applies_to")) or [self.area]

    @property
    def triggers(self) -> list[str]:
        """Words and phrases that put this must-hold's domain in play when a request uses
        them ("dinner", "birthday party")."""
        return [t.lower() for t in listish(self.meta.get("triggers"))]

    @property
    def must_text(self) -> str:
        """The one line a brief and the startup index show for this must-hold."""
        return (str(self.meta.get("must_text") or "").strip() or self.startup_text
                or self.summary)

    @property
    def critical(self) -> bool:
        """Shown in full in the startup context, for models that cannot ask for a brief."""
        return fm.as_bool(self.meta.get("critical"))

    @property
    def partition(self) -> str | None:
        value = str(self.meta.get("partition") or "").strip()
        return value or None

    @property
    def classification(self) -> str:
        return str(self.meta.get("classification") or "internal").strip().lower()

    @property
    def startup_text(self) -> str:
        return str(self.meta.get("startup_text") or "").strip()

    @property
    def summary(self) -> str:
        """One line saying what the note is for (`summary`, or `index_line` in older notes)."""
        line = str(self.meta.get("summary") or self.meta.get("index_line") or "").strip()
        return line or util.excerpt(self.body, 110)

    @property
    def index_line(self) -> str:
        return self.summary

    @property
    def body_hash(self) -> str:
        return util.sha256(self.body.strip())

    @property
    def tokens(self) -> int:
        return util.tokens(self.body.strip())

    @property
    def references(self) -> list[str]:
        """`references/...` paths this note points at, in order of first mention."""
        import re
        seen: dict[str, None] = {}
        for match in re.finditer(r"references/[A-Za-z0-9_./-]+\.md", self.body):
            seen.setdefault(match.group(0).rstrip("."), None)
        return list(seen)


@dataclass
class FocusUpdate:
    seq: int
    at: str
    summary: str
    changes: dict = field(default_factory=dict)
    evidence: str = ""
    session: str = ""
    actor: str = ""


@dataclass
class Focus:
    """A Focus is a live note of kind `focus` (a project's baseline) plus its append-only
    journal. In older vaults every Focus lived in one `state/focus` topic."""

    note: Note
    updates: list = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.note.id

    @property
    def title(self) -> str:
        meta = self.note.meta
        return str(meta.get("project") or meta.get("title") or self.slug.replace("-", " ")).strip()

    @property
    def slug(self) -> str:
        prefix = f"{self.note.area}-{self.note.topic}-"
        return self.id[len(prefix):] if self.id.startswith(prefix) else self.id

    @property
    def objective(self) -> str:
        """The output the project is chasing, in a sentence or two: its `objective` once it
        has one, and until then its summary (what it is for)."""
        return " ".join(str(self.note.meta.get("objective") or self.note.summary or "").split())

    def current(self) -> dict:
        """Baseline fields overlaid with every journal change, last write wins."""
        meta = self.note.meta
        state = {
            "status": str(meta.get("project_status") or meta.get("focus_status")
                          or "active").strip(),
            "current": str(meta.get("summary") or meta.get("index_line") or "").strip(),
            "blockers": str(meta.get("blockers") or "").strip(),
            "next": str(meta.get("next_actions") or meta.get("next") or "").strip(),
        }
        for update in self.updates:
            for key, value in (update.changes or {}).items():
                if value in (None, ""):
                    continue
                name = {"project_status": "status", "focus_status": "status",
                        "current_state": "current", "next_actions": "next",
                        "next_action": "next"}.get(key, key)
                state[name] = value if not isinstance(value, (list, dict)) else value
            if update.summary and not (update.changes or {}).get("current"):
                state["current"] = update.summary
        state["updated"] = self.updates[-1].at if self.updates else str(
            self.note.meta.get("added") or "")
        return state

    @property
    def status(self) -> str:
        return str(self.current().get("status") or "active")

    @property
    def active(self) -> bool:
        return self.status.lower() not in {"done", "complete", "completed", "closed",
                                           "archived", "cancelled", "delivered"}

    @property
    def pinned_notes(self) -> list[str]:
        return fm.as_list(self.note.meta.get("pinned_notes"))

    @property
    def pinned_skills(self) -> list[str]:
        return fm.as_list(self.note.meta.get("pinned_skills"))

    @property
    def participants(self) -> list[str]:
        return fm.as_list(self.note.meta.get("participants"))

    @property
    def aliases(self) -> list[str]:
        return fm.as_list(self.note.meta.get("aliases"))


@dataclass
class Skill:
    name: str
    category: str
    scope: str
    body: str
    path: str                      # vault-relative SKILL.md path
    meta: dict = field(default_factory=dict)

    def _list(self, key):
        return fm.as_list(self.meta.get(key))

    @property
    def description(self) -> str:
        return str(self.meta.get("description") or "").strip()

    @property
    def when_to_use(self) -> str:
        return str(self.meta.get("when_to_use") or "").strip()

    @property
    def summary(self) -> str:
        line = str(self.meta.get("index_line") or "").strip()
        return line or util.excerpt(self.when_to_use or self.description, 200)

    @property
    def triggers(self) -> list[str]:
        return self._list("triggers")

    @property
    def aliases(self) -> list[str]:
        return self._list("aliases")

    @property
    def cue_terms(self) -> list[str]:
        return self._list("cue_terms")

    @property
    def artifacts(self) -> list[str]:
        return self._list("artifacts")

    @property
    def loads(self) -> list[str]:
        return self._list("loads")

    @property
    def depends_on(self) -> list[str]:
        return self._list("depends_on")

    @property
    def quality_gates(self) -> list[str]:
        return self._list("quality_gates")

    @property
    def partition(self) -> str | None:
        value = str(self.meta.get("partition") or "").strip()
        return value or None

    @property
    def load_topics(self) -> list[str]:
        return [item.rstrip("/") for item in self.loads
                if not item.startswith("references/") and "/" in item
                and not item.endswith(".md")]

    @property
    def load_references(self) -> list[str]:
        return [item for item in self.loads if item.startswith("references/")]

    @property
    def body_hash(self) -> str:
        return util.sha256(self.body.strip())

    @property
    def tokens(self) -> int:
        return util.tokens(self.body.strip())


@dataclass
class Reference:
    path: str                      # "references/..."
    body: str

    @property
    def title(self) -> str:
        for line in self.body.splitlines():
            if line.startswith("#"):
                return line.lstrip("#").strip()
        return self.path.rsplit("/", 1)[-1]

    @property
    def body_hash(self) -> str:
        return util.sha256(self.body)

    @property
    def tokens(self) -> int:
        return util.tokens(self.body)


@dataclass
class Proposal:
    id: str
    kind: str                      # note.create | note.update | note.archive | focus.create | skill.create
    scope: str
    meta: dict                     # proposal header (status, created, proposer, evidence ...)
    target: dict                   # proposed note/skill front matter
    body: str
    path: str

    @property
    def created(self) -> str:
        return str(self.meta.get("created") or "")

    @property
    def proposer(self) -> str:
        return str(self.meta.get("proposer") or "")

    @property
    def summary(self) -> str:
        return util.excerpt(self.body, 140)
