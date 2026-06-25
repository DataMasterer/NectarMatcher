# STATUS — namematch

> Living doc. Context in [`CLAUDE.md`](CLAUDE.md); design + SOTA in
> [`DESIGN.md`](DESIGN.md). Parent: `../STATUS.md` (NectarMatcher).

**Status:** Active — v0.2 · **Last activity:** 2026-06-23
**Stack:** Python 3.10+ stdlib only (core); optional ML/LLM extras
**Data:** reuses `../../namesdb` + public benchmarks (ParaNames, Unihan)

## v0.2 progress
- **Eval harness (Workstream A) — done.** `eval/build_dataset.py` +
  `eval/bench.py` (P/R/F1 per category, 3-bucket). Synthetic set (552 pairs from
  on-disk variant clusters + curated headline cases). Baseline: strict P 0.90 /
  lenient R 0.96; weak spots = cross-script & iberian (the B/C targets).
  `test_eval_regression` locks the baseline.
- **Workstream B (auto culture-detection) — done.** `culture.infer_culture`
  routes Romance multi-surname names to the Iberian parser; `match()` uses it.
  `Maria de la Cruz` ↔ `María de la Cruz González` now auto-matches (was
  no-match). Iberian strict recall 0.25 → 0.5.
- **Workstream C (scheme-accurate transliteration) — done.** `translit.py`
  loads `transliteration_schemes.csv` (BGN-PCGN/ALA-LC/UNGEGN/DIN31635/Qalam) and
  `match()` picks the best of several romanizations for the Arabic side.
  Clean transliterations land in **review** by design (محمد→Mohammed/Mohamed/
  Muhammad/Mahmoud is ambiguous — precision-first won't auto-accept).
- **Cross-script benchmarks — BUILT (ParaNames EN↔AR/HE/ZH/HI).** Ingested
  **ParaNames** (Wikidata, CC-BY-SA) from the 1 GB release; committable 4,000-pair
  samples per language (`eval/paranames_en_<lang>.tsv`, public names +
  attribution; raw extracts gitignored). `eval/paranames_derive.py --lang X`
  rebuilds. Catalog: `eval/DATASETS.md`.
- **Transliteration recall — attacked.** Arabic-aware **consonant skeleton**
  (`normalize.consonant_skeleton`, bridged-only: drops short vowels Arabic omits,
  folds v/p→f/b, j→g) lifted **EN↔AR strict recall 0.49 → 0.82** at precision
  0.95, with **no same-script regression** (synthetic harness unchanged).
- **All four cross-script bridges live.** Unified `translit.romanizations(name,
  script)` dispatch; `match()` bridges Arabic, Hebrew, **Chinese**, **Hindi**.
  | bench | strict P | strict R |
  | EN↔AR | 0.95 | 0.82 |
  | EN↔HI | 0.93 | 0.81 |  (Devanagari map + skeleton)
  | EN↔ZH | 0.93 | 0.60 |  (Han→pinyin, Unihan `namematch/data/han_pinyin.tsv`)
  | EN↔HE | 0.94 | 0.45 |  (soft+hard Hebrew candidates)
  28/28 tests pass.
- **Dedup / clustering layer (roadmap #1) — done.** `namematch.dedup(list)`:
  phonetic **blocking** (Soundex per romanized token + a joined key so Chinese
  joined-pinyin shares a block with spaced Latin) → `match()` → **union-find
  clustering** + a **review queue** (precision-first: auto-merge confident pairs,
  queue the rest; `link_review=True` for the aggressive/human-audited mode). CLI:
  `namematch dedup <file>`. `eval/dedup_bench.py` on hard variant data: 95% fewer
  comparisons; auto-merge F1 0.46 / aggressive ceiling F1 0.66 (real distinct
  people cluster cleanly incl. cross-script). Unblocks list-dedup use cases
  (author/customer dedup).
- **Code-review hardening (10 findings) — done.** Hebrew detect/gazetteer now
  use a Hebrew normalizer (was latin-stripped to ''); mononym/partial names
  (`Tolkien` ↔ `J.R.R. Tolkien`) reach the review tier instead of false
  no-match; dedup sub-blocks over-common keys instead of dropping a name's only
  key (preserves Han recall at scale); pure per-token funcs are lru_cached for
  the O(n²) dedup hot path; bridgeable/spaceless scripts are a single source of
  truth; partial transliteration schemes degrade per-char. 31/31 tests;
  benchmarks unchanged.
- **Next levers:** ZH romanization variants (Wade-Giles/name-order) + NEWS EN↔ZH;
  niqqud/scheme Hebrew + `he_*` gazetteers; person+**address** multi-signal
  prototype (libpostal + GeoNames, NCVR/FEBRL); more gazetteers (fr/de/it);
  self-learning ingest; ML/LLM plugin activation; Splink scale path.

## Where it stands
- Module inside NectarMatcher: culture-aware name **detection + matching**,
  deterministic-first with ML/LLM as opt-in plugins.
- v0.1 working examples:
  - `صلاح الأيوبي` ↔ `صلاح الدين الأيوبي` → **0.94 match** (compound given +
    asymmetric containment).
  - `G. Washington` ↔ `George Washington` → **match** (initials).
  - `detect("صلاح الدين الأيوبي")` → script=Arabic, origin=Arabic, gender=M.
  - non-name strings (`invoice 4471 …`) correctly score low.

## Notes
- Lives at `personal/DataMasterer/NectarMatcher/names/`. NectarMatcher is its
  own git repo; namematch work is on a local `feat/namematch` branch (not pushed).
- Precision-first by design: prefer the *review* bucket to a false *match*.
- Public-safe: only public-data benchmarks (ParaNames/Unihan) and synthetic sets
  are tracked; any private-source benchmarking stays in gitignored `eval/_local/`.
