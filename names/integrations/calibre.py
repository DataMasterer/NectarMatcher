"""Dedup the authors of a Calibre library with namematch — the first consumer.

Reads the ``authors`` table from a Calibre ``metadata.db`` (read-only) and
resolves the author list into entity clusters + a review queue, so the same
author under spelling/initial/transliteration variants collapses to one entity.

Generic and public-safe: the library path and all output are the user's data —
keep them out of version control (write reports under ``eval/_local/``).

Usage:
    PYTHONPATH=. python3 integrations/calibre.py /path/to/metadata.db \
        --out eval/_local/calibre_authors
"""
from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

from namematch import RecordMatch, dedup, detect, match
from namematch.normalize import normalize_arabic
from namematch.script import detect_script

_TOKEN_STOP = {"the", "and", "for", "with", "from", "vol", "volume", "edition",
               "book", "books", "guide", "introduction", "ed", "new"}


def read_authors(db_path: str) -> list[str]:
    """Return the author names from a Calibre metadata.db (read-only)."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT name FROM authors WHERE name IS NOT NULL AND trim(name) != '' "
            "ORDER BY name"
        ).fetchall()
    finally:
        con.close()
    return [r[0] for r in rows]


def _tokens(text: str) -> set[str]:
    """Topic tokens from a title/tag: split, lowercase, drop short/stop/digits."""
    out = set()
    for raw in re.split(r"[^\w؀-ۿ]+", normalize_arabic(text or "")):
        tok = raw.strip().lower()
        if len(tok) >= 3 and not tok.isdigit() and tok not in _TOKEN_STOP:
            out.add(tok)
    return out


def read_author_profiles(db_path: str, max_coauthor_partners: int = 5) -> list[dict]:
    """Per author: {name, script, profile}. The profile is a NAMESPACED token set
    from the author's books: ``t:`` title words, ``g:`` tag words, ``c:``
    co-authors. Namespacing stops a title word from spuriously matching a tag or
    co-author. Co-authors that pair with many different authors (translators/
    editors) are dropped — they aren't discriminative."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        names = [r[0] for r in con.execute(
            "SELECT name FROM authors WHERE name IS NOT NULL AND trim(name)!=''").fetchall()]
        prof: dict[str, set] = {nm: set() for nm in names}
        for name, title in con.execute(
                "SELECT a.name, b.title FROM authors a "
                "JOIN books_authors_link bal ON bal.author=a.id "
                "JOIN books b ON b.id=bal.book"):
            if name in prof and title:
                prof[name] |= {"t:" + t for t in _tokens(title)}
        for name, tag in con.execute(
                "SELECT a.name, t.name FROM authors a "
                "JOIN books_authors_link bal ON bal.author=a.id "
                "JOIN books_tags_link btl ON btl.book=bal.book "
                "JOIN tags t ON t.id=btl.tag"):
            if name in prof and tag:
                prof[name] |= {"g:" + t for t in _tokens(tag)}
        co_rows = con.execute(
            "SELECT a.name, a2.name FROM authors a "
            "JOIN books_authors_link bal ON bal.author=a.id "
            "JOIN books_authors_link bal2 ON bal2.book=bal.book AND bal2.author<>a.id "
            "JOIN authors a2 ON a2.id=bal2.author").fetchall()
        partners: dict[str, set] = {}
        for name, co in co_rows:
            partners.setdefault(co, set()).add(name)
        for name, co in co_rows:
            if name in prof and len(partners.get(co, ())) <= max_coauthor_partners:
                prof[name].add("c:" + co.strip().lower())
    finally:
        con.close()
    return [{"name": nm, "script": detect_script(nm).dominant or "?", "profile": prof[nm]}
            for nm in names]


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if (a and b) else 0.0


# --- author-field classification: person vs title vs junk ------------------
# (audit-driven: fixes for the Arabic surname،firstname format, the pipe
#  separator, the eponymous-title trap, and the org-anchor requirement;
#  round-2 residual fixes: input normalization, `;`/`,` co-author rescue,
#  structural-boilerplate junk, GLiNER person/org post-filters, genre-author
#  gazetteer, weak org anchors, pipe corruption)

