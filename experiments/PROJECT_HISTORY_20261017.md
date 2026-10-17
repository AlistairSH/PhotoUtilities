# Historical project notes through October 17, 2026

This is a historical snapshot, not current scope or agent instructions. See
[PROJECT.md](../PROJECT.md) for the reconciled current state.

# PhotoUtilities

Current project scope and confirmed decisions, updated October 17, 2026.
Historical dated sections below record earlier scope and are superseded by the current integration section.
See [README.md](../README.md) for installation, commands, and troubleshooting.


## Current integration — October 17, 2026

The user authorized integrating the latest three-tier review into the CLI on
experiment/ranking-culling, updating the menu around scanning and folder processing,
implementing ordinary-print splitting, and correcting sideways/upside-down photos
without horizon straightening. This supersedes earlier deferrals of those features.
Main remains unchanged; no push/merge is authorized by this implementation request.

Scan/saved-sheet and folder workflows now generate Top Pick / Review / Possible
Cull using fresh local native measurements and the promoted cached-experiment
policy. Solos reference the entire actual batch, not a hardcoded 93 images.
Composition remains advisory, close groups have no forced winner, and only explicit
human selections plus confirmation invoke the existing reversible ZIP archives.
Existing focus suggestions stay independent. Historical experiments are retained.
Foundation Models prompts, Schuhmann/rsinema models and experimental restoration
are not included. RestorationLab is deliberately standalone and rarely used.

Ordinary-print sheets support 1–20 separated rectangular prints against a uniform
contrasting background; touching/ambiguous boundaries are unsupported. Polaroids
retain the existing four-card border alignment and optional fixed TIFF recipe.
`scan --retouch none` now splits without edits; `--capture-only` preserves the old
unsplit acquisition behavior. Ordinary prints cannot receive Polaroid edits.

Visual quarter-turns use upright face/body-pose evidence across four candidates,
with conservative confidence/margin checks. Horizon-only upside-down orientation
can be ambiguous and remains a manual check. Uncertain images are unchanged.
Corrected views feed grouping/ranking; full-resolution TIFF rotation derivatives
are separately preserved with SQLite lineage when persistence is enabled. No-db
runs transform analysis views only. No horizon straightening or source overwrites.

Menu: Scan, Process folder, Existing sheet, Previous review, Restore culls,
Maintenance (diagnostics/history/similarity/retouch), Quit. CLI retains explicit
commands and no-write dry runs. --open-review starts the local interactive session.
The consolidated ../PhotoSamples directory supplies future focus/group/quality
validation; originals remain read-only and mutation tests use disposable copies.

## Historical status and next objective

**Phase 1: functional / done-ish.** The documented 2x2 LiDE 400 Polaroid workflow has worked on actual samples: SANE 600 dpi 48-bit capture, four-print detection/rectification, fixed ImageMagick retouch, immutable TIFFs and SQLite job/asset/recipe tracking. Do not call it feature-complete: the updated Python acquisition wrapper has not been recorded as physically verified; mixed/touching layouts, calibrated ICC, broader input formats, Photos import and quality assessment are unimplemented. The README is the operational record; test counts below are historical, not results from this documentation change.

**Phase 2: related-photo grouping is implemented and accepted.** The existing CLI uses local Vision + SIFT, SQLite source-asset relationships, a lightweight HTML report and the photo-toolkit skill. Technical quality assessment and further editing automation remain deferred. No generative image reconstruction.

**Phase 3: manual focus review is usable on experiment/ranking-culling.** The user
accepted a 475-image batch workflow with similar-group focus highlights and
explicit reversible culling. Archives now retain only verified ZIPs in dated
folders, and unflagged images have no explanatory note. This remains branch-only;
general digital edits and ordinary-print splitting are still deferred.


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
- The October 10 legacy import migrated 31 metadata files; database integrity and foreign keys passed. One old master reference was already missing. The user subsequently confirmed legacy JSON cleanup is complete. Details are in [SQLITE_IMPLEMENTATION.md](../SQLITE_IMPLEMENTATION.md).

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
selected experimental focus policy and reversible manual culling archives. The user authorized this checkpoint to be committed and pushed on the same
experimental branch; it remains unmerged into main. `process` handles one/multiple folders with embedded
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
`restore-archive JOB_ID` restores without overwriting. Verified ZIP-only archives in dated
folders are stored under scan-root/Blurry; companions and tracked derivatives
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
origin protections were tested on synthetic files; no user photo was archived by those tests.
Delete/Undo and report layout were inspected in a synthetic loopback browser page.
Scanner hardware acquisition was not repeated or claimed newly validated.


