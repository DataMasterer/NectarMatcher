# RESUME — NectarMatcher / namematch

> Session handoff. Start the next session with `/orient`.
> This repo is PUBLIC — this file stays public-safe; all private library data
> and the detailed cleanup handoff live in gitignored `names/eval/_local/`
> (read `names/eval/_local/AUTHOR_CLEANUP_HANDOFF.md` first for that workstream).

## Context
NectarMatcher hosts **namematch** (`names/`), the culture-aware name
detection/matching/dedup engine (v0.2, deterministic core + opt-in GLiNER
plugin). Current milestone: the **Calibre author/title cleanup** — its first
real consumer. Classifier quality work (3 audit rounds) is complete; what
remains is applying the results to the user's library.

## THE GATE
**Nothing else until the cleanup is applied to the Calibre library.**
Done means: the mis-filed author entries (title/junk/org export) are
reassigned or removed in Calibre, and the same-script auto-merge clusters are
merged via Calibre "manage authors". Human-in-the-loop; the library DB is
never written by tooling in this repo.

## Done this session
- `c6e5383` — Author-classifier round-3 fixes: all nine round-2 residual
  fixes (input normalization, `;`/`,` co-author rescue, three-way
  `_author_separated` with sort-form pairing + suffix/year segments,
  structural-junk filter, GLiNER person/org post-filters + person-override,
  genre-author gazetteer, weak org anchors + publisher stoplist, pipe
  corruption) + `--classes` flag feeding classification into dedup. One unit
  test per fix; 52/52 green.
- `bf4b42a` — STATUS.md: round-3 record (person buckets audit-clean; full-run
  breakdown; cluster split for application).
- Full-library re-run + a fresh model-audit round: **0/20 hard errors in all
  three person buckets** (was ~3–10%). Mid-round over-tightening caught by the
  audit and fixed before finalizing.
- Apply-phase artifacts generated in gitignored `names/eval/_local/`:
  mis-filed export, review-triage list, same-script auto-merge clusters,
  cross-script review-only clusters (see the handoff there for counts + order
  of operations).

## IN FLIGHT
None. All background runs (classification, dedup, audit) completed.

## Next steps (ranked against THE GATE)
1. Apply the mis-filed export in Calibre — start with the `title/high` slice
   (exact book-title matches, safest), then `junk/high`; reassign the real
   author from the book's other metadata or clear the entry.
2. Merge the same-script auto-merge clusters via Calibre "manage authors";
   spot-check clusters of size ≥4 first.
3. Triage the two small review lists (separated-form review bucket +
   cross-script clusters).
4. After the gate: matcher-level fix for bare-initial cross-script chaining
   (blocks cross-script auto-merge), then the STATUS.md next-levers list.

## Gotchas
- The entity model (GLiNER) reliably junks lexicon-less `Surname| Given` /
  inverted forms and Arabic transliterations of foreign names — deterministic
  evidence must override it, and name-shaped-but-unverifiable forms belong in
  `review`, not `junk`.
- Segment de-duping must NOT run before sort-form pairing (alternating
  `surname| given| surname| given` repeats the surname).
- The shared name lexicon over-credits capitalized English phrases — never use
  a bare `detect().origins` hit as person evidence for Latin strings without
  shape/context gates.
- Full GLiNER library runs take ~10–12 min on CPU; run them in the background
  and verify with stratified diff samples between runs.
- Public repo: scan every diff for personal paths/library data before
  committing; all real-data outputs stay in gitignored `names/eval/_local/`.

## Read order for next session
1. `RESUME.md` (this file)
2. `CLAUDE.md` + `names/CLAUDE.md`
3. `names/STATUS.md`
4. `names/eval/_local/AUTHOR_CLEANUP_HANDOFF.md` (private; the apply-phase
   file index and order of operations)
