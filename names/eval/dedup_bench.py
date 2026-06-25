"""Benchmark dedup() clustering quality + blocking efficiency.

Ground truth: the on-disk name-variant clusters (`*_det.xml`) — every name in a
cluster is the same name, so two names are "same entity" iff they're in the same
source cluster. We flatten clusters into one list, run dedup(), and score the
predicted clustering pairwise against the ground truth.

Run:  PYTHONPATH=. python3 eval/dedup_bench.py
"""
from __future__ import annotations

from itertools import combinations
from pathlib import Path

from build_dataset import read_variant_clusters

from namematch import dedup
from namematch.dedup import candidate_pairs
from namematch.lexicon import default_namesdb


def main() -> int:
    nd = default_namesdb()
    clusters = read_variant_clusters(nd / "ar_babynames_det.xml")
    clusters += read_variant_clusters(nd / "he_babynames_det.xml")
    # flatten -> (name, gold_label)
    names: list[str] = []
    gold: list[int] = []
    for label, cl in enumerate(clusters):
        for nm in cl:
            names.append(nm)
            gold.append(label)
    n = len(names)
    if n < 10:
        print("not enough data")
        return 1

    def prf(pred):
        tp = fp = fn = 0
        for i, j in combinations(range(n), 2):
            sg, sp = gold[i] == gold[j], pred[i] == pred[j]
            tp += sp and sg
            fp += sp and not sg
            fn += (not sp) and sg
        p = tp / (tp + fp) if (tp + fp) else 0.0
        r = tp / (tp + fn) if (tp + fn) else 0.0
        f = 2 * p * r / (p + r) if (p + r) else 0.0
        return p, r, f, tp, fp, fn

    res = dedup(names)                       # precision-first (auto-merge only)
    res_agg = dedup(names, link_review=True)  # aggressive (also merge review)
    allpairs = n * (n - 1) // 2

    print(f"input: {n} names in {len(clusters)} gold clusters (hard short-name variants)")
    print(f"blocking: {res.n_candidates} candidate pairs vs {allpairs} all-pairs "
          f"({100*(1-res.n_candidates/allpairs):.1f}% reduction)")
    p, r, f, tp, fp, fn = prf(res.labels)
    print(f"auto-merge (match only):   P={p:.3f} R={r:.3f} F1={f:.3f}  "
          f"-> {len(res.clusters)} entities, {len(res.review_pairs)} queued for review")
    p2, r2, f2, *_ = prf(res_agg.labels)
    print(f"aggressive (+review/human): P={p2:.3f} R={r2:.3f} F1={f2:.3f}  "
          f"-> {len(res_agg.clusters)} entities  (recall ceiling)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
