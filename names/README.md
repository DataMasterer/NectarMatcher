# namematch

Culture-aware **human-name detection & matching**. A focused module inside
DataMasterer's `NectarMatcher` fuzzy-matching layer.

Two jobs:

1. **Detect** — given a string, decide *is this a person name?* and *what
   origin/script is it?* (Arabic / Latin / Hebrew …; Western / Arabic / Spanish
   / French …) with a calibrated confidence and an explanation.
2. **Match** — decide whether two name strings refer to the **same person**,
   across spelling variants, initials, transliterations, and cultures — and
   bucket the answer **match / review / no-match** (the review tier is a
   first-class output, feeding NectarMatcher's review queue).

Use cases: dedup/link author lists, researcher/staff directories, customer lists; reconcile
catalogs; flag the same person under different spellings or scripts.

## Design stance

**Deterministic-first, fully local.** The core is pure Python stdlib (no
network, no model downloads) and is built on the name corpus already on disk in
[`../../namesdb`](../../namesdb) (25k+ Arabic given names with gender+country,
Hebrew/Islamic sets, a Western first/last-name DB, transliteration tables). This
honors DataMasterer's *100%-local, no-AI-by-default* constraint and keeps every
decision explainable.

**ML/LLM as opt-in plugins** (`namematch.plugins`): a NameBERT/name2nat origin
classifier and a Claude-based judge for the hard *review* cases. Off unless you
install an extra and pass the flag — the only place a network call is allowed.

See [`DESIGN.md`](DESIGN.md) for the SOTA survey, architecture, and roadmap.

## Quick start

```bash
# no install needed for the core — pure stdlib
python -m namematch detect "صلاح الدين الأيوبي"
python -m namematch parse  "Maria de la Cruz Gonzalez" --culture Spanish
python -m namematch match  "G. Washington" "George Washington"
python -m namematch link    authors_a.txt authors_b.txt --threshold 0.85
```

```python
from namematch import detect, match, parse

detect("صلاح الدين")               # -> script=Arabic, origin=Arabic, gender=M
match("صلاح الأيوبي", "صلاح الدين الأيوبي").bucket   # -> "match"
match("G. Washington", "George Washington").bucket  # -> "match"
```

The corpus path defaults to `../../namesdb`; override with
`NAMEMATCH_NAMESDB=/path/to/namesdb`.

## What works today (v0.1)

- Unicode-script detection (Arabic/Latin/Hebrew/Cyrillic/Han/…).
- Arabic normalization (tashkeel/tatweel strip, alef/ya/ta-marbuta unify) and a
  romanization fold so transliteration variants converge.
- Culture-aware parsing: Western, Arabic (ism / nasab forefathers / nisba /
  kunya, compound given names like *صلاح الدين* / *عبد الله*), Spanish two-surname,
  Portuguese/Brazilian multi-surname.
- Lexicon-backed origin detection + gender/country from the Kalmasoft set.
- Role-aware, asymmetric-containment matcher: initials (`G.`↔`George`), the
  *صلاح ⊂ صلاح الدين* subset case, forefathers/middles down-weighted, cross-script
  bridging via transliteration. 3-bucket output with per-signal explanation.

## Tests

```bash
python -m pytest          # or, without pytest:
python -c "import tests.test_core as t; [getattr(t,n)() for n in dir(t) if n.startswith('test_')]"
```
