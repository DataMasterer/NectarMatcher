"""Culture-aware parsing of a full name into role-tagged components.

The same surface string means different things by culture, so matching must
parse before it compares:

- **Western**: given [middle...] surname.
- **Arabic**: ism (given) + nasab (forefather chain, often joined by
  ابن/بن/بنت or simply space-separated) + optional laqab / nisba (al-...i) /
  kunya (Abu/Umm ...). Middle tokens are *forefathers*, not middle names, so
  they carry low weight in matching.
- **Spanish**: given + two surnames (paternal, maternal).
- **Portuguese/Brazilian**: given + several surnames (maternal... paternal),
  with low-weight particles (de, da, dos...).

Compound given names that are a single unit — ``صلاح الدين`` ("Salah al-Din"),
``عبد الله`` ("Abdullah") — are detected and kept as one ``given`` token so a
query of ``صلاح`` can be recognized as a *prefix* of the compound rather than a
separate forefather.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .normalize import normalize_arabic, normalize_latin
from .script import detect_script

# Tokens that *can* begin a compound Arabic given name. They only merge with the
# next token when that token is a known completer (below) — e.g. صلاح merges with
# الدين ("Salah al-Din") but NOT with a following family name like الأيوبي.
_AR_COMPOUND_HEADS = {
    "عبد",   # Abd (servant of) -> عبد الله, عبد الرحمن
    "صلاح",  # Salah -> صلاح الدين
    "نور",   # Nur -> نور الدين
    "سيف",   # Sayf -> سيف الدين
    "بدر", "شمس", "علاء", "جمال", "حسام", "ضياء", "تقي", "نجم", "زين",
    "فخر", "محي", "شهاب", "ركن", "عز", "كمال", "شرف",
}
# Second halves that complete a compound given name (after normalize_arabic,
# which strips tashkeel and unifies alef/ta-marbuta; ال article is kept).
_AR_COMPLETERS = {
    normalize_arabic(t) for t in (
        "الدين", "الله", "الرحمن", "الرحيم", "الملك", "العزيز", "الكريم",
        "القادر", "الحميد", "الوهاب", "الغني", "الستار", "الإسلام", "الدنيا",
        "الحق", "النبي", "الرسول", "الصمد", "الجليل", "السلام", "المجيد",
    )
}
# Kunya heads (Abu/Umm ...) — always merge with the following token.
_AR_KUNYA_HEADS = {normalize_arabic(t) for t in ("ابو", "أبو", "ام", "أم", "ابن")}
_AR_NASAB = {"ابن", "بن", "بنت", "آل", "ال"}
_AR_ARTICLE_PREFIX = ("ال", "عبدال")

# Latin particles (nobiliary / connective) — low weight, not the surname core.
_LATIN_PARTICLES = {
    "de", "del", "della", "di", "da", "dos", "das", "do",
    "van", "von", "der", "den", "ter", "la", "le", "el", "al",
    "bin", "ibn", "bint", "abu", "abd", "ben", "san", "santa",
    "mac", "mc", "o", "st",
}


@dataclass
class ParsedName:
    raw: str
    script: str
    culture: str
    given: list[str] = field(default_factory=list)      # given / ism (may be compound)
    forefathers: list[str] = field(default_factory=list)  # nasab chain / middles
    family: list[str] = field(default_factory=list)      # surname(s)
    particles: list[str] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)

    def core_tokens(self) -> list[str]:
        """High-signal tokens for matching (given + family, no forefathers)."""
        return [*self.given, *self.family]


def _norm(token: str, arabic: bool) -> str:
    return normalize_arabic(token) if arabic else normalize_latin(token)


def parse(name: str, culture: str | None = None) -> ParsedName:
    """Parse *name*; *culture* auto-detected from script when not given."""
    script = detect_script(name).dominant or "Latin"
    arabic = script == "Arabic"
    if culture is None:
        culture = "Arabic" if arabic else "Western"

    tokens = [t for t in name.replace(".", ". ").split() if t.strip()]
    if arabic:
        return _parse_arabic(name, tokens)
    if culture in ("Spanish", "Portuguese", "Brazilian"):
        return _parse_iberian(name, tokens, culture)
    return _parse_western(name, tokens)


def _parse_arabic(raw: str, tokens: list[str]) -> ParsedName:
    p = ParsedName(raw=raw, script="Arabic", culture="Arabic")
    norm = [normalize_arabic(t) for t in tokens]
    i = 0
    n = len(norm)
    # First token (+ optional completer) is the ism / kunya.
    if i < n:
        head = norm[i]
        nxt = norm[i + 1] if i + 1 < n else None
        if nxt is not None and head in _AR_KUNYA_HEADS:
            p.given.append(f"{head} {nxt}")  # kunya: Abu Bakr, Umm Kulthum
            i += 2
        elif nxt is not None and head in _AR_COMPOUND_HEADS and nxt in _AR_COMPLETERS:
            p.given.append(f"{head} {nxt}")  # صلاح الدين, عبد الله
            i += 2
        else:
            p.given.append(head)
            i += 1
    # Remaining tokens: nasab chain -> forefathers; trailing nisba -> family.
    while i < n:
        tok = norm[i]
        if tok in _AR_NASAB:
            i += 1
            continue
        # A nisba (ends with ي and looks like a relation) or last token = family.
        if i == n - 1:
            p.family.append(tok)
        else:
            p.forefathers.append(tok)
        i += 1
    return p


def _parse_western(raw: str, tokens: list[str]) -> ParsedName:
    p = ParsedName(raw=raw, script="Latin", culture="Western")
    norm = [normalize_latin(t.rstrip(".")) for t in tokens]
    norm = [t for t in norm if t]
    if not norm:
        return p
    if len(norm) == 1:
        p.given.append(norm[0])
        return p
    # Trailing particle+word cluster forms the family (van der Berg, de Souza).
    family: list[str] = [norm[-1]]
    j = len(norm) - 2
    while j >= 1 and norm[j] in _LATIN_PARTICLES:
        p.particles.insert(0, norm[j])
        family.insert(0, norm[j])
        j -= 1
    p.family = family
    p.given.append(norm[0])
    p.forefathers.extend(norm[1 : j + 1])  # middle names
    return p


def _parse_iberian(raw: str, tokens: list[str], culture: str) -> ParsedName:
    p = ParsedName(raw=raw, script="Latin", culture=culture)
    norm = [normalize_latin(t) for t in tokens if normalize_latin(t)]
    if not norm:
        return p
    p.given.append(norm[0])
    rest = norm[1:]
    # Glue particles onto the following word (de la Cruz -> "de la cruz").
    glued: list[str] = []
    buf: list[str] = []
    for tok in rest:
        if tok in _LATIN_PARTICLES:
            buf.append(tok)
            p.particles.append(tok)
        else:
            glued.append(" ".join([*buf, tok]))
            buf = []
    if buf and glued:
        glued[-1] = glued[-1] + " " + " ".join(buf)
    p.family = glued
    return p
