"""Detection layer: is this string a person name, and what origin is it?

Deterministic waterfall (cheapest -> most specific):

1. **Script** (``script.py``)            — Arabic vs Latin vs Hebrew ...
2. **Lexicon membership** (``lexicon``)  — does each token appear in a
   given/surname gazetteer, and how *exclusive* is that set?
3. **Structural cues**                   — particles (de/von/al/ibn), token
   count, capitalization, absence of digits/non-name symbols.

Returns calibrated-ish confidences with an explanation, so a caller can set a
high-precision threshold. The optional ``plugins.origin_ml`` (NameBERT /
name2nat) can be consulted for low-confidence cases without changing this API.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .lexicon import Gazetteers, load
from .normalize import normalize_arabic, normalize_latin
from .parse import _LATIN_PARTICLES, parse
from .script import detect_script

# Particle -> origin hint.
_PARTICLE_ORIGIN = {
    "de": "Iberian/French", "del": "Spanish", "della": "Italian", "di": "Italian",
    "da": "Portuguese", "dos": "Portuguese", "das": "Portuguese",
    "van": "Dutch", "von": "German", "der": "Germanic",
    "le": "French", "la": "Romance",
    "bin": "Arabic", "ibn": "Arabic", "bint": "Arabic", "abu": "Arabic",
    "al": "Arabic", "el": "Arabic",
    "mc": "Gaelic", "mac": "Gaelic", "o": "Gaelic",
}

_NON_NAME = re.compile(r"[0-9@#$%^&*_=+\\/<>|~]")


@dataclass
class Detection:
    text: str
    script: str
    is_person_name: float          # 0..1
    origins: dict[str, float] = field(default_factory=dict)  # origin -> 0..1
    gender: str | None = None
    countries: set[str] = field(default_factory=set)
    reasons: list[str] = field(default_factory=list)

    @property
    def top_origin(self) -> str | None:
        return max(self.origins, key=self.origins.get) if self.origins else None


def detect(text: str, gaz: Gazetteers | None = None) -> Detection:
    gaz = gaz if gaz is not None else load()
    prof = detect_script(text)
    script = prof.dominant or "Unknown"
    arabic = script == "Arabic"
    det = Detection(text=text, script=script, is_person_name=0.0)

    tokens = [t for t in re.split(r"\s+", text.strip()) if t]
    norm = [normalize_arabic(t) if arabic else normalize_latin(t.strip(".")) for t in tokens]
    norm = [t for t in norm if t]

    # ---- origin scoring from lexicon + script + particles ----------------
    origin_score: dict[str, float] = {}
    hits = 0
    for tok in norm:
        in_given = gaz.origins_of(tok, "given")
        in_sur = gaz.origins_of(tok, "surname")
        members = in_given | in_sur
        if members:
            hits += 1
            # exclusive membership (1 origin) is a stronger signal than shared
            weight = 1.0 if len(members) == 1 else 0.5
            for o in members:
                origin_score[o] = origin_score.get(o, 0.0) + weight
        if tok in gaz.gender and det.gender is None:
            det.gender = gaz.gender[tok]
        det.countries |= gaz.country.get(tok, set())

    # script prior
    if arabic:
        origin_score["Arabic"] = origin_score.get("Arabic", 0.0) + 1.5
    elif script == "Hebrew":
        origin_score["Hebrew"] = origin_score.get("Hebrew", 0.0) + 1.5

    # particle cues
    for tok in norm:
        if tok in _PARTICLE_ORIGIN:
            o = _PARTICLE_ORIGIN[tok]
            origin_score[o] = origin_score.get(o, 0.0) + 0.75
            det.reasons.append(f"particle '{tok}' -> {o}")

    total = sum(origin_score.values())
    if total:
        det.origins = {o: round(s / total, 3) for o, s in sorted(
            origin_score.items(), key=lambda kv: -kv[1])}

    # ---- is-this-a-person-name -------------------------------------------
    det.is_person_name = _name_likelihood(text, tokens, norm, hits, det.reasons)
    return det


def _name_likelihood(
    text: str, tokens: list[str], norm: list[str], lexicon_hits: int, reasons: list[str]
) -> float:
    if not norm:
        return 0.0
    score = 0.0
    n = len(norm)

    if _NON_NAME.search(text):
        reasons.append("contains digits/symbols -> not a name")
        return 0.05

    # token count: 1-5 typical for a person; 2-4 strongest
    if 2 <= n <= 4:
        score += 0.35
    elif n == 1:
        score += 0.15
    elif n <= 6:
        score += 0.20
    else:
        score += 0.05
        reasons.append("many tokens -> could be an org/sentence")

    # lexicon coverage
    coverage = lexicon_hits / n
    score += 0.45 * coverage
    if lexicon_hits:
        reasons.append(f"{lexicon_hits}/{n} tokens in name gazetteers")

    # capitalization (Latin only): each non-particle token title-cased
    latin_toks = [t for t in tokens if t[:1].isascii() and t[:1].isalpha()]
    if latin_toks:
        capped = sum(1 for t in latin_toks if t[:1].isupper())
        cap_ratio = capped / len(latin_toks)
        score += 0.15 * cap_ratio
        if cap_ratio == 1.0:
            reasons.append("all tokens capitalized")

    # known particle bridging two name tokens is a positive structural cue
    if any(t in _LATIN_PARTICLES for t in norm) and n >= 2:
        score += 0.05

    return round(min(score, 1.0), 3)
