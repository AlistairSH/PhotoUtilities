# PhotoUtilities

An offline Mac CLI for Canon LiDE 400 scanner acquisition, four-print Polaroid
sheet splitting, TIFF retouching, related-photo grouping, and SQLite processing history.
On `experiment/ranking-culling`, the CLI also provides experimental focus review,
relative group focus highlights, and explicit reversible review archives. Normal
analysis preserves sources; requested archives move verified copies out of active
folders and retain a verified ZIP for recovery.

Future features: General digital/RAW archival ingestion, Apple Photos import, Photomator automation, Shortcuts, and watchers
are not implemented.

## Quick start

1. Clone the repository and open its folder in your terminal or editor.
2. Ask your favorite AI agent to set up the project: “Read AGENTS.md and PROJECT.md, create `.venv`, install the dependencies, install this CLI with `pip install -e .`, and run the tests.” Dependencies: Python 3.9+, Homebrew packages `sane-backends`, `imagemagick` (version 7), and `exiftool`; Python packages `numpy==2.0.2`, `opencv-python-headless==4.11.0.86`, and `tifffile==2024.8.30` (installed automatically from `setup.py`).
3. From the repository folder, open the interactive menu:

   ```sh
   .venv/bin/photo-utils
   ```
   

## Experimental branch: batch focus review and archiving

This integration is on `experiment/ranking-culling` only; it remains unmerged into `main`. The user accepted the first full batch workflow
and authorized pushing this checkpoint to the same experimental branch. It proposes manual review, never automatic rejection.

```sh
# Scan a supported four-Polaroid page: split/rotate, group/focus, then existing edits.
.venv/bin/photo-utils scan --kind polaroids

# Process a saved supported Polaroid master with the same flow.
.venv/bin/photo-utils process-sheet "/path/to/master.tif" --kind polaroids

# Process one or several JPEG/HEIC/PNG/single-image TIFF folders.
.venv/bin/photo-utils process "/path/to/folder-one" "/path/to/folder-two"
.venv/bin/photo-utils process "/path/to/rolls" --recursive

# Explicitly request the existing edit recipe on a batch of Polaroid TIFFs.
.venv/bin/photo-utils process "/path/to/polaroid-tiffs" --retouch polaroid

# Add focus review without changing the existing analysis-only similarity command.
.venv/bin/photo-utils similar "/path/to/photos" --focus-review

# Start the report's interactive archive controls (job ID printed after processing).
.venv/bin/photo-utils review REVIEW_JOB_ID

# Restore an explicit review archive to original paths; no overwrites.
.venv/bin/photo-utils restore-archive ARCHIVE_JOB_ID
```

`process` honors embedded image orientation when decoding; it does not guess
upright orientation for untagged photos or rewrite JPEG/HEIC originals. Folders
are shallow unless `--recursive` is supplied. A combined report is written beside
the first target; `--report /existing/folder/new.html` selects another destination.
Reruns choose numbered versions; explicit filenames refuse collisions. Scanner
masters, existing retouches and `Blurry` archives are excluded from folder batch
processing. Maximum 500 source images; grouping remains Vision revision 2 <.45
OR strict SIFT. Similarity alone still does not edit/move photos. Default scan
and process-sheet now include grouping/focus before the existing TIFF edits;
`--no-focus-review` restores the previous split/retouch flow. `scan --retouch none`
still preserves an unsplit master. Ordinary print splitting remains unimplemented:
`--kind prints` fails explicitly before acquisition/writes.

The only implemented edit profile is the existing Polaroid TIFF recipe. Folder
processing defaults to `--retouch none`; requesting the Polaroid profile on
JPEG/HEIC inputs fails before processing rather than inventing digital edits.
Edits remain separate derivatives with SQLite history. `--dry-run` is no-write;
`--no-db` produces an analysis-only report without archive controls or edits.
All commands accept `--state-dir` for an isolated database.

