"""Build a labeled name-pair eval set from on-disk data — fully local.

Sources (no downloads):
- ``namesdb/ar_babynames_det.xml`` + ``he_babynames_det.xml`` — quoted,
  comma-separated *variant clusters* (e.g. ``"Akeelah, Akeela, Akilla, ..."``).
  Every intra-cluster pair is a same-name **positive** (category
  ``variant-spelling``).
- ``eval/headline.tsv`` — curated initials / arabic-subset / cross-script /
  iberian cases (the headline behaviors we must not regress).

Hard **negatives** are sampled across different clusters, biased to the same
initial + similar length so precision is actually tested.

Output: ``eval/pairs.tsv`` with columns ``a  b  label  category`` (committed,
small, deterministic via a fixed seed).
"""
from __future__ import annotations

import random
import re
from itertools import combinations
from pathlib import Path

from namematch.lexicon import default_namesdb

HERE = Path(__file__).resolve().parent
SEED = 20260618
MAX_PAIRS_PER_CLUSTER = 10   # cap to avoid combinatorial blow-up on big clusters
_VARIANT_LINE = re.compile(r'^"(.+?)"', re.UNICODE)


def read_variant_clusters(xml_path: Path) -> list[list[str]]:
    """Extract variant clusters: each quoted comma-list line -> a name set."""
    clusters: list[list[str]] = []
    if not xml_path.exists():
        return clusters
    for line in xml_path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _VARIANT_LINE.match(line.strip())
        if not m:
            continue
        names = [n.strip().strip("\t") for n in m.group(1).split(",")]
        names = [n for n in names if n and " " not in n and n.isascii()]
        uniq = sorted(set(names))
        if len(uniq) >= 2:
            clusters.append(uniq)
    return clusters


def positives_from_clusters(clusters: list[list[str]], rng: random.Random) -> list[tuple]:
    pairs = []
    for cl in clusters:
        combos = list(combinations(cl, 2))
        if len(combos) > MAX_PAIRS_PER_CLUSTER:
            combos = rng.sample(combos, MAX_PAIRS_PER_CLUSTER)
        for a, b in combos:
            pairs.append((a, b, 1, "variant-spelling"))
    return pairs


def hard_negatives(clusters: list[list[str]], n: int, rng: random.Random) -> list[tuple]:
    """Cross-cluster pairs biased to same initial + similar length."""
    flat = [(name, ci) for ci, cl in enumerate(clusters) for name in cl]
    by_initial: dict[str, list[tuple[str, int]]] = {}
    for name, ci in flat:
        by_initial.setdefault(name[0].lower(), []).append((name, ci))
    out: set[tuple] = set()
    keys = [k for k, v in by_initial.items() if len(v) >= 2]
    attempts = 0
    while len(out) < n and attempts < n * 50 and keys:
        bucket = by_initial[rng.choice(keys)]
        (a, ca), (b, cb) = rng.sample(bucket, 2)
        if ca == cb or abs(len(a) - len(b)) > 3:
            attempts += 1
            continue
        key = tuple(sorted((a, b)))
        if key not in out:
            out.add(key)
        attempts += 1
    return [(a, b, 0, "hard-negative") for a, b in out]


def read_headline(path: Path) -> list[tuple]:
    pairs = []
    if not path.exists():
        return pairs
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) >= 4:
            pairs.append((cols[0], cols[1], int(cols[2]), cols[3]))
    return pairs


def main() -> int:
    rng = random.Random(SEED)
    namesdb = default_namesdb()
    clusters = read_variant_clusters(namesdb / "ar_babynames_det.xml")
    clusters += read_variant_clusters(namesdb / "he_babynames_det.xml")

    pos = positives_from_clusters(clusters, rng)
    neg = hard_negatives(clusters, len(pos), rng)
    headline = read_headline(HERE / "headline.tsv")

    all_pairs = headline + pos + neg
    out = HERE / "pairs.tsv"
    with out.open("w", encoding="utf-8") as fh:
        fh.write("a\tb\tlabel\tcategory\n")
        for a, b, label, cat in all_pairs:
            fh.write(f"{a}\t{b}\t{label}\t{cat}\n")

    print(f"clusters={len(clusters)}  positives={len(pos)}  hard_neg={len(neg)}  "
          f"headline={len(headline)}  total={len(all_pairs)}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
