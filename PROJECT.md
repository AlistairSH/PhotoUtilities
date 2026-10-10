# PhotoUtilities

Current project scope and confirmed decisions, updated October 10, 2026.
See [README.md](./README.md) for installation, commands, and troubleshooting.

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
photo-utils jobs [--date YYYYMMDD] [--type scan|split|retouch] [--status STATUS] [--limit N]
photo-utils job show JOB_ID
photo-utils job export JOB_ID [--format json] [--output PATH]
photo-utils assets [--date YYYYMMDD] [--stage master|print|retouch|external] [--status STATUS]
photo-utils recipe show ASSET_ID [--recipe-id RECIPE_ID]
photo-utils history ASSET_ID
photo-utils db check [--checksums]
```

Processing/query commands accept `--state-dir`; see their `--help` for all
options. The menu offers Doctor, Scan, Retouch, History & Database, and Quit.
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

- Keep application code, production processing, photos, and metadata local. No remote Git, cloud processing, telemetry, accounts, or paid service dependency.
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
