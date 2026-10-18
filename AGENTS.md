# Instructions for Codex in PhotoUtilities

## Start with current state

Read `PROJECT.md` before implementation and preserve confirmed user decisions.
`README.md` documents actual commands; `PROJECT.md` distinguishes implemented,
experimental and deferred scope. Research scripts and history are preserved on `experiment/ranking-culling` at
`8809e81`, outside the current main tree. Dated implementation reports are historical
evidence, not current instructions or tasks.
Inspect current CLI/code before editing; preserve unrelated user work. Keep a short
plan for multi-step changes and complete authorized implementation and verification.

## Local development and authorization

- Work locally on a dedicated development branch. The accepted integration is
  merged into `main` and published. Keep research on experimental branches;
  `experiment/ranking-culling` at `8809e81` preserves the removed experiments.
  Commit, push and merge only within the user's current authorized scope.
  Do not create a new remote; the repository already has one.
- Production image processing and metadata remain offline/local. No telemetry,
  accounts, paid services, hosted image inference or private-photo uploads.
  Public documentation and routine development dependency downloads are allowed;
  private photos/previews must not be sent with those requests.
- Keep photo data, generated reports, DBs, caches, binaries and model weights outside
  Git. Documents may be iCloud-synced; do not equate its pathname with local storage.
- Extend the existing Python CLI and small modules. Reuse configuration, locks,
  persistence and logging; avoid unrelated refactoring or dependency changes.
  Use the project virtual environment; preserve Python 3.9 compatibility and strict
  Pyright. Never replace system Python or use sudo pip for project setup.

## User workflows

- Natural-language “process these folders” maps to `photo-utils process TARGET...`;
  use recursion only when requested or consistent with the intended folder tree.
  The interactive folder menu offers recursion by default; explicit CLI is shallow.
- Scan/saved-sheet workflows split/rectify, rotate, group and create tiered review
  before optional Polaroid edits. Polaroids require four separated bordered cards;
  ordinary prints use `--kind prints` and separated rectangles against a contrasting
  uniform background. Ordinary-print splitting is implemented, no longer a placeholder.
- `--retouch none` skips edits but still splits/reviews. `scan --capture-only` keeps
  an unsplit master. The sole edit recipe is for compatible Polaroid TIFFs; never
  apply it to ordinary prints or arbitrary JPEG/HEIC photos.
- Menu: Scan, Process folder, Existing sheet, Previous review, Restore culls,
  Maintenance (diagnostics/history/grouping-only/retouch), Quit. Ordinary batch
  prompts should produce a report and offer an explicit local review session when
  culling is wanted. `--open-review` prints a loopback URL through the review command;
  do not assume it launches a browser automatically.
- Preserve no-write `--dry-run` for acquisition, splitting, folder processing,
  grouping and retouching. `--no-db` analysis writes only a report and changes views,
  not source pixels or rotation derivatives; archiving/edits require persistence.
  Explicit metadata export has no dry-run flag; inspect `job show` first as needed.

## Grouping, tiers and report presentation

- Preserve accepted grouping: local Vision revision 2 distance <.45 OR strict SIFT.
  Hashes/Czkawka are not production signals. Groups can chain; they are candidates
  for human review, not identity, quality or retention verdicts.
- Analyze originals before edits. Preserve existing Gaussian1 focus rules and
  independent sharper/softer highlights. Do not treat missing flags as certified
  sharpness or silently retune thresholds from a few development examples.
- Current tier policy uses native aesthetics/utility, highest face capture quality,
  eye/smile observations, detail, endpoint clipping and saliency layout. Solos use
  the full actual batch; no fixed 93-photo cohort, forced winners or cull quotas.
  Composition-only concerns are advisory. Preserve exact policy/provenance in
  SQLite. Foundation Models prompts and external aesthetic predictors stay research.
- Use bars above previews: green **Top Pick**, blue **Keep & Review**, orange
  **Possible Cull**. Keep internal tier key `Review`; this is a display alias.
  Positive focus text is **Possible Missed Focus**. Unflagged images keep
  `Focus review: No` without an explanatory focus comment.
- Display **Rank within set: x/y** for group members and the ungrouped set, using
  displayed order and that set's size. Do not merely rename a full-batch number.
