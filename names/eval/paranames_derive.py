"""Build a cross-script EN<->AR benchmark from ParaNames (public Wikidata data).

ParaNames (Sälevä & Lignos, LREC-COLING 2024; CC-BY-SA 4.0, derived from
Wikidata) ships a TSV ``wikidata_id, eng, label, language, type``. Each
``language=ar, type=PER`` row is a same-person pair: ``eng`` (the English/Latin
canonical) <-> ``label`` (the Arabic form). That gives clean Latin<->Arabic
positives — exactly the benchmark that could not be reconstructed locally.

Input  : eval/_local/paranames_en_ar.tsv  (eng <TAB> arabic), produced by
         streaming the ParaNames release through an ar/PER filter (gitignored;
         large raw extract).
Output : eval/paranames_en_ar.tsv  — a SAMPLED, committable benchmark
         (a <TAB> b <TAB> label <TAB> category). Public names + attribution,
         (public Wikidata names) so it is safe to commit.

Positives: (eng, arabic) for the same Wikidata person.
Negatives: hard — an English name paired with a *different* person's Arabic
           name that shares the romanized first token (so the name is the real
           discriminator, not an obvious mismatch).

Run:  PYTHONPATH=. python3 eval/paranames_derive.py [--n 2000]
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

from namematch.normalize import normalize_latin

HERE = Path(__file__).resolve().parent
SEED = 20260618


def _attribution(lang: str) -> str:
    return (
        "# Derived from ParaNames (https://github.com/bltlab/paranames), CC-BY-SA 4.0,\n"
        f"# built from Wikidata. Sampled EN<->{lang.upper()} person pairs for cross-script eval.\n"
        "# Columns: a<TAB>b<TAB>label<TAB>category   (label 1=same person, 0=different)\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="ar", help="target language code (ar/he/zh/hi/...)")
    ap.add_argument("--n", type=int, default=2000, help="number of positive pairs to sample")
    args = ap.parse_args()
    RAW = HERE / "_local" / f"paranames_en_{args.lang}.tsv"
    OUT = HERE / f"paranames_en_{args.lang}.tsv"
    if not RAW.exists():
        print(f"missing {RAW}\nStream it first (see module docstring).")
        return 1

    rng = random.Random(SEED)
    rows = []
    for line in RAW.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        eng, ar = parts[0].strip(), parts[1].strip()
        # keep clean, name-like English (latin letters, 1-4 tokens) + Arabic side
        nl = normalize_latin(eng)
        if not nl or not (1 <= len(nl.split()) <= 4):
            continue
        # the target-script side must carry at least one non-ASCII letter
        if not any(ord(ch) > 0x2C0 and ch.isalpha() for ch in ar):
            continue
        rows.append((eng, ar, nl))
    if len(rows) < 10:
        print(f"too few usable rows ({len(rows)})")
        return 1

    rng.shuffle(rows)
    pos = rows[: args.n]

    # hard negatives: same romanized first token, different person/Arabic name.
    from collections import defaultdict
    by_first = defaultdict(list)
    for eng, ar, nl in rows:
        by_first[nl.split()[0]].append((eng, ar))
    negs = []
    keys = [k for k, v in by_first.items() if len(v) >= 2]
    rng.shuffle(keys)
    while len(negs) < len(pos) and keys:
        k = keys[len(negs) % len(keys)]
        a, b = rng.sample(by_first[k], 2)
        if a[1] != b[1]:
            negs.append((a[0], b[1]))  # a's English <-> b's Arabic
        else:
            keys.remove(k)

    cat = f"paranames-en-{args.lang}"
    with OUT.open("w", encoding="utf-8") as fh:
        fh.write(_attribution(args.lang))
        for eng, ar, _ in pos:
            fh.write(f"{eng}\t{ar}\t1\t{cat}\n")
        for eng, ar in negs:
            fh.write(f"{eng}\t{ar}\t0\t{cat}-neg\n")

    print(f"usable rows={len(rows)}  positives={len(pos)}  hard_negatives={len(negs)}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
