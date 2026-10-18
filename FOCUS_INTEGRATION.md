# Branch-only focus review integration

October 12, 2026 · `experiment/ranking-culling` · unmerged into main; checkpoint push authorized.

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
included, masters protected. ZIP-only archives live in dated folders under scan-root
Blurry; original bytes can be restored directly from ZIP members. Restore refuses collisions; failures retain evidence and recorded recovery
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


## Accepted workflow and storage refinement

The user accepted the 475-image four-folder run (55 groups, 322 ungrouped,
228 focus-review flags, about eight minutes). Unflagged images now have no
explanatory focus comment; flags, group highlights and positive reasons remain.
The historical numerical engines/tests are retained on the [experimental branch](https://github.com/AlistairSH/PhotoUtilities/tree/8809e8118783bd1a15513edbd9f02f68adee305c/experiments/ranking_culling)
for reproducibility without adding any photo/report/database artifacts to Git.

Archive v2 uses YYYYMMDD-archive folders and collision suffixes, retains only the
verified ZIP, and restores or serves archived originals directly from members.
Temporary staging supports rollback; cleanup never removes an unverified copy.
compact-archive converts prior archives and updates the existing schema-v1 metadata.
The user authorized local commit and remote push on experiment/ranking-culling only.


Final checkpoint verification: 101 core tests plus 45 experimental tests passed;
strict Pyright reports zero errors. The existing live archive's 22 members were
verified, duplicate loose files removed, and its GUID folder replaced with
Blurry/20261012-archive. Archive asset IDs/dates/lineage match the pre-conversion
SQLite backup. The 475-image report was re-rendered, retaining 228 flags without
rescanning or recategorizing images. ZIP-only archived previews and restore are
covered by synthetic tests. No private image, ZIP, report or database is published.

## Three-tier workflow integration — October 17, 2026

The branch CLI now promotes the cached three-tier policy into production modules,
using fresh native evidence and the actual batch size. Scan and folder workflows
produce Top Pick / Review / Possible Cull with independent focus advice and the
existing explicit reversible archive controls. The menu includes those workflows,
saved sheets, previous reviews, restore and maintenance. Ordinary-print splitting
supports separated rectangular prints against contrasting backgrounds; visual
rotation uses conservative upright-face/body-pose evidence, only quarter-turns,
with separate full-resolution TIFF derivatives and SQLite lineage. Sources remain
unchanged. RestorationLab remains standalone; no Foundation Models prompts or
external aesthetic predictors are incorporated.

Verification: 113 core tests; strict Pyright zero errors. The promoted arithmetic
policy exactly reproduces the archived 93-image tiers (5/60/28). A complete fresh
154-image PhotoSamples run produced 12 Top Picks, 115 Review, 27 Possible Culls,
23 groups and 86 ungrouped images, with all source hashes preserved. It corrected
two image views and marked 89 orientations uncertain. Four disposable quarter-turn
copies of one portrait all recovered upright; a final-helper persisted run checked
four source identities, three rotation derivatives, SQLite integrity/foreign keys
and source/output checksums. Synthetic browser Delete/Undo enabled/disabled the
archive button without preselection. No real sample was archived or retouched.
Physical ordinary-print acquisition and general orientation accuracy remain
unverified; a horizon alone cannot disambiguate upside-down orientation.
