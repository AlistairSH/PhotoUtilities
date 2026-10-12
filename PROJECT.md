# PhotoUtilities

Current project scope and confirmed decisions, updated October 12, 2026.
See [README.md](./README.md) for installation, commands, and troubleshooting.

## Status and next objective

**Phase 1: functional / done-ish.** The documented 2x2 LiDE 400 Polaroid workflow has worked on actual samples: SANE 600 dpi 48-bit capture, four-print detection/rectification, fixed ImageMagick retouch, immutable TIFFs and SQLite job/asset/recipe tracking. Do not call it feature-complete: the updated Python acquisition wrapper has not been recorded as physically verified; mixed/touching layouts, calibrated ICC, broader input formats, Photos import and quality assessment are unimplemented. The README is the operational record; test counts below are historical, not results from this documentation change.

**Phase 2: related-photo grouping is implemented and accepted.** The existing CLI uses local Vision + SIFT, SQLite source-asset relationships, a lightweight HTML report and the photo-toolkit skill. Technical quality assessment and further editing automation remain deferred. No generative image reconstruction.

## Current application

PhotoUtilities is an offline Python CLI for Canon LiDE 400 scanner sheets and
compatible TIFF retouching on an Apple Silicon Mac running macOS Tahoe 26.
It uses SANE `scanimage` for acquisition, NumPy/OpenCV/tifffile for splitting,
and ImageMagick 7/ExifTool for retouching and metadata handling.

Implemented commands:

```text
photo-utils                         interactive menu
photo-utils doctor
photo-utils scan [--root PATH] [--state-dir PATH] [--dry-run] [--retouch polaroid|none]
photo-utils process-sheet SOURCE [--output-dir PATH] [--dry-run] [--retouch polaroid|none]
photo-utils retouch TARGET [--output-dir PATH] [--profile polaroid] [--preview] [--version-history] [--dry-run]
photo-utils similar TARGET... [--recursive] [--report PATH] [--no-db] [--dry-run] [--state-dir PATH]
photo-utils jobs [--date YYYYMMDD] [--type scan|split|retouch|similarity] [--status STATUS] [--limit N]
photo-utils job show JOB_ID
photo-utils job export JOB_ID [--format json] [--output PATH]
photo-utils assets [--date YYYYMMDD] [--stage master|print|retouch|external] [--status STATUS]
photo-utils recipe show ASSET_ID [--recipe-id RECIPE_ID]
photo-utils history ASSET_ID
photo-utils db check [--checksums]
```

Processing/query commands accept `--state-dir`; see their `--help` for all
options. The menu offers Doctor, Scan, Retouch, Related Groups, History & Database, and Quit.
Submenu exit options are labelled Quit and exit the CLI; no Back navigation is implemented.
Scan offers new acquisition or selection of an existing sheet. Only the
interactive new-scan flow asks whether the sheet contains Polaroids; direct
`scan` defaults to splitting/retouching unless `--retouch none` is supplied.

The sheet processor requires exactly four separated Polaroids with detectable
borders. It rectifies the outer corners, retains the borders, aligns the wide
border to the bottom, and preserves sample depth and available resolution/ICC
metadata. Uncertain detection/orientation stops processing; manual correction,
touching/overlapping prints, and mixed layouts are not implemented.

## Confirmed user decisions

- Keep production processing, photos, and metadata local. The project now has an existing GitHub repository; experimental code may be developed on a branch, but no automatic push/merge, no photo/database commits, and no cloud processing, telemetry, accounts, or paid service dependency.
- Preserve untouched sheet masters and extracted print sources. Never silently overwrite an image or automatically delete/reject photographs.
- Use the fixed `polaroid` ImageMagick recipe on the entire 16-bit RGB print TIFF, including its border: sigmoidal contrast `4x35%`, gamma `1.70`, level `5%,98.5%`, gamma `1.09`, red-channel gamma `1.04`, sRGB profiling, and 16-bit output. The retired `faithful` profile is not a CLI option.
- The user confirms the current polaroid profile works as intended. `photo_utils/retouch.py` defines its settings; SQLite recipes record the effective settings used for each output.
- Convert tagged retouch inputs to the system sRGB profile; assign sRGB to untagged inputs. Preserve compatible metadata and record effective parameters/backend versions in SQLite.
- `scan` and `process-sheet` default to `--retouch polaroid`. `scan --retouch none` keeps an unsplit master; `process-sheet --retouch none` still splits but skips retouching.
- Standalone retouch accepts one compatible TIFF or a recursive TIFF folder and can register an external source without requiring a scan job.