# `|` and `;` are NOT junk here — co-author/catalog separators (handled below).
_JUNK_RE = re.compile(r"[=<>{}\\]|^\s*[#$/]|^\s*\d")
# bidi/zero-width controls: U+200B-F, U+202A-E, U+2066-9, U+061C, U+FEFF
_BIDI = re.compile("[​-‏‪-‮⁦-⁩؜﻿]")
_AR = r"؀-ۿ"
_TITLE_WORDS = set(
    "guide course introduction handbook manual encyclopedia dictionary system "
    "systems mechanics edition volume dummies mystery tales story stories novel "
    "programming design theory analysis methods method practice solutions reference "
    "lectures notes essentials techniques fundamentals cookbook tutorial overview "
    "survey approach principles chapter appendix slides applications".split())
_ORG_ANCHOR = re.compile(
    r"\b(inc|llc|ltd|co|corp|company|association|institute|committee|university|"
    r"academy|press|systems|group|agency|dept|department|team|"
    r"labs?|technologies|technology|publishers?|books)\b|\.com|"
    r"مكتبة|مجمع|جامعة|شركة|مؤسسة|\bدار\b", re.I)
# weak org anchors: also common in book titles ('Second Foundation'), so they
# need context (a non-generic word before them) to count as an org.
_ORG_WEAK = re.compile(r"\b(foundation|society)\b", re.I)
_GENERIC_MODIFIERS = {"the", "a", "an", "first", "second", "third", "fourth",
                      "fifth", "new", "old", "last", "final", "dark", "secret",
                      "hidden", "dead", "lost"}
_PUBLISHERS = {"wiley", "springer", "elsevier", "packt", "o'reilly", "oreilly",
               "apress", "wrox", "sybex", "routledge", "macmillan", "bloomsbury",
               "harpercollins", "penguin", "pearson", "cengage", "mcgraw-hill",
               "mcgrawhill", "wesley", "heinemann", "butterworth"}
# nobiliary/conjunction particles that don't count against a segment's length
_PARTICLES = {"von", "van", "de", "der", "den", "des", "du", "la", "le", "und",
              "and", "bin", "ibn", "abu", "abd", "el", "al", "del", "dela",
              "ten", "ter", "y", "e", "da", "dos", "di"}

_ARCHIVE_SUF = re.compile(r"\.(part|r|z)\d+$|\s*\(single pages\)$", re.I)
_TRAIL_ROLE = re.compile(
    r"[;,]?\s*\b(translated|edited(\s+by)?|compiled|illustrated|ed\.|trans\.)\s*$",
    re.I)
_LEAD_ROLE = re.compile(r"^(?:by\s+|dr\.?\s+|prof\.?\s+|د\.\s*)+", re.I)


def _clean(s: str) -> str:
    """Shared input normalization: strip bidi/zero-width controls, archive
    suffixes (.part1/.r03), '(single pages)', trailing role words
    (Translated/Edited/...), and leading By/Dr./Prof./د. honorifics."""
    s = _BIDI.sub("", s or "").strip().strip('"\'')
    prev = None
    while s != prev:
        prev = s
        s = _ARCHIVE_SUF.sub("", s)
        s = _TRAIL_ROLE.sub("", s)
        s = _LEAD_ROLE.sub("", s)
        # trailing authority years need a separator: `عقاد، عباس،, 18891964`
        s = re.sub(r"[،,;]\s*\d{4,8}(\s*-\s*\d{1,4})?-?\s*$", "", s)
        # strip dangling separators (keep trailing hyphens: truncation signal)
        s = s.strip().strip(",;،| ")
    return s


def _norm_title(s: str) -> str:
    s = normalize_arabic(s or "").lower()
    s = re.sub(r"\(.*?\)", "", s)
    return re.sub(r"[^a-z0-9؀-ۿ]+", "", s)


