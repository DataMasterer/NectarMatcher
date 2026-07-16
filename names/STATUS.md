# STATUS — namematch

> Living doc. Context in [`CLAUDE.md`](CLAUDE.md); design + SOTA in
> [`DESIGN.md`](DESIGN.md). Parent: `../STATUS.md` (NectarMatcher).

**Status:** Active — v0.2 · **Last activity:** 2026-07-15
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
- **First consumer — Calibre author dedup (integration).** `integrations/calibre.py`
  reads a Calibre `metadata.db` authors table and runs `dedup` (private library +
  output stay in gitignored `eval/_local/`). Validated on a real 11.5k-author,
  mixed Latin+Arabic library: 98.7% blocking reduction; cross-script variant
  merges work. **Surfaced + fixed a real engine bug**: a lone token (bare given/
  surname) matched every full name sharing it at 1.0 and union-find chained
  hundreds of distinct people (a 254-member junk cluster). Fix: a lone token vs a
  multi-token name is capped at *review*, never auto-merged — which also **lifted
  cross-script precision** (AR 0.95→0.98, HE 0.94→0.99, HI 0.93→0.97; recall
  flat) with no synthetic regression. Largest cluster 254→10; spurious merges
  4058→1037. Residual false merges (initials / short cross-script collisions like
  Baker↔Baqir) remain → motivate the multi-signal scorer.
