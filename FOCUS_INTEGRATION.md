# Branch-only focus review integration

October 12, 2026 · `experiment/ranking-culling` · no merge/push.

## Changes

The main CLI shares original, orientation-aware native decode between Vision/SIFT
similarity and Gaussian1 focus assessment. Scan/process-sheet default to group
and focus analysis before the existing Polaroid TIFF recipe. `process` handles
multiple image folders; edits are opt-in and restricted to the existing TIFF
recipe. `similar --focus-review` adds focus to the accepted analysis-only grouping
command. No arbitrary JPEG/HEIC edits or ordinary-print splitting are claimed.

Selected focus rule: baseline always wins, attention-only fallback, batch-relative
bottom-10% global evidence, global contrast with supported semantic single-scale
confirmation, and objectness contrast fallback only without semantic detections.
The rejected landmark/normalized-patch overrides are omitted. Relative group
focus comparisons share Gaussian1 measurements; directly connected photos with
comparable subject kind/count/area and ≥1.5× both metrics at both sizes can receive
sharper/softer candidate highlights. These new highlights do not change review
flags and require further real-world review, not automatic acceptance/deletion.

Reports retain subject/person/animal/objectness/attention boxes, focus flags,
relative group highlights, original links, and Delete/Undo selection. An explicit
`review JOB_ID` starts a loopback-only, tokenized session; mutation is allowlisted
by image index and rejects foreign host/origin/session requests. A static report
cannot move files. Archive confirmation creates and SHA-256 verifies a stored ZIP
before no-clobber moves. Sidecars/RAW/media companions and tracked descendants are
included, masters protected. ZIP and retained original bytes live under scan-root
Blurry. Restore refuses collisions; failures retain evidence and recorded recovery
plans in the existing schema-v1 database. No data is permanently purged.

Native pixels stream with bounded per-row memory instead of a multi-gigabyte
batch spill; Gaussian1-only calculations omit abandoned diagnostic filters.
Similarity comparisons retain their existing quadratic pair behavior. No added
Python dependencies, schema migration, public service or routine JSON sidecars.
The portable ZIP index is part of the archive; routine job/asset/recipe metadata
continues in the existing SQLite database.

## Verification

- 97 automated tests passed; strict Pyright: zero errors/warnings; Python 3.9
  compile check and Git whitespace checks passed.
- Real CLI runs with isolated state processed 52 FocusTests and 40 FocusTests2
  originals. Results exactly matched the selected experimental per-set decisions:
  19 and 26 flags. All ten explicitly reviewed focus misses remained flagged.
- Final streaming/Gaussian1-only combined run: 92 images, 4,186 similarity pairs,
  45 flags, two related sets; about 82 seconds with cached native helper.
  Initial first-build 52-image run: 95 seconds; cached-helper 40-image run: 39 seconds.
  These timings and labels describe development samples, not universal accuracy.
- IMG_0749 / IMG_0748 received sharper/softer group highlights. Native focus
  on/off comparisons on four mixed samples produced identical Vision/SIFT
  pair measurements, classifications and groups. Existing similarity tests passed.
- Source SHA-256 values were verified unchanged. Real runs used
  `/private/tmp/photo-cli-focus-test-state`; the normal production database was
  not altered. Its test database integrity and checksum checks passed.
- Synthetic-only archives verified companions, retained asset identities and
  dates, ZIP corruption refusal before moves, changed-source refusal, symlink
  refusal, master protection, rollback, restore collisions, no-clobber moves,
  and session/origin protection. No user photograph was archived or retouched.
- Synthetic browser review verified selection, Undo, archive-button availability
  and report layout. The temporary test server was stopped afterward.
- Ordinary print splitting, generic digital edits and newly acquired physical
  scanner validation remain outside this integration.

Latest combined review artifact (outside Git):
`../RankingExperiments/CLI-focus-integration-trial-01/review.html`.
Existing source images, historical reports and experimental scripts are preserved.