def _arabic_inverted_name(s: str) -> bool:
    """Catalog `surname، firstname` (Arabic comma) or `surname. firstname` form —
    unambiguously a person; GLiNER-multi mis-reads it as junk/title/org."""
    if not re.search(f"[{_AR}]", s):
        return False
    # the given part may carry initials with periods: `توملين، أ. و. ف`
    return bool(re.fullmatch(rf"[{_AR}][{_AR}\s]*[،,]\s*[{_AR}][{_AR}\s.]*", s)
                or re.fullmatch(rf"[{_AR}]+\.\s*[{_AR}][{_AR}\s]*", s))


def _namey_segment(p: str) -> str | None:
    """Judge one co-author segment: 'multi' (multi-token name), 'single'
    (lone token — needs corroboration from the caller), or None (not a name).
    Nobiliary/conjunction particles don't count against segment length."""
    if re.search(r"[()\[\]{}=<>;|\\/]|\d", p):
        return None
    toks = p.split()
    if any(t.lower().strip(".") in _TITLE_WORDS for t in toks):
        return None
    core = [t for t in toks if t.lower().strip(".") not in _PARTICLES]
    if not core or len(core) > 4:
        return None
    if len(toks) == 1:
        if re.fullmatch(r"[A-Za-z]\.?", toks[0]):   # bare initial
            return None
        return "single"
    return "multi"


# year / honorific-suffix segments that don't count as (or against) co-authors
_SUFFIX_SEG = {"jr", "sr", "ii", "iii", "iv", "v", "md", "phd", "dphil", "esq",
               "ed", "eds", "editor", "editors", "etal", "trans", "translator",
               "dr", "prof"}


def _author_separated(s: str) -> str | None:
    """Judge a `|`/`&`/` - `-separated string. Returns:
    'high'  — a co-author / authority-control form with name-lexicon evidence
              (`Grisham| John`, `Gates| David| 1947-`, `Johnson| Spencer| M.D.`,
              a long all-multi-token co-author list, alternating
              surname|given pairs);
    'soft'  — every segment is name-shaped but nothing is lexicon-backed
              (`Etoh| Minoru.`) — route to review / the entity model;
    None    — a library list / affiliation / keyword string
              (`Struts| Tapestry| ...`, segments with digits/title-words)."""
    if not re.search(r"[|&]|\s-\s", s):
        return None
    raw = [p.strip().strip(".") for p in re.split(r"\s*[|&]\s*|\s+-\s+", s) if p.strip()]
    if len(raw) < 2:
        return None
    segs = [p for p in raw                          # drop year/suffix/lone-initial
            if not re.fullmatch(r"\d{3,4}(\s*-\s*\d{1,4})?-?", p)
            and re.sub(r"[.\s]+", "", p.lower()) not in _SUFFIX_SEG
            and not re.fullmatch(r"[A-Za-z]\.?", p)]
    if not segs or len(segs) > 8:
        return None
    kinds_all = [_namey_segment(p) for p in segs]
    if None in kinds_all:
        return None
    # all-lone-token lists judged BEFORE de-duping — alternating surname|given
    # sort forms repeat the surname (`Strawbridge| Dick.| Strawbridge| James.`)
    if len(segs) >= 3 and all(k == "single" for k in kinds_all):
        if len(segs) <= 4 and all(_lexicon_name(p) for p in segs):
            return "high"                           # `Ivan| Peter| Jan`
        if len(segs) % 2 == 0:
            pairs = [f"{segs[i]} {segs[i + 1]}" for i in range(0, len(segs), 2)]
            hits = sum(bool(_lexicon_name(q)) for q in pairs)
            if hits == len(pairs):
                return "high"
            if hits * 2 >= len(pairs):
                return "soft"                       # partial evidence -> review
        return None
    parts, seen = [], set()
    for p in segs:                                  # de-dupe repeated segments
        if p.lower() not in seen:
            seen.add(p.lower())
            parts.append(p)
    kinds = [_namey_segment(p) for p in parts]
    singles = [p for p, k in zip(parts, kinds) if k == "single"]
    if len(parts) == 1:                             # collapsed to one real name
        p = parts[0]
        if _lexicon_name(p):                        # `Erdos| P.`, `A. Borovik| A. Borovik`
            return "high"
        if kinds[0] == "multi" and detect(p).is_person_name >= 0.5:
            return "high"
        return "soft" if len(p) >= 4 else None
    if len(singles) == len(parts):                  # lone tokens: surname|given form
        if len(parts) == 2:
            if all(_lexicon_name(p) for p in singles):
                return "high"
            return "soft" if all(len(p) >= 3 for p in singles) else None
        return None
    if len(parts) > 4 and singles:
        return None                                 # long mixed lone-token list = keywords
    return "high" if any(_lexicon_name(p) for p in parts) else "soft"


