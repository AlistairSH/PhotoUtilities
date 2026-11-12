# Native migration status

[Framewise](../../README.md) is the native macOS app for digital-photo review.
The [scanner and batch CLI](../../CLI.md) continues to own scanner workflows,
SQLite history and ZIP archive/restore. The [geometry gate](GEOMETRY_GATE.md)
retains SIFT. Focus validation is documented in [EDGE_PERFORMANCE.md](EDGE_PERFORMANCE.md)
and [DECISION_PARITY.md](DECISION_PARITY.md).

The table distinguishes Framewise’s current macOS path from earlier portability
recommendations and outstanding validation.

| Feature | Status | Evidence / remaining gate |
| --- | --- | --- |
| ImageIO display decode, EXIF orientation, bounded thumbnails | Used by Framewise | The app calls the Swift library directly. The JPEG/HEIC corpus processed without omissions. iOS device validation remains open. |
| Vision feature prints, pinned revision 2 / scaleFit | Used by Framewise | Same native request and cutoff. Feature-print distance remains candidate evidence. |
| Swift connected components and pair-level rule | Used by Framewise | Strict boundary tests, SIFT boolean classification support and chained groups preserved. Vision-only runtime deliberately lacks SIFT evidence. |
| Rotation/crop/resize/display export | Replace with limitations | Synthetic JPEG/HEIC/PNG/TIFF coverage and no-overwrite/source checks pass. Only 8-bit sRGB display derivatives; not high-depth or calibrated archival fidelity. Arbitrary-angle edges/alpha and repeated resampling require visual evaluation. |
| EXIF inspection and capture-date export | Replace with limitations | ImageIO property read and capture-date round trips tested. Maker notes deliberately removed, pixel/orientation tags normalized. No arbitrary metadata fidelity guarantee. |
| RAW review from disk | Implemented for compatible single-image sources | The analysis engine completed focus measurements, grouping, and ranking on an Olympus E-M1 ORF and an iPhone 12 Pro ProRAW DNG. Decoder support depends on macOS, camera model, and shooting mode. RAW Favorites last for the review. |
| ICC, high-depth TIFF and general metadata interoperability | Further validation needed | Display rendering converts to sRGB. Archival color, high-depth processing, manufacturer tags and metadata round trips require separate validation. |
| Favorites | Implemented in Framewise | Verified lossless file updates embed the Favorite keyword in supported JPEG, PNG, single-image TIFF, and PSD files. Other file layouts use review-only Favorites. Library assets use the native Photos Favorite flag. |
| Save to Photos | Implemented in the Photos-enabled build | Copies the selected disk original into Photos with permission to add photos. A user confirmed a disk import. RAW import and original-resource export round trips still need validation. |
| Gaussian1 global/regional focus metrics | Replace with limitations | Pinned grayscale/Gaussian rounding corrected; 302-view native replay preserves all current recommendations and regional mask counts. Larger-corpus/device validation remains open. |
| Edge extraction and subject evidence | Replace with limitations | Corrected arithmetic resolves the 48-versus-50 boundary; all 302 regional sufficiency assessments and global edge flags agree. Two global profile counts still differ slightly. Larger-corpus/device validation remains open. |
| Full focus decisions and sharper/softer recommendations | Used by Framewise | Full Swift port agrees on 151 frozen-image decisions/reasons and 106 synthetic cases. Native pixel replay also preserves all recommendations. Framewise uses the Swift policy. Larger-corpus/device validation remains open. |
| SIFT supplementation | Used by Framewise and validated on macOS | Separate SIFTBridge wraps pinned OpenCV 4.11.0; all 11,325 pair decisions and raw evidence agree, restoring all three labeled SIFT-only links. iOS XCFramework/device validation remains open; no Python application runtime is required. See SIFT_GATE.md. |
| Native homographic alternative | Retain SIFT; tested request fails replacement gate | All returned confidences are 1, including unrelated/featureless controls; known crops misalign. Padding removes dimension rejection but does not recover validated match evidence. See GEOMETRY_GATE.md; human labels and held-out correspondence/coverage validation precede any replacement. |
| Face/body/animal/saliency and native quality evidence | Replace with limitations | Existing native evidence reused, including availability failure for unsupported aesthetics. No confidence-to-quality or aesthetic-to-merit equivalence assumed. iOS/iPadOS validation still needed. |
| Scene classification | Requires further experimentation | Optional Vision labels are evidence, not validated category assignments; no labeled confusion matrix. |
| Foundation Models semantic/aesthetic assessment | Retain existing implementation (disabled in accepted pipeline) | No unvalidated local language-model output is introduced. Availability and image capability need explicit checks before any future use; Vision evidence is the current fallback. |
| Tier ranking and standalone policy | Used by Framewise | Full Swift port preserves tiers, explanations and ordering on the 151-image fixture and synthetic boundary cases. Full-batch references, ties, no quotas and advisory composition are unchanged. |
| Review UI and orchestration | Implemented in Framewise | NativePhotoAnalysis preserves the 151-image fixture’s decisions, pair evidence and ordering. Framewise supports files and Photos picker inputs, progress, cancellation, and confirmed removal. See [COORDINATOR.md](COORDINATOR.md) and [UI.md](UI.md). |
| SQLite/history | Retain existing implementation | No portability blocker demonstrated; no experiment DB, schema or historical record changes. |
| Scanner capture, splitting, fixed retouch and ICC | Retain existing implementation | Explicitly outside scope; no changes. |

The Accelerate/partial-selection backend passes the frozen decision gate and is
3.27× faster in the paired eight-view benchmark. Full replay takes 71 seconds,
with peak child memory about 550 MiB versus 524 MiB for the earlier scalar replay.
Keep the scalar backend as a reference; mobile memory and thermal validation remain open.

Human review confirms all three SIFT-only links: the accepted rule agrees on all
eight decisive labels (one uncertain is excluded); Vision-only agrees on five.
Next gate: use full Xcode to build the prepared OpenCV XCFramework and a small
consumer app, then verify matching parity and memory/thermal behavior on an actual
iPhone/iPad.
Expand labeled real crop/reframe/burst and confusing-negative cases before changing
algorithms or thresholds. Obtain the real 475-image manifest before claiming full
workflow parity. Photos export and archival RAW and high-depth processing remain
deferred.

November 3 update: the live file-analysis coordinator passes the full current
151-image / 11,325-pair comparison with zero decision/pair/rotation differences.
This replay preceded current Framewise integration. Full-Xcode/device,
mobile-memory and saved-review checks remain open.
