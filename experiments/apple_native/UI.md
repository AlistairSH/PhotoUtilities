# Native Mac review prototype — November 3, 2026

The `photo-review` executable is the first SwiftUI consumer of NativePhotoAnalysis.
A local app bundle is generated outside Git at:
`/Users/alistairhastings/.codex/visualizations/2026/11/03/01a1a3b9-b444-79d1-b23a-a1f0e6227b1f/Photo Review Diagnostics.app`.

The diagnostics build is version 0.2 with corrected progress labels and phase timings.
The original app is retained so an existing in-memory review is not closed.

## Current experience

Choose up to 500 JPEG, HEIC/HEIF, PNG or single-image TIFF files using the native
file picker, choose whether to apply conservative visual rotation, then Analyze.
The app displays progress and allows cooperative cancellation. Successful results
show related sets and an ungrouped set in the sidebar, tier totals, ordered photo
cards, focus notes, positive and advisory reasons, applied rotations and ranks
within displayed sets. Subject boxes can be toggled with the accepted legend.
Show in Finder reveals the original selected file.

Previews are bounded to 640 pixels, loaded off MainActor through a serial thumbnail
actor, with a 64 MiB cost-limited cache. Their embedded orientation and the analysis
quarter-turn are applied for display. This cache limit is not a bound on the whole
analysis engine's memory or a guaranteed process memory ceiling.

The MainActor view model owns one coordinator actor and one cancellable Task.
Progress is forwarded to MainActor and gated by run identity/running state so
late callbacks cannot overwrite a completed result. File selection and analysis
options are disabled during a run. Security-scoped URL access is retained until
replacement selection or application exit. Results live in memory only.

The app has no Photos permissions/access, saved reviews, database writes, archive,
delete or editing actions. All source photographs remain read-only. The existing
Python CLI and analysis engine algorithms are unchanged. The prototype currently
supports macOS 15+, not iOS/iPadOS; shared libraries retain their separate declared
platform availability and device-validation limits.

The earlier test bundle under `../NativeApps/` is retained as a development artifact;
iCloud adds Finder metadata there that causes strict signature verification to fail.
Use the local artifact above, or build to a new folder outside iCloud.

## Build

With the pinned local OpenCV dependency prepared:

```sh
OPENCV_ROOT=/path/to/opencv/install \
SIFT_BUILD_ROOT=/private/tmp/photo-review-build \
experiments/apple_native/SIFTBridge/build_app.sh "/absolute/path/New Photo Review.app"
```

The destination must be a new absolute `.app` path; the script refuses occupied
paths and symlinks. It compiles, creates the bundle, removes inherited metadata
from that newly generated bundle and ad-hoc signs/verifies it. Binaries, caches,
build logs and app bundles stay outside Git. This is a local development bundle,
not a notarized or App Store distribution build. Full Xcode remains required for
the planned Apple-platform app/device build and distribution work.

The installed Command Line Tools SDK declares both a State macro and the standard
State property wrapper but lacks the SwiftUIMacros compiler plugin. A public type
alias selects the standard property-wrapper type explicitly; no private SwiftUI
API is used. No toolkit installation or developer-directory change is needed.

## Validation

The macOS app compiles and its ad-hoc signature verifies. Native UI inspection
covers the empty screen, file selection, live progress, cancellation returning to
a rerunnable state, successful photo review, tier totals, subject-box toggle and
set navigation. Visual inspection caught and corrected vertical alignment of
mixed-aspect photo cards. UI processing uses disposable, checksum-identical copies
of real samples in `../IntegrationChecks/20261103-native-ui/samples`; source and
copy checksums are verified separately. That initial run was a small UI smoke test. The later full 151-photo timing
investigation is recorded below; device validation remains open. The coordinator's earlier full 151-photo
parity result remains documented in COORDINATOR.md.

Next: read-only PhotoKit input, followed by persisted reviews through the existing
SQLite contract. Mobile builds, permissions and memory/thermal validation remain
open. A local Git checkpoint was authorized on November 3; no push or merge was requested.