# small public gazetteer of genre (SF/fantasy/chess) authors the shared name
# lexicon misses — used to veto the eponymous-title trap and gate rescues.
_GENRE_AUTHORS = {"cassandra clare", "c.j. cherryh", "cj cherryh", "c. j. cherryh",
                  "piers anthony", "valeri beim", "robin hobb"}
_GENRE_SURNAMES = {"cherryh", "beim", "pratchett", "gaiman", "zelazny", "bujold",
                   "lackey", "hobb", "nimzowitsch", "tartakower", "capablanca",
                   "alekhine", "botvinnik", "euwe"}
_INITIALS_NAME = re.compile(r"(?:[A-Z]\.\s*){1,3}[A-Z][A-Za-z'’-]+")


def _genre_author(s: str) -> bool:
    low = re.sub(r"\s+", " ", s.lower()).strip(" .")
    if low in _GENRE_AUTHORS or low in _GENRE_SURNAMES:
        return True
    toks = low.split()
    return bool(toks) and len(toks) <= 4 and toks[-1].strip(".,") in _GENRE_SURNAMES


def _lexicon_name(p: str) -> bool:
    """Shared-lexicon or genre-gazetteer evidence that `p` is a name."""
    return bool(detect(p).origins) or _genre_author(p)


def _initials_form(s: str) -> bool:
    """Initials+surname shapes that are structurally person names:
    `C.J. Cherryh`, `Shafarevich I.R`, `S.Sivalingam` (all-caps 'surnames'
    like `J. ECONOMETRICS` excluded)."""
    toks = s.split()
    last = toks[-1].replace(".", "") if toks else ""
    if len(last) > 2 and last.isupper():
        return False
    return bool(_INITIALS_NAME.fullmatch(s)
                or re.fullmatch(r"[A-Z][\w'’-]+[,\s]+(?:[A-Z]\.?\s*){1,3}", s)
                or re.fullmatch(r"[A-Z]\.[A-Z][a-z][\w'’-]*", s))


def _gliner_person_override(s: str) -> bool:
    """Person forms the entity model reliably mislabels as junk/title, where
    deterministic evidence should win: gazetteer-backed Arabic-script names,
    Latin initials shapes, and transliterated Arabic names (ibn/abu/al-)."""
    if re.search(f"[{_AR}]", s):
        d = detect(s)
        # nasab chains (بن/ابن) score low on length but are unambiguous persons
        return bool(d.origins) and (d.is_person_name >= 0.5
                                    or bool(re.search(r"\b(بن|ابن|أبو|ابو)\b", s)))
    if _initials_form(s):
        return True
    if re.search(r"\b(ibn|bin|abu|al-\w)", s, re.I):
        d = detect(s)
        return bool(d.origins) and d.is_person_name >= 0.5
    if _author_separated(s) == "soft":
        # separated soft form with any lexicon-backed segment (`Pelonero|
        # Catherine`) — the model junks these inverted forms too often
        parts = [p.strip().strip(".") for p in re.split(r"\s*[|&]\s*|\s+-\s+", s)
                 if p.strip()]
        return any(_lexicon_name(p) for p in parts)
    return False


