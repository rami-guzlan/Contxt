"""Does a proposal disagree with a note? The baseline check's cheap checks, before any model.

Two sentences are compared only when they are about the same thing: they share two or more
content words (`subject`: not figures, days, times of day or the names of people and places),
and those make up enough of the shorter one (`overlap`). In a lived-in Brain, notes about the
same people and days share words all the time; without that bar, two in five ordinary notes
read as disagreeing with something.

CHECK 1, NEAR PARAPHRASES (the review's sentence heuristic): the two sentences that share the
most words, nearly all of them (PARAPHRASE), one negating what the other states.

CHECK 2, FIGURES, NAMES AND OPPOSITES, sentence by sentence:

    figures     values of one kind with nothing in common: money, percentages, plain numbers
                with their unit, ordinal days ("the 5th"), times of day, dates ("November 12")
                and codes ("#1B2A4A") (FIGURES)
    names       each names someone for the same thing, and no name is shared ("leads go to
                Sam" against "leads now go to Priya") (NAMES)
    polarity    one rules something out (never, no, do not, without, nothing) and the other
                allows or asks for it ("never deploy on a Friday" against "Fridays are fine
                for deploys") (POLARITY)
    opposites   opposite actions on the same thing ("keep the free tier" against "remove the
                free tier") (POLARITY)

A model reading the pair through the owner's own AI is the third check, for what these miss
(an allergy against "can eat peanut butter now"); it runs in the app, not here.

ONE MEASURE, TWO DATES (`same_measure`): two sentences about the same thing giving different
values of one kind ("MRR was $36,100 at the end of August" and "MRR was $38,400 at the end
of September") are one value and its history when the notes are dated. The router keeps the
newest in a brief, and the review reads a newer dated value as an update, not a
disagreement.

Every finding is a reason in plain words, or None.
"""
from __future__ import annotations

import re

from . import util

MONTHS = {m: i for i, m in enumerate(
    "january february march april may june july august september october november december"
    .split(), 1)}
MONTHS.update({m[:3]: i for m, i in list(MONTHS.items())})
MONTHS["sept"] = 9
DAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
TIMES = {"am", "pm", "noon", "midnight"}
# How much of the shorter sentence's subject two sentences must share, by check.
PARAPHRASE = 0.75
FIGURES = 0.6
NAMES = 0.67
POLARITY = 0.5
NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen twenty".split())}
NUMBER_WORDS.update({"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
                     "eighty": 80, "ninety": 90, "hundred": 100, "dozen": 12})
SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "mm": 1e6, "b": 1e9,
         "billion": 1e9}

MONEY = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s?(k|m|mm|b|thousand|million|billion)?\b",
                   re.IGNORECASE)
PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s?(?:%|percent\b)", re.IGNORECASE)
ORDINAL = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\b", re.IGNORECASE)
CLOCK = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s?(am|pm|a\.m\.|p\.m\.)(?!\w)|\b(\d{1,2}):(\d{2})\b",
                   re.IGNORECASE)
DATE = re.compile(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True))
                  + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.IGNORECASE)
CODE = re.compile(r"#[0-9a-f]{6}\b", re.IGNORECASE)
VERSION = re.compile(r"(?<![\w.])v?(\d+(?:\.\d+){2,})\b", re.IGNORECASE)
NUMBER = re.compile(r"(?<![\w$#.:])(\d[\d,]*(?:\.\d+)?)(?![\w%:])")
WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")

NEGATIVE = re.compile(
    r"\b(never|not|no|nothing|nobody|none|don't|do not|doesn't|does not|cannot|can't|"
    r"mustn't|must not|shouldn't|should not|won't|without|avoid|stop|forbidden|banned|"
    r"off-limits|off limits|out of|excluded|fewer than|under no)\b", re.IGNORECASE)
# What the side that does not rule a thing out must say for the two to disagree: it allows
# it, asks for it, or requires it. A plain statement ("Ollie is allergic to peanuts") does
# neither, so it never clashes with a ban on the same thing.
PERMISSIVE = re.compile(
    r"\b(fine|okay|ok|allowed|can|may|go ahead|straight away|right away|directly|is a "
    r"priority|are a priority|priority segment|expand|add|include)\b", re.IGNORECASE)
REQUIRE = re.compile(r"\b(needs?|need to|must|has to|have to|requires?|required)\b",
                     re.IGNORECASE)
OPPOSITES = [("keep", "remove"), ("keep", "drop"), ("add", "remove"), ("include", "exclude"),
             ("allow", "forbid"), ("allow", "ban"), ("allow", "block"), ("enable", "disable"),
             ("start", "stop"), ("open", "close"), ("always", "never"), ("raise", "lower"),
             ("hire", "fire"), ("approve", "reject")]
