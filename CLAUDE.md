# NectarMatcher — repo context

## What this is

NectarMatcher is the **fuzzy-matching / record-linkage layer** of DataMasterer:
given records (CSV / JSON / SQL output), score and link them — the
"is this the same thing under a different name?" step.

Bee theme: after scent-foraging finds flowers, bees match each flower's
**nectar** to others of the same kind.

## What's here

- **`names/` — namematch (the real, working implementation).** A culture-aware
  human-name detection & matching engine:
  - `detect` — is a string a person name + its script/origin
    (Arabic / Latin / Hebrew / …), with gender/country from gazetteers;
  - `parse` — culture-aware components (Arabic ism / nasab / nisba / kunya,
    Spanish & Portuguese multi-surname, Western);
  - `match` — are two names the same person, across scripts and spellings?
    (`match` / `review` / `no-match`, precision-first; cross-script bridging for
    Arabic, Hebrew, Chinese via Han→pinyin, and Hindi via Devanagari);
  - `dedup` — resolve a whole list into entities (phonetic blocking + union-find
    clustering + a review queue).

  Deterministic, pure-stdlib core; ML/LLM are opt-in plugins. Reads the shared
  name corpus in a sibling `namesdb/` (not vendored here). Start with
  `names/CLAUDE.md`, then `names/DESIGN.md` and `names/STATUS.md`.

- **`main.py` / `__init__.py` — the v1 (2017) sketch.** A ~30-line pseudocode
  outline of the intended pipeline (named stages: phonetic scores, letter-stats
  hashes, datatype-aware enhancements, JSON output). Superseded by namematch;
  kept for history. Its value was the **named stages**, which namematch honors
  (the `review` tier as a first-class output, etc.).

## Status

namematch v0.2 is on `master`: detection + culture-aware parsing + cross-script
matching + list dedup. Tested (full pytest suite) and benchmarked on public data
only — ParaNames (Wikidata, CC-BY-SA) and a synthetic variant set. Numbers and
roadmap live in `names/STATUS.md`; the external benchmark/data-source catalog in
`names/eval/DATASETS.md`.

## Conventions

- **Public repo.** Keep PII and private/source-derived data out of it. Any
  private benchmarking stays in the gitignored `names/eval/_local/`.
- **100% local by default.** The core makes no network calls at import or
  runtime; optional extras (rapidfuzz/jellyfish, ML backends, an LLM judge) are
  lazy and opt-in.
- **exFAT-friendly.** Run via `python -m namematch`; no symlinks / bin-links
  assumed. `core.fileMode = false` is set locally to quiet exFAT mode-flips.