## Accepted batch workflow checkpoint — October 12, 2026

The user reviewed the combined run on 08477, OldScans01, Photos20260618 and
17268 08082025 2 and called it successful. It processed 475 originals recursively
in about eight minutes: 55 groups (39 pairs, four triples, 12 groups of 4–9),
322 ungrouped images, 228 focus-review flags, seven sharper and five softer group
highlights. Source checksums were preserved; no image was automatically culled.
An explicit loopback review session provided Delete/Undo and confirmed archival.

The requested UI refinement removes explanatory text from unflagged images.
Their yes/no status and relative group highlights remain visible; stored category
continues to mean unassessed. Positive flags retain reasons and bounding boxes.
Historical saved jobs can be re-rendered without reanalyzing photos. Diagnostic
code/tests and findings are retained on this branch, while image/report/database
artifacts remain local and untracked. CLI focus policy and archive behavior remain
unchanged. This is a usable manual-review workflow, not a universally validated
focus classifier. General digital edits and ordinary-print splitting remain deferred.

The user explicitly authorized a local commit and remote push of this checkpoint
on experiment/ranking-culling only; no merge into main, PR or photo upload.


The archive storage refinement retains only the verified ZIP in human-readable
YYYYMMDD-archive folders (numbered suffixes for same-day collisions). Temporary
loose staging is removed after verification and metadata commit, with recovery
copies retained on failure. Restore and archived preview links read ZIP members;
asset IDs, historical paths, checksums, dates and lineage remain in SQLite. The
compact-archive command safely converts older ZIP-plus-loose-file archives and
updates locations. No schema change is needed. The user's existing archive is
converted only after ZIP/member and duplicate-file checksums match.


Current storage verification: the user's live 22-file archive was checksum-verified
and converted to Blurry/20261012-archive/deleted-photos.zip, with no individual
copies retained. The old GUID folder was removed. A pre-conversion SQLite backup
was saved; asset IDs, dates and parent relationships were verified unchanged.
The accepted 475-image report was re-rendered without rescanning and preserves
all 228 review flags. Core tests: 101 passed; experimental tests: 45 passed;
strict Pyright: zero errors. Private ZIPs, photo data and metadata backups remain
outside Git. The updated review session uses ZIP-backed archived previews.

## Isolated aesthetics trial — October 12, 2026

The user authorized a native Apple Vision aesthetics experiment using the new
BestPhotoSamples folder first. Standalone implementation and instructions live
in `experiments/ranking_culling/aesthetics/`. It uses original-file requests,
raw native overallScore/isUtility, accepted grouping/focus evidence, conservative
direct comparisons and blind preference export. All images/results/reports stay
outside Git. No application behavior or schema changed. Human agreement and
production integration remain pending; scoring does not authorize culling.

## Aesthetics human review decision — October 12, 2026

After the initial, expanded-set and reduced-pair human reviews, the user accepts
Apple aesthetic scoring as useful comparison context, explicitly not a true
winner or best-photo verdict. Personal preferences can prioritize expression,
mood and intent over a technically preferable image. Preserve human choice,
side-by-side comparison and separate focus advice. Do not infer component-level
model explanations from the overall score. This decision does not authorize CLI
integration, winner badges, automated culling, score weighting or threshold tuning.
Private evaluation results remain outside Git.

## Authorized alternative aesthetic model trial