def _person_shaped(s: str) -> bool:
    """Strong person signal used to veto the eponymous-title trap: Arabic-
    inverted, a genre-gazetteer author, an initials+surname pattern
    (`C.J. Cherryh`), or 2-4 tokens (no title-word) with a real name-lexicon
    hit. Capitalization alone is NOT enough — it can't tell 'Emanuel Lasker'
    from 'Club Dead'."""
    if _arabic_inverted_name(s):
        return True
    if _genre_author(s):
        return True
    if _ORG_ANCHOR.search(s) or _ORG_WEAK.search(s):
        return False
    if _INITIALS_NAME.fullmatch(s):
        return True
    toks = s.split()
    if not (2 <= len(toks) <= 4) or (set(t.lower() for t in toks) & _TITLE_WORDS):
        return False
    return bool(detect(s).origins)


# structural/boilerplate strings in the author column: chapter/volume rows,
# ISBNs, document codes, and bare generic section words. Junk, never a title.
_STRUCTURAL_RE = re.compile(
    r"^chap[-\s]|^chapter\s*\d|^volume\s+\d+$|^vols?\.?\s+\d+$|^isbn[\s:]*\d|"
    r"^appendices$|^appendix\b|^study\s+guide$|^poem$|^applications$", re.I)
_DOC_CODE = re.compile(r"^[A-Z]{2,}-[A-Z]{2,}-\d+")
_GENERIC_SINGLE = {"introduction", "contents", "index", "preface", "foreword",
                   "bibliography", "glossary", "notes", "references", "untitled",
                   "misc", "various", "appendix", "appendices", "poem",
                   "applications", "toc", "cover", "frontmatter", "backmatter"}


def _structural_junk(s: str) -> bool:
    if _STRUCTURAL_RE.match(s) or _DOC_CODE.match(s):
        return True
    toks = s.split()
    return len(toks) == 1 and toks[0].lower().strip(".,") in _GENERIC_SINGLE


def _coauthor_rescue(s: str) -> bool:
    """`;`/`,`-separated co-author list (`Stephen King; Peter Straub`) →
    person. Gated: every segment must be name-shaped (a `title; subtitle`
    string fails — subtitles carry title-words), lone tokens must be
    lexicon-backed, and at least one segment needs lexicon evidence."""
    if not re.search(r"[;,]", s):
        return False
    parts, seen = [], set()
    for p in (q.strip(" .") for q in re.split(r"\s*[;,]\s*", s)):
        if p and p.lower() not in seen:
            seen.add(p.lower())
            parts.append(p)
    if not (2 <= len(parts) <= 4):
        return False
    got_lexicon = False
    for p in parts:
        kind = _namey_segment(p)
        if kind is None:
            return False
        if kind == "single" and not _lexicon_name(p):
            return False
        if _lexicon_name(p) or _person_shaped(p):
            got_lexicon = True
    return got_lexicon


# role/placeholder words that GLiNER mislabels as persons
_ROLE_STOP = {"owner", "admin", "administrator", "administrador", "editor",
              "editors", "author", "authors", "anonymous", "unknown", "various",
              "translator", "compiler", "publisher", "staff", "team", "user",
              "guest", "webmaster", "مجهول"}
_ORG_HINT = re.compile(
    r"\b(editorial|press|publishing|publishers?|magazine|journal)\b|"
    r"إدارة|\bدار\b|مطبعة|مؤسسة", re.I)


def refine_person(s: str) -> str:
    """Post-filter a GLiNER 'person' call: bare role/placeholder words are
    junk, editorial/press collectives are orgs, visibly truncated strings are
    junk; everything else stays person."""
    s = _clean(s)
    if s.endswith(("-", "–")) or s.count("(") > s.count(")"):
        return "junk"                               # truncated mid-string
    toks = re.sub(r"[^\w\s'؀-ۿ-]", " ", s.lower()).split()
    if toks and all(t in _ROLE_STOP for t in toks):
        return "junk"
    if _ORG_HINT.search(s) or (len(toks) > 1 and {"editor", "editors"} & set(toks)):
        return "org"
    return "person"


