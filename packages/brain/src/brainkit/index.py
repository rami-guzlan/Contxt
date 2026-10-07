"""The derived read model: lookup tables and search over one vault snapshot.

NOTHING HERE IS PERSISTED EXCEPT EMBEDDING VECTORS. An `Index` is built in memory from a
`Snapshot` in well under a second and rebuilt whenever the vault fingerprint changes, so
there is no index file that can fall behind the notes and no refresh step to remember.
Vectors are cached on disk by content hash because computing them is the one slow part.

Relevance is BM25 over light-stemmed terms, plus cosine similarity from a small local
embedding model when `fastembed` is installed. Both are optional evidence for the router;
neither decides admission, which is scope and status only.
"""
from __future__ import annotations

import contextlib
import math
import os
import re
import sqlite3
import struct
import threading
from collections import Counter

from . import sections as sections_mod
from . import util
from .model import Focus

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
# Asymmetric retrieval models are trained with an instruction on the query side only.
# Without it a short question is embedded like a passage and matches on tone, not subject.
_BGE_QUERY = "Represent this sentence for searching relevant passages: "
QUERY_INSTRUCTIONS = {
    "BAAI/bge-small-en-v1.5": _BGE_QUERY,
    "BAAI/bge-base-en-v1.5": _BGE_QUERY,
    "BAAI/bge-large-en-v1.5": _BGE_QUERY,
    "snowflake/snowflake-arctic-embed-m": _BGE_QUERY,
    "snowflake/snowflake-arctic-embed-l": _BGE_QUERY,
}
# Where a model's cosines start to mean "related" and how wide its useful range is: every
# model spreads similarity differently. (semantic_floor, semantic_span) for the router; a
# vault's routing.json `policy` overrides them. bge-base's scale maps bge-small's onto the same
# quantiles of request-to-note similarity over a real brain's benchmark requests (2026-10-06). That
# comparison kept bge-small as the default: bge-base found the right file part for 11 of 15
# labeled questions to bge-small's 15, and held-out note recall fell from 0.84 to 0.80.
MODEL_SCALES = {
    "BAAI/bge-small-en-v1.5": (0.34, 0.42),
    "BAAI/bge-base-en-v1.5": (0.267, 0.44),
}


def configured_model(vault_root: str) -> str:
    """The embedding model a vault asks for: $BRAIN_EMBED_MODEL, else brain.json
    `embeddings.model`, else the small default."""
    named = os.environ.get("BRAIN_EMBED_MODEL")
    if named:
        return named.strip()
    try:
        import json
        with open(os.path.join(vault_root, "brain.json"), encoding="utf-8") as handle:
            data = json.load(handle)
        named = str(((data.get("embeddings") or {}).get("model")) or "").strip()
    except (OSError, ValueError, AttributeError):
        named = ""
    return named or EMBED_MODEL