GENERIC = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "for", "by", "with",
           "is", "are", "was", "be", "it", "its", "this", "that", "these", "each", "every",
           "per", "our", "we", "they", "now", "then", "so", "as", "from", "than", "up", "out",
           "all", "any", "more", "most", "much", "very", "just", "also", "only", "same",
           "new", "next", "last", "first", "one", "two", "three", "four", "five", "six",
           "seven", "eight", "nine", "ten", "twelve", "twenty", "fifty", "hundred", "can",
           "may", "must", "should", "will", "would", "do", "does", "not", "no", "never",
           "always", "fine", "ok", "okay", "without", "nothing", "go", "goes", "get",
           "make", "use", "have", "has", "had", "there", "here", "when", "where", "while",
           "under", "over", "after", "before", "until", "between", "into", "about"}


def sentences(text) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?;])\s+|\n+", str(text or "")) if s.strip()]


def _num(text: str) -> float:
    return float(text.replace(",", ""))


def figures(sentence: str) -> dict[str, set]:
    """{kind: values} for every figure a sentence gives."""
    out: dict[str, set] = {}
    rest = sentence

    def take(kind, value, span):
        nonlocal rest
        out.setdefault(kind, set()).add(value)
        rest = rest[:span[0]] + " " * (span[1] - span[0]) + rest[span[1]:]

    for m in CODE.finditer(sentence):
        take("code", m.group(0).lower(), m.span())
    for m in VERSION.finditer(rest):
        take("version", m.group(1), m.span())
    for m in MONEY.finditer(rest):
        scale = SCALE.get((m.group(2) or "").lower(), 1.0)
        take("money", round(_num(m.group(1)) * scale, 2), m.span())
    for m in PERCENT.finditer(rest):
        take("percent", _num(m.group(1)), m.span())
    for m in DATE.finditer(rest):
        take("date", (MONTHS[m.group(1).lower()], int(m.group(2))), m.span())
    for m in CLOCK.finditer(rest):
        if m.group(4):
            hour, minute = int(m.group(4)), int(m.group(5))
        else:
            hour, minute = int(m.group(1)), int(m.group(2) or 0)
            if m.group(3).lower().startswith("p") and hour < 12:
                hour += 12
            if m.group(3).lower().startswith("a") and hour == 12:
                hour = 0
        take("time", hour * 60 + minute, m.span())
    for m in ORDINAL.finditer(rest):
        take("ordinal", int(m.group(1)), m.span())
    for m in NUMBER.finditer(rest):
        unit = _unit_after(rest, m.end())
        take(f"number:{unit}" if unit else "number", _num(m.group(1)), m.span())
    words = [w.lower() for w in WORD.findall(rest)]
    for i, word in enumerate(words):
        if word in NUMBER_WORDS and word not in ("one",):
            unit = util.stem(words[i + 1]) if i + 1 < len(words) else ""
            unit = unit if unit not in GENERIC else ""
            out.setdefault(f"number:{unit}" if unit else "number", set()).add(
                float(NUMBER_WORDS[word]))
    return out


def _unit_after(text: str, end: int) -> str:
    match = WORD.match(text[end:].lstrip())
    if not match:
        return ""
    unit = util.stem(match.group(0).lower())
    return "" if unit in GENERIC else unit


def _stem(word: str) -> str:
    """The shared light stemmer, plus short plurals it leaves alone ("ads" is "ad")."""
    word = util.stem(word)
    if len(word) == 3 and word.endswith("s") and word not in ("bus", "gas", "yes", "has",
                                                               "was", "its", "his", "ops"):
        return word[:-1]
    return word


def subject(sentence: str) -> set[str]:
    """What a sentence is about: its content words, light-stemmed, without figures, days,
    times of day, and the names of people and places (capitalized past the first word;
    acronyms such as MRR stay)."""
    out = set()
    for i, word in enumerate(WORD.findall(sentence)):
        low = word.lower()
        if (len(low) < 2 or low in GENERIC or low in NUMBER_WORDS or low in MONTHS
                or low in DAYS or low.rstrip("s") in DAYS or low in TIMES):
            continue
        if i and word[:1].isupper() and not word.isupper():
            continue
        out.add(_stem(low))
    return out


def overlap(left: set[str], right: set[str]) -> float:
    """The share of the smaller subject the two have in common."""
    return len(left & right) / min(len(left), len(right)) if left and right else 0.0


def names(sentence: str) -> set[str]:
    """Capitalized words past a sentence's first word: the people and places it names. Days
    ("Saturdays" too) and months are dates, not names."""
    words = WORD.findall(sentence)
    return {w for w in words[1:] if w[:1].isupper() and w.lower().rstrip("s") not in DAYS
            and w.lower() not in DAYS and w.lower() not in MONTHS
            and w not in ("I", "AI", "US", "UK", "OK")}


def figure_subjects(text) -> list[set[str]]:
    """What each sentence that gives a figure is about: two notes giving figures for the same
    subject are worth comparing, however far apart they are filed."""
    return [subject(s) for s in sentences(text) if figures(s)]