The user authorized starting Christoph Schuhmann's CLIP-based predictor on the
existing samples, with isolated local runtime/model downloads and advisory
comparisons against human choices and Apple. Implementation remains under the
standalone aesthetics experiment; no canonical database or application CLI
changes. A separate Python 3.12 environment preserves the production Python 3.9
venv. Originals remain read-only and inference runs locally. The next proposed
rsinema phase could overlay its seven component scores for human/Apple/Schuhmann
picked images on radar charts, with shared axes and deduplicated picks. No
rsinema components or charts have been invented or implemented in this phase.

## rsinema test and proposed advisory review design

The user authorized testing rsinema's seven predicted components on the current
sample set before deciding whether they add useful context. Runtime/model data
remain outside Git, images are read-only, and existing human/Apple/Schuhmann
results are reused. The diagnostic report may compare the selected images on
optional shared-axis radar charts. Production integration remains deferred.
The user-proposed future design orders group images by Apple score, highlights
the Schuhmann top, allows a manual human favorite, and optionally charts rsinema
components for those 2–3 distinct images. No combined true-winner score or
automatic culling is authorized by this experiment.

## Foundation Models triage plan — October 12, 2026

The revised direction assesses photographic interest for both grouped and solo
images using common criteria, with group context as a separate comparison.
Multiple interesting images, maybes, ties and possible technical problems are
allowed without quotas. Interest and problem warnings can coexist; unmatched
membership and lower relative preference do not justify culling.

This is planning only pending the laptop OS upgrade. The experiment, capability
verification, pilot evaluation and deferred metadata investigation are described
in [FOUNDATION_MODELS_PLAN.md](../experiments/ranking_culling/FOUNDATION_MODELS_PLAN.md).
No Foundation Models implementation or availability claim is made. Production
integration and metadata writes remain deferred.


## Foundation Models pilot execution — October 13, 2026

After upgrading the Mac, the user authorized extended Vision testing followed
by the standalone Foundation Models experiment, including grouped and solo
interest assessment. The user accepted the Foundation Models CLI terms directly.
The verified platform is macOS 27.0.1 / SDK 27.0, A18 Pro, 8 GiB; AFM 3 Core
reports available with image understanding and guided generation.

Standalone helpers and instructions are in
[foundation_models/README.md](../experiments/ranking_culling/foundation_models/README.md).
The local Vision pilot tested classification, face capture quality, landmarks,
people/animals and saliency on 93 active images at two sizes; all seven requests
succeeded with native-service access. Native image buffers fail in the general
agent sandbox, so sandbox-only failures are not model findings. The new 27
iterative segmentation assets were downloaded using Apple's public API.

The Foundation Models one-to-four-image gates, stable IDs, repetitions, reversed
order and 2048-resolution call succeeded. The pilot compares independent general
and scene-aware prompts, group contexts and a later separate Vision supplement.
Private images, model views, reports, human labels and explicit exports remain
outside Git. All interest/cull recommendations are advisory; no production
integration, photo mutation, canonical database change or archive action occurs.
The initial general prompt highlighted all 93 images, so it does not yet reduce
review workload. Useful interest/scene judgments need human validation.

Metadata checks used disposable synthetic copies only. XMP keywords/ratings
round-tripped in JPEG/HEIC/TIFF/PNG without decoded-pixel changes; IPTC keywords
worked on JPEG/TIFF and sidecar creation succeeded. Photos/Photomator application
interoperability and end-to-end network-disabled daemon inference remain
unverified. New macOS 27 public Photos rating/keyword APIs are declared in the
installed SDK; no live-library access or metadata integration was attempted.


The first pilot completed 231 attempted Foundation Models calls, 230 valid,
covering 63 grouped images in 20 groups plus 30 solos. General prompts highlighted
93/93 images; scene-aware prompts highlighted 92/93 and changed 10 scene labels.
Group context did not change matched interest labels. Median successful-call
latency was 6.9 seconds; the full pilot took about 32.9 minutes. Current prompts
are not recommended for production shortlist integration. Human scene/interest
accuracy remains unevaluated. A separate six-call Vision supplement had five
valid responses and one vocabulary failure; a stricter enum schema is tested
separately and baseline exports are preserved. The new iterative segmentation
request produced three diagnostic masks after asset setup on the configured
request. No mask-based focus rule is adopted.