- **Multi-signal scorer (roadmap #3) — done.** `namematch.match_records(a, b,
  signals)` scores a weighted bag of field signals (name via `match()`, plus
  title/year/subject/… via `cmp_fuzzy`/`cmp_exact`/`cmp_year`/`cmp_token_set`),
  bucketed match/review/no-match; absent fields are skipped (degrades exactly to
  `match()` when only a name is present). Vetoes name-only false positives:
  `Stephen King` vs `Stephen Hawking` is a name-only **match (0.885)** but a
  disagreeing subject signal demotes it to **review** — while true variants +
  agreeing fields stay match.
- **Author→books features wired into Calibre dedup.** `dedup` is now
  record-aware (`key` + `compare`); `integrations/calibre.py --books` builds a
  per-author **namespaced profile** (`t:` title words, `g:` tags, `c:` co-authors
  with hyper-common translators/editors dropped) and a veto comparator: a
  same-script auto-merge whose two authors' profiles are disjoint is demoted to
  *review*. **Size-gated** — only vetoes when both profiles are substantial
  (`min_profile`, default 8), since disjointness is only evidence of *different
  people* for prolific authors; a sparse profile is just missing data. This
  recovers sparse true-splits (`A./Arthur Conan Doyle` stay merged) while still
  splitting prolific coincidental collisions. Cross-script pairs are exempt
  (their titles are in different scripts).
- **Honest limit (well-characterized).** Series is dead in this library (0.3%),
  tags ~15%, many titles are filename junk — so book features are sparse. On
  sparse data the veto can't separate a true sparse-split (Conan Doyle, ~7
  tokens) from a false sparse-collision (`Albert Einstein`/`Bronstein`, 3–4
  tokens, disjoint): any size threshold that vetoes one vetoes the other. The
  default favors recovering true splits; the residual sparse false-merges
  (`Einstein`/`Bronstein`) are really a **name-matcher** precision issue (shared
  given + `-stein` suffix → 0.88), to fix at the matcher level — not via books.
  `min_profile` is the precision↔recall knob (lower = more vetoes → more to
  review).
- **Name-matcher suffix-precision fix.** Same-script surnames sharing only a
  *suffix* (`Einstein`/`Bronstein`, `King`/`Hawking`) over-scored on the raw
  edit-ratio fallback; combined with a shared given they crossed 0.85. Fix
  (`token_sim`): when same-script initials differ, require a strong ratio (C/K-
  type shifts are already handled earlier by the fold, and bridged/cross-script
  is exempt). Resolves the residual the book-profile veto couldn't (it was a
  name issue, not a books issue) — and it's general, not Calibre-specific.
  **Author benchmark precision 0.92 → 1.00**; cross-script (AR/HE/ZH/HI) and
  synthetic benchmarks unchanged; true variants preserved (`Mohammed`/`Muhammad`,
  `Dostoevsky`/`Dostoyevsky`, `A.`/`Arthur Conan Doyle`).
- **Author-field classification (person / title / junk).** `integrations/calibre.py
  --classify` labels each author-field entry, cross-referencing the **books'
  titles** (a title misfiled as an author is the common Calibre import error).
  Confidence-tiered + transparent. On the real library (11,502 entries): ~**1,400
  high-confidence** (814 junk-code + 605 titles matching a real book title) are
  directly actionable; person ↔ title-phrase is a **fuzzy ceiling** for
  heuristics (gazetteer-hit over-credits capitalized phrases; real non-Western
  names lack lexicon coverage), so the ambiguous middle is flagged `review`.
  `dedup` can consume this to drop junk+confirmed-titles from its input.
- **Entity-type plugin (GLiNER) — resolves the fuzzy boundary, opt-in & local.**
  `plugins/entity_type.classify(text) -> person|title|org|none` wraps **GLiNER**
  (zero-shot NER, CPU, no API; `pip install namematch[entity-type]`). It
  classifies by *structure*, so it generalizes to names in no gazetteer — a spike
  correctly labels `عبد الرحمن بن خلدون` (Ibn Khaldun), `غونتر غراس`,
  `The Swiss Gambit`→title, etc. — which a person-*index* can't (coverage + it
  goes stale as authors grow). `calibre --classify --gliner` layers it after the
  deterministic prefilters (junk-regex, book-title match handle what GLiNER is
  weakest on). Spike numbers: titles→not-person 90%, persons→person 85%, and it
  *decides* the fuzzy `review` bucket. The deterministic core stays zero-dep.
- **Full-library run + Opus multi-agent audit + fixes.** Ran `--classify --gliner`
  over all 11,502 authors; a 3-agent Opus audit found high error rates in junk
  (~40–58% false-junk) and org (~55%), with clear root causes — fixed all four:
  (#1) Arabic `surname، firstname` catalog form → person, first (+ strip bidi
  chars) — GLiNER was junking real Arabic authors; (#2) `|` is a co-author/
  authority separator, not code (removed from junk regex; `_author_separated`);
  (#3) eponymous trap — an exact book-title match no longer scrubs a
  gazetteer-backed person (`Emanuel Lasker`, `Ibn Sina`); (#4) `org` requires an
  anchor token, else persons-first. Re-run: person 6642→**8375**, junk
  3326→**2165** (false-junk), org 517→**93**. All audit-flagged errors verified
  fixed. 43/43 tests.
- **Author-classifier round 3 (audit-driven residual fixes) — done.** Implemented
  the nine round-2 residual fixes + a mid-round self-audit pass in
  `integrations/calibre.py`: shared input normalization (bidi/zero-width,
  archive suffixes, role words, honorifics, authority years); `;`/`,`
  co-author rescue with a title;subtitle guard; `_author_separated` reworked to
  a three-way verdict (high / soft→review / reject) with particle + suffix +
  year-range segment handling, sort-form surname|given pairing, and
  keyword-list rejection; a structural-boilerplate junk filter ahead of any
  title acceptance; GLiNER post-filters (`refine_person`, comma-ifying pipes
  before the model, a person-override for Arabic/nasab/initials forms the model
  reliably junks, soft forms → review not junk); a public genre-author
  gazetteer backing the eponymous veto; `refine_org` weak-anchor context +
  publisher stoplist + person-prefix split; pipe-corruption → junk. New
  `--classes` flag feeds the classification into dedup (persons only).
  **Full-library re-run:** person 8,375→8,505, junk 2,165→2,088, title
  869→796, org 93→81, review 32. **Round-3 Opus audit: 0/20 hard errors in all
  three person buckets** (was ~3–10%); residuals are minor title↔junk slippage
  and lexicon-less transliterations. Cluster split for application: same-script
  auto-merge vs cross-script review (bare-initial cross-script chaining is the
  next matcher-level lever). 52/52 tests.
- **Author benchmark — added.** `eval/authors.tsv` (curated public authors, no
  PII): initials / diacritics / cross-script positives + same-given & short
  cross-script negatives. Name-only baseline strict P 0.92 / R 1.0 (one FP =
  the Stephen King/Hawking case, which #3 resolves with a second signal).
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
