"""Infer a name's culture so the parser picks the right structure.

This closes the gap where ``match()`` parsed by script alone and misread
two-surname Iberian names as Western (``Maria de la Cruz`` vs
``María de la Cruz González``).

Coarse and conservative — it only needs to choose a *parse strategy*:
- ``Arabic``  — Arabic script.
- ``Spanish`` — Latin name with a Romance connective particle and >=3 tokens,
  i.e. the multi-surname Iberian/Romance structure (routes to the Iberian
  parser, which keeps each surname separate for asymmetric matching).
- ``Western`` — everything else (the safe default; the Western parser already
  handles trailing nobiliary particles like ``van``/``von``).
"""
from __future__ import annotations

from .normalize import normalize_latin
from .script import detect_script

# Romance connectives that signal multi-surname Iberian/Romance structure.
_ROMANCE_PARTICLES = {"de", "del", "della", "di", "da", "dos", "das", "do", "la", "le"}
# Arabic structural particles when the name is transliterated into Latin.
_ARABIC_LATIN = {"bin", "ibn", "bint", "abu", "abd"}


def infer_culture(name: str, detection=None) -> str:
    if (detect_script(name).dominant or "Latin") == "Arabic":
        return "Arabic"
    toks = normalize_latin(name).split()
    if not toks:
        return "Western"
    low = set(toks)
    if low & _ARABIC_LATIN:
        return "Arabic"  # transliterated Arabic; Western parser handles it fine
    if len(toks) >= 3 and (low & _ROMANCE_PARTICLES):
        return "Spanish"  # -> Iberian parser (Spanish/Portuguese share structure)
    return "Western"
