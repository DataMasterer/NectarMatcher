"""Benchmark match() over the labeled pair set; report P/R/F1 per category.

Two operating points:
- **strict** (predicted-positive = bucket "match"): the precision number.
- **lenient** (predicted-positive = bucket in {match, review}): the recall
  number / triage coverage.

Usage::
    python eval/bench.py                 # human-readable report
    python eval/bench.py --json          # machine-readable (for regression test)
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from namematch import match

HERE = Path(__file__).resolve().parent


def load_pairs(path: Path) -> list[tuple]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue  # skip blanks + attribution/comment lines
        cols = line.split("\t")  # tolerate extra feature columns after the first 4
        if len(cols) < 4 or cols[0] == "a" or not cols[2].lstrip("-").isdigit():
            continue  # skip header row / malformed lines
        a, b, label, cat = cols[0], cols[1], cols[2], cols[3]
        rows.append((a, b, int(label), cat))
    return rows


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return round(p, 3), round(r, 3), round(f, 3)


def evaluate(pairs: list[tuple]) -> dict:
    # counters[(category, mode)] = [tp, fp, fn, tn]
    counters: dict[tuple, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for a, b, label, cat in pairs:
        r = match(a, b)
        for mode, predicted in (
            ("strict", r.bucket == "match"),
            ("lenient", r.bucket in ("match", "review")),
        ):
            for scope in (cat, "ALL"):
                c = counters[(scope, mode)]
                if predicted and label:
                    c[0] += 1
                elif predicted and not label:
                    c[1] += 1
                elif not predicted and label:
                    c[2] += 1
                else:
                    c[3] += 1

    result: dict[str, dict] = {}
    scopes = sorted({k[0] for k in counters})
    for scope in scopes:
        result[scope] = {}
        for mode in ("strict", "lenient"):
            tp, fp, fn, tn = counters[(scope, mode)]
            p, r, f = _prf(tp, fp, fn)
            result[scope][mode] = {
                "precision": p, "recall": r, "f1": f,
                "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            }
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default=str(HERE / "pairs.tsv"))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    pairs = load_pairs(Path(args.pairs))
    res = evaluate(pairs)

    if args.json:
        print(json.dumps(res, indent=2))
        return 0

    print(f"\nEval: {len(pairs)} pairs from {args.pairs}\n")
    hdr = f"{'category':<18}{'strict P':>9}{'strict R':>9}{'lenient P':>11}{'lenient R':>11}{'F1(s)':>8}"
    print(hdr)
    print("-" * len(hdr))
    for scope in [s for s in res if s != "ALL"] + ["ALL"]:
        s, l = res[scope]["strict"], res[scope]["lenient"]
        line = (f"{scope:<18}{s['precision']:>9}{s['recall']:>9}"
                f"{l['precision']:>11}{l['recall']:>11}{s['f1']:>8}")
        print(("\033[1m" + line + "\033[0m") if scope == "ALL" else line)

    # Precision-critical view: how many negatives leak into match / review.
    neg = res["ALL"]["strict"]["fp"] + res["ALL"]["strict"]["tn"]
    print(f"\nnegatives={neg}  false-positives: "
          f"strict(match)={res['ALL']['strict']['fp']}  "
          f"lenient(match+review)={res['ALL']['lenient']['fp']}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
