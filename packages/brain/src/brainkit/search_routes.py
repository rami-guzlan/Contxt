"""A second way to search (v4 backend plan, 16.2): routes that miss differently from the
packet's matching, merged by reciprocal rank fusion.

- words: the packet's own matching (router.score_notes), on the query and, when the calling AI
  passes one, on its `rephrase` of what it is missing;
- exact: ids, titles and headings, matched as written (BM25 on those alone);
- graph: one relation hop (relations.py) out from the best word matches.

Every hit says which routes found it. No model call.
"""
from __future__ import annotations

from .index import BM25

K = 60          # reciprocal rank fusion: 1 / (K + rank)
GRAPH_FROM = 3  # the best word matches the graph route walks out from


def _labels(st) -> BM25:
    """A note's id, title and headings, indexed once per state of the Brain."""
    found = getattr(st.index, "_label_bm25", None)
    if found is None:
        texts = {}
        for note in st.index.notes.values():
            heads = [line.lstrip("#").strip() for line in str(note.body or "").splitlines()
                     if line.startswith("#")]
            texts[note.id] = " ".join([note.id.replace("-", " ").replace("_", " "),
                                       str(note.title or ""), *heads])
        found = BM25(texts, fold=st.index.fold)
        st.index._label_bm25 = found
    return found


def fused(brain, st, query: str, notes: list, chain, partitions, *, rephrase: str = "",
          limit: int = 12) -> list[tuple]:
    """[(note, words score, [routes])] best first, for the notes the caller may see."""
    from . import relations
    by_id = {n.id: n for n in notes}
    lists: dict[str, list[str]] = {}
    scores: dict[str, float] = {}
    for name, text in (("words", query), ("your rephrase", rephrase)):
        if not str(text or "").strip():
            continue
        ranked = [s for s in st.router.score_notes(str(text), notes) if s.score > 0.05]
        lists[name] = [s.item.id for s in ranked]
        for s in ranked:
            scores[s.item.id] = max(scores.get(s.item.id, 0.0), s.score)
    exact = _labels(st).scores(" ".join(t for t in (query, rephrase) if t),
                               restrict=list(by_id))
    lists["title or heading"] = sorted(exact, key=lambda i: -exact[i])
    graph: list[str] = []
    for start in (lists.get("words") or [])[:GRAPH_FROM]:
        for edge in relations.neighbours(brain, st, start, chain, partitions, depth=1):
            if edge["id"] in by_id and edge["id"] not in graph:
                graph.append(edge["id"])
    lists["related"] = graph
    fused_score: dict[str, float] = {}
    found_by: dict[str, list[str]] = {}
    for name, ids in lists.items():
        for rank, note_id in enumerate(ids):
            fused_score[note_id] = fused_score.get(note_id, 0.0) + 1.0 / (K + rank + 1)
            found_by.setdefault(note_id, []).append(name)
    order = sorted(fused_score, key=lambda i: (-fused_score[i], i))[:int(limit or 12)]
    return [(by_id[i], scores.get(i, 0.0), found_by[i]) for i in order]
