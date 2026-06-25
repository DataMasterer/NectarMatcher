# NectarMatcher

The fuzzy-matching / record-linkage layer of DataMasterer — the
"is this the same thing under a different name?" step.

## namematch — the working implementation

[`names/`](names/) contains **namematch**, a culture-aware human-name detection
& matching engine. Deterministic and fully local (pure-stdlib core); ML/LLM are
opt-in plugins. It can:

- **detect** — is a string a person name, and what script/origin
  (Arabic / Latin / Hebrew / …)?
- **parse** — culture-aware components (Arabic ism / nasab / nisba / kunya,
  Spanish & Portuguese multi-surname, Western).
- **match** — are two names the same person, across scripts and spellings?
  (`match` / `review` / `no-match`, precision-first).
- **dedup** — resolve a whole list into entities (phonetic blocking +
  clustering + a review queue), including cross-script.

Cross-script bridging works for Arabic, Hebrew, Chinese (Han→pinyin) and Hindi
(Devanagari). Quick start and API: [`names/README.md`](names/README.md);
design + benchmarks: [`names/DESIGN.md`](names/DESIGN.md) and
[`names/eval/DATASETS.md`](names/eval/DATASETS.md).

```bash
python -m namematch match "G. Washington" "George Washington"
python -m namematch dedup names.txt
```

## History

v1 (2017) was a ~30-line pseudocode sketch (`main.py`) of the intended pipeline.
namematch (2026) is the first real implementation, built as the
name-specialized component of this layer.
