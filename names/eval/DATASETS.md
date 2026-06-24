# Benchmarks & data sources for name matching

> Catalog of external datasets to raise accuracy + measure it, across English,
> Arabic, Hebrew, Indian, Chinese names and their transliterations — plus the
> person+address direction. Companion to `../DESIGN.md`. Nothing here is vendored;
> this is a sourcing/ingest plan. License-check before redistributing any of it.

## Tier 1 — multilingual cross-script name corpora (highest value)

| Source | What | Langs / scripts | Use |
|---|---|---|---|
| **ParaNames 1.0** (LREC-COLING 2024, Wikidata-derived) | ~16M entity names aligned across languages | **400+** incl. Arabic, Hebrew, Chinese, Hindi/Indic, English | Gold cross-script *same-entity* pairs → the primary Latin↔{Arabic,Hebrew,Chinese,Indic} benchmark we lack locally. arXiv 2405.09496. |
| **NEWS Machine Transliteration Shared Tasks** (2009–2018) | Parallel name pairs mined from Wikipedia titles | EN↔{Arabic, Chinese, Hindi, Tamil, **Hebrew**, Russian, ...} | Transliteration ground truth → eval the cross-script bridge per language pair. ACL Anthology (W*-shared-task whitepapers). |
| **Wikidata** (direct) | ~2M person entities, multilingual `labels`/`aliases` | all scripts | Generate our own cross-script + alias pairs; basis of ParaNames. |
| **JRC-Names** (EU JRC) | Multilingual person/org name variants & spellings | many scripts incl. Arabic, Cyrillic, Greek | Variant/transliteration pairs; entity-linked. |
| **Amazon multilingual name dataset** | ~400k names | Arabic, English, **Hebrew**, Japanese Katakana, Russian | Transliteration training/eval; open (amazon-science). |

## Tier 2 — per-language depth

- **Indian:** **Aksharantar** (AI4Bharat, 2022) — 26M transliteration pairs across **12 Indic languages**; the largest Indic source. (arXiv 2205.03018.) Also NEWS Indic subsets.
- **Chinese:** Roman↔Han matching + **Pinyin/Jyutping** linkage studies (PMC "Alternative Name Encodings"); pinyin romanization for blocking. Author-disambiguation corpora for Chinese names.
- **Arabic:** our `../../namesdb` (Kalmasoft 25k+ given names, gender+country) + an **Arabic Wikipedia dump** for real-world Arabic person names; transliteration schemes CSV already wired (Workstream C).
- **Hebrew:** `../../namesdb/he_*` sets + NEWS EN↔HE + Wikidata HE labels.
- **English/variants & nicknames:** behindthename, US-census first/last (already in namesdb), Wikipedia redirects/aliases (Bob↔Robert, Bill↔William).
- Tooling: **`names-dataset`** (philipperemy, 160M names + country) for priors; **HMNI** transliterated-Latin training pairs.

## Tier 3 — person + **address/location** (the multi-signal direction)

For many real entity-resolution problems a name alone is insufficient and the
strongest systems blend **name + address + category + geo**. To add location:

| Source | What | Use |
|---|---|---|
| **NCVR** (North Carolina Voter Registration) | 8M+ records: first/middle/last + **residential address**, with ground-truth voter IDs across snapshots | The reference person+address linkage benchmark (English). |
| **FEBRL** | Synthetic name+address record-linkage datasets + generator | Controlled precision/recall with injected typos/moves. |
| **GeoNames** | Place names with **multilingual `alternatenames`** (incl. Arabic) | Cross-script place matching; geo-block. |
| **OpenStreetMap / Who's-on-First** | Global multilingual gazetteer | City/region normalization & matching. |
| **libpostal** | Statistical international **address parser/normalizer** (60+ countries) | Normalize/segment street addresses before matching — the address analog of `parse.py`. |

**Plan (not yet built):** add an `address` scorer alongside the name scorer and
blend (name-sim, address-sim, geo-distance, category-match) into one confidence
— following NectarMatcher's weighted-bag pattern. Name stays this module;
address/geo becomes a sibling signal. Block on geo (region/city) to keep it
scalable; hand large jobs to Splink.

## Local benchmarks already built (this repo)

- **Synthetic** (`build_dataset.py` → `pairs.tsv`, 552 pairs): variant clusters
  from on-disk `*_det.xml` + curated headline cases (initials, arabic-subset,
  cross-script, iberian). Baseline strict P 0.90 / lenient R 0.96.
- **ParaNames cross-script** (`paranames_derive.py`): public Wikidata person
  pairs, EN↔{AR,HE,ZH,HI}, 4,000 each — see the table below.

> For benchmarking against a *private* labeled list, the `eval/_local/`
> directory is gitignored: keep any source data + derived artifacts there so
> nothing private is ever committed.

## Cross-script benchmarks: BUILT (from ParaNames)

We ingested **ParaNames** (Wikidata, CC-BY-SA): person pairs filtered from the
1 GB release per language, sampled into committable benchmarks.

- Builder: `paranames_derive.py --lang {ar,he,zh,hi}` (raw extracts gitignored
  in `_local/`; the sampled `paranames_en_<lang>.tsv` — public names +
  attribution — are committed, 4,000 pairs each).

| Benchmark | strict P | strict R | lenient R | bridge |
|---|---|---|---|---|
| **EN↔AR** | 0.95 | **0.82** | 0.87 | scheme translit + consonant skeleton |
| **EN↔HI** | 0.93 | **0.81** | 0.90 | Devanagari map + skeleton |
| **EN↔ZH** | 0.93 | **0.60** | 0.71 | Han→pinyin (Unihan) + joined compare |
| **EN↔HE** | 0.94 | **0.45** | 0.64 | Hebrew soft+hard candidates + skeleton |

All four bridge cross-script now (precision held ~0.93–0.95). Mechanics:
- **Consonant skeleton** (`normalize.consonant_skeleton`, bridged-only): drops
  the short vowels Arabic/Hebrew omit and folds v/p→f/b, j→g. Lifted AR strict
  recall **0.49 → 0.82** with **no same-script regression** (synthetic harness
  unchanged).
- **Hindi**: flat Devanagari→Latin map; vowels are approximate but the skeleton
  carries it → 0.81 recall.
- **Chinese**: 44k-char Han→pinyin table from **Unihan** (`kMandarin`, committed
  at `namematch/data/han_pinyin.tsv`, Unicode license); name compared as joined
  pinyin vs space-stripped Latin (习近平 → `xijinping`).
- **Hebrew**: two romanization candidates (bet=b/v, pe=p/f, shin=sh/s) + skeleton.

**Open levers:** ZH (0.60) loses on Wade-Giles / non-pinyin English renderings
and name-order — add a romanization-variant set + NEWS EN↔ZH. HE (0.45) wants
niqqud/scheme-aware vowels + the `he_*` namesdb gazetteers. HI could add
schwa-deletion. Add **NEWS EN↔{AR,ZH,HI}** for scheme-level tuning.

## Suggested ingest order

1. **ParaNames EN↔{AR, HE, ZH, HI}** → first true cross-script benchmark (gates
   the transliteration work end-to-end).
2. **NEWS EN↔AR** → per-scheme transliteration tuning.
3. **Aksharantar** → Indic coverage; **Pinyin** tables → Chinese.
4. **NCVR + libpostal** → stand up the person+address multi-signal prototype.
