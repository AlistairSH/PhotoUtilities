# PhotoUtilities

An offline Mac CLI for pre-process and scanning before importing into primary photo edit/management tools. Optionally starts with scanning sheets of images with sheet
splitting. Pre-procession includes conservative visual rotation, related-photo grouping, and a three-tier review with optional culling. Scan flow includes optional automatic editing of Polaroid TIFFs. A SQLite DB preserves processing history and source/derivative relationships. Originals are retained.

This describes the integrated `experiment/ranking-culling` checkpoint. It has not
yet been merged into `main`.
[RestorationLab](RestorationLab/README.md) is a related, separate film-restoration
tool whose effectively complete source is preserved here for occasional use. RAW ingestion,
generic photo edits, Apple Photos import, Photomator automation, Shortcuts and
watchers are not implemented.

## Quick start

1. Clone the repository and open its folder in your terminal or editor.
2. Ask your favorite AI agent to set up the project: “Read AGENTS.md and PROJECT.md, create `.venv`, install the dependencies, install this CLI with `pip install -e .`, and run the tests.” Dependencies: Python 3.9+, Homebrew packages `sane-backends`, `imagemagick` (version 7), and `exiftool`; Python packages `numpy==2.0.2`, `opencv-python-headless==4.11.0.86`, and `tifffile==2024.8.30` (installed automatically from `setup.py`).
3. From the repository folder, open the interactive menu:

   ```sh
   .venv/bin/photo-utils
   ```
   

## Main workflows: three-tier review and reversible culling

The user has accepted the integrated workflow and report presentation. Tier labels
help manual selection; they never automatically select photos for archiving.

```sh
# Scan four Polaroids: split/rotate, group/tier review, then the fixed edit recipe.
.venv/bin/photo-utils scan --kind polaroids
.venv/bin/photo-utils scan --kind prints --open-review
.venv/bin/photo-utils scan --kind polaroids --retouch none
.venv/bin/photo-utils scan --capture-only

# Process a saved supported Polaroid master with the same flow.
.venv/bin/photo-utils process-sheet "/path/to/master.tif" --kind polaroids

# Process one or several JPEG/HEIC/PNG/single-image TIFF folders.
.venv/bin/photo-utils process "/path/to/folder-one" "/path/to/folder-two"
.venv/bin/photo-utils process "/path/to/rolls" --recursive --open-review

# Explicitly request the existing edit recipe on a batch of Polaroid TIFFs.
.venv/bin/photo-utils process "/path/to/polaroid-tiffs" --retouch polaroid

# Add focus review without changing the existing analysis-only similarity command.
.venv/bin/photo-utils similar "/path/to/photos" --focus-review

# Start the report's interactive archive controls (job ID printed after processing).
.venv/bin/photo-utils review REVIEW_JOB_ID

# Restore an explicit review archive to original paths; no overwrites.
.venv/bin/photo-utils restore-archive ARCHIVE_JOB_ID
```

`process` defaults to Top Pick / Keep & Review / Possible Cull review and visual quarter-turn
rotation after honoring embedded orientation. No horizon straightening is applied.
Upright face/people evidence must clearly favor one orientation; ambiguous scenes
retain their orientation silently in the report; uncertainty is retained in metadata.
Applied rotations have a note. Horizon measurements alone
cannot resolve upside-down ambiguity. Corrected analysis views drive grouping and
ranking. When using SQLite, full-resolution losslessly compressed TIFF derivatives
are saved under `rotated/`, with retained depth/metadata, source checksums and lineage;
original JPEG/HEIC/TIFF files are never overwritten. `--no-db` rotates analysis views
only. `--no-auto-rotate` uses embedded orientation only.

Folders are shallow unless `--recursive` is supplied. A combined report is written
beside the first target; `--report /existing/folder/new.html` selects another path.
Reruns choose numbered versions; explicit filenames refuse collisions. Scanner
masters, existing retouches, `rotated/` and `Blurry` archives are excluded. Maximum
500 source images; grouping remains Vision revision 2 <.45 OR strict SIFT.
`similar` retains grouping-only behavior; add `--tier-review` for three tiers or
`--focus-review` for the older focus report.

