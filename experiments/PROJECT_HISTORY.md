# PhotoUtilities

## Similarity integration — October 11, 2026

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

MissedSet follow-up: five prior-version HEIC images form one connected set at
unchanged Vision <.45 OR strict SIFT settings. Seven direct links include the
human-confirmed pair (Vision .261) and a SIFT-only link that connects the fifth
image. The proposed triplet connects through another member rather than all
matching directly. Previously missed triplet Vision distances improved from
.588–.638 to .373–.545; this suggests version changes matter but does not
isolate WB/tint from other edits or format changes. Local browser previews and
scores are under `VisionExperiments/MissedSet-combo045/`; photographs and
SQLite checksums remain unchanged. No threshold tuning or integration.

Edited-color grouping experiment: the 60-image SimilarityTests batch was run
with the accepted Vision <.45 OR strict SIFT rule. It returned 15 pairs, four
triplets, one 11-image connected set, and seven unpaired images (known misses
because every input has a partner). The large set has 48/55 direct matches and
no bridges. One missed pair narrowly failed SIFT coverage despite 99 inliers;
large framing changes remain a limitation. A separate experimental group
gallery now reports direct links, bridges, singletons and larger sets. Eight
similarity tests passed; input and SQLite checksums were unchanged. No
threshold adjustment or production integration was performed.

Current project scope and confirmed decisions, updated October 11, 2026.
See [README.md](./README.md) for installation, commands, and troubleshooting.

## Status and next objective

**Phase 1: functional / done-ish.** The documented 2x2 LiDE 400 Polaroid workflow has worked on actual samples: SANE 600 dpi 48-bit capture, four-print detection/rectification, fixed ImageMagick retouch, immutable TIFFs and SQLite job/asset/recipe tracking. Do not call it feature-complete: the updated Python acquisition wrapper has not been recorded as physically verified; mixed/touching layouts, calibrated ICC, broader input formats, Photos import and quality assessment are unimplemented. The README is the operational record; test counts below are historical, not results from this documentation change.

**Phase 2: experiment with local image intelligence, starting with Apple Vision.** Separate analysis from editing, make conservative quality recommendations, preserve historical detail, and eventually choose between extending the CLI, building a parallel companion CLI, and a Codex Skill/plugin interface. No generative image reconstruction. Work on a Git experimental branch; keep `main` stable.

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
photo-utils jobs [--date YYYYMMDD] [--type scan|split|retouch] [--status STATUS] [--limit N]
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

## Phase 2 experimental roadmap (planned, not implemented)

### Experiment 1: Apple Vision feasibility and read-only assessment (start here)

Goal: determine whether native on-device Vision adds *measurable* value to technical quality assessment and near-duplicate matching without changing a single archived image. It is not a photo-restoration engine and must not invent detail.

Suggested branch: `experiment/apple-vision`, created from up-to-date local `main` after checking the Git worktree. Do not push, open PRs, or merge without explicit approval. Keep photographs and SQLite outside Git. Use test fixtures or separately approved sample files; neither originals nor derivatives are committed.

**Spike A: runtime bridge.** On the real Apple Silicon/Tahoe machine, examine Vision APIs and availability. Prototype one small local operation using PyObjC (`Vision`, `Foundation`, `Quartz`) and, if bridge ergonomics or performance are poor, a tiny Swift command-line helper. Test startup, packaging, local-only execution, pixel orientation, TIFF/HEIC/JPEG compatibility in the experiment, and error handling. Record any API/version limitations. Avoid claims of capabilities until verified. No new cloud models.

**Spike B: measure.** Start with read-only samples: existing TIFF prints/retouches and a small separately chosen digital-image fixture set. Produce downsampled previews in temporary local storage; correctly handle ICC profiles, EXIF orientation, and the physical Polaroid border (exclude it from photographic sharpness/exposure metrics while retaining it for paper/color diagnostics). Explore confirmed Vision image-feature-print APIs for visual similarity and near-duplicate clustering; benchmark against OpenCV metrics (variance of Laplacian and/or gradient/edge measures) and luminance/clipping statistics. Feature-print similarity is *not* an absolute quality or focus score. Explicitly test cases where vintage softness or shallow depth of field should **not** trigger rejection.

**Spike C: report, no edit.** Prototype an independent, non-destructive `analyze` interface, possibly `photo-utils analyze IMAGE|FOLDER [--no-db] [--json]`, after checking the existing CLI parser. Return image identity, findings, scores and algorithm names, evidence, optional duplicate candidates, warnings, and `pass` / `review` / `unable-to-determine`. Thresholds are source-type-specific, conservative and user-configurable. Never auto-delete, auto-move, auto-cull, or change image pixels. Do not present a proposed command as implemented in README before it actually exists.

**Acceptance gate:** run existing regression suite and type checks; confirm bytewise unchanged test masters/prints, no unexpected production DB writes, fully offline execution, clear unsupported-platform fallback, and documented run time/memory. Manually inspect at least a small representative set of sharp/blurred digital images and naturally soft vintage Polaroids. Report false-positive review flags and uncertain cases. Only then propose integrating assessment rows in the existing SQLite database with a versioned migration and backup. Pause for user approval before adding this to default scan flow.