def refine_org(s: str, titles: frozenset | set = frozenset()) -> str:
    """Validate a GLiNER 'organization' call. Real org needs an anchor token —
    a strong one, a publisher name, or a weak one (Foundation/Society) with a
    non-generic word before it ('Second Foundation' is a title). A person
    glued to an affiliation ('Wenbo Mao Hewlett-Packard Company') is a person;
    otherwise persons-first, or title/junk if digits/title-words."""
    s = _clean(s)
    low = s.lower()
    toks = [t.strip(".,&") for t in low.split()]
    if re.fullmatch(r"\w{0,2}\.?\s?university", low):
        return "junk"                               # truncated '<X> University'
    if _norm_title(s) in titles:
        return "title"
    if any(t in _PUBLISHERS for t in toks):
        return "org"
    if _ORG_ANCHOR.search(s):
        if re.search(r"\((19|20)\d\d\)", s):
            return "title"                          # '... of Computing Systems (2004)'
        stoks = s.split()
        if len(stoks) >= 4 and detect(" ".join(stoks[:2])).origins:
            return "person"                         # '<Name> <Company>' glue
        return "org"
    w = _ORG_WEAK.search(low)
    if w:
        before = low[:w.start()].split()
        prev = before[-1] if before else ""
        if prev and prev not in _GENERIC_MODIFIERS:
            return "org"                            # 'American Chess Foundation'
        if re.fullmatch(r"(?:the|a|an)?\s*(?:foundation|society)", low):
            return "junk"                           # 'The Society'
        return "title"                              # 'Second Foundation'
    if re.search(r"\d", s) or (set(toks) & _TITLE_WORDS):
        return "title"
    return "person"


def read_titles(db_path: str) -> set[str]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        ts = {_norm_title(r[0]) for r in con.execute(
            "SELECT title FROM books WHERE title IS NOT NULL") if r[0]}
    finally:
        con.close()
    return ts - {""}


def classify_author(name: str, titles: set[str]) -> tuple[str, str]:
    """Classify an author-field entry. Returns (category, confidence).

    Categories: 'person', 'title' (book title misfiled as an author), 'junk'
    (code/noise), 'review' (name-like but ambiguous). High-confidence rules run
    first (Arabic inverted names, co-author strings, code, book-title match)."""
    s = _clean(name)
    if not s:
        return "junk", "high"
    # structural boilerplate (Chap-01, ISBN..., doc codes) is junk, never a title.
    if _structural_junk(s):
        return "junk", "high"
    # catalog Arabic names and co-author/authority strings are persons.
    sep = _author_separated(s)
    if _arabic_inverted_name(s) or sep == "high":
        return "person", "high"
    if sep == "soft":
        return "review", "low"      # name-shaped list; the entity model decides
    # a raw `|` that survived _author_separated is field-merge corruption.
    if "|" in s:
        return "junk", "high"
    if _JUNK_RE.search(s):
        return "junk", "high"
    if _initials_form(s):
        return "person", "med"
    # `(With <Name>)` credit and `Surname YYYY` citation forms are persons.
    m = re.fullmatch(r"\(?\s*with\s+(.+?)\s*\)?", s, flags=re.I)
    if m and (detect(m.group(1)).origins or _person_shaped(m.group(1))):
        return "person", "med"
    m = re.fullmatch(r"([^\d,;|]+?),?\s+(?:1[5-9]|20)\d{2}[a-z]?", s)
    if m and (detect(m.group(1)).origins or _person_shaped(m.group(1))):
        return "person", "med"
    # camelcase-glued name (`ValeriBeim`) that splits into a known name.
    m = re.fullmatch(r"([A-Z][a-z]{2,})([A-Z][a-z]{2,})", s)
    if m:
        split = f"{m.group(1)} {m.group(2)}"
        if split.lower() in _GENRE_AUTHORS or detect(split).origins:
            return "person", "med"
    d = detect(s)
    has_title_word = bool({t for t in re.sub(r"[^a-z ]", " ", s.lower()).split()} & _TITLE_WORDS)
    if _norm_title(s) in titles:
        # don't let an eponymous book title scrub a real person — but a comma'd
        # exact title match (`Love, Rosie`) is title-first, not inverted-name.
        veto = _person_shaped(s) and (not re.search(r"[,;]", s)
                                      or _arabic_inverted_name(s))
        return ("person", "med") if veto else ("title", "high")
    # `;`/`,` co-author lists (after the title-match check: `Love, Rosie` is a title).
    if _coauthor_rescue(s):
        return "person", "high"
    if has_title_word and not d.origins:
        return "title", "low"
    if d.origins and d.is_person_name >= 0.5 and not has_title_word:
        return "person", "med"
    if d.is_person_name < 0.3:
        return "junk", "low"
    return "review", "low"