`scan` and `process-sheet` split/rectify prints, rotate, generate tier review and
then apply optional Polaroid edits. `--retouch none` skips edits **but still splits**;
`scan --capture-only` explicitly saves an unsplit master. `--no-tier-review` keeps
the older focus-only report. `--no-focus-review` skips review entirely on sheet
commands unless `--find-similar` is supplied. `--open-review` starts the interactive
local archive session after processing.

`--kind polaroids` retains the four separated bordered-card layout and wide-border
alignment. `--kind prints` supports 1–20 separated rectangular ordinary prints
against a uniform contrasting background, with clear margins. Variable sizes and
counts are accepted; uncertain boundaries/touching layouts stop processing.
Perfectly aligned touching prints can be indistinguishable from one rectangle:
physically separate prints. Ordinary prints default to no auto-edit; requesting
`--retouch polaroid` for them fails before acquisition. Physical validation of the
new ordinary-print splitter remains pending.

Three-tier policy is promoted from the latest cached experiment, generalized to
the actual batch size. It uses native Vision aesthetics/utility, highest face
capture quality, eyes/smile, Gaussian1 regional detail, display-view endpoint
clipping and saliency layout. Composition is advisory only. There are no quotas;
close groups can have no Top Pick. Solos use the full batch as reference. The
full policy is in the report and SQLite. Existing focus advice stays separate.
macOS 15+ is required for tier aesthetics. No Foundation Models language-model
calls or downloaded aesthetic predictors are used. RestorationLab source is preserved under `RestorationLab/` as a separate tool;
its private runtime/data remain outside Git and it is not part of this workflow.

### Review sheet presentation

Tier labels appear in bars above each preview: green **Top Pick**, blue
**Keep & Review**, and orange **Possible Cull**. The stored tier name `Review`
is displayed as Keep & Review. Positive focus warnings read **Possible Missed
Focus**; unflagged photos show `Focus review: No` without an explanatory note.
Sharper/softer highlights remain separate from the tier.

**Rank within set: x/y** is each photo's displayed position within its related set;
for ungrouped images, it is the position within the ungrouped set. Solo tier
assessment still uses full-batch evidence; the display rank is not a global rank.

Boxes: red - faces, green - people, orange - animals, purple - objects, cyan -
attention areas. The legend uses object/objects rather than the native detector
identifier. Reports omit unknown-orientation comments and the retired introductory
experimental-flags paragraph. Useful positive reasons and applied-rotation notes
remain visible.

The consolidated `../PhotoSamples/` collection is the reference for future mixed
focus, group and quality tests. Never rewrite those originals during validation;
use isolated SQLite and disposable copies for mutation/archive tests.

The only implemented edit profile is the existing Polaroid TIFF recipe. Folder
processing defaults to `--retouch none`; requesting the Polaroid profile on
JPEG/HEIC inputs fails before processing rather than inventing digital edits.
Edits remain separate derivatives with SQLite history. `--dry-run` is no-write;
`--no-db` produces an analysis-only report without archive controls or edits.
Processing, review, history and database commands accept `--state-dir` for isolated
state; `doctor` has no state option.

Focus uses original sRGB pixels at 1024 and 2048 with Gaussian sigma 1. Baseline
Yes always remains Yes. Baseline uses relative subject/background measurements,
attention only when no other usable region exists, and a batch-bottom-10% global
rule (requires at least 20 images; ties conservative). The additional score is
contrast-aware edge spread, with the tested single-scale semantic confirmation
and no-semantic object-region fallback. Unsupported regions cannot clear flags.
Mixed material batches may change the relative baseline; no universal material
calibration is claimed. Landmark and normalized-patch overrides are not used.

Similar groups highlight relative sharper/softer candidates only for directly
matched photos, comparable subject kind/count/area, and at least a 1.5× difference
in both selected focus metrics at both sizes. This conservative new group
heuristic is not calibrated; texture, grain and framing can affect it. Relative
highlights do not change general focus-review flags. Reports contain the flags,
explanations, detection boxes, and original-image links; numerical evidence and
settings are persisted in the existing SQLite jobs/recipes for reproducibility.
Unflagged photos have no explanatory focus comment; the yes/no status and group
focus highlights remain. Positive review flags include their reason. Stored No
results remain unassessed rather than certified sharp.

