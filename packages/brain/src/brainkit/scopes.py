"""Who may see what: the scope chain and the partition axis.

SCOPES are an inheritance tree declared in `brain.json` under `scopes`. A caller's chain is
its own scope plus every ancestor, root first: `company > team:design > person:alex`.
A note is visible when its scope is on the chain. The closest scope wins when two notes
supersede each other.

PARTITIONS (clients, projects) are a sealed second axis. A request names at most one active
partition. A note that carries a partition is visible only while that partition (or one of
its descendants) is active, and only to a caller whose chain contains the partition's owner.
Unpartitioned notes are visible regardless. Two sibling clients can therefore never appear
in the same packet.
"""
from __future__ import annotations


class Scopes:
    def __init__(self, config):
        self.levels = list(config.structure.get("scope_levels") or [])
        self.declared = {k: dict(v or {}) for k, v in (config.data.get("scopes") or {}).items()
                         if not k.startswith("_")}
        self.partitions = {k: dict(v or {})
                           for k, v in (config.data.get("partitions") or {}).items()
                           if not k.startswith("_")}
        if not self.declared:
            self.declared = {"company": {}}

    # ------------------------------------------------------------------ scopes
    def root(self) -> str:
        for handle, spec in self.declared.items():
            if not spec.get("parent"):
                return handle
        return "company"

    def exists(self, handle) -> bool:
        return str(handle or "") in self.declared

    def kind(self, handle) -> str:
        handle = str(handle or "")
        for level in self.levels:
            prefix = level.get("prefix") or ""
            if prefix and handle.startswith(prefix):
                return level["kind"]
        return self.levels[0]["kind"] if self.levels else "company"

    def label(self, handle) -> str:
        return str(self.declared.get(handle, {}).get("label") or handle)

    def parents(self, handle) -> list[str]:
        spec = self.declared.get(handle) or {}
        out = [spec["parent"]] if spec.get("parent") else []
        out += [p for p in spec.get("alt_parents") or [] if p not in out]
        return out

    def principals(self) -> list[str]:
        kinds = {level["kind"] for level in self.levels if level.get("principal")}
        return [h for h in self.declared if self.kind(h) in kinds]

    def resolve(self, handle) -> str | None:
        """Accept `alex` as shorthand for the one principal scope ending in `:alex`."""
        handle = str(handle or "").strip()
        if not handle:
            return None
        if handle in self.declared:
            return handle
        matches = [h for h in self.declared if h.split(":", 1)[-1] == handle]
        return matches[0] if len(matches) == 1 else None

    def chain(self, handle, via=None) -> list[str] | None:
        """Root-first inheritance chain, or None for an unknown handle.

        `via` picks which parent a multi-parent scope inherits through (a person who belongs
        to two departments). It must be one of the declared parents.
        """
        handle = self.resolve(handle)
        if handle is None:
            return None
        out = [handle]
        current = handle
        first = True
        seen = {handle}
        while True:
            parents = self.parents(current)
            if not parents:
                break
            parent = parents[0]
            if first and via:
                via = self.resolve(via) or via
                if via not in parents:
                    return None
                parent = via
            first = False
            if parent in seen or parent not in self.declared:
                break
            seen.add(parent)
            out.append(parent)
            current = parent
        return list(reversed(out))

    def descendants(self, handle) -> set[str]:
        out = set()
        frontier = [handle]
        while frontier:
            current = frontier.pop()
            for child, spec in self.declared.items():
                if child in out:
                    continue
                if current == spec.get("parent") or current in (spec.get("alt_parents") or []):
                    out.add(child)
                    frontier.append(child)
        return out

    def scope_path(self, handle) -> str:
        handle = str(handle or "")
        for level in self.levels:
            prefix = level.get("prefix") or ""
            if prefix and handle.startswith(prefix):
                return f"{level.get('container') or level['kind']}/{handle[len(prefix):]}"
        return ""

    # ------------------------------------------------------------------ partitions
    def partition_chain(self, partition, chain) -> list[str] | None:
        """The active partition and its ancestors, or None when the caller may not use it."""
        if not partition:
            return []
        partition = str(partition).strip()
        if partition not in self.partitions:
            return None
        out = []
        current = partition
        while current and current not in out:
            spec = self.partitions.get(current)
            if spec is None:
                return None
            owner = spec.get("owner")
            if owner and owner not in (chain or []):
                return None
            out.append(current)
            current = spec.get("parent")
        return list(reversed(out))

    def owned_partitions(self, chain) -> list[str]:
        return sorted(p for p, spec in self.partitions.items()
                      if not spec.get("owner") or spec.get("owner") in (chain or []))

    # ------------------------------------------------------------------ admission
    @staticmethod
    def admits(scope, partition, chain, partitions=()) -> bool:
        if str(scope or "") not in (chain or []):
            return False
        if partition and partition not in (partitions or ()):
            return False
        return True
