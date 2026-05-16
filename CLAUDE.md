# NectarMatcher — repo context

## What this is

NectarMatcher is the v1 **fuzzy-matching layer** for DataMasterer.
The intent: given two collections of records (CSV / JSON / SQL
output), score and link them via phonetic similarity, letter-
statistics hashes, and domain-aware enhancements (movie names,
book names, location names).

Bee theme: after scent-foraging finds flowers, bees match each
flower's **nectar** to others of the same kind. NectarMatcher is the
"is this the same thing under a different name?" step.

## Status

- **Last functional update: 2017** — only the initial commit + a
  `.gitignore` add are in the history.
- **2026-05-16 housekeeping** (`6fccbd0`): added `__init__.py` and
  `main.py` — the latter is a 30-line pseudocode sketch of the
  intended pipeline, not running code.
- **No real implementation has ever been written.** This subproject
  exists as design intent only.

## What's actually in `main.py` (pseudocode)

```
# two csv files are entered
# give each record ids
# calculate some scores based on
#   phonetics
# calculate some hashes based on
#   letter statistics
# calculate some enhanced matches based on
#   datatype (movienames, booknames, locationnames)
# allow adding metadata and bins through GUI
# two files with json lists are produced
list1_file = preparefilelist(file1)
list2_file = preparefilelist(file2)
…
save_scores(record1, scores)
cleanup_and_process_saved_scores(options)
```

The body calls undefined functions (`preparefilelist`, `nectarmatch`,
`compare_and_enhance`, `check_target_reached`, `save_scores`,
`cleanup_and_process_saved_scores`). The value is the **named
stages** — those are the API the v2 implementation should respect.

## How this maps to v2

This subproject is the **v1 ancestor of `nectarmatcher` in
DataMasterer v2** (per the bee-themed package layout). The v2
implementation should be the first one ever written and is informed
by what the disk-toolkit field study learned about fuzzy matching:

- **Content-hash matching is decisive when available.** The
  disk-toolkit's `dedup-loose-vs-lib.py` used SHA-256(first 64 KB +
  last 64 KB + size) and hit a 92.5 % match rate against a cleaned
  library. v2's `nectarmatcher.content_hash` should ship this
  algorithm as the default for binary-blob dedup.
- **Title + author fuzzy match is much worse (72.5 % hit + heavy
  rate-limiting from external sources).** v2 should reserve
  fuzzy-match for the cases where no ID is available, not as the
  default.
- **Calibre's title-dedup has a 12.5 % silent rejection rate.** v2's
  calibre integration must surface the rejection stance explicitly
  (`--duplicates` policy + post-hoc merge prompts).
- The **`book_id` schema-migration story** in
  `docs/design/inspiration/disk-toolkit-cleanup-2026-05/04-phase6-fieldnotes.md`
  is the cautionary tale for nectarmatcher's record-id design: every
  per-record artifact must carry the canonical primary key from the
  moment it's created. No retro-resolution.

Recommended port order (from the fieldnotes' "Concrete v1-sprint
ordering" section):

3. `dm.calibre.cohort` context manager (depends on tag-based
   selection — first NectarMatcher-flavoured component to ship).
4. The full `find_duplicates()` + clustering primitive.
5. Cross-source completion (the `bookanchor-retier --promote` logic).

## Hygiene applied 2026-05-16

- `core.fileMode = false` (exFAT mode-flip mitigation; local config).
- The previously-untracked `__init__.py` + `main.py` were committed
  so the sketch is in git history.

## Hygiene still needed (before any push)

- The README is a 2-line stub. v2 will replace it with real content.
- No `.gitignore`; if anyone actually runs Python here, `*.pyc` and
  `__pycache__/` will pollute. Add a Python `.gitignore` even though
  there's nothing to run yet.
