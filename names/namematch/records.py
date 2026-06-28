"""Multi-signal record matching (roadmap #3).

``match()`` scores names; real entity resolution blends the name with other
fields — a book's title / year / publisher, a person's specialty / address. This
is the *weighted bag of soft signals* scorer: each signal compares one field and
contributes its weight; the weighted mean over the **present** signals is
bucketed match / review / no-match. The name signal delegates to ``match()``;
no single signal is required, and absent fields are skipped (not penalized).

This is what lifts hard name-only false positives out of ``match``: two records
whose names falsely collide (e.g. ``Baker`` vs ``Baqir`` across scripts) but
whose titles/years disagree now score low overall and stay split. With only a
name field present, ``match_records`` degrades exactly to ``match()``.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from .match import HIGH, REVIEW
from .match import match as _name_match
from .normalize import normalize_latin

# --- field comparators: (a, b) -> 0..1, or None to skip this pair ----------

def cmp_name(a: Any, b: Any) -> float:
    """Compare two names with the full culture-aware/cross-script matcher."""
    return _name_match(str(a), str(b)).score


def cmp_exact(a: Any, b: Any) -> float:
    return 1.0 if normalize_latin(str(a)) == normalize_latin(str(b)) else 0.0


def cmp_fuzzy(a: Any, b: Any) -> float:
    """Lowercased edit-distance ratio — for titles, publishers, free text."""
    return SequenceMatcher(None, str(a).lower(), str(b).lower()).ratio()


def cmp_year(tolerance: int = 1) -> Callable[[Any, Any], float | None]:
    """Factory: 1.0 within *tolerance* years, decaying to 0.0 by 2x tolerance."""
    def f(a: Any, b: Any) -> float | None:
        try:
            ya, yb = int(str(a)[:4]), int(str(b)[:4])
        except (ValueError, TypeError):
            return None
        d = abs(ya - yb)
        if d <= tolerance:
            return 1.0
        if d >= 2 * tolerance + 1:
            return 0.0
        return 1.0 - (d - tolerance) / (tolerance + 1)
    return f


def cmp_token_set(a: Any, b: Any) -> float:
    """Jaccard overlap of token sets — co-authors, subjects, tags."""
    ta = a if isinstance(a, (set, list, tuple)) else normalize_latin(str(a)).split()
    tb = b if isinstance(b, (set, list, tuple)) else normalize_latin(str(b)).split()
    sa, sb = {str(x).lower() for x in ta}, {str(x).lower() for x in tb}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


# --- signals + scorer ------------------------------------------------------

@dataclass
class Signal:
    field: str
    weight: float
    compare: Callable[[Any, Any], float | None] = cmp_fuzzy


@dataclass
class RecordMatch:
    score: float
    bucket: str
    signals: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.bucket == "match"


def _present(v: Any) -> bool:
    return v is not None and not (isinstance(v, str) and not v.strip())


def match_records(a: dict, b: dict, signals: list[Signal],
                  high: float = HIGH, review: float = REVIEW) -> RecordMatch:
    """Score two records over a weighted bag of field signals.

    Absent fields (missing/blank on either side, or a comparator returning None)
    are skipped and their weight removed — so the score is the weighted mean over
    the signals that actually fired. If nothing fires, score is 0.
    """
    res = RecordMatch(score=0.0, bucket="no-match")
    acc = 0.0
    wsum = 0.0
    for s in signals:
        va, vb = a.get(s.field), b.get(s.field)
        if not _present(va) or not _present(vb):
            continue
        sc = s.compare(va, vb)
        if sc is None:
            continue
        res.signals[s.field] = round(sc, 3)
        res.reasons.append(f"{s.field} sim={sc:.2f} (w={s.weight})")
        acc += sc * s.weight
        wsum += s.weight
    score = acc / wsum if wsum else 0.0
    res.score = round(score, 3)
    res.bucket = "match" if score >= high else "review" if score >= review else "no-match"
    return res
