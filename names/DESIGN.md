# namematch — design & SOTA survey

> Research synthesis + architecture for the culture-aware name engine.
> Companion to [`README.md`](README.md). Decisions settled with the maintainer
> 2026-06-18: **deterministic-first core, ML/LLM as opt-in plugins**; lives
> **inside `NectarMatcher`** (the v2 `nectarmatcher` fuzzy-match layer).

## 1. Problem

Detect human names with very high precision and decide cross-list identity,
across scripts (Arabic / Latin / French / Hebrew …) and cultures. Headline
cases the design must nail:

- `George Washington` ≡ `G. Washington` (initials).
- `صلاح` ≡ `صلاح الدين` *when middle/last align* — compound given name +
  asymmetric containment.
- `صلاح الدين` ↔ `Salah al-Din` ↔ `Saladin` — transliteration across scripts.
- Culture rules: Arabic middle tokens are **forefathers** (nasab), not middle
  names → low weight; Brazilian/Portuguese carry **several** surnames; Spanish
  carries **two**; French/Iberian particles (`de`, `le`, `da`) are connectives.

## 2. State of the art (survey, 2025–26)

**Name detection / origin / nationality**
- **NamePrism** — Naïve-Bayes over ~74M email/Twitter names, 39 nationality
  groups. Web API; good coverage, not local.
- **NameBERT** (2026) — mBERT fine-tune, WordPiece + [CLS] head. Current SOTA
  accuracy for name→nationality. Larger, needs a checkpoint.
- **name2nat** — bi-GRU over ~1.1M Wikipedia names, 170+ countries. Lightweight,
  local once downloaded. → our default `origin-ml` backend.
- **ethnicolr / rethnicity** — US-census-trained LSTM, race/ethnicity. Narrow
  label space, US-biased.
- *Bias note* ("Equal accuracy for Andrew and Abubakar", AI&Society 2022):
  name-ethnicity classifiers are systematically less accurate on
  under-represented groups → we keep ML advisory, never the sole signal.

**Name parsing**
- `nameparser` (rules), **`probablepeople`** (CRF; handles couples/orgs mixed in
  with people — useful as a precision gate for "is this even a person?").

**Fuzzy matching / record linkage**
- **Splink** — probabilistic Fellegi-Sunter linkage, term-frequency
  adjustments, scales to 100M+ on DuckDB/Spark. The reference for *scoring at
  scale*; our `match.py` mirrors its soft-signal→probability philosophy and is
  the natural escalation target for big list-vs-list jobs.
- **HMNI** ("Hello My Name Is") — Siamese net on internationally-transliterated
  Latin first names, **precision-prioritized**. Closest existing tool to this
  brief; a candidate `match-ml` backend.
- **Abydos** / `name-matching` — large library of phonetic + string-distance
  algorithms (Beider-Morse, Double Metaphone, editex…). Source for stronger
  phonetics when the `fuzzy` extra is installed.
- `rapidfuzz` / `jellyfish` — fast edit-distance + phonetic primitives.

**Arabic specifics**
- CAMeL Tools / Farasa — segmentation, diacritization, NER for Arabic.
- Transliteration schemes (already on disk in
  `namesdb/done/transliteration_schemes.csv`): BGN/PCGN, UNGEGN, ALA-LC, EI,
  IPA. The bridge for Arabic↔Latin identity.

**Takeaway.** No single off-the-shelf tool covers *detection + cross-script +
culture-aware matching* with a local default. The high-value, defensible core
is a deterministic lexicon+transliteration+phonetic+rules engine over the
existing corpus; ML/LLM buy the last few points of precision on hard cases.

## 3. On-disk assets reused (no downloads)

`../../namesdb/`:
- `KDBAGIV.txt` — Kalmasoft, 25k+ Arabic given names, vocalized + unvocalized,
  **gender (M/F/U)** + **country (19 ISO-2)**.