class BM25:
    """Okapi BM25 over a fixed document set, with light stemming."""

    def __init__(self, documents: dict, k1=1.2, b=0.75, unseen_idf=None, fold=None):
        self.k1, self.b = k1, b
        # Multiword terms read as one word, on the documents and the queries alike.
        self.fold = fold or util.phrase_folder()
        self.docs = {}
        self.lengths = {}
        df = Counter()
        for key, text in documents.items():
            words = [util.stem(w) for w in util.terms(self.fold(text))
                     if w not in util.STOPWORDS]
            counts = Counter(words)
            self.docs[key] = counts
            self.lengths[key] = len(words)
            df.update(counts.keys())
        self.n = max(1, len(self.docs))
        self.avg = (sum(self.lengths.values()) / self.n) if self.docs else 1.0
        self.idf = {t: math.log(1 + (self.n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        # A query word no document contains is the most informative miss there is: the
        # corpus knows nothing about it. It weighs as much as the rarest word, so "tell me
        # the weather" is not carried by "tell" alone.
        self.unseen_idf = (math.log(1 + (self.n + 0.5) / 0.5) if unseen_idf is None
                           else unseen_idf)
        # A query read once per index: routing scores it against every document, and a long
        # text (a proposal under review) costs more to split into terms than to score.
        self._queries: dict = {}

    def _query(self, query):
        """(terms, [(term, weight)], total weight) of a query, computed once."""
        found = self._queries.get(query)
        if found is None:
            seen: dict[str, None] = {}
            for word in util.content_terms(self.fold(query)):
                seen.setdefault(util.stem(word), None)
            terms = list(seen)
            weights = [(t, self.idf.get(t, self.unseen_idf)) for t in terms]
            found = (terms, weights, sum(w for _t, w in weights) or 1.0)
            if len(self._queries) >= 256:
                self._queries.clear()
            self._queries[query] = found
        return found

    def query_terms(self, query) -> list[str]:
        return list(self._query(query)[0])

    def scores(self, query, restrict=None) -> dict:
        """Raw BM25 score per document with a non-zero score."""
        qterms = self.query_terms(query) if isinstance(query, str) else list(query)
        out = {}
        keys = self.docs.keys() if restrict is None else [k for k in restrict if k in self.docs]
        for key in keys:
            counts = self.docs[key]
            length = self.lengths[key] or 1
            score = 0.0
            for term in qterms:
                freq = counts.get(term)
                if not freq:
                    continue
                idf = self.idf.get(term, 0.0)
                score += idf * freq * (self.k1 + 1) / (
                    freq + self.k1 * (1 - self.b + self.b * length / self.avg))
            if score > 0:
                out[key] = score
        return out

    def matched(self, query, key) -> int:
        """How many of the query's distinct terms one document contains."""
        counts = self.docs.get(key) or {}
        return sum(1 for term in self._query(query)[0] if counts.get(term))

    def shared(self, query, key, limit=5) -> list[str]:
        """The query's terms one document contains, rarest (most telling) first."""
        counts = self.docs.get(key) or {}
        _terms, weights, _total = self._query(query)
        found = sorted(((w, t) for t, w in weights if counts.get(t)), key=lambda p: (-p[0], p[1]))
        return [t for _w, t in found[:limit]]

    def coverage(self, query, key) -> float:
        """Share of the query's (idf-weighted) terms present in one document."""
        terms, weights, total = self._query(query)
        if not terms or key not in self.docs:
            return 0.0
        counts = self.docs[key]
        return sum(w for t, w in weights if counts.get(t)) / total


class Embedder:
    """Optional local sentence embeddings with an on-disk vector cache."""

    def __init__(self, runtime_dir: str, model_name: str = EMBED_MODEL, local_only=False):
        self.model_name = model_name
        self.cache_path = os.path.join(runtime_dir, "embeddings.sqlite")
        self.model_dir = os.path.join(runtime_dir, "models")
        # A server never fetches a model on its own: it uses one already in the brain's
        # model folder, or matches by words until the owner downloads one.
        self.local_only = bool(local_only)
        self._model = None
        self._failed = None
        self._lock = threading.Lock()
        self._memo: dict[str, list] = {}

    @property
    def available(self) -> bool:
        if self._failed:
            return False
        if self.local_only and not self.present():
            self._failed = (f"{self.model_name} is not in {self.model_dir}; matching by words "
                            "until it is downloaded")
            return False
        try:
            import fastembed  # noqa: F401
        except ImportError:
            self._failed = "fastembed is not installed"
            return False
        return True

    def status(self) -> dict:
        return {"available": self.available, "model": self.model_name,
                "reason": self._failed, "loaded": self._model is not None}

    def download(self) -> dict:
        """Fetch the model into the brain's model folder (an owner's command; a server never
        calls this). Returns the status afterwards."""
        with self._lock:
            self._model, self._failed = None, None
            local_only, self.local_only = self.local_only, False
        try:
            self._load()
        finally:
            self.local_only = local_only
        return self.status()

    def present(self) -> bool:
        """Is the model already in the brain's model folder? (fastembed keeps each one in a
        `models--<publisher>--<name>[...]` folder.)"""
        short = "--" + self.model_name.split("/")[-1].lower()
        try:
            return any(short in name.lower() for name in os.listdir(self.model_dir))
        except OSError:
            return False

    def _load(self):
        if self._model is None and not self._failed and self.local_only and not self.present():
            self._failed = (f"{self.model_name} is not in {self.model_dir}; matching by words "
                            "until it is downloaded")
        if self._model is None and not self._failed:
            try:
                from fastembed import TextEmbedding
                os.makedirs(self.model_dir, exist_ok=True)
                self._model = TextEmbedding(model_name=self.model_name, cache_dir=self.model_dir,
                                            local_files_only=self.local_only)
            except Exception as exc:
                self._failed = f"embedding model unavailable: {exc}"
        return self._model

    def _db(self):
        conn = sqlite3.connect(self.cache_path, timeout=10)
        conn.execute("CREATE TABLE IF NOT EXISTS vectors (key TEXT PRIMARY KEY, data BLOB)")
        return conn  # callers close it explicitly

    def _key(self, text: str) -> str:
        return util.sha256(self.model_name + "\x00" + text)

    def embed_query(self, text: str) -> list | None:
        """The vector for a search query, with the model's query instruction."""
        vectors = self.embed([QUERY_INSTRUCTIONS.get(self.model_name, "") + text])
        return vectors[0] if vectors else None

    def embed(self, texts: list[str]) -> list | None:
        """Vectors for `texts` (cached), or None when embeddings are unavailable."""
        if not self.available:
            return None
        with self._lock:
            keys = [self._key(t) for t in texts]
            missing = [k for k in keys if k not in self._memo]
            if missing:
                try:
                    with contextlib.closing(self._db()) as conn:
                        for start in range(0, len(missing), 400):
                            chunk = missing[start:start + 400]
                            marks = ",".join("?" * len(chunk))
                            for key, blob in conn.execute(
                                    f"SELECT key, data FROM vectors WHERE key IN ({marks})",
                                    chunk):
                                count = len(blob) // 4
                                self._memo[key] = list(struct.unpack(f"{count}f", blob))
                except sqlite3.Error:
                    pass
            todo = [(k, t) for k, t in zip(keys, texts) if k not in self._memo]
            if todo:
                model = self._load()
                if model is None:
                    return None
                vectors = [list(map(float, v)) for v in model.embed([t for _k, t in todo])]
                try:
                    with contextlib.closing(self._db()) as conn:
                        conn.executemany(
                            "INSERT OR REPLACE INTO vectors (key, data) VALUES (?, ?)",
                            [(k, struct.pack(f"{len(v)}f", *v))
                             for (k, _t), v in zip(todo, vectors)])
                        conn.commit()
                except sqlite3.Error:
                    pass
                for (key, _text), vector in zip(todo, vectors):
                    self._memo[key] = vector
            return [self._memo[k] for k in keys]


RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"


class Reranker:
    """Optional local cross-encoder that reads a request and a note together.

    An embedding compares two separately computed vectors; a cross-encoder reads the pair
    at once, so it can tell "how do I add utm tracking to a link" belongs with the UTM
    scheme even where the vectors are close for many notes. It is slower (tens of
    milliseconds per note), so the router only rescores its top few candidates.

    NEVER DOWNLOADS ON ITS OWN. It loads from the brain's model folder only; fetching the
    model is an explicit, owner-approved step (`brain models --download`). When
    the model is not there, the reranker is simply unavailable and routing works without it.
    """

    def __init__(self, runtime_dir: str, model_name: str = RERANK_MODEL):
        self.model_name = model_name
        self.model_dir = os.path.join(runtime_dir, "models")
        self._model = None
        self._failed = None
        self._lock = threading.Lock()
        self._memo: dict[tuple, float] = {}

    @property
    def available(self) -> bool:
        return self._load() is not None

    def status(self) -> dict:
        present = self.present()
        return {"available": present and not self._failed, "model": self.model_name,
                "downloaded": present, "reason": self._failed,
                "loaded": self._model is not None}

    def present(self) -> bool:
        folder = os.path.join(self.model_dir, "models--" + self.model_name.replace("/", "--"))
        return os.path.isdir(folder)

    def _load(self, download=False):
        if self._model is not None or self._failed:
            return self._model
        with self._lock:
            if self._model is not None or self._failed:
                return self._model
            if not download and not self.present():
                self._failed = "reranker model not downloaded (brain models --download)"
                return None
            try:
                from fastembed.rerank.cross_encoder import TextCrossEncoder
                os.makedirs(self.model_dir, exist_ok=True)
                self._model = TextCrossEncoder(model_name=self.model_name,
                                               cache_dir=self.model_dir,
                                               local_files_only=not download)
            except Exception as exc:
                self._failed = f"reranker unavailable: {exc}"
        return self._model

    def download(self) -> dict:
        """Fetch the model into the brain's model folder. Only called on an owner's command."""
        self._failed = None
        model = self._load(download=True)
        return {"ok": model is not None, **self.status()}

    def score(self, query: str, texts: list[str]) -> list | None:
        """Relevance logits for (query, text) pairs, or None when unavailable. Memoized."""
        model = self._load()
        if model is None:
            return None
        keys = [(query, util.sha256(t)) for t in texts]
        todo = [(k, t) for k, t in zip(keys, texts) if k not in self._memo]
        if todo:
            if len(self._memo) > 20000:
                self._memo.clear()
            scores = list(model.rerank(query, [t for _k, t in todo], batch_size=32))
            for (key, _text), value in zip(todo, scores):
                self._memo[key] = float(value)
        return [self._memo[k] for k in keys]


def cosine(a, b) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    # math.sumprod runs in C: comparing a request with every stored vector stays cheap.
    dot = math.sumprod(a, b)
    na = math.sqrt(math.sumprod(a, a))
    nb = math.sqrt(math.sumprod(b, b))
    return dot / (na * nb) if na and nb else 0.0


def _cased(word: str, texts: list[str]) -> str | None:
    """How texts write a word: an acronym or inner capital (UTM, HubSpot) when that is
    how it is often written, a capital when it mostly has one (a name), else lowercase.
    None when no text uses it."""
    forms = Counter(m for text in texts
                    for m in re.findall(rf"\b{re.escape(word)}\b", text, re.IGNORECASE))
    total = sum(forms.values())
    if not total:
        return None
    special = [(n, f) for f, n in forms.items()
               if (f.isupper() and len(f) > 1) or any(c.isupper() for c in f[1:])]
    if special and max(special)[0] >= 0.3 * total:
        return max(special)[1]
    capital = sum(n for f, n in forms.items() if f[:1].isupper())
    return word.capitalize() if capital > total / 2 else word.lower()


def note_search_text(note) -> str:
    topic_words = note.topic.replace("-", " ")
    title = str(note.meta.get("title") or "").strip()
    return f"{topic_words} {title} {note.summary} {note.body}"


def skill_search_text(skill) -> str:
    parts = [skill.name.replace("-", " ").replace("_", " "), skill.category,
             skill.description, skill.when_to_use, str(skill.meta.get("index_line") or "")]
    parts += skill.triggers + skill.aliases + skill.cue_terms + skill.artifacts
    return " ".join(p for p in parts if p)


def file_cards(notes, references) -> dict:
    """{reference path: the note that is its card}. A card names its file in `file`; older
    pointer notes ("Pointer: ... is filed whole at references/...") count too."""
    out = {}
    for note in sorted(notes.values(), key=lambda n: n.id):
        path = str(note.meta.get("file") or "").strip()
        if path in references:
            out.setdefault(path, note)
            continue
        if note.body.lstrip().startswith("Pointer:"):
            for path in note.references:
                if path in references:
                    out.setdefault(path, note)
    return out


class Index:
    """Everything the router needs from one snapshot, in memory."""

    def __init__(self, snapshot, config, embedder: Embedder | None = None):
        self.snapshot = snapshot
        self.config = config
        self.embedder = embedder
        self.notes = {nid: n for nid, n in snapshot.notes.items() if n.live}
        self.archived = {nid: n for nid, n in snapshot.notes.items() if not n.live}
        self.skills = dict(snapshot.skills)
        self.references = dict(snapshot.references)
        self.by_topic: dict[str, list[str]] = {}
        for note in self.notes.values():
            self.by_topic.setdefault(note.route_key, []).append(note.id)
        self.focuses = {
            nid: Focus(note=n, updates=list(snapshot.focus_updates.get(nid, [])))
            for nid, n in self.notes.items() if config.is_focus(n)}
        self.fold = util.phrase_folder(config.routing.phrases)
        self.note_bm25 = BM25({nid: note_search_text(n) for nid, n in self.notes.items()},
                              fold=self.fold)
        self.skill_bm25 = BM25({name: skill_search_text(s) for name, s in self.skills.items()},
                               fold=self.fold)
        self.topics = dict(config.topics)
        self.topic_texts = self._topic_texts(config)
        self.topic_bm25 = BM25(self.topic_texts, fold=self.fold)
        # Filed documents: each file's card, and the sections a request can reach on their
        # own (sections.py). A file whose card was archived is out of the Brain: its sections
        # are not offered.
        self.cards = file_cards(self.notes, self.references)
        retired = set(file_cards(self.archived, self.references)) - set(self.cards)
        self.sections = {}
        for path, ref in sorted(self.references.items()):
            if os.path.basename(path).lower() == "readme.md" or path in retired:
                continue
            for section in sections_mod.split(path, ref.body):
                self.sections[section.id] = section
        # A request's words that no file uses ("tighten", "shorter") say what to do, not which
        # part of a file it is about: they weigh like ordinary words in a section's coverage,
        # not like the rarest one.
        self.section_bm25 = BM25({sid: self.section_search_text(s)
                                  for sid, s in self.sections.items()}, fold=self.fold,
                                 unseen_idf=1.0)
        self._vectors: dict[str, list] | None = None
        self._vector_lock = threading.RLock()
        self._centrality: dict[str, float] | None = None
        self._labels: dict[str, str] = {}

    def _topic_texts(self, config) -> dict:
        """What each topic is about, for matching a request to a whole topic.

        A topic's line in topics.md when it has one. A topic without a line (a project folder,
        a topic a new note just created) is described by what is filed in it: the project's
        title and current state, or the titles of its notes. Every topic with a live note
        gets a description, so a new topic is matchable the moment its first note lands.
        """
        members: dict[str, list] = {}
        for note in self.notes.values():
            members.setdefault(note.route_key, []).append(note)
        out = {}
        for key in sorted(set(members) | set(self.topics)):
            area, _, name = key.partition("/")
            words = f"{area.replace('-', ' ')} {name.replace('-', ' ')}"
            topic = self.topics.get(key)
            if topic is not None:
                out[key] = f"{words} {topic.description}"
                continue
            notes = members.get(key) or []
            focus = next((n for n in notes if config.is_focus(n)), None)
            if focus is not None:
                out[key] = f"{words} {focus.title} {focus.summary}"
            else:
                out[key] = f"{words} " + " ".join(n.title for n in sorted(notes, key=lambda n: n.id))
        return out

    # ------------------------------------------------------------------ files
    def file_title(self, path) -> str:
        card = self.cards.get(path)
        if card is not None and card.meta.get("title"):
            return card.title
        ref = self.references.get(path)
        return ref.title if ref is not None else path.rsplit("/", 1)[-1]

    def section_search_text(self, section) -> str:
        """What a section is matched on: its file's title, its headings and its text. The
        title makes "the LinkedIn part of the campaign proposal" prefer the proposal's
        LinkedIn section to a LinkedIn section elsewhere."""
        return f"{self.file_title(section.path)} {section.heading} {section.text}"

    def file_sections(self, path) -> list:
        return [s for s in self.sections.values() if s.path == path]

    def file_project(self, path):
        """The project (Focus) a filed document belongs to: the one its card names in
        `project_id`, else, in the area layout, the project whose folder holds the card."""
        card = self.cards.get(path)
        if card is None:
            return None
        named = str(card.meta.get("project_id") or "").strip()
        if named:
            return self.focuses.get(named)
        if self.config.uses_areas:
            return next((f for f in self.focuses.values()
                         if f.note.route_key == card.route_key), None)
        return None

    def project_files(self, focus) -> list:
        """[(path, card)] of the documents filed in a project."""
        return [(path, card) for path, card in sorted(self.cards.items())
                if (found := self.file_project(path)) is not None and found.id == focus.id]

    # ------------------------------------------------------------------ lookups
    def note(self, note_id, include_archived=False):
        note_id = str(note_id or "").strip()
        target = self.config.aliases.get(note_id, note_id)
        note = self.notes.get(target)
        if note is None and include_archived:
            note = self.archived.get(target)
        return note

    def topic_label(self, key: str) -> str:
        """A topic's name the way its notes write it: "utm" is "UTM", "hubspot" is "HubSpot",
        "jane-doe" is "Jane Doe", "content-strategy" is "Content strategy"."""
        found = self._labels.get(key)
        if found is None:
            name = key.partition("/")[2] or key
            own = [f"{n.title} {n.summary} {n.body}" for n in self.notes.values()
                   if n.route_key == key]
            every = [f"{n.title} {n.summary} {n.body}" for n in self.notes.values()]
            words = [_cased(word, own) or _cased(word, every) or word
                     for word in name.replace("_", "-").split("-") if word]
            if words and words[0] == words[0].lower():
                words[0] = words[0][:1].upper() + words[0][1:]
            found = self._labels[key] = " ".join(words) or key
        return found

    def supersedes_map(self) -> dict:
        out = {}
        for note in self.notes.values():
            for old in (str(note.meta.get("supersedes") or "").split(",")):
                old = old.strip()
                if old and old.lower() != "none":
                    out[old] = note.id
        return out

    # ------------------------------------------------------------------ centrality
    def centrality(self, note_id) -> float:
        """How central a note is to its own topic, 0..1: its similarity to the topic's line
        in topics.md. The notes a topic line describes are the topic's essence; a note about
        a side detail sits further out. Semantic when embeddings are on, lexical otherwise."""
        if self._centrality is None:
            with self._vector_lock:
                if self._centrality is None:
                    self._centrality = self._compute_centrality()
        return self._centrality.get(note_id, 0.5)

    def _compute_centrality(self) -> dict:
        out = {}
        vectors = self._item_vectors() if self.semantic_ready() else {}
        for note_id, note in self.notes.items():
            text = self.topic_texts.get(note.route_key)
            if text is None:
                continue
            note_vec = vectors.get(f"note:{note_id}")
            topic_vec = vectors.get(f"topic:{note.route_key}")
            if note_vec and topic_vec:
                value = (cosine(note_vec, topic_vec) - 0.34) / 0.42
            else:
                value = self.note_bm25.coverage(text, note_id)
            out[note_id] = round(max(0.0, min(1.0, value)), 4)
        return out

    # ------------------------------------------------------------------ semantic
    def semantic_ready(self) -> bool:
        return bool(self.embedder and self.embedder.available)

    def _item_vectors(self):
        if self._vectors is not None:
            return self._vectors
        with self._vector_lock:
            if self._vectors is not None:
                return self._vectors
            items = [(f"note:{nid}", note_search_text(n)[:2000]) for nid, n in self.notes.items()]
            items += [(f"skill:{name}", skill_search_text(s)[:2000])
                      for name, s in self.skills.items()]
            items += [(f"topic:{key}", text) for key, text in self.topic_texts.items()]
            items += [(f"section:{sid}", self.section_search_text(s)[:2000])
                      for sid, s in self.sections.items()]
            vectors = self.embedder.embed([text for _key, text in items]) if self.embedder else None
            self._vectors = ({key: vec for (key, _t), vec in zip(items, vectors)}
                             if vectors else {})
            return self._vectors

    def warm(self) -> None:
        """Compute what the first request would otherwise wait for (the vectors of a newly
        filed document's sections). The vectors are cached on disk, so every other process
        reading this vault finds them ready."""
        if self.semantic_ready():
            self._item_vectors()

    def similarity(self, request: str) -> dict:
        """Cosine similarity of the request to every note, skill, topic and file section
        ("kind:id")."""
        if not self.semantic_ready():
            return {}
        vectors = self._item_vectors()
        if not vectors:
            return {}
        qv = self.embedder.embed_query(request)
        if not qv:
            return {}
        return {key: cosine(qv, vec) for key, vec in vectors.items()}
