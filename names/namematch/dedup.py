"""List dedup / clustering on top of pairwise ``match()``.

Turns the name-comparison primitive into "resolve a list of names into entities":

1. **Block** — generate candidate pairs cheaply instead of comparing all O(n²).
   Each name yields a set of phonetic block keys (Soundex per token, after
   romanizing non-Latin names so an Arabic name and its Latin form can share a
   key). Two names are candidates iff they share a key. Over-common keys (bucket
   bigger than ``max_block``) are dropped as non-discriminative — the
   stop-word-style guard that keeps a sea of "Muhammad"s from exploding.
2. **Compare** — run ``match()`` on each candidate pair.
3. **Cluster** — union-find over the ``match`` edges → entity groups. ``review``
   edges that cross final clusters become a **review queue** (precision-first:
   auto-merge only the confident matches, queue the uncertain ones).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations

from .match import match
from .normalize import normalize_latin
from .phonetics import soundex
from .script import detect_script
from .translit import romanizations


def _romanized(name: str) -> str:
    script = detect_script(name).dominant or "Latin"
    if script != "Latin":
        cands = romanizations(name, script)
        if cands:
            name = cands[0]
    return normalize_latin(name)


def _keys_from_roman(roman: str) -> set[str]:
    keys = set()
    for tok in roman.split():
        if len(tok) >= 2:
            s = soundex(tok)
            if s:
                keys.add(s)
    joined = soundex(roman.replace(" ", ""))  # bridges spaceless scripts (习近平 / Xi Jinping)
    if joined:
        keys.add(joined)
    return keys


def block_keys(name: str) -> set[str]:
    """Phonetic block keys (Soundex per romanized token + a joined key)."""
    return _keys_from_roman(_romanized(name))


def candidate_pairs(names: list[str], max_block: int = 400) -> set[tuple[int, int]]:
    """Indices (i<j) that share a block key.

    Over-common keys (bucket > max_block) are NOT dropped — they are sub-blocked
    by the exact romanized form, so a name whose only key is over-common (e.g. a
    Han name whose single joined Soundex collides widely) still pairs with its
    true duplicates without an O(bucket^2) blowup over distinct names.
    """
    romans = [_romanized(n) for n in names]
    fine = [r.replace(" ", "") for r in romans]  # exact romanization, for sub-blocking
    inv: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(romans):
        for k in _keys_from_roman(r):
            inv[k].append(i)

    pairs: set[tuple[int, int]] = set()

    def emit(members: list[int]) -> None:
        for a, b in combinations(members, 2):
            pairs.add((a, b) if a < b else (b, a))

    for members in inv.values():
        if len(members) <= max_block:
            emit(members)
        else:
            sub: dict[str, list[int]] = defaultdict(list)
            for i in members:
                sub[fine[i]].append(i)
            for grp in sub.values():
                if len(grp) <= max_block:
                    emit(grp)
    return pairs


class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


@dataclass
class DedupResult:
    clusters: list[list[int]] = field(default_factory=list)   # entity groups (indices)
    labels: list[int] = field(default_factory=list)           # per-input cluster id
    canonical: list[str] = field(default_factory=list)        # representative per cluster
    review_pairs: list[tuple[int, int, float]] = field(default_factory=list)
    n_input: int = 0
    n_candidates: int = 0
    n_comparisons: int = 0

    @property
    def n_duplicates_removed(self) -> int:
        return self.n_input - len(self.clusters)


def _pick_canonical(names: list[str], members: list[int]) -> str:
    # most complete form: most tokens, then longest string
    return max((names[i] for i in members), key=lambda s: (len(s.split()), len(s)))


def dedup(items, max_block: int = 400, link_review: bool = False,
          key=None, compare=None) -> DedupResult:
    """Resolve *items* into entity clusters + a review queue.

    *items* are name strings by default. To dedup richer **records** (multi-
    signal), pass ``key`` (item -> the name to block on) and ``compare``
    (item_a, item_b -> a result with ``.bucket``/``.score``, e.g. from
    ``match_records``). Blocking is always on the name; the comparison can use
    any signals.

    Auto-merges ``match`` pairs; collects ``review`` pairs for human triage.
    ``link_review=True`` also merges review edges (aggressive / human-audited).
    """
    if key is None:
        key = lambda x: x if isinstance(x, str) else x.get("name", "")
    if compare is None:
        compare = lambda a, b: match(key(a), key(b))

    n = len(items)
    names = [key(it) for it in items]
    res = DedupResult(n_input=n, labels=[0] * n)
    uf = _UnionFind(n)
    candidates = candidate_pairs(names, max_block=max_block)
    res.n_candidates = len(candidates)

    review_edges: list[tuple[int, int, float]] = []
    for i, j in candidates:
        r = compare(items[i], items[j])
        res.n_comparisons += 1
        if r.bucket == "match":
            uf.union(i, j)
        elif r.bucket == "review":
            review_edges.append((i, j, r.score))
            if link_review:
                uf.union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[uf.find(i)].append(i)
    clusters = list(groups.values())

    for cid, members in enumerate(clusters):
        for i in members:
            res.labels[i] = cid
    res.clusters = clusters
    res.canonical = [_pick_canonical(names, m) for m in clusters]

    # review queue: uncertain edges that did NOT get auto-merged
    seen = set()
    for i, j, score in sorted(review_edges, key=lambda e: -e[2]):
        if uf.find(i) != uf.find(j):
            key = (min(i, j), max(i, j))
            if key not in seen:
                seen.add(key)
                res.review_pairs.append((i, j, score))
    return res