The user clarified pilot human labeling: Worth keeping is boolean; No is
equivalent to Possible cull Yes. Use one keep decision with an inverse derived
cull field. Unanswered images remain unjudged; interest is still separate.

## Human pilot review — October 13, 2026

The user supplied a matching label export with 89 answer records. Of 77 explicit
interest judgments, 17 are interesting, 22 maybe and 38 no clear interest. Both
individual model conditions highlight all 77, giving 17/77 strong-interest
precision with no review reduction. Keep decisions are separate: 65 Yes, 23 No;
blank decisions remain unjudged. Cull No/Yes is derived from Keep Yes/No, never
from comment text. The labels and verbatim comments are preserved outside Git.

The user clarified that ordinary family/friend/event snapshots may be worth
keeping for memories without being editing candidates. Some imperfect older
images may still be restoration candidates. This reinforces separate editing
interest, observable technical problems and human retention decisions. Generic
positive descriptions of mood, texture or narrative do not establish editing
value. Do not assume technical deficiencies are artistic intent. Scene subject
and context can differ with framing; exact primary-label matches alone do not
establish classification usefulness.

`foundation_models/evaluate_human.py` validates manifest/image identities,
keeps unanswered labels out of agreement denominators, preserves notes as data,
and exports private comparison findings. Human Keep No includes redundancy and
preference as well as technical issues; it is not a technical-defect ground truth.
The next proposed experiment is a stricter editing-candidate prompt with concrete
anchors and the tested enum schema, followed by an independent held-out review.
No new inference, personalized training, image removal or archive action was
performed during this human-label evaluation.

## Revised prompt and face-count audit

The user authorized more specific editing-interest language. The new optional
`foundation_models/prompts/editing_candidates_v2.txt` defines strong editing or
restoration candidates, plausible maybes and ordinary snapshots separately from
personal retention; generic mood/texture/narrative praise is insufficient. It
requires independent technical uncertainty and classification by dominant subject
and framing. `fm_run.py --prompt-file` records the effective prompt and refuses
reusing incompatible old prompt gates. The original default/pilot remains intact;
no new inference was run during this audit.

Against 76 supplied primary scene labels, general Foundation Models labels match
41 and scene-aware labels match 44. These are literal category matches; subject
and context overlap. Native Vision emitted broad image-classification labels,
not a mapped primary category in the user's taxonomy, so comparable native
category accuracy was not claimed.

The cached Vision human-face audit found boxes on 10/13 user-labeled portraits
at both sizes. More than one human face was returned on 11/18 group portraits
at both sizes. Several face/person detections vary with input size, and positive
counts do not establish complete or correctly located detection. Explicit
face/head and related people/glasses comments are preserved in the separate
private overlay audit. Human face boxes do not establish animal-face detection.
No-face results must not become a sharpness certificate or remove uncertainty.

## Raw face-capture ordering experiment

The latest user instruction supersedes the proposed subject-focus ranking prompt:
use native raw face-capture quality directly. The user chose the highest detected
face score per image for multiple faces. The standalone `face_score_report.py`
uses cached 2048 results, orders each existing group descending, preserves ties
in source order, and leaves missing/failed scores unassessed. It changes neither
production focus rules nor previous model results or human labels.

The user deferred a solo exceptional-score cutoff until viewing the distribution.
The experimental report therefore starts with no solo cutoff/highlight and offers
an explicit interactive cutoff preview/export. This sample has 36/63 grouped
images with scores (max 0.738) and 8/30 solos (max 0.425). No threshold was fitted
or lowered merely to produce highlighted solos. The optional v3 focus/composition
prompt remains an unused earlier draft, not the selected ranking mechanism.

## Cascade diagnostics: exposure, saliency location and regional detail

The user proposed utility, comparative blur, exposure clipping, facial expression,
saliency layout and aesthetic tie-breaking experiments. These are not production
rules or fixed quotas. Installed Vision headers do not expose the suggested
VNDetectBlurlinessRequest; the user selected face-capture quality and local
Laplacian-like measurements instead. Face-capture quality remains a broader
capture-quality signal, using the previously chosen highest face score.