## File organization and identifiers

The repository is `~/Documents/PhotoScans/PhotoUtilities`. Photo data stays
outside it. The default scan root is `~/Documents/PhotoScans`; `scan --root`
selects another parent. Documents may be iCloud-synced; its pathname alone does
not guarantee local-only storage.
 
New scans use `YYYYMMDD/{masters,prints,retouches}/` under the root, based on
local scan initiation date. All derivatives inherit that date, even when
processed later. Names are:

```text
YYYYMMDD-NNN-master.tif
YYYYMMDD-NNN-PP-print.tif
YYYYMMDD-NNN-PP-retouch.tif
YYYYMMDD-NNN-PP-retouch-v02.tif     explicit version history
```

Daily master numbers start at `001`, are reserved atomically before acquisition,
and expand beyond `999`. Failed, interrupted, or deleted scans consume their
IDs. Prints are numbered top-left, top-right, bottom-left, bottom-right; resume
preserves assigned geometry/identities. Identical completed retouches are
verified/reused; changed outputs or settings are refused. `--version-history`
creates subsequent numbered versions for identified prints.

`--folder` is accepted only for backward compatibility and does not change the
scan date directory. The menu no longer asks for a custom scan folder.
`--output-dir` explicitly overrides derivative destinations while retaining IDs.
Identified prints default to the original date's `retouches/`; unidentified
standalone TIFFs retain the sibling `-retouched` directory behavior.

Existing photos are never automatically renamed or moved. Existing legacy
split jobs retain their image names. New processing of a legacy sheet registers
a persistent identity using its LiDE filename date, or local modification date
when the original scan date is unknown.

## SQLite tracking

The existing `jobs.sqlite3` is the single tracking database. Its default state
directory is `~/Library/Application Support/PhotoUtilities`; configuration is
through `--state-dir` or `PHOTO_UTILITIES_STATE_DIR`. Scan-root bindings prevent
separate databases from allocating IDs for the same root. Existing naming
ledgers are read-only migration inputs; counters are never reset.

Schema version 1 extends existing scan jobs and adds assets, recipes, complete
metadata records, migration tracking, and naming counters. Jobs/assets/recipes
have indexed relational identities, parents, dates, stages, and statuses;
variable fields retain their full JSON-compatible TEXT structure. Imported
original JSON text preserves numerical precision. Images are not SQLite BLOBs.
Schema changes back up existing SQLite first and use repeatable transactions
with foreign keys enabled.

Routine processing writes no manifest/recipe/job JSON sidecars. JSON export is
explicit. The user confirmed legacy metadata cleanup is complete. The one-time
legacy import and cleanup commands have been removed; imported history remains
in SQLite.

## Verification and known limits

Application modules pass Pyright strict checking with Python 3.9 compatibility;
`pyrightconfig.json` selects the project virtual environment. See README for
the optional development checker and regression commands.

- Direct physical `scanimage` acquisition was verified on this Mac at 600 dpi and 48-bit RGB (three 16-bit samples per pixel). Acquisition through the latest Python wrapper has simulated coverage, not a recorded physical verification. Higher advertised resolutions remain untested.
- A real scanner sheet was split into four 16-bit RGB derivatives. Other sheet layouts and calibrated color appearance remain unverified.
- The SQLite implementation passed 67 current automated tests and an actual ImageMagick/ExifTool run on a synthetic TIFF with 16-bit RGB, sRGB, checksums, and no JSON sidecars.
- The October 10 legacy import migrated 31 metadata files; database integrity and foreign keys passed. One old master reference was already missing. The user subsequently confirmed legacy JSON cleanup is complete. Details are in [SQLITE_IMPLEMENTATION.md](./SQLITE_IMPLEMENTATION.md).

## Accepted similarity feature — October 11, 2026

The user authorized integrating Vision <.45 OR strict SIFT into the existing
toolkit, preserving image folders and adding a lightweight HTML review report
beside images. `photo-utils similar` accepts standalone camera/lab photos;
JPEG/HEIC recent test batches were camera images, not all scans. Original scans
or camera images should be analyzed before manual edits. Reports list likely
and potential groups and unmatched photos, with embedded previews and no
diagnostic scores. Chaining is retained; no culling or photo relocation.

