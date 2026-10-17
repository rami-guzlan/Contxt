"""Each Brain's own bar for "nothing here" (general-retrieval plan 3.3).

A Brain is asked a bank of requests unrelated to anyone's notes (null_requests.txt): trivia,
history, language, arithmetic, small talk. The best match each one reaches among the Brain's
on-demand notes, by meaning (raw cosine) and by words (raw BM25), is the Brain's null
distribution. A match's EVIDENCE is the share of unrelated requests whose best match it
beats: 0.97 means only 3% of requests that have nothing to do with this Brain come this
close. Bars are set on that share (router.Policy `*_share`), the same for every Brain,
whatever its size, its vocabulary, the length of its notes or the embedding model.

Must-hold domains get the same treatment: the bank's similarity to each domain passage.

Meaning decides when the Brain has an embedding model; words otherwise. Measured on the
generated tuning Brains (October 16, 2026): raw cosine and raw BM25 tell real requests from
unrelated ones (AUC 1.00 and 0.98 to 1.00), where today's relative score did not (0.77 to
0.82 for coverage, and a top note always scoring at least 0.4 by words).

The calibration is kept beside the embedding cache and redone when its retrieval content,
eligible note/domain ids, model, or request bank changes. Counts alone cannot detect an edit
that changes what the Brain is about.
"""
from __future__ import annotations

import bisect
import json
import os
from importlib import resources

from . import util

# A big Brain is calibrated on part of the bank: the bar barely moves, the cost does.
LARGE_BRAIN = 2000
LARGE_SAMPLE = 120


def null_bank() -> list[str]:
    """The requests unrelated to anyone's notes."""
    text = resources.files("brainkit").joinpath("null_requests.txt").read_text(
        encoding="utf-8")
    return [line.strip() for line in text.splitlines()
            if line.strip() and not line.startswith("#")]


def bank_fingerprint(requests: list[str]) -> str:
    """Identity of the effective calibration input, independent of file line endings."""
    return util.sha256(json.dumps(requests, ensure_ascii=False, separators=(",", ":")))


def _requests(note_ids, requests=None) -> list[str]:
    bank = list(null_bank() if requests is None else requests)
    return bank[:LARGE_SAMPLE] if len(note_ids) > LARGE_BRAIN else bank


def corpus_fingerprint(index, note_ids, domain_ids) -> str:
    """Hash the inputs used by calibration, including enrichment and the word index."""
    from .index import note_vector_text, note_ask_lines, must_hold_search_text
    notes = getattr(index, "notes", {})
    config = getattr(index, "config", None)
    routing = getattr(config, "routing", None)
    payload = {
        "notes": {nid: {"text": note_vector_text(n), "hints": note_ask_lines(n)}
                  for nid, n in notes.items()},
        "domains": {nid: must_hold_search_text(notes[nid]) for nid in domain_ids if nid in notes},
        "note_ids": sorted(note_ids), "domain_ids": sorted(domain_ids),
        "words": getattr(index.note_bm25, "docs", {}),
        "phrases": getattr(routing, "phrases", {}),
    }
    return util.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False))


def _share(ordered: list[float], value: float) -> float:
    return bisect.bisect_right(ordered, value) / len(ordered) if ordered else 0.0


class Calibration:
    def __init__(self, cos: list[float] | None, bm: list[float],
                 domains: dict[str, list[float]] | None = None, notes: int = 0,
                 model: str = "", bank: str = "", corpus: str = ""):
        self.cos = sorted(cos) if cos else None
        self.bm = sorted(bm)
        self.domains = {k: sorted(v) for k, v in (domains or {}).items()}
        self.notes = notes
        self.model = model
        self.bank = bank
        self.corpus = corpus

    def evidence(self, cos_raw: float | None, bm_raw: float | None) -> float:
        """The share of unrelated requests this match beats: by meaning when the Brain has
        it, else by words."""
        if self.cos is not None and cos_raw is not None:
            return _share(self.cos, cos_raw)
        return _share(self.bm, bm_raw or 0.0)

    def domain_share(self, note_id: str, cos_raw: float | None) -> float | None:
        ordered = self.domains.get(note_id)
        if not ordered or cos_raw is None:
            return None
        return _share(ordered, cos_raw)

    def to_dict(self) -> dict:
        return {"cos": self.cos, "bm": self.bm, "domains": self.domains,
                "notes": self.notes, "model": self.model, "bank": self.bank, "corpus": self.corpus}

    @classmethod
    def from_dict(cls, data: dict) -> Calibration:
        return cls(data.get("cos"), data.get("bm") or [], data.get("domains") or {},
                   int(data.get("notes") or 0), str(data.get("model") or ""),
                   str(data.get("bank") or ""), str(data.get("corpus") or ""))


def build(index, note_ids: list[str], domain_ids: list[str] = (),
          requests: list[str] | None = None) -> Calibration:
    """Score the bank against these notes and must-hold domains."""
    from .index import QUERY_INSTRUCTIONS
    bank = _requests(note_ids, requests)
    bm = [max(index.note_bm25.scores(r, restrict=note_ids).values(), default=0.0)
          for r in bank]
    cos, domains, model = None, {}, ""
    if index.semantic_ready():
        model = index.embedder.model_name
        prefix = QUERY_INSTRUCTIONS.get(model, "")
        queries = index.embedder.embed([prefix + r for r in bank]) or []
        keys = [f"note:{i}" for i in note_ids]
        sims = [index.similarity_vector(q) for q in queries]
        if sims and any(k in sims[0] for k in keys):
            cos = [max(s.get(k, 0.0) for k in keys) for s in sims]
            for note_id in domain_ids:
                if f"domain:{note_id}" in sims[0]:
                    domains[note_id] = [s[f"domain:{note_id}"] for s in sims]
    return Calibration(cos, bm, domains, len(note_ids), model, bank_fingerprint(bank),
                       corpus_fingerprint(index, note_ids, domain_ids))


def for_index(index, note_ids: list[str], domain_ids: list[str] = ()) -> Calibration:
    """The Brain's calibration, cached only while its retrieval inputs are unchanged."""
    embedder = getattr(index, "embedder", None)
    path = (os.path.join(os.path.dirname(embedder.cache_path), "calibration.json")
            if embedder is not None else None)
    model = embedder.model_name if embedder is not None and index.semantic_ready() else ""
    bank = _requests(note_ids)
    fingerprint = bank_fingerprint(bank)
    corpus = corpus_fingerprint(index, note_ids, domain_ids)
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as handle:
                cached = Calibration.from_dict(json.load(handle))
            if cached.corpus == corpus and cached.bank == fingerprint and cached.model == model \
                    and set(domain_ids) <= set(cached.domains) \
                    | (set(domain_ids) if not model else set()):
                return cached
        except (OSError, ValueError, TypeError):
            pass
    found = build(index, note_ids, domain_ids, requests=bank)
    if path:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            util.atomic_write(path, json.dumps(found.to_dict()))
        except OSError:
            pass
    return found