Standalone exposure and saliency-layout diagnostics processed all 93 active pilot
images using checksum-verified cached views/detections. Exposure measures endpoint
pixels in 8-bit display views, not RAW clipping or recovery. Saliency measures
attention and objectness box centers against frame center and thirds, using the
largest visible box provisionally. Center and thirds produce different attention
orders in 19/20 groups; that is differentiation, not proof of better selection.

`detail_probe.py` reuses the existing Gaussian1 regional focus implementation on
all 93 exact 1024 views: global, face, person, animal, attention and objectness
Laplacian/Tenengrad remain separate. Small regions are unassessed. These single-
scale diagnostics do not claim the CLI's accepted two-scale relative-focus flags.
Grain, texture and contrast affect detail scores. No new Foundation Models run,
expression detection, automatic cull flags or production changes were performed.

The subsequent user request authorized a sample cascade report with ordered
groups, possible-cull suggestions and solos ranked against the full sample.
`cascade_probe.swift` now measures aesthetics/utility and Core Image expressions
on all 93 cached 1024 views. Two utility flags were true in this fresh run; the
previous 65-image source-based run had none, so results are input/run-specific.
Core Image returned 69 face features; these are not identities matched to Vision.

`cascade_report.py` generated the private cascade-01 report: 20 groups/63 images,
30 solos and 29 possible-cull suggestions (16 grouped, 13 solo). Every threshold
and ordering key is documented in the report, including provisional comparative
detail, endpoint exposure and anchor-distance flags. No mandatory quotas apply.
Solos receive their position among all 93 under the same cascade, with full-sample
detail percentiles. No solo reaches the top aesthetic decile without flags; no
exceptional face-quality threshold was chosen. Four synthetic policy tests pass.
This remains experimental and does not change production ranking, metadata,
human choices, archive selections or originals. No additional Foundation Models
inference was used.

## Three-tier cached review (October 17)

The user approved Top Pick / Review / Possible Cull and requested regeneration
using saved scan results. `foundation_models/tier_report.py` consumes the previous
cascade JSON and pilot thumbnails; it performs no scanning or model inference.
Top Picks require no technical flags, both detail metrics outside the full-sample
bottom decile, and either a ≥0.10 face-quality lead over every scored group peer
or ≥1.5× detail on both metrics over every same-kind group peer. Comparisons
include all group members, not just survivors. Close groups have no forced pick.
Solos retain a full-93-image reference and need top-decile aesthetics with no
technical flags; the exceptional raw face-quality threshold remains unset.
Composition-only flags become advisories and cannot alone cause Possible Cull.

The private three-tier-01 report contains 5 Top Picks, 60 Review and 28 Possible
Culls. Of 64 previous retain candidates, 5 promote and 59 stay Review. Image-087
is the sole cull removal (composition only); no new culls appear. All 93 identities,
group memberships and underlying measurements are checked against the prior
report. No solo qualifies as Top Pick. The previous report remains intact.
Six synthetic tier tests pass; the combined report test selection passes 14 tests.
Production behavior, human labels, archives and original photographs are unchanged.

### October 17 integration validation

113 core regression tests and strict Pyright passed. Cached policy parity matches
all 93 historical tiers exactly (5 Top Pick / 60 Review / 28 Possible Cull). The
new PhotoSamples collection contains 154 images; a full fresh report produced
12 Top Pick / 115 Review / 27 Possible Cull, 23 groups and 86 ungrouped images.
Two views were quarter-turned; 89 orientations remained uncertain. Every source
checksum was preserved. The report is outside Git under IntegrationChecks.
Native quarter-turn tests recovered upright from all four versions of a portrait.
Isolated persisted native analysis verified tiers, three rotation derivatives,
SQLite integrity/foreign keys and checksums. Synthetic archive/restore regressions
and browser selection/Undo passed. No physical scan was acquired in these tests;
ordinary-print hardware behavior and broad orientation accuracy remain unverified.
