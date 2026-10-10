# SQLite metadata consolidation — October 10, 2026

## Audit and design

The original state was a `scan_jobs` table in the existing application-state
`jobs.sqlite3`, root-specific SQLite naming ledgers, split manifests, retouch
batch manifests, per-image recipes, and per-output job sidecars. There was no
schema version/migration layer. No Photos import is implemented in this project.

Schema version 1 extends `scan_jobs` in place with job type, optional parent job,
processing date/status, command, and complete metadata TEXT. The original status
column stays compatible with scanner code; `processing_status` supports pending,
running, completed, partial, and failed. New tables are `assets`, `recipes`,
`metadata_records`, `legacy_imports`, `daily_ids`, and `legacy_sources`. Parent
assets/jobs and recipes use enforced foreign keys and indexed relationships,
dates, types/stages, and statuses. Images remain on disk. Full variable metadata
is stored losslessly; imported original JSON text is retained, including numeric
lexemes. Explicit exports also include that stored text.

All connections enable foreign keys. Schema upgrade takes a filesystem lock,
creates a recoverable SQLite backup before changing an existing database, and
applies its versioned changes transactionally. Metadata writes use immediate
transactions; existing derivative/scanner locks protect publication and resume.
Naming counters move into the existing state database. Original ledgers are
read-only inputs; imported counters only increase. A scan-root database binding
prevents concurrent allocators from using different databases for one root.

Metadata record keys retain old locator names internally for compatibility;
these are SQLite lookup keys, not routinely generated files. Legacy on-disk
metadata can still be read until explicit migration/cleanup. Prepared retouch
recipes are committed before atomic TIFF publication. Completed outputs are
verified on reuse; missing images are reported separately from corruption.
A canonical batch retouch is one job with several result assets/recipes.

## Commands and compatibility

The existing CLI adds `job show/export`, `assets`, `recipe show`, `history`, and
`db check/migrate/cleanup`. `jobs` now covers scan/split/retouch jobs and supports
date/type/status filters. The main menu adds Retouch and History & Database.
History provides date-filtered/recent jobs, details, assets, recipe selection,
lineage, explicit exports, and diagnostics. See README for exact commands.

Migration imports validated legacy records in relationship order, checks paths
and image hashes, reports ambiguity, preserves all supported fields, and tracks
source JSON checksums for idempotency. Cleanup is a separate explicit action:
only verified, unchanged, imported metadata is eligible. No image deletion,
renaming, or migration is performed automatically. Hardware settings, image
algorithms, ICC handling, and filenames remain unchanged.

## Verification

70 automated tests pass in the project virtual environment. They cover
schema backup/retry, foreign keys/rollback, scan/split/batch lineage, arbitrary
standalone retouch, queries/menus/exports, complete recipes/numeric text,
legacy migration/retry/cleanup, counters/concurrency, missing files, no routine
JSON outputs, and recovery after TIFF publication is interrupted.

A real local ImageMagick/ExifTool run on a synthetic external TIFF verified
16-bit RGB, the system sRGB profile, database checksums, and no JSON sidecars.
No physical scanner acquisition was performed in this session.

A rehearsal against a temporary backup of the real database imported 31 legacy
metadata files and repeated with 31 duplicates and no additional records:
15 jobs, 48 assets, 42 recipes, 31 metadata records. SQLite integrity and foreign
keys passed. One master referenced by an old scan record was already missing:
`LiDE400-20261009T161737-0400-600dpi-48bit-b2164654.tif`. Its history is retained;
no replacement or deletion is attempted. The live migration result is recorded
below after execution. Legacy JSON cleanup is not performed automatically.

## Live migration result

The live schema upgrade/import succeeded after filesystem approval:
31 imported, 0 failed, 0 skipped; 15 jobs, 48 assets, 42 recipes, and 31 metadata
records. A repeat dry run reports 31 duplicates and no new imports. The backup
is `jobs.backup-v0-366e977d6d1c4ee385420943c858e003.sqlite3` beside the live
state database. Final checksum diagnostics show SQLite integrity OK, no foreign
key errors, no changed image checksums, and the one pre-existing missing master
listed above. All legacy JSON and photos remain unchanged. Cleanup was not run.

The real cleanup dry run verifies 31 eligible legacy metadata files and removes
0; no cleanup action was taken. Date-filtered live job browsing also passed.

## Modified files

Source: `database.py` (new), `migration.py` (new), `history_cli.py` (new),
`cli.py`, `scanning.py`, `processing.py`, `retouch.py`, and `naming.py` in
`photo_utils/`. Tests: new `tests/test_database.py` plus updated scanning,
processing, retouch, and naming tests. Documentation: README, PROJECT,
this report, and database exclusions in `.gitignore`.
No dependencies were changed or upgraded.
