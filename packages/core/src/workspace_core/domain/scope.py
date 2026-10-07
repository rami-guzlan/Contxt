"""Where a working-context item (or any scoped record) lives: `project:proj_...`."""

from __future__ import annotations

from dataclasses import dataclass

from workspace_core.errors import ValidationFailed

KINDS = ("workspace", "goal", "project", "task", "inbox", "meeting")


@dataclass(frozen=True)
class ScopeRef:
    kind: str
    id: str | None = None

    @classmethod
    def parse(cls, text: str) -> ScopeRef:
        raw = str(text or "").strip()
        kind, _, ident = raw.partition(":")
        if kind == "workspace" and not ident:
            return cls("workspace", None)
        if kind not in KINDS or kind == "workspace" or not ident:
            raise ValidationFailed(
                "A scope is 'workspace', 'goal:<id>', 'project:<id>', 'task:<id>', "
                f"'meeting:<id>' or 'inbox:<actor id>', not {raw!r}.",
                field="scope",
            )
        return cls(kind, ident)

    def __str__(self) -> str:
        return self.kind if self.id is None else f"{self.kind}:{self.id}"
