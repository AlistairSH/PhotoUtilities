# Framewise macOS app

Framewise is the SwiftUI app built on NativePhotoAnalysis. See the
[project README](../../README.md) for a quick start.

## Current experience

Use **Choose Files…** or **Choose from Photos…** to select up to 500 JPEG,
HEIC/HEIF, PNG or single-image TIFF images. Set **Auto-rotate** before choosing a
batch. Scanning starts when you confirm the selection. **Stop Scan** cancels
loading or analysis. Successful results
show related sets and an ungrouped set in the sidebar, tier totals, ordered photo
cards, focus notes, positive and advisory reasons, applied rotations and ranks
within displayed sets. Subject boxes can be toggled with the accepted legend.
Show in Finder reveals the original for selections made through the file picker.

The macOS system Photos picker supplies only explicitly selected items. Framewise
requests their current image representations. The app loads
these in selection order, stages byte-for-byte copies for the same analysis
coordinator, and keeps the copies available for review previews. Staged copies
are removed on replacement selection or normal app exit. A failed or cancelled
load discards the new batch and leaves the previous selection or review available.
The Photos picker may need to retrieve an image that is stored in iCloud.

Previews are bounded to 640 pixels, loaded off MainActor through a serial thumbnail
actor, with a 64 MiB cost-limited cache. Their embedded orientation and the analysis
quarter-turn are applied for display. This cache limit is not a bound on the whole
analysis engine's memory or a guaranteed process memory ceiling.

The MainActor view model owns one coordinator actor and one cancellable Task.
Progress is forwarded to MainActor and gated by run identity/running state so
late callbacks cannot overwrite a completed result. File selection and analysis
options are disabled during a run. Security-scoped URL access is retained until
replacement selection or application exit. Results live in memory only.

**Zoom…** on each card opens a full-resolution preview
with Fit, 100%, 200% and 400% views. Scroll to inspect different parts of the
image. The app decodes one full-resolution preview at a time.

**Delete…** asks for confirmation. A file selection goes to the Mac Trash
after the app checks that its contents still match the analyzed file.
The remaining cards keep their analysis and update their displayed counts and
ranks. Click **Scan Again** to recompute the review for the remaining photos.
In the Photos-enabled build, **Delete…** moves the confirmed asset to Recently
Deleted using its Photos identifier and macOS authorization. Restore library
items in Photos or use **Put Back** in Finder for files moved to Trash.

Open **Help → Framewise Help** to search topics inside the app. The Help menu also
lists individual topics. Use **Window → Show Framewise** to restore the main
review window after it has been minimized, hidden or closed.

## Build

Follow the [project build instructions](../../README.md#build-and-run).
`build_app.sh` packages the SwiftPM `Framewise` executable and generates
`AppIcon.icns` from the approved `Resources/AppIcon.png`. The bundle identifier
is `local.photoutilities.review`. The `--enable-photos-delete` option adds the
Photos usage description and Photos-library entitlement when signing.

The script requires a new absolute `.app` path and refuses occupied paths.
Use a destination outside Git and iCloud. The script removes inherited metadata
from the newly generated bundle before signing and verifying it. This is a local
development build. Full Xcode remains necessary for device and distribution work.

The installed Command Line Tools SDK declares both a State macro and the standard
State property wrapper but lacks the SwiftUIMacros compiler plugin. The app's
`ViewState` type alias explicitly selects the standard property wrapper.

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

Saved reviews, mobile builds and memory/thermal validation remain open.

For version 0.3, the signed app opened the system picker and displayed its
selected-items privacy notice. A local file-provider test transferred five
disposable JPEG and HEIC fixtures through the app's transfer representation.
The staged bytes matched the source bytes, and all five review results and ten
pair records matched direct-file analysis after normalizing paths and excluding
timings. The test also checked staging cleanup, unreadable-file rejection and a
cancelled staging task.

A live six-photo review produced the expected two groups. The four runner
photos delivered by the picker were Display P3 HEIC files. Their corresponding
disk files were JPEGs with the Apple Wide Color Sharing Profile. A replay in
the same input order reproduced one additional Possible Cull on the HEIC
representation. The difference came from a peer crossing the 1.5× threshold
on both subject-detail measures. For a parity check, compare the same image
representation in the same order and with the same auto-rotate setting. A follow-up
using HEIF exports matched the Photos picker results for all six images. The user
also confirmed the zoom, deletion, and equal-height card tests.

## November 3 progress and timing investigation

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