A portable static report allows Delete/Undo selection, but cannot move files.
`review JOB_ID` prints a temporary tokenized loopback URL; open it while the
command is running to enable **Archive deleted photos**. Stop with Ctrl-C.
No watcher, public server, remote service or account is added. State and mutations
require the session token; archive requests reject foreign origins/hosts and
arbitrary filesystem paths. Selections are manually chosen and confirmed; the
focus flag never starts an archive automatically. Selections are not saved across
page reloads. Archived status is recovered from SQLite.

Archives default to the configured scan root's `Blurry/YYYYMMDD-archive/`;
further batches that day use `YYYYMMDD-archive-02`, `-03`, and so on. Each completed
folder contains only `deleted-photos.zip`. Every member is SHA-256 verified before
sources leave their active folders. Temporary staging permits rollback until the
ZIP and asset metadata are committed; verified duplicate loose copies are then
removed. Cleanup failures retain those copies and report the need for attention.
Matching sidecars/RAW/media companions and tracked derivatives are included;
parent scanner masters are protected. Archive requests are always explicit.

Original bytes remain recoverable from the ZIP. Asset IDs, dates and lineage
remain in SQLite with historical source paths plus ZIP/member metadata. Archived
original links read from the ZIP, and database checksum checks understand archived
members. Restore extracts into verified temporary files before publishing to the
original locations, preserves recorded permissions/mtime, and refuses changed or
occupied destinations. The ZIP remains after restore. Routine metadata stays in
the existing database; the ZIP's internal index records original paths. No separate
tracking database or routine filesystem manifest is introduced. Stored ZIP
compression favors predictable speed for already-compressed photos.

`review --archive-root /path/on/same/filesystem` selects another destination;
source and staging must share a filesystem for no-clobber moves. To convert an
older archive with retained individual copies, use:

```sh
.venv/bin/photo-utils compact-archive ARCHIVE_JOB_ID
```

Compaction verifies all ZIP members and duplicate loose copies before removing
them, converts GUID folder names to dated names, and updates asset/job metadata.
Unexpected or changed files are retained. Interrupted archive jobs have stored
recovery plans; `restore-archive` restores published ZIP contents without needing
loose copies. Failed work retains its recovery data rather than silently purging it.

