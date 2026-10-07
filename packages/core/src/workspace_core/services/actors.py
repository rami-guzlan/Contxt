"""People and models, and the credentials that say who is calling.

Each model connection gets its own revocable credential. Tokens are shown once and stored only
as a SHA-256 hash; authentication turns a token into a Principal, which is the only source of
identity and authority the rest of the core accepts.
"""

from __future__ import annotations

import builtins
import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import sqlalchemy as sa

from workspace_core.clock import iso, parse_iso
from workspace_core.db import schema
from workspace_core.db.tx import Tx
from workspace_core.domain.policy import MODEL_DEFAULTS, Grant, Principal
from workspace_core.domain.records import Actor, Credential
from workspace_core.errors import NotFound, Unauthenticated, ValidationFailed

from .runtime import Runtime

TOKEN_PREFIX = "wst_"
PROVIDERS = (
    "claude-code",
    "claude-desktop",
    "chatgpt",
    "codex",
    "gemini",
    "cursor",
    "ollama",
    "other",
)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Connection:
    """A model connection as created: the token is only ever returned here."""

    actor: Actor
    credential: Credential
    token: str


def actor_can_claim(tx: Tx, actor_id: str, project_id: str | None) -> bool:
    """Whether any active credential of this actor could claim work in this project."""
    actor = tx.get(schema.actors, actor_id)
    if actor is None or actor["disabled_at"] is not None:
        return False
    if actor["kind"] == "human":
        return True
    creds = schema.credentials
    rows = tx.rows(
        sa.select(creds).where(creds.c.actor_id == actor_id, creds.c.revoked_at.is_(None))
    )
    for row in rows:
        grant = Grant.of(row["actions"], row["projects"], kind=actor["kind"])
        if "tasks.claim" in grant.actions and (
            project_id is None or grant.projects is None or project_id in grant.projects
        ):
            return True
    return False


