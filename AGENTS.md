# Instructions for Codex in PhotoUtilities

## Start here
Read `PROJECT.md` before implementation and preserve its confirmed user decisions.
Inspect the current code and CLI before changing files. `README.md` documents
user commands; `PROJECT.md` describes current scope and deferred requirements.
Implementation reports record historical checks, not instructions to repeat
completed work. Preserve unrelated user work. Keep a short plan for multi-step
changes and carry authorized work through implementation and verification.

## Local-only development
- Work in this local project. The project now has an existing GitHub remote. Use a dedicated branch for new development; never change `main`, push, publish, open a PR, merge, or upload photos without explicit user authorization. Local commits on the experimental branch are allowed. Do not create a new remote.
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

## Established similarity workflow
- Related-photo grouping is accepted production functionality: `photo-utils similar` uses local Vision revision 2 distance <.45 OR strict SIFT. Preserve the tested rule unless the user asks to change it; hashes and Czkawka are not production signals.
- Analyze original scans/camera images before manual edits when available. Similarity never scans, retouches, moves, deletes, imports to Photos or transmits images. Results are candidates for manual review, with chaining, not identity or quality verdicts.
- Retain the clean image layout and one self-contained HTML report beside images. Persist routine scores/settings/groups against source assets in existing SQLite, with `--no-db` and no-write `--dry-run` options. Derivative history inherits source analysis rather than pretending edited pixels were reassessed.
- The accepted main-branch `scan` and `process-sheet` have opt-in `--find-similar`, after saving prints and before retouching. On the current culling branch, grouping/focus review is enabled by default with `--no-focus-review` opt-out. The four-Polaroid splitter remains the supported layout. `--kind prints` deliberately fails before acquisition/writes with `Print Splitting Not Implemented Yet`.
- General technical quality assessment, digital archival and RAW/Photos integration remain deferred. Branch-only manual focus review is implemented and accepted as described below. Vision similarity is not a focus classifier; no automatic culling or generative reconstruction.
- Keep pure feasibility/benchmark artifacts on `experiment/apple-vision`; production modules, regression tests, documentation and the photo-toolkit skill belong on `main`. Do not push/merge without explicit authorization.

## Engineering approach
- Extend the existing Python CLI and small modules. Reuse configuration, persistence, locks, logging, and tests; avoid unrelated refactoring or dependency changes.
- Document actual parser command names and menu choices consistently. Do not present deferred features as available or treat them as a current assignment.
- Preserve `--dry-run` for scanning, splitting, and retouching. Explicit metadata export currently has no dry-run flag; inspect with `job show` first when needed.
- Verify new hardware/backend capabilities on this Mac; do not invent scanner flags, RAW support, Photomator automation, or Photos APIs. Use official documentation when external verification is needed.
- Use the project virtual environment. Never use `sudo pip`, replace system Python, or modify system tooling casually. Explain material installs and permissions; proceed with routine reversible project setup.
- Quote shell paths containing spaces. Avoid hardcoded usernames and machine-specific absolute paths in code.
- Do not enable watchers, a web app, cloud services, hosted image inference, elaborate UI, or paid dependencies without a concrete user requirement. The accepted local similarity feature does not authorize blanket deployment of deferred roadmap features.
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


## Current experimental branch workflow

The user explicitly authorized focus/culling CLI integration on
`experiment/ranking-culling` only. The user authorized committing and pushing the
October 12 checkpoint to that same remote branch; do not change or merge main.
Future pushes still require explicit authorization. On this branch, natural-language
“process these folders” maps to `photo-utils process TARGET...`; “scan this page
and process” maps to the supported Polaroid scan workflow, including grouping/focus
before existing edits. Ordinary print splitting remains an explicit error. Read
README for the branch-only commands and supported formats/edits. Do not apply a
Polaroid recipe to arbitrary digital photos. Focus flags and relative highlights
are suggestions. Do not automatically archive flagged or softer images.

The user expressly authorized manual reversible review archives. Only explicit
Delete selections followed by archive confirmation may move selected images,
companions and tracked derivatives to verified Blurry archives. Scanner masters
remain protected. Retain original bytes in verified ZIP-only archives, preserve IDs/dates/lineage,
record job states and recoverability, refuse changes/collisions, and never purge
the archival ZIP. Use dated folder names, not GUID directory names. Remove loose
duplicate copies only after verifying ZIP members and committing recovery metadata. Use the existing jobs.sqlite3 for routine metadata.


The user accepted the 475-image four-folder workflow as successful. Unflagged
images should have no explanatory focus comment; keep the yes/no status and
relative group highlights. Explain positive review flags only. Treat no flag as
unassessed in stored metadata, rather than certifying sharpness. Preserve subject
boxes and manual archive controls. Ordinary batch prompts should produce the
report and open an explicit local review session when archive controls are needed.
Keep historical experimental scripts/tests on this branch; private photographs,
reports, databases, caches and binaries remain outside Git.
