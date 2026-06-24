"""``namematch`` CLI — detect, parse, match, and bulk-link name lists.

Examples::

    python -m namematch detect "صلاح الدين الأيوبي"
    python -m namematch parse "Maria de la Cruz Gonzalez" --culture Spanish
    python -m namematch match "G. Washington" "George Washington"
    python -m namematch link authors_a.txt authors_b.txt --threshold 0.85
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from . import detect, match, parse


def _print(obj) -> None:
    def default(o):
        if isinstance(o, set):
            return sorted(o)
        return str(o)
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=default))


def cmd_detect(args) -> int:
    d = detect(args.name)
    _print({
        "text": d.text, "script": d.script,
        "is_person_name": d.is_person_name,
        "origins": d.origins, "top_origin": d.top_origin,
        "gender": d.gender, "countries": sorted(d.countries),
        "reasons": d.reasons,
    })
    return 0


def cmd_parse(args) -> int:
    p = parse(args.name, culture=args.culture)
    _print(asdict(p))
    return 0


def cmd_match(args) -> int:
    r = match(args.a, args.b)
    _print({"score": r.score, "bucket": r.bucket, "signals": r.signals, "reasons": r.reasons})
    return 0 if r.bucket == "match" else 1


def cmd_link(args) -> int:
    a = [ln.strip() for ln in open(args.file_a, encoding="utf-8") if ln.strip()]
    b = [ln.strip() for ln in open(args.file_b, encoding="utf-8") if ln.strip()]
    for na in a:
        best = None
        for nb in b:
            r = match(na, nb)
            if best is None or r.score > best.score:
                best = r
        if best and best.score >= args.threshold:
            print(f"{best.score:.2f}\t{best.bucket}\t{na}\t<->\t{best.b}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="namematch", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("detect"); p.add_argument("name"); p.set_defaults(fn=cmd_detect)
    p = sub.add_parser("parse"); p.add_argument("name")
    p.add_argument("--culture", default=None); p.set_defaults(fn=cmd_parse)
    p = sub.add_parser("match"); p.add_argument("a"); p.add_argument("b")
    p.set_defaults(fn=cmd_match)
    p = sub.add_parser("link"); p.add_argument("file_a"); p.add_argument("file_b")
    p.add_argument("--threshold", type=float, default=0.85); p.set_defaults(fn=cmd_link)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