### Subsequent candidates, in order of demonstrated value

| Candidate | Purpose | Decision gate |
| --- | --- | --- |
| `scikit-image` | Additional interpretable quality metrics, exposure/contrast/structural analysis | Only if existing NumPy/OpenCV insufficient; compare against baseline |
| `ImageHash` (and/or Vision feature prints) | Duplicate/near-duplicate grouping for digital bursts | Evaluate false merges on distinct photos; no automatic deletion |
| Pillow + `pillow-heif` | Local JPEG/HEIC ingestion and previews | Check ICC/EXIF, orientation, timestamps and companion files |
| darktable CLI **or** `rawpy`/LibRaw | RAW processing while retaining immutable source and editing history | Compare format coverage, color management and reproducibility; avoid dual engines without reason |
| ArgyllCMS + LittleCMS | Profile LiDE 400 with a **measured reflective IT8.7/2 target** once purchased | Verify target reference values and scanner conditions; preserve untagged masters and compare accuracy, not just attractive output |
| OpenImageIO | More robust color-managed float pipeline, comparisons and batch operations | Adopt only for clear technical benefit over ImageMagick/tifffile |
| Local Apple Photos import | Add approved rendered derivatives through supported interfaces | Explicit opt-in; duplicate avoidance; never touch Photos library internals |
| Codex Skill / plugin / orchestration CLI | Conversational planning, reports, preview review, deterministic parameter proposals | Stable machine-readable CLI contract, permission controls, privacy boundary and repeatability first |

### Proposed architecture and safety boundary

```text
Immutable SANE TIFF masters / future checked digital archive
        |
        +--> existing deterministic split & retouch (unchanged)
        |
        +--> local read-only preview + Vision/OpenCV analysis
                  |
                  +--> report / conservative manual-review queue
                  +--> optional versioned SQLite assessment history (later)
                  +--> optional future agent recommends numeric adjustments
                                   |
                                   +--> local allowlist + bounds validation
                                   +--> deterministic ImageMagick/RAW export
                                   +--> new derivative, never overwrite master
```

The AI may analyze approved previews and choose/describe bounded exposure, white balance, curves, rotation or saturation adjustments, but **must not generate output pixels**. No generative fill, inferred facial detail, AI upscaling or content replacement in the faithful archive pipeline, whether local or cloud. Local Vision processing is the Phase 2 default; using cloud-hosted analysis of personal images requires a separate explicit user choice. Record operator, algorithm and parameters for any future edit in SQLite. Keep fixed `polaroid` preset unchanged unless asked.

### Phase 2 handoff and work sequence

1. Create/check out experimental branch without disturbing working tree; verify `.gitignore` excludes photos, DB and generated previews.
2. Read AGENTS, PROJECT and README; inspect actual CLI/tests and existing data model.
3. Verify Apple Vision's actual local APIs on this Mac; choose PyObjC or Swift prototype with minimal footprint.
4. Implement read-only experiment, test fixture analysis, and compare Vision usefulness against existing OpenCV/NumPy baseline.
5. Report methods, trade-offs, sample assessments, speed, error modes and recommended next step. Do **not** automatically proceed to digital ingestion, SQLite schema changes, Photos integration, or skill/plugin implementation.
6. After review, incrementally build the most useful feature behind an opt-in CLI switch with tests and documentation updates.

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

### Experiment 1 progress — October 11, 2026

The independent read-only Swift/Python feasibility spike is on
`experiment/apple-vision`; see [findings](experiments/apple_vision/FINDINGS.md)
and [experimental commands](experiments/apple_vision/README.md). Feature-print
revision 2 worked locally/offline on this Mac; OpenCV/NumPy evidence remains
necessary for technical assessment. Existing production commands/persistence
are unchanged. Representative real digital/vintage visual review, calibrated
thresholds, and production integration remain pending; no `photo-utils analyze`
command or assessment migration has been added.

### Similarity comparison progress — October 11, 2026

At the user's request, a separate [hash/SIFT experiment](experiments/similarity_compare/README.md)
compared 254 reviewed scans and 7,838 pairs using the same native previews.
SIFT recovered a confirmed pair missed by Vision at .45, while strict SIFT and
whole-image hashes also missed genuine pairs. Sparse explicit user labels and
local disagreement galleries support further review, not a calibrated universal
threshold. Vision .40–.45 remains a candidate-review hypothesis for color and
B&W; user feedback does not establish a color-only restriction. No production
command, persistence, culling, dependency install, or Czkawka evaluation was added.

### User review and standalone comparison — October 11, 2026

The user accepted Vision <0.45 plus SIFT as useful complementary similarity
candidates and rejected the previous whole-image pHash/dHash results because of
false positives. A separately authorized [Czkawka CLI experiment](experiments/czkawka_compare/README.md)
installed an official standalone binary outside Git and compared twelve settings
on the same five datasets. Default found no groups; no tested setting found more
than one of four explicitly confirmed similar pairs, versus all four for the
combo. Additional groups and timing comparisons remain reviewable local reports;
no universal accuracy/scalability claim or production integration follows.
Production commands, photographs and SQLite remain unchanged.
