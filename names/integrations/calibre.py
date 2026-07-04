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
import re
import sqlite3
from pathlib import Path

from namematch import RecordMatch, dedup, detect, match
from namematch.normalize import normalize_arabic
from namematch.script import detect_script

_TOKEN_STOP = {"the", "and", "for", "with", "from", "vol", "volume", "edition",
               "book", "books", "guide", "introduction", "ed", "new"}


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


def _tokens(text: str) -> set[str]:
    """Topic tokens from a title/tag: split, lowercase, drop short/stop/digits."""
    out = set()
    for raw in re.split(r"[^\w؀-ۿ]+", normalize_arabic(text or "")):
        tok = raw.strip().lower()
        if len(tok) >= 3 and not tok.isdigit() and tok not in _TOKEN_STOP:
            out.add(tok)
    return out


def read_author_profiles(db_path: str, max_coauthor_partners: int = 5) -> list[dict]:
    """Per author: {name, script, profile}. The profile is a NAMESPACED token set
    from the author's books: ``t:`` title words, ``g:`` tag words, ``c:``
    co-authors. Namespacing stops a title word from spuriously matching a tag or
    co-author. Co-authors that pair with many different authors (translators/
    editors) are dropped — they aren't discriminative."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        names = [r[0] for r in con.execute(
            "SELECT name FROM authors WHERE name IS NOT NULL AND trim(name)!=''").fetchall()]
        prof: dict[str, set] = {nm: set() for nm in names}
        for name, title in con.execute(
                "SELECT a.name, b.title FROM authors a "
                "JOIN books_authors_link bal ON bal.author=a.id "
                "JOIN books b ON b.id=bal.book"):
            if name in prof and title:
                prof[name] |= {"t:" + t for t in _tokens(title)}
        for name, tag in con.execute(
                "SELECT a.name, t.name FROM authors a "
                "JOIN books_authors_link bal ON bal.author=a.id "
                "JOIN books_tags_link btl ON btl.book=bal.book "
                "JOIN tags t ON t.id=btl.tag"):
            if name in prof and tag:
                prof[name] |= {"g:" + t for t in _tokens(tag)}
        co_rows = con.execute(
            "SELECT a.name, a2.name FROM authors a "
            "JOIN books_authors_link bal ON bal.author=a.id "
            "JOIN books_authors_link bal2 ON bal2.book=bal.book AND bal2.author<>a.id "
            "JOIN authors a2 ON a2.id=bal2.author").fetchall()
        partners: dict[str, set] = {}
        for name, co in co_rows:
            partners.setdefault(co, set()).add(name)
        for name, co in co_rows:
            if name in prof and len(partners.get(co, ())) <= max_coauthor_partners:
                prof[name].add("c:" + co.strip().lower())
    finally:
        con.close()
    return [{"name": nm, "script": detect_script(nm).dominant or "?", "profile": prof[nm]}
            for nm in names]


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if (a and b) else 0.0


# --- author-field classification: person vs title vs junk ------------------

_JUNK_RE = re.compile(r"[=<>{}|;\\]|^\s*[#$/]|^\s*\d")
_TITLE_WORDS = set(
    "guide course introduction handbook manual encyclopedia dictionary system "
    "systems mechanics edition volume dummies mystery tales story stories "
    "programming design theory analysis methods practice solutions reference "
    "lectures notes essentials techniques fundamentals cookbook tutorial overview "
    "survey approach principles chapter appendix slides".split())


def _norm_title(s: str) -> str:
    s = normalize_arabic(s or "").lower()
    s = re.sub(r"\(.*?\)", "", s)
    return re.sub(r"[^a-z0-9؀-ۿ]+", "", s)


def read_titles(db_path: str) -> set[str]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        ts = {_norm_title(r[0]) for r in con.execute(
            "SELECT title FROM books WHERE title IS NOT NULL") if r[0]}
    finally:
        con.close()
    return ts - {""}


def classify_author(name: str, titles: set[str]) -> tuple[str, str]:
    """Classify an author-field entry. Returns (category, confidence).

    Categories: 'junk' (code/symbols/filenames), 'title' (a book title misfiled
    as an author), 'person', 'review' (name-like but ambiguous). 'junk' and a
    book-title-matched 'title' are HIGH confidence; person/title-phrase/review is
    a fuzzy boundary (LOW) — flag for human/LLM review, don't trust blindly."""
    s = name.strip().strip('"\'')
    d = detect(s)
    has_title_word = bool({t for t in re.sub(r"[^a-z ]", " ", s.lower()).split()} & _TITLE_WORDS)
    if _JUNK_RE.search(s):
        return "junk", "high"
    if _norm_title(s) in titles:
        return "title", "high"        # exact match to a real book title
    if has_title_word and not d.origins:
        return "title", "low"         # title-word phrase, no name-lexicon hit
    if d.origins and d.is_person_name >= 0.5 and not has_title_word:
        return "person", "med"        # lexicon hit + name-shaped
    if d.is_person_name < 0.3:
        return "junk", "low"
    return "review", "low"            # name-like but ambiguous -> human/LLM


