"""Phonetic keys for fuzzy name comparison (pure stdlib).

- ``soundex`` / ``refined_key`` for Latin/romanized tokens.
- ``arabic_phonetic`` collapses Arabic letters that natives hear as near-
  identical (س/ص/ث, ت/ط, د/ض, ذ/ز/ظ, ه/ح, ك/ق ...) so misspellings and
  dialectal spellings of the same Arabic name share a key.

For production-grade Latin phonetics (Double Metaphone, Beider-Morse) the
optional ``jellyfish``/``abydos`` extras are preferred; these stdlib keys keep
the core dependency-free and good enough for blocking + a similarity signal.
"""
from __future__ import annotations

import functools
import re

# --- Latin Soundex --------------------------------------------------------

_SOUNDEX_MAP = {
    **dict.fromkeys("bfpv", "1"),
    **dict.fromkeys("cgjkqsxz", "2"),
    **dict.fromkeys("dt", "3"),
    "l": "4",
    **dict.fromkeys("mn", "5"),
    "r": "6",
}


@functools.lru_cache(maxsize=8192)
def soundex(token: str) -> str:
    t = re.sub(r"[^a-z]", "", token.lower())
    if not t:
        return ""
    first = t[0]
    encoded = first
    prev = _SOUNDEX_MAP.get(first, "")
    for ch in t[1:]:
        code = _SOUNDEX_MAP.get(ch, "")
        if code and code != prev:
            encoded += code
        if ch not in "hw":
            prev = code
        if len(encoded) >= 4:
            break
    return (encoded + "000")[:4].upper()


# --- Arabic phonetic class key -------------------------------------------

# Each group maps to one representative class char.
_AR_GROUPS = [
    "اوي",        # long vowels / matres lectionis
    "بپ",
    "تطث",        # t-like + thaa
    "دضذزظ",      # d/z emphatics + dhaal
    "سصش",        # s-like + shin
    "حهخ",        # h-like + kha
    "كقگ",        # k/q
    "عءأإئؤ",     # ayn + hamza family
    "غ",
    "ف",
    "ل",
    "من",         # nasals
    "ر",
    "ج",
]
_AR_CLASS = {}
for _i, _grp in enumerate(_AR_GROUPS):
    for _c in _grp:
        _AR_CLASS[_c] = chr(ord("A") + _i)


def jaro(s1: str, s2: str) -> float:
    """Jaro similarity, 0..1."""
    if s1 == s2:
        return 1.0
    l1, l2 = len(s1), len(s2)
    if l1 == 0 or l2 == 0:
        return 0.0
    reach = max(l1, l2) // 2 - 1
    if reach < 0:
        reach = 0
    m1 = [False] * l1
    m2 = [False] * l2
    matches = 0
    for i in range(l1):
        for j in range(max(0, i - reach), min(i + reach + 1, l2)):
            if m2[j] or s1[i] != s2[j]:
                continue
            m1[i] = m2[j] = True
            matches += 1
            break
    if matches == 0:
        return 0.0
    k = trans = 0
    for i in range(l1):
        if not m1[i]:
            continue
        while not m2[k]:
            k += 1
        if s1[i] != s2[k]:
            trans += 1
        k += 1
    trans /= 2
    return (matches / l1 + matches / l2 + (matches - trans) / matches) / 3


def jaro_winkler(s1: str, s2: str, p: float = 0.1, max_prefix: int = 4) -> float:
    """Jaro-Winkler similarity — a widely used name-similarity metric in record
    linkage; included here as a reusable signal. Boosts a shared prefix."""
    j = jaro(s1, s2)
    if j <= 0.7:
        return round(j, 4)
    prefix = 0
    for a, b in zip(s1, s2):
        if a != b or prefix >= max_prefix:
            break
        prefix += 1
    return round(j + prefix * p * (1 - j), 4)


@functools.lru_cache(maxsize=8192)
def arabic_phonetic(token: str) -> str:
    """Collapse an Arabic token to a class string, dropping long vowels."""
    out = []
    prev = None
    for ch in token:
        cls = _AR_CLASS.get(ch)
        if cls is None:
            continue
        if cls == "A":  # drop long-vowel class entirely (skeletonize)
            continue
        if cls != prev:
            out.append(cls)
        prev = cls
    return "".join(out)
