"""Scheme-accurate Arabic->Latin transliteration (Workstream C).

Loads ``namesdb/done/transliteration_schemes.csv`` — a table whose ``Letter``
row lists the Arabic letters as columns and whose other rows are romanization
schemes (BGN_PCGN, UNGEGN, ALA_LC, Buckwalter, DIN31635, Qalam, ...). We build
one ``letter -> latin`` map per scheme and can generate *multiple* romanization
candidates for a name, so cross-script matching isn't hostage to one scheme's
spelling (Salah al-Din / Salah ad-Deen / Saladin all reachable).

Falls back to the stopgap single-char map in ``normalize.transliterate_arabic``
when the CSV is absent, so the core still works on a bare checkout.
"""
from __future__ import annotations

import csv
import functools
from pathlib import Path

from .lexicon import default_namesdb
from .normalize import (
    normalize_arabic,
    transliterate_arabic,
    transliterate_devanagari,
    transliterate_hebrew,
    transliterate_hebrew_hard,
)

# Schemes to use for candidate generation (broad-coverage, common in the wild).
CANDIDATE_SCHEMES = ("BGN_PCGN", "UNGEGN", "ALA_LC", "DIN31635", "Qalam")


def _clean(val: str) -> str:
    """Take the first variant of an entry like 'w/ū' and drop length marks."""
    val = val.split("/")[0].strip()
    # strip combining marks / non-ascii diacritics; keep base latin letters
    import unicodedata
    val = "".join(c for c in unicodedata.normalize("NFKD", val)
                  if not unicodedata.combining(c))
    return "".join(c for c in val if c.isascii()).lower()


@functools.lru_cache(maxsize=2)
def load_schemes(namesdb: str | Path | None = None) -> dict[str, dict[str, str]]:
    """Return ``{scheme_name: {arabic_letter: latin}}`` (cached)."""
    root = Path(namesdb) if namesdb else default_namesdb()
    path = root / "done" / "transliteration_schemes.csv"
    schemes: dict[str, dict[str, str]] = {}
    if not path.exists():
        return schemes
    with path.open(encoding="utf-8", errors="replace", newline="") as fh:
        rows = list(csv.reader(fh))
    letters = None
    for row in rows:
        if not row:
            continue
        label = row[0].strip().strip('"')
        if label == "Letter":
            letters = [c.strip() for c in row[1:]]
            continue
        if letters is None:
            continue
        mapping = {}
        for letter, val in zip(letters, row[1:]):
            la = _clean(val)
            if letter and la:
                mapping[normalize_arabic(letter)] = la
        if mapping:
            schemes[label] = mapping
    return schemes


def transliterate(name: str, scheme: str = "BGN_PCGN") -> str:
    """Romanize *name* with one scheme (falls back to the stopgap map)."""
    schemes = load_schemes()
    table = schemes.get(scheme)
    if not table:
        return transliterate_arabic(name)
    out = []
    for ch in normalize_arabic(name):
        if ch.isspace():
            out.append(" ")
        else:
            out.append(table.get(ch, ""))
    return "".join(out)


def candidates(name: str) -> list[str]:
    """Distinct romanizations of *name* across the candidate schemes + stopgap."""
    seen: list[str] = []
    for scheme in CANDIDATE_SCHEMES:
        cand = transliterate(name, scheme).strip()
        if cand and cand not in seen:
            seen.append(cand)
    stop = transliterate_arabic(name).strip()
    if stop and stop not in seen:
        seen.append(stop)
    return seen or [name]


# --- Chinese (Han -> Mandarin pinyin) -------------------------------------

@functools.lru_cache(maxsize=1)
def load_han_pinyin() -> dict[str, str]:
    """char -> toneless pinyin, from the committed Unihan-derived data file."""
    path = Path(__file__).resolve().parent / "data" / "han_pinyin.tsv"
    table: dict[str, str] = {}
    if not path.exists():
        return table
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or "\t" not in line:
            continue
        ch, py = line.split("\t", 1)
        if ch and py:
            table[ch] = py.strip()
    return table


def transliterate_chinese(name: str) -> str:
    """Concatenate the pinyin of each Han character (no spaces).

    Chinese names have no internal spaces; the caller compares this against the
    space-stripped Latin name (e.g. 习近平 -> 'xijinping' vs 'Xi Jinping').
    """
    table = load_han_pinyin()
    return "".join(table.get(ch, "") for ch in name)


# --- unified dispatch ------------------------------------------------------

def hebrew_candidates(name: str) -> list[str]:
    """Soft + hard Hebrew romanizations (bet=v/b, pe=f/p, shin=sh/s ...)."""
    out = []
    for fn in (transliterate_hebrew, transliterate_hebrew_hard):
        c = fn(name).strip()
        if c and c not in out:
            out.append(c)
    return out or [name]


def romanizations(name: str, script: str) -> list[str]:
    """Latin romanization candidates for *name* in a non-Latin *script*."""
    if script == "Arabic":
        return candidates(name)
    if script == "Hebrew":
        return hebrew_candidates(name)
    if script == "Devanagari":
        return [transliterate_devanagari(name)]
    if script == "Han":
        return [transliterate_chinese(name)]
    return [name]