def make_profile_compare(min_profile: int = 8, veto_overlap: float = 0.05):
    """A comparator: name match, but demote a same-script auto-merge to *review*
    when both authors have **substantial** book profiles that barely overlap
    (their books are about entirely different topics -> probably different
    people). Disjointness is only evidence of difference when each profile is
    big enough (>= min_profile tokens); a sparse profile (an author with few/
    badly-titled books, e.g. 'A. Conan Doyle') is just missing data, so it is NOT
    vetoed. Cross-script pairs are skipped — their titles are in different scripts
    by nature, so disjointness there is expected, not evidence."""
    def compare(a: dict, b: dict) -> RecordMatch:
        r = match(a["name"], b["name"])
        pa, pb = a["profile"], b["profile"]
        if (r.bucket == "match" and a["script"] == b["script"]
                and len(pa) >= min_profile and len(pb) >= min_profile):
            ov = _jaccard(pa, pb)
            if ov < veto_overlap:
                return RecordMatch(score=min(r.score, 0.84), bucket="review",
                                   signals={"name": r.score, "profile_overlap": round(ov, 3)},
                                   reasons=[f"book profiles disagree (overlap {ov:.2f}) -> review"])
        return RecordMatch(score=r.score, bucket=r.bucket, signals={"name": r.score})
    return compare


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Dedup Calibre authors with namematch")
    ap.add_argument("db", help="path to Calibre metadata.db")
    ap.add_argument("--max-block", dest="max_block", type=int, default=400)
    ap.add_argument("--min-name-score", dest="min_name", type=float, default=0.3,
                    help="drop entries whose is_person_name score is below this "
                         "(the Calibre author field holds non-author junk); 0 disables")
    ap.add_argument("--classify", action="store_true",
                    help="classify each author-field entry as person/title/junk "
                         "(report + <out>_classes.tsv) instead of deduping")
    ap.add_argument("--gliner", action="store_true",
                    help="with --classify: refine non-high-confidence entries with the "
                         "GLiNER entity-type plugin (opt-in; generalizes to Arabic/unseen)")
    ap.add_argument("--books", action="store_true",
                    help="use the author->books profile (title/tag topic overlap) as a "
                         "second signal to veto coincidental same-script name collisions")
    ap.add_argument("--out", default="", help="output prefix (writes <out>_clusters.tsv + _review.tsv)")
    args = ap.parse_args(argv)

    if args.classify:
        from collections import Counter
        titles = read_titles(args.db)
        rows = [(a, *classify_author(a, titles)) for a in read_authors(args.db)]
        if args.gliner:
            # layered: trust deterministic HIGH (junk-code, book-title matches);
            # refine everything else with the structure-based model.
            from namematch.plugins import entity_type
            _map = {"person": "person", "title": "title", "organization": "org", "none": "junk"}
            rows = [(a, c, conf) if conf == "high"
                    else (a, _map[entity_type.classify(a)], "gliner")
                    for a, c, conf in rows]
        by_cat = Counter(c for _, c, _ in rows)
        by_cc = Counter((c, conf) for _, c, conf in rows)
        print(f"classified {len(rows)} author-field entries:")
        for c, _n in by_cat.most_common():
            confs = {cf: n for (cc, cf), n in by_cc.items() if cc == c}
            print(f"  {c:8} {by_cat[c]:6}  by confidence: {confs}")
        if args.out:
            p = Path(f"{args.out}_classes.tsv")
            with p.open("w", encoding="utf-8") as fh:
                fh.write("category\tconfidence\tname\n")
                for a, c, conf in rows:
                    fh.write(f"{c}\t{conf}\t{a}\n")
            print(f"wrote {p}")
        return 0

    if args.books:
        records = read_author_profiles(args.db)
        if args.min_name > 0:
            kept = [r for r in records if detect(r["name"]).is_person_name >= args.min_name]
            print(f"filtered {len(records) - len(kept)} non-name entries "
                  f"(is_person_name < {args.min_name}); {len(kept)} authors remain")
            records = kept
        names = [r["name"] for r in records]
        res = dedup(records, max_block=args.max_block,
                    key=lambda r: r["name"], compare=make_profile_compare())
    else:
        raw = read_authors(args.db)
        if args.min_name > 0:
            names = [a for a in raw if detect(a).is_person_name >= args.min_name]
            print(f"filtered {len(raw) - len(names)} non-name entries "
                  f"(is_person_name < {args.min_name}); {len(names)} authors remain")
        else:
            names = raw
        res = dedup(names, max_block=args.max_block)

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
                        fh.write(f"{cid}\t{res.canonical[cid]}\t{names[i]}\n")
        rf = Path(f"{args.out}_review.tsv")
        with rf.open("w", encoding="utf-8") as fh:
            fh.write("score\tname_a\tname_b\n")
            for i, j, score in res.review_pairs:
                fh.write(f"{score:.3f}\t{names[i]}\t{names[j]}\n")
        print(f"wrote {cf}\nwrote {rf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