def _negative(sentence: str) -> bool:
    return bool(NEGATIVE.search(sentence))


def _opposite(left: set[str], right: set[str]) -> tuple[str, str] | None:
    for a, b in OPPOSITES:
        if (a in left and b in right) or (b in left and a in right):
            return (a, b) if a in left else (b, a)
    return None


def _words(sentence: str) -> set[str]:
    return {util.stem(w.lower()) for w in WORD.findall(sentence)}


def check_two(proposed: str, existing: str) -> str | None:
    """Check 2: figures, names, polarity and opposites between sentences about one thing."""
    found = _check_two(proposed, existing)
    return found[1] if found else None


def _check_two(proposed: str, existing: str) -> tuple[str, str] | None:
    for left in sentences(proposed):
        left_subject = subject(left)
        for right in sentences(existing):
            right_subject = subject(right)
            shared = left_subject & right_subject
            if len(shared) < 2:
                continue
            near = overlap(left_subject, right_subject)
            about = ", ".join(sorted(shared)[:3])
            one, other = figures(left), figures(right)
            if near >= FIGURES:
                for kind in sorted(set(one) & set(other)):
                    if not one[kind] & other[kind]:
                        return ("figures", f"different figures for {about}: "
                                f"“{util.excerpt(left, 90)}” against "
                                f"“{util.excerpt(right, 90)}”")
            left_names, right_names = names(left), names(right)
            if near >= NAMES and left_names and right_names and not (left_names & right_names):
                return ("names", f"different names for {about}: "
                        f"“{util.excerpt(left, 90)}” against "
                        f"“{util.excerpt(right, 90)}”")
            if near < POLARITY:
                continue
            if _negative(left) != _negative(right):
                yes, no = (left, right) if _negative(right) else (right, left)
                if PERMISSIVE.search(yes) or REQUIRE.search(yes):
                    return ("polarity", f"one rules out what the other allows ({about}): "
                            f"“{util.excerpt(no, 90)}” against "
                            f"“{util.excerpt(yes, 90)}”")
            pair = _opposite(_words(left), _words(right))
            if pair:
                return ("opposites", f"opposite actions on {about} ({pair[0]} against "
                        f"{pair[1]}): “{util.excerpt(left, 90)}” against "
                        f"“{util.excerpt(right, 90)}”")
    return None


def check_one(proposed: str, existing: str) -> str | None:
    """Check 1: the review's sentence heuristic (the two sentences sharing the most words, at
    least three and nearly all of the shorter one's), read with the wider list of what rules
    a thing out, so "out of scope" and "keep it out of" count as negations. Figures are
    check 2's."""
    from .review import _sentences, _stems
    best = None
    for left in _sentences(proposed):
        left_terms = set(_stems(left))
        for right in _sentences(existing):
            right_terms = set(_stems(right))
            shared = len(left_terms & right_terms)
            if shared >= 3 and (best is None or shared > best[0]):
                best = (shared, left, right, overlap(left_terms, right_terms))
    if best is None or best[3] < PARAPHRASE:
        return None
    _shared, left, right, _near = best
    if _negative(left) != _negative(right):
        return (f"one says “{util.excerpt(left, 90)}”, the other "
                f"“{util.excerpt(right, 90)}”")
    return None


def classify(proposed: str, existing: str) -> tuple[str, str] | None:
    """(what disagrees, why in plain words), or None: "sentences" (check 1), or "figures",
    "names", "polarity" or "opposites" (check 2)."""
    found = check_one(proposed, existing)
    if found:
        return "sentences", found
    return _check_two(proposed, existing)


def tension(proposed: str, existing: str) -> str | None:
    """Why `proposed` may disagree with `existing` (checks 1 and 2), or None."""
    found = classify(proposed, existing)
    return found[1] if found else None


_MEASURES: dict[str, list[tuple[set, dict]]] = {}


def measures(text) -> list[tuple[set, dict]]:
    """(subject, figures) of every sentence that gives a figure, kept by text."""
    key = util.sha256(str(text or ""))
    found = _MEASURES.get(key)
    if found is None:
        if len(_MEASURES) > 20000:
            _MEASURES.clear()
        found = _MEASURES[key] = [(subject(s), figures(s)) for s in sentences(text)
                                  if figures(s)]
    return found


def same_measure(one, other) -> bool:
    """Do two texts give different values for the same thing (a sentence each, about the
    same thing, with a figure of one kind whose values differ)? Texts, or what `measures`
    made of them."""
    left = measures(one) if isinstance(one, str) else one
    right = measures(other) if isinstance(other, str) else other
    for left_subject, left_figures in left:
        for right_subject, right_figures in right:
            if len(left_subject & right_subject) < 2:
                continue
            if overlap(left_subject, right_subject) < FIGURES:
                continue
            if any(left_figures[k] != right_figures[k]
                   for k in set(left_figures) & set(right_figures)):
                return True
    return False
