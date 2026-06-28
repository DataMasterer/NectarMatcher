"""The matcher: score whether two names refer to the same person.

Design mirrors the field-tested nectarmatcher pattern (weighted bag of soft
signals -> confidence -> high / review / no-match bucket); none of the signals
is individually required.

Name-specific intelligence added on top:

- **Cross-script bridge** — if the two names are in different scripts, the
  Arabic side is transliterated then both are romanize-folded so
  ``صلاح الدين`` aligns with ``Salah al-Din`` / ``Saladin``.
- **Role-aware alignment** — given/family tokens are high weight; Arabic
  forefathers (nasab chain) and Western middle names are *optional* low weight,
  per the cultural rules.
- **Asymmetric containment** — a shorter query that fully aligns to a subset of
  the longer name's roles is NOT penalized for the missing tokens. This is what
  makes ``صلاح`` match ``صلاح الدين`` (compound-given prefix) and a query of
  given+family match a fuller record with extra forefathers/middles.
- **Initials** — ``G.`` aligns to ``George``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .culture import infer_culture
from .normalize import (
    consonant_skeleton,
    normalize_arabic,
    normalize_latin,
    romanize_fold,
    transliterate_arabic,
)
from .parse import ParsedName, parse
from .phonetics import arabic_phonetic, soundex
from .script import detect_script
from .translit import BRIDGEABLE_SCRIPTS, SPACELESS_SCRIPTS, romanizations

HIGH = 0.85
REVIEW = 0.62


@dataclass
class MatchResult:
    score: float
    bucket: str                    # "match" | "review" | "no-match"
    a: str
    b: str
    signals: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.bucket == "match"


# --- token-level similarity ----------------------------------------------

def _is_initial(tok: str) -> bool:
    return len(tok) == 1


def token_sim(a: str, b: str, arabic: bool, bridged: str = "") -> float:
    """Similarity of two already-normalized tokens, 0..1.

    *bridged* is the source script being romanized ("" when same-script), so the
    skeleton policy can be tuned per script. The Arabic-aware consonant skeleton
    is applied for all bridged scripts: it is conceptually a Semitic device, but
    on the ParaNames benchmarks it is net-positive for Han/Devanagari too (the
    recall it buys outweighs the occasional vowel-collision).
    """
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # initials
    if _is_initial(a) or _is_initial(b):
        return 0.80 if a[0] == b[0] else 0.0
    # compound-given prefix containment (صلاح vs "صلاح الدين")
    aw, bw = a.split(), b.split()
    if len(aw) != len(bw):
        short, long = (aw, bw) if len(aw) < len(bw) else (bw, aw)
        if short and short == long[: len(short)]:
            return 0.90
    if arabic:
        ka = arabic_phonetic(a)
        if ka and ka == arabic_phonetic(b):
            return 0.85
    else:
        fa, fb = romanize_fold(a), romanize_fold(b)
        if fa and fa == fb:
            return 0.92
        if bridged:
            sa, sb = consonant_skeleton(a), consonant_skeleton(b)
            if len(sa) >= 2 and sa == sb:
                return 0.93
            if len(sa) >= 3 and len(sb) >= 3 and SequenceMatcher(None, sa, sb).ratio() >= 0.82:
                return 0.86
        sx = soundex(a)
        if sx and sx == soundex(b):
            return 0.84
    ratio = SequenceMatcher(None, a, b).ratio()
    # Same-script suffix trap: surnames sharing only a tail (Einstein/Bronstein,
    # King/Hawking) over-score on raw edit ratio. A real spelling variant keeps
    # the initial (and C/K-type shifts are already handled by the fold above), so
    # when same-script initials differ, demand a strong ratio.
    if not bridged and a[:1] != b[:1] and ratio < 0.80:
        return 0.0
    return round(ratio, 3) if ratio >= 0.5 else 0.0


# --- bag alignment (greedy best-match, asymmetric) ------------------------

def _align(short: list[str], long: list[str], arabic: bool, bridged: str = "") -> tuple[float, int]:
    """Greedily match each token of *short* to its best in *long*.

    Returns (mean similarity over short tokens, count of strong matches).
    Asymmetric: extra tokens in *long* are not penalized.
    """
    if not short:
        return 0.0, 0
    used: set[int] = set()
    total = 0.0
    strong = 0
    for s in short:
        best = 0.0
        best_j = -1
        for j, l in enumerate(long):
            if j in used:
                continue
            sim = token_sim(s, l, arabic, bridged)
            if sim > best:
                best, best_j = sim, j
        if best_j >= 0 and best > 0:
            used.add(best_j)
        total += best
        if best >= 0.8:
            strong += 1
    return total / len(short), strong


def _prepare(name: str) -> tuple[ParsedName, bool, str]:
    script = detect_script(name).dominant or "Latin"
    # Workstream B: infer culture so two-surname Iberian names parse correctly.
    return parse(name, culture=infer_culture(name)), script == "Arabic", script


def _to_common(tokens: list[str], arabic: bool, cross: bool) -> list[str]:
    """Normalize tokens; if bridging scripts, romanize-fold to a common space."""
    out: list[str] = []
    for t in tokens:
        if cross:
            base = transliterate_arabic(t) if arabic else normalize_latin(t)
            out.append(romanize_fold(base))
        else:
            out.append(normalize_arabic(t) if arabic else normalize_latin(t))
    return [t for t in out if t]


def _score(a: str, b: str, bridged: str = "") -> MatchResult:
    pa, a_ar, a_script = _prepare(a)
    pb, b_ar, b_script = _prepare(b)
    cross = a_script != b_script
    arabic = (a_ar or b_ar) and not cross  # Arabic-phonetic only same-script

    res = MatchResult(score=0.0, bucket="no-match", a=a, b=b)

    given_a = _to_common(pa.given, a_ar, cross)
    given_b = _to_common(pb.given, b_ar, cross)
    fam_a = _to_common(pa.family, a_ar, cross)
    fam_b = _to_common(pb.family, b_ar, cross)
    fore_a = _to_common(pa.forefathers, a_ar, cross)
    fore_b = _to_common(pb.forefathers, b_ar, cross)

    # Align shorter onto longer for each role (asymmetric containment).
    def role(xa: list[str], xb: list[str]) -> float:
        short, long = (xa, xb) if len(xa) <= len(xb) else (xb, xa)
        sim, _ = _align(short, long, arabic, bridged)
        return sim

    g = role(given_a, given_b) if (given_a and given_b) else 0.0
    f = role(fam_a, fam_b) if (fam_a and fam_b) else None
    fo = role(fore_a, fore_b) if (fore_a and fore_b) else None

    # Weights: given + family carry the decision; forefathers/middles optional.
    weights: list[tuple[str, float, float]] = []
    weights.append(("given", g, 0.55))
    if f is not None:
        weights.append(("family", f, 0.40))
    else:
        # No family on one side: lean on given + any forefather overlap.
        if fo is not None:
            weights.append(("forefather", fo, 0.25))
    if f is not None and fo is not None:
        weights.append(("forefather", fo, 0.10))

    wsum = sum(w for _, _, w in weights)
    score = sum(val * w for _, val, w in weights) / wsum if wsum else 0.0

    for label, val, w in weights:
        res.signals[label] = round(val, 3)
        res.reasons.append(f"{label} sim={val:.2f} (w={w})")
    if cross:
        res.reasons.append(f"cross-script bridge {a_script}<->{b_script} via transliteration")

    # Lone-token handling. When one side is a single token (a bare given or
    # surname), identity is genuinely uncertain — a bare 'Jan' is NOT 'Jan
    # Axelson', yet a naive role score normalizes over the one present role and
    # returns 1.0, which then auto-merges every same-given name (and chains them
    # via union-find in dedup). Precision-first rule: a lone-token comparison can
    # reach at most the *review* tier, never auto-match. We still compute the
    # best component match so 'Tolkien' vs 'J.R.R. Tolkien' is surfaced (not a
    # false no-match) — just for review, not auto-merge.
    core_a = given_a + fam_a + fore_a
    core_b = given_b + fam_b + fore_b
    # Applies only to a lone token vs a MULTI-token name ('Jan' vs 'Jan Axelson')
    # — matching a single component of a fuller name is weak. Two single-token
    # names that are variants of each other (Akeela vs Akeelah) are NOT capped.
    # Spaceless scripts (Han) romanize the whole name to one token -> never cap.
    if (bridged not in SPACELESS_SCRIPTS and core_a and core_b
            and min(len(core_a), len(core_b)) == 1 and max(len(core_a), len(core_b)) > 1):
        mono, og, of = (core_a[0], given_b, fam_b) if len(core_a) == 1 else (core_b[0], given_a, fam_a)
        best_fam = max((token_sim(mono, t, arabic, bridged) for t in of), default=0.0)
        best_giv = max((token_sim(mono, t, arabic, bridged) for t in og), default=0.0)
        mono_score = max(best_fam, 0.6 * best_giv)
        score = min(max(score, mono_score), 0.84)  # lone token -> at most 'review'
        res.reasons.append("single-token name: weak evidence, capped at review")

    res.score = round(score, 3)
    res.bucket = "match" if score >= HIGH else "review" if score >= REVIEW else "no-match"
    return res


def match(a: str, b: str) -> MatchResult:
    """Score whether two names are the same person.

    Same-script: scored directly. Cross-script (one Arabic, one Latin): the
    Arabic side is romanized with several transliteration schemes (Workstream C)
    and the best-scoring candidate wins, so the comparison isn't hostage to one
    spelling of the name.
    """
    a_script = detect_script(a).dominant or "Latin"
    b_script = detect_script(b).dominant or "Latin"
    # We can only bridge a non-Latin script we have a romanizer for, against Latin.
    other = BRIDGEABLE_SCRIPTS & {a_script, b_script}
    if a_script == b_script or not other or "Latin" not in (a_script, b_script):
        return _score(a, b)

    src_script = next(iter(other))
    src_name, lat_name = (a, b) if a_script == src_script else (b, a)
    # Drop empty romanizations (e.g. missing pinyin data) so we never compare ''.
    cands = [c for c in romanizations(src_name, src_script) if c.strip()]
    if not cands:
        return _score(a, b)  # can't romanize -> fall back to same-space scoring
    # Spaceless scripts (Han) romanize without spaces -> compare against the joined Latin.
    lat_cmp = normalize_latin(lat_name).replace(" ", "") if src_script in SPACELESS_SCRIPTS else lat_name

    best: MatchResult | None = None
    best_cand = ""
    for cand in cands:
        r = _score(cand, lat_cmp, bridged=src_script)
        if best is None or r.score > best.score:
            best, best_cand = r, cand
    assert best is not None
    best.a, best.b = a, b  # report original strings, not the romanization
    best.reasons.append(
        f"cross-script {a_script}<->{b_script}: best of romanizations ('{best_cand}')")
    return best