## Progress-label correction and timing investigation

The original prototype displayed the matching phase as “Comparing photos” while
its counter actually represented pairs. For 151 selected photos, the engine checks
151 × 150 / 2 = **11,325 pairs**. No additional files are discovered or scanned
in that phase. Its bar also restarted at each phase without a visible step number.

The updated UI explicitly identifies all five steps, uses “selected photos” for
file counts and “pairs across 151 selected photos” for matching, and labels the bar
as progress for the current step. It shows live elapsed time, completed-run time
and a Processing time disclosure with the five phase durations. Durations are
recorded in memory as part of AnalysisResult, using a monotonic clock in the
coordinator; there are no new routine logs, sidecars or database writes.

The earlier roughly 39–41 second SIFT benchmark consumed frozen pixels and Vision
distances. It excluded live decoding, orientation, Vision and full image analysis.
The original complete 151-photo coordinator run took 160.99 seconds. Neither test
by itself measures a user's app session. A separately named Photo Review Diagnostics
bundle preserves the user's existing app/review while exercising this change;
it differs in bundle identifier/display name but uses the same updated executable.

The analysis Task explicitly uses user-initiated priority and brackets the finite
operation with `ProcessInfo.beginActivity(.userInitiatedAllowingIdleSystemSleep)`.
`defer` ends that activity on success, cancellation and failure. This tells macOS
about the requested work without disabling normal idle sleep or changing system
settings. A runtime stack sample before this addition already showed the worker
on a user-initiated cooperative queue, so priority alone is not claimed as the
cause of the reported slowdown. The one-second sample found substantial active
focus-measurement work while MainActor was idle; it is a snapshot, not a complete
CPU attribution or proof of App Nap. Timing comparisons below remain empirical.

The file picker now sorts selected URLs by path (UTF-8 lexical order), matching
the accepted CLI sample order instead of inheriting Finder's current display
order. The earlier native coordinator preserved caller order; comparisons using
different input orders are not exact replays of the accepted fixture. No metric,
matching threshold or ranking rule is retuned by this change.

### Measured UI results after the correction

| Run | Analyze photos | Compare pairs | Total |
| --- | ---: | ---: | ---: |
| Original scheduling / Finder order | 5m 8s | 1m 51s | 7m 3s |
| Scoped user activity / CLI-compatible path order | 2m 10s | 32s | 2m 45s |
| Earlier full coordinator test | Not recorded separately | Not recorded separately | 160.99s |

Both UI runs selected exactly 151 files and checked 11,325 pairs with auto-rotation
enabled. These are observed runs, not a controlled speedup estimate: input order,
cache state and operating-system scheduling were not varied independently. The
updated app is close to the earlier complete test time. No inference, focus,
matching or ranking algorithm was changed.

The updated UI returned the accepted counts: 23 groups, 86 ungrouped, 12 Top Pick,
112 Keep & Review and 27 Possible Cull. Before canonical ordering, the picker-order
run returned 85 ungrouped and 12/110/29 tiers; that is not presented as an exact
replay of the accepted path-ordered fixture. The raw coordinator comparison below
checks all evidence/decisions with exactly matched input order.

Private timing records and the stack sample are retained outside Git under
`../IntegrationChecks/20261103-native-progress/`. The diagnostics app is version
0.2. Existing user reviews in the original app were not closed or overwritten.

The final path-ordered 151-photo / 11,325-pair CLI replay passed with **zero**
differences in decisions, pair levels/evidence, keypoints, rotations, focus flags,
tiers and UI summary ranks. Original checksums were unchanged. This fresh run
took 160.79 seconds including comparison overhead, independently confirming the
updated UI's 2m 45s result is near the complete native engine's current runtime.
Per-phase timings are validated as finite/nonnegative complete phase data in the
comparison harness; the private summary retains the exact phase durations.