Streaming native pixels avoids a multi-gigabyte temporary batch export. Only
Gaussian1 is measured during routine focus processing; unrelated experimental
filters/patches are omitted. Similarity pair comparisons still grow quadratically.
On this Mac, a cached-helper 92-image combined run took about 82 seconds, retained
all ten reviewed focus misses and produced 45 review flags. This is development-set
verification, not independently validated accuracy or a guarantee for every batch.
The first larger four-folder run processed 475 images in about eight minutes,
with 55 groups, 322 ungrouped images and 228 review suggestions. The user accepted
the workflow after reviewing its report. Historical experiment scripts/tests are
retained on the [experimental branch](https://github.com/AlistairSH/PhotoUtilities/tree/8809e8118783bd1a15513edbd9f02f68adee305c/experiments/ranking_culling); they are development records, not extra
filters run by the CLI. Photographs, generated reports, databases and compiled
helpers are not included in Git. Physical acquisition of the latest scanner
wrapper remains separately unverified.

## Installation

Run from the project directory. The default three-tier workflows require macOS
15+ and Apple Command Line Tools; grouping without tiers supports macOS 14+.
Python 3.9 or newer is required. The package is `photo_utils` and the installed
command is `photo-utils`.

```sh
cd "$HOME/Documents/PhotoScans/PhotoUtilities"
brew install sane-backends imagemagick exiftool
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/photo-utils --help
```

On Apple Silicon, if Homebrew is not on PATH:

```sh
eval "$(/opt/homebrew/bin/brew shellenv)"
```

Python dependencies are pinned in `setup.py`: NumPy, headless OpenCV, and
tifffile. ImageMagick 7 and ExifTool are separate local executables. Production
processing works offline after installation.

## Interactive menu

```sh
.venv/bin/photo-utils
```

The menu requires a terminal and offers:

- **S — Scan a sheet:** choose Polaroids/ordinary prints, optional Polaroid edits,
  then split/rotate and generate three-tier review.
- **P — Process a photo folder:** optional recursion and Polaroid TIFF edits,
  visual rotation, grouping and three-tier review.
- **E — Process an existing sheet:** reuse a saved master without acquisition.
- **V — Review a previous run:** enter the printed review job ID.
- **U — Restore culled photos:** enter the archive job ID.
- **M — Maintenance and other tools:** scanner diagnostics, history/database,
  similarity-only grouping and standalone TIFF retouching.
- **Q — Quit.**

Successful processing offers an interactive local review session for manually
selected Delete/Undo actions and confirmed reversible ZIP archival. Reports do
not preselect Possible Cull photos. Ctrl-C ends the session. The menu returns
after ordinary operations; maintenance provides a Back option.

History & Database offers date-filtered jobs, recent jobs, job details,
date-filtered assets, recipe selection, asset history, job export, diagnostics,
and Quit. Date prompts default to the current local date.

## Find related photo groups

```sh
.venv/bin/photo-utils similar "/path/to/photos"
.venv/bin/photo-utils similar "/path/to/photos" --dry-run
.venv/bin/photo-utils similar "/path/to/photos" --no-db
.venv/bin/photo-utils similar "/path/to/roll-one" "/path/to/roll-two" --report "/existing/folder/related.html"
.venv/bin/photo-utils similar "/path/to/photos" --recursive
```

Use original camera images or lab scans before manual edits where possible.
Supports JPEG, HEIC/HEIF, PNG and single-image TIFF; RAW, video and multi-page
TIFF are unsupported. Folders are shallow unless `--recursive` is supplied.
Up to 500 images per run; every image pair is compared, so large batches cost
more time. Files are deduplicated by resolved path, not by content.

The rule is Vision revision 2 distance <.45 **OR** conservative SIFT.
No hashes contribute. `--vision-threshold` changes the Vision cutoff explicitly;
the default is the tested .45. “Likely” links have Vision <.40 or both Vision
and SIFT support; other accepted links are “potential.” These are review labels,
not probabilities or identity decisions. A group is likely when all its members
connect through likely links; otherwise it appears under potential groups.
Chaining is allowed, so not every pair within a set necessarily matches.

One self-contained `similarity.html` is saved beside the images, with embedded
JPEG previews, likely/potential groups and unmatched photos at the bottom.
Click a preview to open its original; HEIC/TIFF originals may require a native
viewer. No browser server, internet assets, extra preview folder or JSON sidecar
is needed. Reruns create `similarity-v02.html` onward; explicit report filenames
refuse overwrites. Moving the HTML preserves previews, but original links remain
relative to its creation folder. Source images and their folder layout are unchanged.

Routine scores, settings, groups, checksums and source asset links are recorded
in existing SQLite as `similarity` jobs and analysis recipes. No schema change
is required. `jobs --type similarity`, `job show JOB_ID` and `history ASSET_ID`
expose results. Retouch derivative history includes source similarity recipes;
these describe the original, not a new assessment of the edited pixels.
`--state-dir` selects another state directory; otherwise existing scan-root
bindings are respected. `--no-db` writes only the HTML; `--dry-run` performs no
decoding, helper build, report or database writes. Failed inputs abort the batch;
they are not quietly classified as unmatched. Interrupted/failed runs retain
job state; rerun creates a new analysis job/report rather than overwriting history.

Requires macOS 14+ and Apple Command Line Tools (`xcode-select --install`).
The bundled Swift source builds locally on first use, cached under
`~/Library/Caches/PhotoUtilities/vision/`; no model download or PyObjC dependency.
Similarity runs locally and offline. First compilation takes longer.

Plain-English requests can use the [photo-toolkit skill](skills/photo-toolkit/SKILL.md):
“Find similar groups in this folder” or “Scan this Polaroid page and find related
photos.” The skill routes to these CLI commands; the CLI does not parse English
or contact an AI service itself.

## Scan and process a sheet

```sh
.venv/bin/photo-utils doctor
.venv/bin/photo-utils scan --dry-run
.venv/bin/photo-utils scan
.venv/bin/photo-utils scan --retouch none
.venv/bin/photo-utils scan --root "/local/path/PhotoScans" --dry-run
.venv/bin/photo-utils scan --kind polaroids --find-similar
.venv/bin/photo-utils scan --kind prints
```

`scan` defaults to full-bed TIFF, 600 dpi, `48-bit-color`, and Polaroid
splitting/retouching. Direct commands do not ask whether the sheet contains
Polaroids. Use `--retouch none` to skip edits or `--capture-only` to save only the untouched sheet.
A dry run validates scanner settings and shows the output pattern without
acquiring, reserving a master ID, or writing files/database records.

Analysis runs on saved original prints before retouching. The default tier workflow
compares this sheet's extracted prints and places the report beside them. With
`--no-focus-review --find-similar`, legacy grouping compares the saved-print folder
(including prior sheets). Analysis failure stops subsequent edits but retains
completed master/split outputs. `--kind prints` selects the ordinary-print splitter
and defaults to no edits; `--kind polaroids` retains the established four-card
splitter and default Polaroid recipe. Both support `--retouch none`.

Other scan options:

| Option | Behavior |
| --- | --- |
| `--device ID` | Select a SANE device; otherwise detect one LiDE 400. |
| `--resolution DPI` | Accepts 75, 150, 300, 600, 1200, 2400, 4800; only 600 has a recorded physical test. |
| `--mode MODE` | `48-bit-color`, `color`, `gray`, or `16-bit-gray`. Retouch requires 16-bit RGB. |
| `--root PATH` | Parent for date-based scan directories; default `~/Documents/PhotoScans`. |
| `--state-dir PATH` | Local job database directory. |
| `--folder NAME` | Deprecated compatibility option; does not override the initiation-date directory. |

Split an existing sheet, optionally without retouching:

```sh
.venv/bin/photo-utils process-sheet "/path/to/sheet.tif" --dry-run
.venv/bin/photo-utils process-sheet "/path/to/sheet.tif"
.venv/bin/photo-utils process-sheet "/path/to/sheet.tif" --retouch none
```

With `--kind polaroids`, the splitter requires exactly four separated Polaroids
with detectable bright borders. It rectifies the outer corners, preserves the full borders, aligns the
wide border to the bottom, and preserves sample depth and available resolution/
ICC metadata. Ambiguous geometry or Polaroid wide-border detection stops splitting. Visual
upright uncertainty after splitting leaves orientation unchanged. With `--kind prints`, 1–20 separated rectangular prints are supported against a uniform
contrasting background. Mixed Polaroid/ordinary layouts, touching/overlapping
prints and manual correction are unsupported.

`process-sheet --output-dir PATH` overrides the print destination while keeping
identifiers. `--retouch none` still splits the sheet. A process-sheet dry run
checks detection only; it does not subsequently retouch prints.

## Retouch TIFFs

```sh
.venv/bin/photo-utils retouch "/path/to/print.tif" --dry-run
.venv/bin/photo-utils retouch "/path/to/print.tif" --profile polaroid
.venv/bin/photo-utils retouch "/path/to/print-folder" --preview
.venv/bin/photo-utils retouch "/path/to/20261010-001-01-print.tif" --version-history
```

Retouch accepts one single-page 16-bit/channel RGB TIFF or recursively processes
TIFFs in a folder. An arbitrary compatible external TIFF needs no scan job;
it is registered without modifying or relocating its source.

The only profile is `polaroid`. Its fixed operations apply to the **entire TIFF,
including its physical border**, in this order:

```text
-sigmoidal-contrast 4x35%
-gamma 1.70
-level 5%,98.5%
-gamma 1.09
-channel R -gamma 1.04 +channel
-profile /System/Library/ColorSync/Profiles/sRGB Profile.icc
-depth 16
```

Tagged inputs are converted to system sRGB; untagged inputs are assigned sRGB.
Compatible metadata is copied with ExifTool, and output depth/profile are
verified. There is no adaptive exposure analysis, border-excluded correction,
sharpening, or generative restoration. Review the appearance of real prints;
these fixed parameters are not calibrated color restoration.

Identified prints default to their original scan date's `retouches/` directory.
For unidentified TIFFs, a single input defaults to a sibling
`<containing-folder>-retouched/`; folder inputs default to a sibling
`<folder>-retouched/` and retain relative subdirectories. `--output-dir PATH`
selects another destination. `--preview` adds a labeled `.before-after.jpg`;
it is never used to generate the TIFF. `--dry-run` writes no outputs or tracking.

Identical completed requests verify and reuse existing outputs. Changed sources,
settings, or output checksums are refused. Choose a new `--output-dir` for changed
settings, or `--version-history` for identified prints to create `-v02`, `-v03`,
and subsequent versions. The default retouch is never silently replaced.
Version history is not supported for unidentified standalone TIFFs. Process
original prints rather than chaining edits from retouched outputs.

## Data layout and identities

```text
PhotoScans/20261010/
  masters/20261010-001-master.tif
  prints/20261010-001-01-print.tif
  prints/20261010-001-02-print.tif
  prints/20261010-001-03-print.tif
  prints/20261010-001-04-print.tif
  retouches/20261010-001-01-retouch.tif
  retouches/20261010-001-01-retouch-v02.tif
```

`YYYYMMDD` is the local scan initiation date, retained across midnight and later
processing. Daily master numbers start at `001` and expand beyond `999`.
SQLite reserves IDs atomically before acquisition; failed, interrupted, and
deleted scans do not release their numbers. Print numbers start at `01` in
spatial order: top-left, top-right, bottom-left, bottom-right for four Polaroids;
ordinary prints use detected spatial row order. Resume preserves
assigned print identities; detection failure does not renumber them.

Acquisition and derivatives use temporary TIFFs and atomic publication that
refuses occupied filenames. A scan partial has a visible
`*.partial-<job-id>.tif` filename. Retrying acquisition allocates a new master ID;
interrupted derivative jobs can resume with their existing identities.

Existing photos are not automatically renamed or moved. Legacy split jobs
retain their image names. New processing of a legacy sheet registers an identity
using its LiDE filename date, or the local file modification date when original
scan initiation is unknown.

## Configuration and SQLite

The default database is
`~/Library/Application Support/PhotoUtilities/jobs.sqlite3`. It stores jobs,
assets, recipes, full processing metadata, relationships, checksums, and daily
ID counters; images remain on disk. Routine processing creates no manifest,
recipe, or job JSON sidecars. JSON export is explicit.

Processing/query commands accept `--state-dir PATH`. The environment variable
`PHOTO_UTILITIES_STATE_DIR` configures the default. Processing under a bound scan
root discovers its database unless an explicit state directory is supplied.
The scan root's `.photo-utils-database` binding prevents separate databases from
allocating IDs for that root. Existing `.photo-utils-naming.sqlite3` counters
are imported monotonically; the original ledger is not changed or deleted.
Keep the database and binding when cleaning up photos. Move the whole state
directory and update the binding only while no operations run.

Other environment variables:

| Variable | Purpose |
| --- | --- |
| `PHOTO_UTILITIES_SCANIMAGE` | Nonstandard `scanimage` executable. |
| `PHOTO_UTILITIES_MAGICK` | Nonstandard ImageMagick executable. |
| `PHOTO_UTILITIES_EXIFTOOL` | Nonstandard ExifTool executable. |
| `PHOTO_UTILITIES_PREVIEW_FONT` | Local font file for preview labels. |

Photo data must stay outside the source repository. A Documents pathname does
not guarantee freedom from iCloud syncing; choose a genuinely local root if
local-only storage is required.

## History and explicit exports

```sh
.venv/bin/photo-utils jobs
.venv/bin/photo-utils jobs --date 20261010 --type retouch --status completed --limit 20
.venv/bin/photo-utils job show JOB_ID
.venv/bin/photo-utils assets --date 20261010 --stage print
.venv/bin/photo-utils recipe show ASSET_ID
.venv/bin/photo-utils recipe show ASSET_ID --recipe-id RECIPE_ID
.venv/bin/photo-utils history ASSET_ID
.venv/bin/photo-utils job export JOB_ID --format json --output "/local/path/job.json"
```

Use IDs printed by job/asset queries; a readable filename is not a database ID.
`jobs` defaults to the 20 most recent jobs, with optional date/type/status filters.
Types are `scan`, `split`, `retouch`, `similarity`, `review-archive`; statuses are
`pending`, `running`,
`completed`, `partial`, `failed`. Job times display in the local timezone.
`assets` can filter by date, stage (`master`, `print`, `retouch`, `external`),
and stored asset status. It groups assets by their master or external source.
CLI lists have no implicit today filter.

`job show` includes metadata, family assets, available recipes, warnings, and
errors. `recipe show` displays result-asset recipes; `--recipe-id` selects one
when multiple histories exist. `history` shows chronological recipes and lineage.
`job export` includes full metadata and original stored JSON text, defaults to
stdout, and refuses an occupied output filename. It has no `--dry-run` flag;
use `job show` to inspect the data first. It exports metadata, not image files.

## Diagnostics and maintenance

```sh
.venv/bin/photo-utils db check
.venv/bin/photo-utils db check --checksums
```

Diagnostics distinguish database corruption/foreign-key errors from missing
image files; `--checksums` also checks image SHA-256 values. `db check` exits 1
for integrity errors, missing images, or changed checksums. A missing image does
not trigger deletion of its record or replacement of its master.

Schema version 1 extends the original scan-job table and adds asset/recipe/
metadata/migration/counter tables. Connections enforce foreign keys. Existing
databases are backed up through SQLite before a schema upgrade, producing
`jobs.backup-v0-<unique-id>.sqlite3` alongside the database. To restore, stop
operations, preserve the current database separately, and copy the chosen backup
to `jobs.sqlite3`, keeping the root binding pointed at that location. Never
remove the database simply to reset an error or counter.

No background watcher/service is installed. Removing `.venv` removes the project CLI but keeps
photos and state; `brew uninstall sane-backends` removes the scanner backend,
not the PhotoUtilities application.

## Troubleshooting and verification

If discovery fails, check USB and run `scanimage -L` and `sane-find-scanner -q`.
Use `--device` when multiple LiDE 400 scanners are connected. For uncertain
splitting, keep all four Polaroid borders in frame or separate ordinary prints
against a contrasting background with clear margins; manual corner correction
is unsupported. Unsupported retouch formats
must be converted separately while retaining the original source.

For a database-binding mismatch, use the root's configured `--state-dir`; do not
create another database to bypass its counters. Inspect missing-file reports
before deciding how to restore an image. Do not modify Photos library internals.

Run automated tests from the project directory:

```sh
.venv/bin/python -B -m unittest discover -q
```

Strict application type checking uses `pyrightconfig.json`, which selects the
project virtual environment and Python 3.9 compatibility. Install the optional
development checker and run it with:

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/pyright
```

Pyright may download a Node runtime on its first run. The checker covers
`photo_utils`; the regression suite verifies tests separately.

Recorded October 17 integration validation: **113 core tests passed**, strict
Pyright reported zero errors, and the promoted tier arithmetic exactly matched
all 93 cached historical tier assignments (5 Top Pick / 60 Review / 28 Possible
Cull). A fresh then-154-image PhotoSamples run produced 12 Top Pick, 115 Review,
27 Possible Cull, 23 groups and 86 ungrouped images with unchanged source hashes.
These are recorded sample outcomes, not a universal accuracy estimate or a claim
that this documentation edit reran image processing.

Synthetic checks covered source/output changes, 16-bit rotation pixels and depth,
lineage, archive/restore, ZIP corruption, collisions, rollback and local HTTP
protections. Four quarter-turn copies of a portrait recovered upright; isolated
persisted native analysis passed database integrity/foreign-key/checksum checks.
Report layout and Delete/Undo were checked using synthetic browser images.

Direct SANE acquisition at 600 dpi/48-bit RGB and a real four-Polaroid split were
previously verified. Hardware acquisition through the latest Python wrapper,
ordinary-print physical scanning, higher resolutions, calibrated colour and broad
orientation/ranking accuracy remain unverified. Analysis uses macOS 14+ Vision;
the default three-tier aesthetic measurement requires macOS 15+.

The standalone object/attention orientation fallback was evaluated on 89 available
mixed examples, including the two previously rotated photos. User labels marked
five needing rotation and 84 correct at 0°. Both methods missed all five needed
rotations and each suggested six incorrect rotations; the fallback was **not
adopted**. Its long-edge boundary was only a proxy for horizon height. Normal CLI
rotation continues to use face/body evidence and leaves uncertain images unchanged,
without a report comment. See [the standalone experiment](https://github.com/AlistairSH/PhotoUtilities/tree/8809e8118783bd1a15513edbd9f02f68adee305c/experiments/orientation_saliency/README.md).

The legacy import migrated 31 metadata files, with integrity/foreign keys passing
and no changed image checksums. One pre-existing master reference was missing;
its history remains in the database. The user confirmed legacy metadata cleanup
is complete; the one-time import and cleanup commands have been retired.
See [SQLITE_IMPLEMENTATION.md](./SQLITE_IMPLEMENTATION.md) for the database
backup location and implementation checks.
See [PROJECT.md](./PROJECT.md) for confirmed decisions and deferred requirements,
and [AGENTS.md](./AGENTS.md) for development instructions.
