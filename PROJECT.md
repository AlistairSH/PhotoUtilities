# PhotoUtilities — current project state

Updated October 18, 2026. [README.md](README.md) documents operation;
[AGENTS.md](AGENTS.md) governs development. Dated decisions and earlier validation
are preserved in [project history](https://github.com/AlistairSH/PhotoUtilities/tree/8809e8118783bd1a15513edbd9f02f68adee305c/experiments/PROJECT_HISTORY_20261017.md).

## Status and scope

PhotoUtilities is an offline Mac Python CLI for Canon LiDE 400 sheet acquisition,
print separation/rectification, conservative visual quarter-turns, related-photo
grouping, three-tier selection review, optional Polaroid TIFF editing and explicit
reversible culling. SQLite records jobs, assets, recipes, checksums and lineage.

The user has reviewed and accepted the integrated workflow and report refinements.
The accepted integration and standalone RestorationLab checkpoint are merged into
`main` and published on GitHub. Research scripts and history are preserved on
`experiment/ranking-culling` at `8809e81`; they are not required to run the CLI,
RestorationLab, packaging or core tests and have been removed from `main`.

## Common workflows and menu

| Menu | Workflow |
| --- | --- |
| S — Scan a sheet | Choose Polaroids or ordinary prints, optional Polaroid edits and dry run; acquire, split/rectify, rotate, group and generate tier review. |
| P — Process a photo folder | Choose recursion, optional Polaroid TIFF edits and dry run; rotate, group and generate tier review. |
| E — Process an existing sheet | Select a saved master and use the sheet workflow without acquisition. |
| V — Review a previous run | Enter a completed review job ID for the local interactive session. |
| U — Restore culled photos | Enter an archive job ID; restore without overwriting and retain the verified ZIP. |
| M — Maintenance | Scanner diagnostics, history/database, grouping only and standalone TIFF retouching; Back returns to the main menu. |
| Q — Quit | Exit. |

Successful menu processing offers a local interactive review session. Explicit
commands include `scan`, `process-sheet`, `process`, `similar`, `retouch`, `review`,
`restore-archive`, `compact-archive`, `doctor`, `jobs`, `job show/export`, `assets`,
`recipe show`, `history` and `db check`. See command help for exact flags.

`scan` and `process-sheet` default to Polaroids, three-tier/focus review and visual
rotation. Polaroids default to the fixed edit recipe; ordinary prints default to
no edits. `--retouch none` still splits and reviews. `scan --capture-only` saves an
unsplit master. `process` defaults to no edits and shallow folders; its menu offers
recursive processing by default. `--open-review` starts the local review command,
which prints the browser URL. `--no-tier-review` selects focus-only reporting;
`--no-auto-rotate` uses embedded orientation only. Sheet commands can skip analysis
with `--no-focus-review`; adding `--find-similar` then requests legacy grouping.

## Image inputs and sheet splitting

Folder analysis supports JPEG, HEIC/HEIF, PNG and single-image TIFF, with at most
500 images per run. RAW/video/multi-page TIFF ingestion is unsupported. Folder
processing excludes scanner masters, generated retouches/rotation derivatives and
Blurry archives. Source pixels are analyzed before optional edits.

Polaroid splitting requires four separated bright bordered cards, rectifies outer
corners, preserves borders and aligns the wide border to the bottom. Ordinary
splitting supports 1–20 separated rectangular prints against a uniform contrasting
background, with clear outer margins. Prints can vary in size. Uncertain boundaries
stop processing; overlapping/touching layouts and manual corner correction remain
unsupported. Perfectly aligned touching prints can appear to be one rectangle.
Ordinary-print physical scanner validation is still pending.

## Visual orientation

Embedded orientation is applied first. Native upright face/body-pose evidence
compares four quarter-turn candidates; a conservative confidence/margin rule must
clearly favor one. Uncertain images remain unchanged. There is no horizon
straightening, forced orientation or automatic landscape/portrait assumption.

Corrected views feed grouping and ranking. Persisted workflows save separately
verified full-resolution TIFF rotation derivatives under `rotated/`, preserving
source bytes, sample depth, metadata and SQLite parent/date relationships. Optional
edits use the upright derivative when one exists. `--no-db` changes analysis views
only and produces neither rotation derivatives nor archive controls.

Normal reports show applied rotation notes but **no unknown-orientation comment**.
Stored uncertainty is retained; most visually unconfirmed sample images were
already upright. The standalone object/attention-below-boundary hypothesis is not
adopted: on 89 user-reviewed images, five needed rotation, neither method recovered
any of those five, and each proposed six incorrect rotations. This evaluates the
specific long-edge boundary/region-box heuristic, not every saliency approach.
User clarified that unmarked choices in that particular export mean original 0°;
do not generalize that convention to other unlabeled experiments.

## Grouping and selection policy

Accepted grouping remains Vision revision 2 distance <.45 OR strict SIFT. No hash
or Czkawka signal participates. Likely/potential sets allow chaining; not every
pair must match. Similarity is candidate grouping, not identity or retention proof.
`similar` remains grouping only unless `--focus-review` or `--tier-review` is added.

Three-tier evidence uses native Vision aesthetics/utility, highest face capture
quality, eye/smile observations, Gaussian1 regional detail, display-view endpoint
clipping and saliency layout. No Foundation Models language-model prompt or
external downloaded aesthetic model runs in the CLI. Missing observations remain
unassessed. Composition alone is advisory and cannot cause Possible Cull. No
quotas force a winner or rejection. Solos use the full actual batch as reference.
Exact policies/settings and measurements are retained in SQLite and application
modules `tiers.py`, `focus.py` and their supporting modules.

Focus review retains the selected Gaussian1 baseline, attention-only fallback,
10% cohort tail, contrast/scale confirmation and no-semantic object fallback.
Relative sharper/softer highlights require directly matched photos, comparable
subject evidence and >=1.5× both focus metrics at both sizes. Focus flags remain
independent of tiers and never automatically select photos for archiving.

### Accepted report presentation

- Coloured bars above previews: green **Top Pick**, blue **Keep & Review**, orange
  **Possible Cull**. Internal stored tier `Review` is displayed as Keep & Review.
- Positive focus warning: **Possible Missed Focus**. Unflagged photos retain
  `Focus review: No` without an explanatory note or a sharpness certification.
- **Rank within set: x/y** follows displayed order and that set's size; ungrouped
  photos use the ungrouped set. Stored full-batch ranks/reference evidence remain.
- Boxes legend: **Boxes: red - faces, green - people, orange - animals, purple -
  objects, cyan - attention areas.** Display object/objects rather than objectness;
  keep native detector keys unchanged.
- Omit the removed introductory experimental-flags paragraph and unknown-orientation
  notes. Retain useful positive reasons, subject boxes, original links and controls.

## Preservation, edits and archives

Masters and original photos are immutable. Never silently overwrite an image,
rename existing originals, auto-delete a photo or infer a retention decision from
quality, scene labels, tier, notes or ungrouped membership. New derivatives use
checksums, collision refusal and atomic publication; interrupted work retains state.

The sole edit profile is `polaroid`, applied to the entire 16-bit RGB TIFF including
its border: sigmoidal contrast `4x35%`, gamma `1.70`, level `5%,98.5%`, gamma `1.09`,
red-channel gamma `1.04`, sRGB conversion/assignment and 16-bit output. Preserve its
confirmed recipe and compatible metadata. Generic JPEG/HEIC edits are unsupported.

Only explicit Delete selections followed by confirmation invoke archives. The
loopback-only tokenized review session allows only job-listed images and rejects
foreign hosts/origins. Static reports cannot move files. Archive original bytes,
companions and tracked descendants only after ZIP/member checksum verification;
protect parent scanner masters. Completed archives retain only verified ZIPs in
`Blurry/YYYYMMDD-archive` folders with collision suffixes. Restore refuses collisions,
retains the ZIP and preserves identities/dates/lineage. Recovery evidence survives
failures; never purge archival ZIPs. `compact-archive` converts older archive layouts.

## Identity and database contract

New scans use initiation-date `YYYYMMDD/{masters,prints,retouches}/` layout. Names
retain master/print identity: `YYYYMMDD-NNN-master.tif`,
`YYYYMMDD-NNN-PP-print.tif`, `YYYYMMDD-NNN-PP-retouch.tif`; explicit retouch history
adds `-v02` etc. Reserve master IDs atomically; failures and deletions consume IDs.
Polaroids use top-left/top-right/bottom-left/bottom-right order; ordinary prints
use spatial row order. Resume preserves assigned geometry and print identities.
Derivatives inherit the source scan date; never guess original capture dates.

The existing schema-v1 `jobs.sqlite3` is the sole routine tracking database,
by default under `~/Library/Application Support/PhotoUtilities`. Use `--state-dir`
or `PHOTO_UTILITIES_STATE_DIR`; respect scan-root database bindings and migrated
counters. Routine metadata belongs in SQLite, not JSON sidecars or a second DB.
JSON export is explicit; standalone research artifacts may retain experiment
records outside Git. Legacy metadata import/cleanup is complete and retired.
Back up SQLite before schema changes; use versioned migrations, transactions,
foreign keys and indexed lineage. Never reset the DB to bypass a binding error.

## Verification and limits

Recorded integration checks: 113 core tests and strict Pyright passed. Promoted
arithmetic exactly reproduced the cached 93-image tiers (5/60/28). A fresh run of
the then-154-image PhotoSamples produced 12 Top Pick, 115 Review, 27 Possible Cull,
23 groups and 86 ungrouped images, with source hashes unchanged. These are dated
sample outcomes, not current inventory promises or general accuracy estimates.

Four quarter-turn copies of one portrait recovered upright; an isolated persisted
run verified tiers, three rotated derivatives, depth/pixels, lineage, integrity,
foreign keys and checksums. Synthetic tests cover archive/restore, source changes,
ZIP corruption, collisions, rollback and HTTP protections. No real sample photo was
archived by these validation runs. Later report wording/layout checks were targeted;
these recorded checks do not claim a fresh full-suite run for documentation edits.

Direct SANE 600 dpi/48-bit acquisition and a real four-Polaroid split were previously
verified. The latest acquisition wrapper, ordinary-print hardware acquisition,
higher DPI settings, calibrated ICC appearance and broad orientation/ranking
accuracy remain unverified. Similarity comparisons grow quadratically.

## Samples, research and deferred work

Use `../PhotoSamples/` for future focus, group and quality experiments. Inventory
may change; verify paths and checksums, explicitly record missing inputs and never
silently substitute similarly named photos. Preserve samples; use isolated state
and disposable copies for editing/archive tests. Private photos, previews, reports,
DBs, binaries and model weights stay outside Git and off remote inference services.

Historical focus, aesthetics, Foundation Models, metadata, face-capture and cascade
experiments are preserved in the [experimental branch snapshot](https://github.com/AlistairSH/PhotoUtilities/tree/8809e8118783bd1a15513edbd9f02f68adee305c/experiments);
research artifacts are separate from CLI features. Only the selected native measurement/tier policy was
promoted. Orientation saliency is a rejected standalone fallback trial.

RestorationLab is a related but separate, effectively complete film-restoration
tool worth preserving for occasional future rolls. Its active runners, historical
algorithm source, dependency snapshot and licensed SCUNet architecture are versioned
under `RestorationLab/`; see [its README](RestorationLab/README.md). The existing
private environment, weights, real input lists, manifests, audits and reference
photos remain in sibling `../RestorationLab`, with outputs in `../Restored`. Active
versioned runners accept explicit workspace/data paths; they are not photo-utils
commands, menu items, pipeline stages or installation dependencies. Preserve the
standalone restoration manifests rather than adding them to main CLI SQLite.
No photographs, model weights or runtime environments are committed. Digital
archival ingestion/RAW support, generic edits, Photos import/export and library
interoperability, Photomator automation, capture-date overrides, mixed/overlapping
sheet layouts, manual geometry correction, Shortcuts and watchers remain deferred.