def read_person_filter(classes_tsv: str) -> set[str]:
    """Names classified 'person' in a --classify output TSV
    (category<TAB>confidence<TAB>name) — the dedup input filter."""
    keep = set()
    with open(classes_tsv, encoding="utf-8") as fh:
        next(fh, None)                               # header
        for line in fh:
            parts = line.rstrip("\n").split("\t", 2)
            if len(parts) == 3 and parts[0] == "person":
                keep.add(parts[2])
    return keep


def make_profile_compare(min_profile: int = 8, veto_overlap: float = 0.05):
    """A comparator: name match, but demote a same-script auto-merge to *review*
    when both authors have **substantial** book profiles that barely overlap
    (their books are about entirely different topics -> probably different
    people). Disjointness is only evidence of difference when each profile is
    big enough (>= min_profile tokens); a sparse profile (an author with few/
    badly-titled books, e.g. 'A. Conan Doyle') is just missing data, so it is NOT
    vetoed. Cross-script pairs are skipped — their titles are in different scripts
    by nature, so disjointness there is expected, not evidence."""
    def compare(a: dict, b: dict) -> RecordMatch:
        r = match(a["name"], b["name"])
        pa, pb = a["profile"], b["profile"]
        if (r.bucket == "match" and a["script"] == b["script"]
                and len(pa) >= min_profile and len(pb) >= min_profile):
            ov = _jaccard(pa, pb)
            if ov < veto_overlap:
                return RecordMatch(score=min(r.score, 0.84), bucket="review",
                                   signals={"name": r.score, "profile_overlap": round(ov, 3)},
                                   reasons=[f"book profiles disagree (overlap {ov:.2f}) -> review"])
        return RecordMatch(score=r.score, bucket=r.bucket, signals={"name": r.score})
    return compare


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Dedup Calibre authors with namematch")
    ap.add_argument("db", help="path to Calibre metadata.db")
    ap.add_argument("--max-block", dest="max_block", type=int, default=400)
    ap.add_argument("--min-name-score", dest="min_name", type=float, default=0.3,
                    help="drop entries whose is_person_name score is below this "
                         "(the Calibre author field holds non-author junk); 0 disables")
    ap.add_argument("--classify", action="store_true",
                    help="classify each author-field entry as person/title/junk "
                         "(report + <out>_classes.tsv) instead of deduping")
    ap.add_argument("--gliner", action="store_true",
                    help="with --classify: refine non-high-confidence entries with the "
                         "GLiNER entity-type plugin (opt-in; generalizes to Arabic/unseen)")
    ap.add_argument("--books", action="store_true",
                    help="use the author->books profile (title/tag topic overlap) as a "
                         "second signal to veto coincidental same-script name collisions")
    ap.add_argument("--classes", default="",
                    help="a _classes.tsv from --classify: restrict dedup to entries "
                         "classified 'person' (replaces the --min-name-score filter)")
    ap.add_argument("--out", default="", help="output prefix (writes <out>_clusters.tsv + _review.tsv)")
    args = ap.parse_args(argv)

    if args.classify:
        from collections import Counter
        titles = read_titles(args.db)
        rows = [(a, *classify_author(a, titles)) for a in read_authors(args.db)]
        if args.gliner:
            # layered: trust deterministic HIGH (junk-code, book-title matches);
            # refine everything else with the structure-based model.
            from namematch.plugins import entity_type
            _map = {"person": "person", "title": "title", "organization": "org", "none": "junk"}

            def _refine(a):
                s = _clean(a)
                # `|` never helps the model — present separated forms as commas
                cat = _map[entity_type.classify(re.sub(r"\s*\|\s*", ", ", s))]
                if cat == "org":
                    return refine_org(s, titles)     # validate org anchors
                if cat == "person":
                    return refine_person(s)          # role/collective/truncation
                if cat in ("junk", "title") and _gliner_person_override(s):
                    return "person"                  # person forms the model misses
                if cat == "junk" and _author_separated(s) == "soft":
                    return "review"                  # name-shaped list neither tier
                                                     # could verify -> manual triage
                if cat == "title":
                    if _structural_junk(s):
                        return "junk"                # boilerplate is not a title
                    if _genre_author(s):
                        return "person"              # known genre author, not a title
                return cat

            rows = [(a, c, conf) if conf == "high" else (a, _refine(a), "gliner")
                    for a, c, conf in rows]
        by_cat = Counter(c for _, c, _ in rows)
        by_cc = Counter((c, conf) for _, c, conf in rows)
        print(f"classified {len(rows)} author-field entries:")
        for c, _n in by_cat.most_common():
            confs = {cf: n for (cc, cf), n in by_cc.items() if cc == c}
            print(f"  {c:8} {by_cat[c]:6}  by confidence: {confs}")
        if args.out:
            p = Path(f"{args.out}_classes.tsv")
            with p.open("w", encoding="utf-8") as fh:
                fh.write("category\tconfidence\tname\n")
                for a, c, conf in rows:
                    fh.write(f"{c}\t{conf}\t{a}\n")
            print(f"wrote {p}")
        return 0

    persons = read_person_filter(args.classes) if args.classes else None

    def _keep(all_names, key=lambda x: x):
        # the classifier filter supersedes the cruder is_person_name gate
        if persons is not None:
            kept = [x for x in all_names if key(x) in persons]
            print(f"classes filter: kept {len(kept)} 'person' entries "
                  f"of {len(all_names)} (dropped {len(all_names) - len(kept)})")
            return kept
        if args.min_name > 0:
            kept = [x for x in all_names if detect(key(x)).is_person_name >= args.min_name]
            print(f"filtered {len(all_names) - len(kept)} non-name entries "
                  f"(is_person_name < {args.min_name}); {len(kept)} authors remain")
            return kept
        return all_names

    if args.books:
        records = _keep(read_author_profiles(args.db), key=lambda r: r["name"])
        names = [r["name"] for r in records]
        res = dedup(records, max_block=args.max_block,
                    key=lambda r: r["name"], compare=make_profile_compare())
    else:
        names = _keep(read_authors(args.db))
        res = dedup(names, max_block=args.max_block)

    merged_clusters = [c for c in res.clusters if len(c) > 1]
    allpairs = res.n_input * (res.n_input - 1) // 2
    print(f"authors: {res.n_input}")
    print(f"blocking: {res.n_candidates} candidate pairs vs {allpairs} all-pairs "
          f"({100 * (1 - res.n_candidates / allpairs):.1f}% reduction); "
          f"{res.n_comparisons} comparisons")
    print(f"entities: {len(res.clusters)} ({res.n_duplicates_removed} duplicates merged "
          f"across {len(merged_clusters)} multi-author clusters)")
    print(f"review queue: {len(res.review_pairs)} uncertain pairs")

    if args.out:
        cf = Path(f"{args.out}_clusters.tsv")
        with cf.open("w", encoding="utf-8") as fh:
            fh.write("cluster_id\tcanonical\tmember\n")
            for cid, members in enumerate(res.clusters):
                if len(members) > 1:
                    for i in members:
                        fh.write(f"{cid}\t{res.canonical[cid]}\t{names[i]}\n")
        rf = Path(f"{args.out}_review.tsv")
        with rf.open("w", encoding="utf-8") as fh:
            fh.write("score\tname_a\tname_b\n")
            for i, j, score in res.review_pairs:
                fh.write(f"{score:.3f}\t{names[i]}\t{names[j]}\n")
        print(f"wrote {cf}\nwrote {rf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
