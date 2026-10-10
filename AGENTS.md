# Instructions for Codex in PhotoUtilities

## Start here
Read `PROJECT.md` before implementation and preserve its confirmed user decisions.
Inspect the current code and CLI before changing files. `README.md` documents
user commands; `PROJECT.md` describes current scope and deferred requirements.
Implementation reports record historical checks, not instructions to repeat
completed work. Preserve unrelated user work. Keep a short plan for multi-step
changes and carry authorized work through implementation and verification.

## Local-only development
- Work in this local project. Git is optional and local only; never create a remote, push, publish, deploy, or upload source code or photos.
- Production processing and metadata storage must remain offline and local. Do not add telemetry, remote image APIs, or accounts.
- Public documentation and dependency downloads are allowed for development; keep private images out of those requests.
- Keep photo data and databases outside the repository and out of Git. Documents may be iCloud-synced; do not assume it is genuinely local storage.

## Protect photographs and history
- Never destructively edit, move, or delete source photographs. Preserve sheet masters, extracted prints, and any original sidecars or related media.
- Use collision-safe paths, checksums, temporary outputs, atomic publication, and explicit job states. Resume derivatives without overwriting verified results.
- Preserve the original scan date, daily master ID, spatial print identities, and parent relationships. Failed/deleted/interrupted scans must not release allocated IDs.
- Store routine manifests, recipes, history, and naming counters in the existing `jobs.sqlite3`. Do not reintroduce routine JSON sidecars or a second tracking database. JSON export is explicit.
- Back up existing SQLite before schema changes; use versioned migrations, transactions, foreign keys, and indexed relationships. Preserve complete parameters, metadata, tool versions, and old records.
- Preserve legacy metadata until explicit verified cleanup. Cleanup must never target images or unrelated JSON. Do not run cleanup merely because a migration succeeds.
- Keep retouching reproducible and non-destructive. Preserve the confirmed Polaroid recipe, TIFF depth, and color-management behavior unless the user requests a change.
- Never alter Apple Photos library internals. Any future Photos integration must use supported local interfaces and explicit import actions.

## Engineering approach
- Extend the existing Python CLI and small modules. Reuse configuration, persistence, locks, logging, and tests; avoid unrelated refactoring or dependency changes.
- Document actual parser command names and menu choices consistently. Do not present deferred features as available or treat them as a current assignment.
- Preserve `--dry-run` for scanning, splitting, retouching, legacy migration, and cleanup. Explicit metadata export currently has no dry-run flag; inspect with `job show` first when needed.
- Verify new hardware/backend capabilities on this Mac; do not invent scanner flags, RAW support, Photomator automation, or Photos APIs. Use official documentation when external verification is needed.
- Use the project virtual environment. Never use `sudo pip`, replace system Python, or modify system tooling casually. Explain material installs and permissions; proceed with routine reversible project setup.
- Quote shell paths containing spaces. Avoid hardcoded usernames and machine-specific absolute paths in code.
- Do not enable watchers, a web app, cloud services, AI models, elaborate UI, or paid dependencies without a concrete user requirement.
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
troubleshooting, migration, and cleanup guidance. Update PROJECT when requirements
or implemented scope change; preserve confirmed decisions and distinguish deferred
work. Report relevant verification and remaining limitations concisely.
