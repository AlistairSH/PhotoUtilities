# PhotoUtilities

An offline Mac CLI for Canon LiDE 400 scanner acquisition, four-print Polaroid
sheet splitting, TIFF retouching, and SQLite processing history. It preserves
source images and writes separate TIFF derivatives. 

Future features: Digital JPEG/HEIC/RAW ingestion, Apple Photos import, Photomator automation, Shortcuts, and watchers
are not implemented.

## Quick start

1. Clone the repository and open its folder in your terminal or editor.
2. Ask your favorite AI agent to set up the project: “Read AGENTS.md and PROJECT.md, create `.venv`, install the dependencies, install this CLI with `pip install -e .`, and run the tests.” Dependencies: Python 3.9+, Homebrew packages `sane-backends`, `imagemagick` (version 7), and `exiftool`; Python packages `numpy==2.0.2`, `opencv-python-headless==4.11.0.86`, and `tifffile==2024.8.30` (installed automatically from `setup.py`).
3. From the repository folder, open the interactive menu:

   ```sh
   .venv/bin/photo-utils
   ```
   
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
- **H — History & Database:** browse jobs/assets/recipes, inspect lineage, export metadata, or run diagnostics.
- **Q — Quit.**

Under Scan, **S** acquires a new sheet, **P** selects an existing sheet, and
**B** returns from the scan workflow. New acquisition asks whether the sheet
contains Polaroids: Yes splits/retouches; No retains an unsplit master. The menu
shows the date-based master destination and asks whether to dry-run. It does not
ask for a custom folder name. Existing sheets are listed newest first, with the
newest selected by Enter. Existing-sheet processing defaults to retouching.

History & Database offers date-filtered jobs, recent jobs, job details,
date-filtered assets, recipe selection, asset history, job export, diagnostics,
and Back. Date prompts default to the current local date.

## Scan and process a sheet

```sh
.venv/bin/photo-utils doctor
.venv/bin/photo-utils scan --dry-run
.venv/bin/photo-utils scan
.venv/bin/photo-utils scan --retouch none
.venv/bin/photo-utils scan --root "/local/path/PhotoScans" --dry-run
```

`scan` defaults to full-bed TIFF, 600 dpi, `48-bit-color`, and Polaroid
splitting/retouching. Direct commands do not ask whether the sheet contains
Polaroids. Use `--retouch none` to acquire only the untouched sheet.
A dry run validates scanner settings and shows the output pattern without
acquiring, reserving a master ID, or writing files/database records.

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
Types are `scan`, `split`, `retouch`; statuses are `pending`, `running`,
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
