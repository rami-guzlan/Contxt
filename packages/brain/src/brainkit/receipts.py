"""The evidence receipt of one request (Release 1 plan, M07): exactly what was delivered.

Built from what the session ledger kept when the packet was handed over, so a receipt never
changes afterwards and always equals the delivery:

    sent              every item in the packet, whole or in short, with its tokens; the
                      startup context and the Brain map when they went with it
    opened            what the AI opened afterwards, before its next request (notes_get)
    did_not_fit       chosen but past the budget, named, not sent; and the related items
                      named for one call away
    already_delivered held from earlier in the conversation, not sent again
    unknown           what the Brain could not supply (nothing matched); the app adds the
                      captures that were not searchable yet
    tokens            the whole delivery, and how it was counted

A receipt lists what was sent. It is not proof that nothing was missed.
"""
from __future__ import annotations

from . import util

NOT_COMPLETE = ("A receipt lists what was sent and opened. It is not proof that nothing "
                "relevant was missed.")


def counted() -> str:
    """How token counts were made: exact or estimated."""
    return "exact (tiktoken)" if util._encoder() is not None else "estimated (characters / 4)"


def build(brain, packet_id: str) -> dict | None:
    row = brain.ledger.packet(str(packet_id or ""))
    if row is None:
        return None
    data = row.get("data") or {}
    st = brain.state()

    def named(note_id):
        note = st.index.note(note_id, include_archived=True)
        return {"id": note_id, "title": note.title if note is not None else note_id}

    tokens = data.get("note_tokens") or {}
    short = set(data.get("pointer_ids") or [])
    sent = [{**named(i), "form": "short" if i in short else "whole",
             "tokens": int(tokens.get(i) or 0)} for i in data.get("note_ids") or []]
    sent += [{**named(i), "form": "rule", "tokens": 0} for i in data.get("must_hold_ids") or []]
    sent += [{"id": s, "title": s, "form": "quoted section", "tokens": 0}
             for s in data.get("section_ids") or []]
    extra = []
    if data.get("kernel_included"):
        extra.append({"id": f"kernel:{data.get('kernel_fingerprint')}",
                      "title": "Startup context", "form": "whole", "tokens": 0})
    if data.get("map_included") in ("full", "changes"):
        extra.append({"id": f"map:{data.get('map_fingerprint')}", "title": "Brain map",
                      "form": data["map_included"], "tokens": int(data.get("map_tokens") or 0)})
    opened = [{**named(o["item"]), "tokens": int(o["tokens"] or 0), "at": o["at"]}
              for o in brain.ledger.opened_after(row["session_id"], row["id"])]
    did_not_fit = ([{**named(i), "why": "past this brief's budget"}
                    for i in data.get("unfit_ids") or []]
                   + [{**named(i), "why": "named as related, one call away"}
                      for i in data.get("related_ids") or []
                      if i not in set(data.get("unfit_ids") or [])]
                   + [{"id": s, "title": s, "why": "a file section past its allowance"}
                      for s in data.get("section_pointer_ids") or []]
                   + [{**named(i), "why": "a rule past the cap, listed"}
                      for i in data.get("must_hold_listed") or []])
    held = ([named(i) for i in data.get("held_ids") or []]
            + [{"id": s, "title": s} for s in data.get("held_section_ids") or []])
    unknown = []
    if not data.get("note_ids") and not data.get("must_hold_ids"):
        unknown.append("Nothing in the Brain matched this request.")
    total = (int(data.get("token_count") or 0) + int(data.get("map_tokens") or 0)
             + sum(o["tokens"] for o in opened))
    return {"id": row["id"], "session_id": row["session_id"], "at": row["at"],
            "request": row.get("request") or "", "scope": data.get("scope_chain") or [],
            "partition": data.get("partition"), "sent": sent + extra, "opened": opened,
            "did_not_fit": did_not_fit, "already_delivered": held, "unknown": unknown,
            "conflicts": data.get("conflict_ids") or [], "older": data.get("older_ids") or [],
            "tokens": {"packet": int(data.get("token_count") or 0),
                       "map": int(data.get("map_tokens") or 0),
                       "opened": sum(o["tokens"] for o in opened), "total": total,
                       "budget": data.get("note_budget"), "counted": counted()},
            "text": row.get("text") or "", "complete": False, "note": NOT_COMPLETE}


def render(found: dict) -> str:
    def items(rows, key="form"):
        return [f"- {r['title']} (`{r['id']}`)" + (f", {r[key]}" if r.get(key) else "")
                + (f", {r['tokens']} tokens" if r.get("tokens") else "") for r in rows]

    lines = [f"Receipt {found['id']} for: {found['request']}", ""]
    for label, rows, key in (("Sent", found["sent"], "form"), ("Opened afterwards",
                             found["opened"], ""), ("Did not fit", found["did_not_fit"], "why"),
                             ("Already delivered in this conversation",
                              found["already_delivered"], "")):
        if rows:
            lines += [f"{label}:"] + items(rows, key) + [""]
    if found["unknown"]:
        lines += ["Unknown:"] + [f"- {u}" for u in found["unknown"]] + [""]
    t = found["tokens"]
    lines.append(f"Tokens: {t['total']:,} in all ({t['packet']:,} packet, {t['map']:,} map, "
                 f"{t['opened']:,} opened), {t['counted']}.")
    lines.append(found["note"])
    return "\n".join(lines) + "\n"