Focus uses original sRGB pixels at 1024 and 2048 with Gaussian sigma 1. Baseline
Yes always remains Yes. Baseline uses relative subject/background measurements,
attention only when no other usable region exists, and a batch-bottom-10% global
rule (requires at least 20 images; ties conservative). The additional score is
contrast-aware edge spread, with the tested single-scale semantic confirmation
and no-semantic objectness fallback. Unsupported regions cannot clear flags.
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
retained in `experiments/ranking_culling`; they are development records, not extra
filters run by the CLI. Photographs, generated reports, databases and compiled
helpers are not included in Git. Physical acquisition of the latest scanner
wrapper remains separately unverified.

## Installation

Run from the project directory. Python 3.9 or newer is required; the Python
package is `photo_utils` and the installed command is `photo-utils`.

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

- **D — Doctor:** check scanner availability.
- **S — Scan:** acquire a new sheet or select an existing Polaroid sheet.
- **R — Retouch:** enter a TIFF/folder path and choose whether to dry-run.
- **G — Related groups:** select an image folder and create a local report.
- **H — History & Database:** browse jobs/assets/recipes, inspect lineage, export metadata, or run diagnostics.
- **Q — Quit.**

Under Scan, **S** acquires a new sheet, **P** selects an existing sheet, and
**T** is the ordinary-print placeholder; **Q** quits. New acquisition asks whether the sheet
contains Polaroids: Yes splits/retouches; No retains an unsplit master. The menu
shows the date-based master destination and asks whether to dry-run. It does not
ask for a custom folder name. Existing sheets are listed newest first, with the
newest selected by Enter. Existing-sheet processing defaults to retouching.

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
Polaroids. Use `--retouch none` to acquire only the untouched sheet.
A dry run validates scanner settings and shows the output pattern without
acquiring, reserving a master ID, or writing files/database records.

`--find-similar` analyzes saved original prints before default retouching, so
manual/recipe edits cannot disturb the initial matching. It compares the saved
prints in the output folder (normally that scan day's `prints/`, including prior
sheets), and places the report there. Similarity failure stops the follow-up;
the completed master/split outputs remain available. Existing scan behavior is
unchanged when the flag is omitted. `scan --retouch none --find-similar` is
invalid because that scan mode leaves the sheet unsplit.

`--kind prints` is a deliberate placeholder: **Print Splitting Not Implemented
Yet**, before acquisition or writes. Ordinary print pages are not treated as
Polaroids. `process-sheet` has the same `--kind` placeholder and supports
`--find-similar` with either `--retouch polaroid` or `--retouch none`.

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

The splitter requires exactly four separated Polaroids with detectable bright
borders. It rectifies the outer corners, preserves the full borders, aligns the
wide border to the bottom, and preserves sample depth and available resolution/
ICC metadata. Uncertain geometry or orientation stops processing. Mixed layouts,
touching/overlapping prints, and manual correction are unsupported.

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
spatial order: top-left, top-right, bottom-left, bottom-right. Resume preserves
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
Types are `scan`, `split`, `retouch`, `similarity`; statuses are `pending`, `running`,
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
splitting, ensure all four cards and their separated borders are in frame;
the CLI cannot provide manual corner correction. Unsupported retouch formats
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

As recorded October 10, 2026: 67 automated tests pass. Actual local
ImageMagick/ExifTool processing on a synthetic TIFF verified 16-bit RGB, system
sRGB, checksums, and no JSON sidecars. A direct physical `scanimage` acquisition
was verified at 600 dpi/48-bit RGB, and a real sheet was split into four prints.
The latest Python acquisition wrapper has simulated coverage; a physical test
of that updated wrapper and calibrated color appearance remain outstanding.

The legacy import migrated 31 metadata files, with integrity/foreign keys passing
and no changed image checksums. One pre-existing master reference was missing;
its history remains in the database. The user confirmed legacy metadata cleanup
is complete; the one-time import and cleanup commands have been retired.
See [SQLITE_IMPLEMENTATION.md](./SQLITE_IMPLEMENTATION.md) for the database
backup location and implementation checks.
See [PROJECT.md](./PROJECT.md) for confirmed decisions and deferred requirements,
and [AGENTS.md](./AGENTS.md) for development instructions.