class Actors:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt

    # ---------------------------------------------------------------- queries

    def list(self, who: Principal, include_disabled: bool = False) -> builtins.list[Actor]:
        table = schema.actors
        query = sa.select(table).where(table.c.workspace_id == self.rt.workspace_id)
        if not include_disabled:
            query = query.where(table.c.disabled_at.is_(None))
        with self.rt.read() as tx:
            return [Actor.from_row(r) for r in tx.rows(query.order_by(table.c.created_at))]

    def get(self, who: Principal, actor_id: str) -> Actor:
        with self.rt.read() as tx:
            return Actor.from_row(tx.one(schema.actors, actor_id, "actor"))

    def credentials(self, who: Principal, actor_id: str) -> builtins.list[Credential]:
        who.require("workspace.admin")
        table = schema.credentials
        with self.rt.read() as tx:
            rows = tx.rows(
                sa.select(table).where(table.c.actor_id == actor_id).order_by(table.c.created_at)
            )
        return [Credential.from_row(r) for r in rows]

    # ---------------------------------------------------------------- connections

    def connect_model(
        self,
        who: Principal,
        *,
        name: str,
        provider: str,
        description: str | None = None,
        projects: builtins.list[str] | None = None,
        actions: builtins.list[str] | None = None,
        label: str | None = None,
    ) -> Connection:
        """Add a model and issue its first credential. Returns the token once."""
        who.require("workspace.admin")
        name = (name or "").strip()
        if not name:
            raise ValidationFailed(
                "A connection needs a name, such as 'Claude Code'.", field="name"
            )
        if provider not in PROVIDERS:
            raise ValidationFailed(
                f"Provider must be one of {', '.join(PROVIDERS)}.", field="provider"
            )
        with self.rt.write() as tx:
            actor_id = tx.new_id("act")
            tx.insert(
                schema.actors,
                {
                    "id": actor_id,
                    "workspace_id": self.rt.workspace_id,
                    "kind": "model",
                    "name": name,
                    "provider": provider,
                    "description": description,
                    "created_at": tx.now,
                    "updated_at": tx.now,
                    "version": 1,
                },
            )
            credential, token = self._issue(
                tx, who, actor_id, "model", label or name, actions, projects
            )
            tx.emit(
                "actor.connected",
                actor_id=who.actor_id,
                subject_type="actor",
                subject_id=actor_id,
                data={"name": name, "provider": provider, "projects": projects},
            )
            actor = Actor.from_row(tx.one(schema.actors, actor_id, "actor"))
        return Connection(actor=actor, credential=credential, token=token)

    def issue_token(
        self,
        who: Principal,
        actor_id: str,
        *,
        label: str | None = None,
        actions: builtins.list[str] | None = None,
        projects: builtins.list[str] | None = None,
    ) -> Connection:
        """A new credential for an existing actor (rotation: issue, switch, revoke the old)."""
        who.require("workspace.admin")
        with self.rt.write() as tx:
            actor = tx.one(schema.actors, actor_id, "actor")
            credential, token = self._issue(
                tx, who, actor_id, actor["kind"], label, actions, projects
            )
            tx.emit(
                "credential.issued",
                actor_id=who.actor_id,
                subject_type="actor",
                subject_id=actor_id,
                data={"credential_id": credential.id},
            )
        return Connection(actor=Actor.from_row(actor), credential=credential, token=token)

    def revoke(self, who: Principal, credential_id: str) -> Credential:
        who.require("workspace.admin")
        with self.rt.write() as tx:
            row = tx.one(schema.credentials, credential_id, "credential")
            if row["revoked_at"] is None:
                tx.conn.execute(
                    schema.credentials.update()
                    .where(schema.credentials.c.id == credential_id)
                    .values(revoked_at=tx.now)
                )
                row["revoked_at"] = tx.now
                tx.emit(
                    "credential.revoked",
                    actor_id=who.actor_id,
                    subject_type="actor",
                    subject_id=row["actor_id"],
                    data={"credential_id": credential_id},
                )
        return Credential.from_row(row)

    def rename(self, who: Principal, actor_id: str, name: str) -> Actor:
        """A new display name: the owner's own name instead of "Owner", a model's clearer one.
        People may rename themselves; the admin may rename anyone."""
        if actor_id != who.actor_id:
            who.require("workspace.admin")
        text = " ".join(str(name or "").split())
        if not text or len(text) > 80:
            raise ValidationFailed("A name has 1 to 80 characters.", field="name")
        with self.rt.write() as tx:
            row = tx.one(schema.actors, actor_id, "actor")
            if row["workspace_id"] != self.rt.workspace_id:
                raise ValidationFailed("No such actor here.", field="actor_id")
            if text == row["name"]:
                return Actor.from_row(row)
            before = row["name"]
            row = tx.update(schema.actors, row, {"name": text})
            tx.emit(
                "actor.renamed",
                actor_id=who.actor_id,
                subject_type="actor",
                subject_id=actor_id,
                data={"from": before, "to": text},
            )
        return Actor.from_row(row)

    def disable(self, who: Principal, actor_id: str) -> Actor:
        """Disconnect a model: its credentials stop working; its history stays."""
        who.require("workspace.admin")
        with self.rt.write() as tx:
            row = tx.one(schema.actors, actor_id, "actor")
            if row["kind"] != "model":
                raise ValidationFailed("Only model connections can be disabled here.")
            row = tx.update(schema.actors, row, {"disabled_at": tx.now})
            tx.conn.execute(
                schema.credentials.update()
                .where(
                    schema.credentials.c.actor_id == actor_id,
                    schema.credentials.c.revoked_at.is_(None),
                )
                .values(revoked_at=tx.now)
            )
            tx.emit(
                "actor.disabled", actor_id=who.actor_id, subject_type="actor", subject_id=actor_id
            )
        return Actor.from_row(row)

    def register_token(self, actor_id: str, token: str, label: str) -> None:
        """Accept a token chosen outside the app (the owner token in .env). Idempotent."""
        if not token.startswith(TOKEN_PREFIX) or len(token) < 24:
            raise ValidationFailed(
                f"Tokens start with {TOKEN_PREFIX} and are at least 24 "
                "characters long; generate one with `workspace token`."
            )
        digest = hash_token(token)
        with self.rt.write() as tx:
            table = schema.credentials
            if tx.first(sa.select(table.c.id).where(table.c.token_hash == digest)):
                return
            actor = tx.one(schema.actors, actor_id, "actor")
            tx.insert(
                table,
                {
                    "id": tx.new_id("cred"),
                    "actor_id": actor_id,
                    "token_hash": digest,
                    "token_hint": token[:8],
                    "label": label,
                    "actions": ["*"],
                    "projects": None,
                    "created_by": actor_id,
                    "created_at": tx.now,
                },
            )
            tx.emit(
                "credential.issued",
                actor_id=actor_id,
                subject_type="actor",
                subject_id=actor["id"],
                data={"label": label},
            )

    # ---------------------------------------------------------------- authentication

    def authenticate(self, token: str | None) -> Principal:
        if not token or not token.startswith(TOKEN_PREFIX):
            raise Unauthenticated("Missing or malformed token.")
        digest = hash_token(token)
        creds, actors = schema.credentials, schema.actors
        with self.rt.read() as tx:
            row = tx.first(
                sa.select(creds, actors.c.kind, actors.c.name, actors.c.disabled_at)
                .join(actors, actors.c.id == creds.c.actor_id)
                .where(creds.c.token_hash == digest)
            )
        if row is None or row["revoked_at"] is not None or row["disabled_at"] is not None:
            raise Unauthenticated("This token is not valid (unknown or revoked).")
        self._touch(row)
        return Principal(
            actor_id=row["actor_id"],
            kind=row["kind"],
            name=row["name"],
            grant=Grant.of(row["actions"], row["projects"], kind=row["kind"]),
            credential_id=row["id"],
        )

    def principal(self, actor_id: str) -> Principal:
        """The principal of a built-in actor (the owner, the system): full authority."""
        with self.rt.read() as tx:
            row = tx.one(schema.actors, actor_id, "actor")
        if row["kind"] == "model":
            raise NotFound("Models act only through their credentials.")
        return Principal(
            actor_id=row["id"],
            kind=row["kind"],
            name=row["name"],
            grant=Grant.of({"*"}, None, kind="human"),
        )

    def can_claim(self, actor_id: str, project_id: str | None) -> bool:
        with self.rt.read() as tx:
            return actor_can_claim(tx, actor_id, project_id)

    # ---------------------------------------------------------------- internals

    def _issue(
        self,
        tx: Tx,
        who: Principal,
        actor_id: str,
        kind: str,
        label: str | None,
        actions: builtins.list[str] | None,
        projects: builtins.list[str] | None,
    ) -> tuple[Credential, str]:
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        wanted = list(actions) if actions else sorted(MODEL_DEFAULTS if kind == "model" else {"*"})
        grant = Grant.of(wanted, projects, kind=kind)
        row = {
            "id": tx.new_id("cred"),
            "actor_id": actor_id,
            "token_hash": hash_token(token),
            "token_hint": token[:8],
            "label": label,
            "actions": sorted(grant.actions),
            "projects": sorted(projects) if projects is not None else None,
            "created_by": who.actor_id,
            "created_at": tx.now,
        }
        tx.insert(schema.credentials, row)
        return Credential.from_row(dict(row, last_used_at=None, revoked_at=None)), token

    def _touch(self, row: dict[str, Any]) -> None:
        """Record use at most once a minute, so authentication stays a read."""
        now = self.rt.clock.now()
        last = row.get("last_used_at")
        if last and parse_iso(last) > now - timedelta(minutes=1):
            return
        with self.rt.write() as tx:
            tx.conn.execute(
                schema.credentials.update()
                .where(schema.credentials.c.id == row["id"])
                .values(last_used_at=iso(now))
            )
            tx.conn.execute(
                schema.actors.update()
                .where(schema.actors.c.id == row["actor_id"])
                .values(last_seen_at=iso(now))
            )
