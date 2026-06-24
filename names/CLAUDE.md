# namematch — repo context

> A submodule of **NectarMatcher** (DataMasterer's v2 `nectarmatcher`
> fuzzy-match layer). Read `../CLAUDE.md` for the parent, and
> `../../CLAUDE.md` for DataMasterer-wide constraints.

## What this is

`namematch` is a **culture-aware human-name detection & matching** engine:
*is this a person name and what origin?* + *do these two names refer to the same
person?* (match / review / no-match). It exists to power dedup/linking of author
lists, researcher/staff directories, customer lists, and cross-catalog reconciliation.

## Decisions (settled with maintainer 2026-06-18)

- **Deterministic-first, ML/LLM opt-in.** Core is pure stdlib, fully local,
  explainable, built on `../../namesdb`. ML (NameBERT/name2nat) and an LLM judge
  (Claude) are **plugins, off by default** — the only place a network call is
  allowed. This honors DataMasterer's *100%-local, no-AI-by-default* rule while
  still reaching high precision when extras are enabled.
- **Lives inside NectarMatcher** as the name-specialized matcher; `match()` is
  meant to become a comparison signal in `nectarmatcher`'s record-linkage scorer
  and feed the FlowerFest review queue.

## Layout

```
names/
  namematch/
    script.py      unicode-script detection (Arabic/Latin/Hebrew/…)
    normalize.py   tashkeel/alef normalize, romanize_fold, transliterate_arabic
    phonetics.py   soundex + arabic_phonetic class key
    lexicon.py     loads gazetteers from ../../namesdb (lazy, cached)
    parse.py       culture-aware parse (Western/Arabic/Spanish/Portuguese)
    detect.py      is-person-name + origin/gender/country
    match.py       role-aware, asymmetric-containment matcher (3 buckets)
    cli.py         python -m namematch {detect,parse,match,link}
    plugins/       origin_ml (name2nat/NameBERT), llm_judge (Claude) — opt-in
  tests/test_core.py
  DESIGN.md        SOTA survey + architecture + roadmap   <- read this next
  README.md
```

## Conventions / constraints

- **exFAT-aware**: no symlinks, no bin-links. Run via `python -m namematch`;
  core has **zero runtime deps** so it works on a bare checkout.
- **Corpus is shared, not vendored.** Data stays in `../../namesdb`; resolved
  relative to this file, overridable with `NAMEMATCH_NAMESDB`. Don't copy the
  149 MB Arabic wordlist in here.
- **Precision over recall.** Prefer the *review* bucket to a false *match*; every
  verdict carries a per-signal explanation. Don't change scoring thresholds
  without the (v0.2) labeled eval harness.
- Tests run with pytest **or** the stdlib runner in `README.md` (pytest may not
  be installed in this environment).

## Status

v0.1 runnable: 16/16 tests pass; CLI verified against the real corpus
(`صلاح الأيوبي ↔ صلاح الدين الأيوبي` → 0.94 match; `G.`↔`George` → match).
Next: scheme-accurate transliteration + a precision/recall harness (see
`DESIGN.md` §5). Track in `STATUS.md`.