- `done/ar_*.csv`, `done/he_*.csv`, `done/isl_*.csv` — given-name gazetteers.
- `CSV_Database_Of_First_And_Last_Names.zip` — Western first + last names.
- `done/transliteration_schemes.csv` — Arabic→Latin scheme tables (BGN-PCGN,
  ALA-LC, UNGEGN, EI, IPA) for exact romanization.
- `instance_types_ar.ttl.bz2` — DBpedia Arabic person entities (future:
  real-world full-name training/eval set).

## 4. Architecture (waterfall — cheapest, most deterministic first)

```
                       ┌──────────── core (always-on, local, stdlib) ───────────┐
 input string ──▶ script.py  ──▶ normalize.py ──▶ lexicon.py ──▶ detect.py
                  (Arabic/        (tashkeel strip,   (namesdb       (is-name? +
                   Latin/…)        alef unify,        gazetteers,    origin +
                                   romanize fold)     gender/country) gender/country)
                                        │
                 parse.py ◀─────────────┘  (culture-aware: ism/nasab/nisba/kunya,
                    │                        Western, Spanish ×2, Portuguese ×N)
                    ▼
                 match.py  (role-aware alignment, asymmetric containment,
                            initials, phonetics, cross-script bridge →
                            match / review / no-match + explanation)
                       └──────────── plugins (opt-in, flag-gated) ──────────────┐
                            origin_ml (name2nat/NameBERT)   llm_judge (Claude)
```

Matching design = NectarMatcher's field-tested pattern: a **weighted bag of
soft signals → confidence → 3 buckets**, none individually required; the
**review** tier is a first-class output for the FlowerFest review queue.

### Key algorithms
- **Romanization fold** (`normalize.romanize_fold`): drop doubled letters, fold
  digraphs (kh/gh/dh/th, q↔k↔c), strip the definite article (al-/el-/ad-) and
  hamza, squeeze vowels → coarse skeleton where transliteration variants meet.
- **Compound given names** (`parse`): a head (عبد، صلاح، نور…) merges with the
  *next* token only if it's a known completer (الدين، الله…); kunya heads
  (أبو/أم) always merge. This is what makes صلاح a *prefix* of صلاح الدين rather
  than a separate forefather, and prevents over-merging family names.
- **Asymmetric containment** (`match`): align the shorter name's tokens onto the
  longer's per role; extra forefathers/middles on the longer side are *not*
  penalized. Weights: given 0.55, family 0.40, forefathers 0.10.
- **Cross-script bridge**: transliterate the Arabic side (default scheme, or the
  namesdb tables) then romanize-fold both before comparing.

## 5. Roadmap

- **v0.1 (done)** — script ID, normalization, romanization fold, lexicon load,
  origin detection, culture-aware parse, role-aware matcher, CLI, tests.
- **v0.2** — load `transliteration_schemes.csv` for scheme-accurate Arabic↔Latin
  (multi-scheme candidate generation); precision/recall harness over labeled
  pairs (mine DBpedia `instance_types_ar` + Wikipedia for an eval set);
  surname/given disambiguation; French/German/Italian gazetteers.
- **v0.3** — blocking + scale path (hand off large list-vs-list to **Splink**);
  self-learning: ingest a user list, cluster variants, extend gazetteers with
  frequency; gender/diminutive tables (Bob↔Robert).
- **v0.4** — wire `origin_ml` (name2nat first) and `llm_judge` (Claude Haiku)
  behind flags; calibrate ML blend weight against the eval harness.
- **Integration** — expose `match()` as a comparison signal inside
  `nectarmatcher`'s record-linkage scorer; feed `review` bucket to FlowerFest.

## 6. Precision discipline

The brief is *very high precision*. Therefore: ML is advisory and blended, never
sole; thresholds favor the **review** bucket over a false **match**; every
verdict ships a per-signal explanation; and the deterministic core is the
reference even when plugins are on. Evaluate with a labeled pair set before
trusting any score change (v0.2 harness).