Routine analysis is persisted in existing schema-v1 SQLite jobs/recipes linked
to source asset identities. Derivative history includes inherited source
similarity analysis. No additional tracking database or schema migration.
`--no-db` and no-write `--dry-run` remain available. `scan`/`process-sheet`
support opt-in `--find-similar`, after saving prints and before retouching.
The saved-print output folder is the comparison set, normally all prints from
that date. Existing processing without the flag is retained.

The user requested an ordinary-print splitting placeholder: `--kind prints`
must error with `Print Splitting Not Implemented Yet` before scanning/writing.
Actual ordinary-print splitting remains deferred. The local photo-toolkit
skill routes plain-English prompts to these commands; it is not an English
parser or cloud inference dependency inside the CLI.

Integration verification: 81 automated tests passed; strict Pyright reports zero
errors. The integrated native CLI reproduced the existing 60-image grouping
exactly (20 sets, seven unmatched), and the five HEIC images connected as one
set. Persistence/integrity checks used isolated SQLite; the production database
and source checksums were unchanged. Embedded previews and original links were
checked, the Swift helper is included in the source distribution, and the
installed skill passed its standard validator. Scan follow-up order has
simulated coverage; no new physical scanner acquisition was performed.

The user reviewed 13 recursive photo batches (1,205 original images), with
143 candidate groups and 820 unmatched images, and accepted this as a permanent
feature. Sources remained unchanged. Pure feasibility/benchmark scripts and
historical experiment notes are retained only on `experiment/apple-vision`.
Production regression tests remain with the feature.

## Deferred requirements

Earlier goals for digital JPEG/HEIC/RAW folder ingestion, checksummed digital
archival, conservative quality review, capture-date overrides, image export for
Apple Photos, and explicit supported Photos import remain unimplemented.
The existing `job export` exports metadata JSON, not photos to Apple Photos.

Photomator automation, Shortcuts, inbox watching, broader sheet layouts, and
manual correction are also deferred. Do not begin them without a new user task.
If added later, retain RAW/sidecar/Live Photo relationships, verify archived
copies before editing, never invent capture dates for scanned prints, and keep
quality screening optional with no automatic deletion. Verify external tool
support on this Mac before promising automation or import capabilities.


## Branch-only focus-review integration — October 12, 2026

On `experiment/ranking-culling` the user authorized main-CLI integration of the
selected experimental focus policy and reversible manual culling archives. This
has not been merged/pushed. `process` handles one/multiple folders with embedded
orientation, accepted similarity grouping and focus review before optional
existing Polaroid TIFF edits. Scan/process-sheet include group/focus review before
retouch by default, with `--no-focus-review` opt-out. Ordinary print splitting,
general JPEG/HEIC edits, guessed upright rotation and RAW ingestion remain deferred.

The selected policy preserves baseline Yes, Gaussian1, attention-only fallback,
10% global cohort tail, global contrast with semantic scale confirmation and
no-semantic objectness fallback. Failed landmark/patch overrides are excluded.
Group sharper/softer highlights use a new conservative direct-pair focus heuristic,
not a calibrated universal score or automatic deletion decision.

The user expressly requested soft deletion. `review JOB_ID` runs an explicit
loopback-only tokenized session for Delete/Undo selections and archive confirmation.
`restore-archive JOB_ID` restores without overwriting. Verified ZIP plus retained
original files are stored under scan-root/Blurry; companions and tracked derivatives
move, scanner masters do not. Asset identities/dates/lineage are preserved in the
existing schema-v1 database; no new tracking database or routine sidecars. These
explicit user-requested archive moves are the exception to unchanged-source analysis.

Verification: 97 automated tests passed, including no-clobber moves and ZIP
verification failure before any source move. Strict Pyright
reports zero errors. Native CLI ran both existing sample sets, matched the selected
per-set flags exactly, retained all ten confirmed misses, and found one sharper/
softer group pair. Final streaming/Gaussian1-only combined run: 92 originals,
19 + 26 review flags, 82 seconds including grouping with cached helper. Originals
were verified unchanged, and persistence/integrity checks used isolated SQLite.
Archive/restore, failure rollback, collisions, companions, masters and HTTP session/
origin protections were tested on synthetic files; no user photo was archived.
Delete/Undo and report layout were inspected in a synthetic loopback browser page.
Scanner hardware acquisition was not repeated or claimed newly validated.
