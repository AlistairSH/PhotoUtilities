# Instructions for Codex in PhotoUtilities

## Start here
Read `PROJECT.md` before implementation and preserve its confirmed user decisions.
Inspect the current code and CLI before changing files. `README.md` documents
user commands; `PROJECT.md` describes current scope and deferred requirements.
Implementation reports record historical checks, not instructions to repeat
completed work. Preserve unrelated user work. Keep a short plan for multi-step
changes and carry authorized work through implementation and verification.

## Local-only development
- Work in this local project. The project now has an existing GitHub remote. Use a dedicated experimental branch from `main` for Phase 2 work; never change `main`, push, publish, open a PR, merge, or upload photos without explicit user authorization. Local commits on the experimental branch are allowed. Do not create a new remote.
- Production processing and metadata storage must remain offline and local. Do not add telemetry, remote image APIs, or accounts.
- Public documentation and dependency downloads are allowed for development; keep private images out of those requests.
- Keep photo data and databases outside the repository and out of Git. Documents may be iCloud-synced; do not assume it is genuinely local storage.

## Protect photographs and history
- Never destructively edit, move, or delete source photographs. Preserve sheet masters, extracted prints, and any original sidecars or related media.
- Use collision-safe paths, checksums, temporary outputs, atomic publication, and explicit job states. Resume derivatives without overwriting verified results.
- Preserve the original scan date, daily master ID, spatial print identities, and parent relationships. Failed/deleted/interrupted scans must not release allocated IDs.
- Store routine manifests, recipes, history, and naming counters in the existing `jobs.sqlite3`. Do not reintroduce routine JSON sidecars or a second tracking database. JSON export is explicit.
- Back up existing SQLite before schema changes; use versioned migrations, transactions, foreign keys, and indexed relationships. Preserve complete parameters, metadata, tool versions, and old records.
- Keep retouching reproducible and non-destructive. Preserve the confirmed Polaroid recipe, TIFF depth, and color-management behavior unless the user requests a change.
- Never alter Apple Photos library internals. Any future Photos integration must use supported local interfaces and explicit import actions.

## Phase 2 operating mode: Vision-first experiments
- Treat the existing four-Polaroid scan/split/retouch/SQLite pipeline as **Phase 1 functional (done-ish)**. Maintain it; do not treat support for other sheet arrangements or end-to-end calibrated scans as validated.
- Work on a new branch based on current `main`, suggested `experiment/apple-vision`. Check for uncommitted changes and existing branches first; do not reset or discard user work. Avoid committing test photographs or database files. Do not automatically push or merge.
- **First authorized experiment:** local Apple Vision analysis of existing image derivatives and reduced-resolution previews. Begin with a feasibility spike before implementing a new production command. Inspect available Apple Vision APIs on the actual macOS Tahoe 26 host; compare PyObjC bridge versus a small Swift CLI invoked from Python. Choose the lowest-maintenance route supported by tests. Use Apple's built-in local APIs; no network inference or model downloads.
- Vision is not assumed to have a reliable generic 'out-of-focus' classifier. Test only confirmed APIs (e.g. feature prints and similarity) and combine with existing OpenCV/NumPy measures for blur/exposure/clipping. Treat values as evidence, not verdicts. Compare modern digital images separately from vintage scans.
- Prefer read-only analysis and an experimental `photo-utils analyze` interface (exact CLI names to be decided from actual code), with `--dry-run` or `--no-db` for evaluation. Never cause scanning, retouching, file moves, Photos import, or destructive operations from analysis. Gate database-writing integration behind passing tests and explicit user approval.
- Sample analysis outputs should explain evidence, confidence/limitations, and conservative dispositions such as `pass`, `review`, and `unable-to-determine`; *no auto-delete or auto-cull*. Assess using a deliberate test set, including vintage softness, intentional shallow depth of field, motion blur, duplicate frames and difficult lighting. Measure false-positive reviews, performance, and offline behavior.
- AI, if added later as a Codex Skill/plugin/orchestrator, may inspect user-approved previews and propose strictly allowlisted numerical editing parameters. Actual editing remains local, deterministic and auditable. **No generative fill, face reconstruction, super-resolution, content synthesis or guessed detail** in the archival path. Never automatically transmit photos/previews or private metadata to cloud models.
- Use existing `jobs.sqlite3` as the one provenance store if/when assessment persistence is approved. Record asset/job linkage (including standalone images), analyzer/version, metric values, decisions, confidence, and user review; use migrations/backups. No routine JSON sidecars.
- Other candidate tools (`scikit-image`, `ImageHash`, Pillow/`pillow-heif`, darktable/`rawpy`, OpenImageIO, ArgyllCMS/LittleCMS) are **future evaluations**, not permission to install or integrate all of them immediately. See the ordered roadmap in `PROJECT.md`.

## Engineering approach
- Extend the existing Python CLI and small modules. Reuse configuration, persistence, locks, logging, and tests; avoid unrelated refactoring or dependency changes.
- Document actual parser command names and menu choices consistently. Do not present deferred features as available or treat them as a current assignment.
- Preserve `--dry-run` for scanning, splitting, and retouching. Explicit metadata export currently has no dry-run flag; inspect with `job show` first when needed.
- Verify new hardware/backend capabilities on this Mac; do not invent scanner flags, RAW support, Photomator automation, or Photos APIs. Use official documentation when external verification is needed.
- Use the project virtual environment. Never use `sudo pip`, replace system Python, or modify system tooling casually. Explain material installs and permissions; proceed with routine reversible project setup.
- Quote shell paths containing spaces. Avoid hardcoded usernames and machine-specific absolute paths in code.
- Do not enable watchers, a web app, cloud services, hosted image inference, elaborate UI, or paid dependencies without a concrete user requirement. The user explicitly authorized **investigating local Apple Vision first**, not blanket deployment of all roadmap features.
- If digital archival or quality screening is later implemented, verify archived byte-for-byte copies before derivatives and never automatically delete/reject photos based on a score. Preserve RAW/media companions and flag uncertain cases conservatively.

## Verification and continuity
Use meaningful tests for IDs/concurrency, checksums, collisions, resume,
SQLite migrations/relationships/recipes, metadata handling, and invalid inputs.
Use synthetic images for processing tests and visual review of representative
real samples when image behavior changes. Documentation-only changes need
command/help and link checks, not a new hardware acquisition.

Physical acquisition through the updated wrapper, real RAW decoding, calibrated
color appearance, and Photos import require direct checks. Mark them unverified
until performed; do not infer hardware success from simulated acquisition.

Maintain README installation, exact commands, data layout, configuration,
troubleshooting and maintenance guidance. Update PROJECT when requirements
or implemented scope change; preserve confirmed decisions and distinguish deferred
work. Report relevant verification and remaining limitations concisely.