- Legend: **Boxes: red - faces, green - people, orange - animals, purple - objects,
  cyan - attention areas.** Use object/objects in visible text while retaining
  native detector identifiers. Omit the removed experimental-flags introduction.
- Apply embedded orientation, then conservative face/body-pose quarter-turns when
  evidence is clear. Preserve originals and separately track full-resolution upright
  derivatives. No horizon straightening. Unknown orientation remains in metadata
  but produces no comment on normal reports; show notes for applied rotations.
- Object/attention area below a long-edge horizon proxy was tested and not adopted.
  Never enable that fallback from the standalone trial. Missing research labels
  stay unjudged unless the user explicitly defines their meaning; only the specific
  October 17 orientation export used unmarked = correct original 0° by clarification.

## Protect photographs, identities and history

- Never destructively edit, silently overwrite, automatically rename or automatically
  delete source photographs. Preserve masters, extracted originals and companions.
  Use collision-safe paths, checksums, temporary outputs, atomic publication and
  explicit job states. Resume verified derivatives without replacing changed files.
- Preserve scan initiation date, daily master ID, spatial print identities and parent
  relationships. Failed/interrupted/deleted scans do not release IDs. Derivatives
  inherit source dates; never invent original capture dates for scanned prints.
- Preserve the confirmed full-image Polaroid recipe, including border, 16-bit RGB,
  compatible metadata and sRGB handling. Keep retouching reproducible/non-destructive.
- Existing `jobs.sqlite3` is the sole routine metadata store. Do not reintroduce
  routine JSON sidecars or a second tracking DB. Explicit exports and isolated
  research artifacts are separate. Respect root bindings and migrated counters.
- Back up SQLite before schema changes. Use versioned migrations, transactions,
  foreign keys and indexed lineage; preserve parameters, metadata, tool versions
  and old records. Never reset a DB/counter to bypass an error.
- Never modify Apple Photos library internals. Future integration requires supported
  local interfaces and explicit import actions; it is not implemented now.

## Explicit reversible culling

- Only manual Delete selections followed by archive confirmation may move images,
  companions and tracked descendants. A tier, score, note, model suggestion or
  ungrouped status never selects/archives photos automatically. Protect masters.
- Preserve loopback-only, tokenized, allowlisted review operations and host/origin
  protections. A static HTML report cannot move files. Keep one self-contained
  review report with embedded previews and original links.
- Verify original bytes in ZIP members with checksums before moving sources.
  Completed archives retain verified ZIPs only, in dated Blurry folders with
  collision suffixes. Remove loose duplicates only after verification/metadata
  commit; retain recovery copies on failure. Never purge archival ZIPs.
- Restore without overwriting; retain ZIPs and asset IDs/dates/lineage. Preserve
  companions, source bytes, failure evidence and recorded recovery plans.

## Verification and remaining limits

Use meaningful tests for source checksums, IDs/concurrency, collisions, resume,
SQLite migrations/lineage, recipes, metadata, invalid inputs and archive recovery.
Use synthetic images for mutations and visual review of representative samples
when image behavior changes. Run relevant tests and strict checking; distinguish
fresh results from historical recorded counts. Documentation-only edits need
command/help/link checks, not fresh scanner acquisition or repeated image inference.

Use `../PhotoSamples` for future focus/group/quality tests. Verify its current
inventory and source hashes, record missing paths explicitly, and do not substitute
similarly named photos. Use isolated SQLite and disposable copies for mutation tests.

Latest acquisition-wrapper hardware validation, ordinary-print physical scans,
higher DPI, calibrated colour, broad orientation/ranking accuracy, RAW decoding and
Photos round trips remain unverified. Do not infer hardware success from mocks.
Keep generic edits, RAW/digital archival ingestion, Photos/Photomator integration,
manual geometry correction, mixed/touching layouts, Shortcuts and watchers deferred
until requested. Do not add a background watcher or public service incidentally.

RestorationLab source is versioned under `RestorationLab/` as a related but
separate, effectively complete tool for occasional use. Its working private data,
weights and isolated runtime remain in sibling `../RestorationLab`; outputs stay
in `../Restored`. Do not add them to Git or integrate restoration into the main
CLI, menu, pipeline or installation dependencies. Its separate batch manifests
remain part of that tool, not routine main-CLI metadata. Maintain README/PROJECT and the repository skill when
implemented scope changes; preserve research history without presenting it as live
CLI behavior.
