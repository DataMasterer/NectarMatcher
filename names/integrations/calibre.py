"""Dedup the authors of a Calibre library with namematch — the first consumer.

Reads the ``authors`` table from a Calibre ``metadata.db`` (read-only) and
resolves the author list into entity clusters + a review queue, so the same
author under spelling/initial/transliteration variants collapses to one entity.

Generic and public-safe: the library path and all output are the user's data —
keep them out of version control (write reports under ``eval/_local/``).

Usage:
    PYTHONPATH=. python3 integrations/calibre.py /path/to/metadata.db \
        --out eval/_local/calibre_authors
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from namematch import dedup, detect


def read_authors(db_path: str) -> list[str]:
    """Return the author names from a Calibre metadata.db (read-only)."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT name FROM authors WHERE name IS NOT NULL AND trim(name) != '' "
            "ORDER BY name"
        ).fetchall()
    finally:
        con.close()
    return [r[0] for r in rows]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Dedup Calibre authors with namematch")
    ap.add_argument("db", help="path to Calibre metadata.db")
    ap.add_argument("--max-block", dest="max_block", type=int, default=400)
    ap.add_argument("--min-name-score", dest="min_name", type=float, default=0.3,
                    help="drop entries whose is_person_name score is below this "
                         "(the Calibre author field holds non-author junk); 0 disables")
    ap.add_argument("--out", default="", help="output prefix (writes <out>_clusters.tsv + _review.tsv)")
    args = ap.parse_args(argv)

    raw = read_authors(args.db)
    if args.min_name > 0:
        authors = [a for a in raw if detect(a).is_person_name >= args.min_name]
        print(f"filtered {len(raw) - len(authors)} non-name entries "
              f"(is_person_name < {args.min_name}); {len(authors)} authors remain")
    else:
        authors = raw
    res = dedup(authors, max_block=args.max_block)

    merged_clusters = [c for c in res.clusters if len(c) > 1]
    allpairs = res.n_input * (res.n_input - 1) // 2
    print(f"authors: {res.n_input}")
    print(f"blocking: {res.n_candidates} candidate pairs vs {allpairs} all-pairs "
          f"({100 * (1 - res.n_candidates / allpairs):.1f}% reduction); "
          f"{res.n_comparisons} comparisons")
    print(f"entities: {len(res.clusters)} ({res.n_duplicates_removed} duplicates merged "
          f"across {len(merged_clusters)} multi-author clusters)")
    print(f"review queue: {len(res.review_pairs)} uncertain pairs")

    if args.out:
        cf = Path(f"{args.out}_clusters.tsv")
        with cf.open("w", encoding="utf-8") as fh:
            fh.write("cluster_id\tcanonical\tmember\n")
            for cid, members in enumerate(res.clusters):
                if len(members) > 1:
                    for i in members:
                        fh.write(f"{cid}\t{res.canonical[cid]}\t{authors[i]}\n")
        rf = Path(f"{args.out}_review.tsv")
        with rf.open("w", encoding="utf-8") as fh:
            fh.write("score\tname_a\tname_b\n")
            for i, j, score in res.review_pairs:
                fh.write(f"{score:.3f}\t{authors[i]}\t{authors[j]}\n")
        print(f"wrote {cf}\nwrote {rf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
