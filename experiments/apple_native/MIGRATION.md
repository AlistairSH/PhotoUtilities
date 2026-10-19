# Migration recommendation

This experiment does not authorize integration or dependency removal. The [geometry gate](GEOMETRY_GATE.md) retains SIFT after known-transform and control evaluation. Current focus validation is documented in [EDGE_PERFORMANCE.md](EDGE_PERFORMANCE.md) and [DECISION_PARITY.md](DECISION_PARITY.md).
The 475-image workflow is not yet reproducible entirely in native Swift with accepted behavioral
parity. Keep the accepted pipeline as the working implementation.

| Feature | Recommendation | Evidence / remaining gate |
| --- | --- | --- |
| ImageIO display decode, EXIF orientation, bounded thumbnails | Ready to replace the bridge for standalone native display analysis | Already native in the accepted helper; retained decoding path, current JPEG/HEIC corpus processed without omissions. A library API and iOS device validation still precede shared app integration. |
| Vision feature prints, pinned revision 2 / scaleFit | Ready to replace the Python orchestration of these operations | Same native request and cutoff. Feature-print distance remains candidate evidence. |
| Swift connected components and pair-level rule | Ready to replace | Strict boundary tests, SIFT boolean classification support and chained groups preserved. Vision-only runtime deliberately lacks SIFT evidence. |
| Rotation/crop/resize/display export | Replace with limitations | Synthetic JPEG/HEIC/PNG/TIFF coverage and no-overwrite/source checks pass. Only 8-bit sRGB display derivatives; not high-depth or calibrated archival fidelity. Arbitrary-angle edges/alpha and repeated resampling require visual evaluation. |
| EXIF inspection and capture-date export | Replace with limitations | ImageIO property read and capture-date round trips tested. Maker notes deliberately removed, pixel/orientation tags normalized. No arbitrary metadata fidelity guarantee. |
| ICC, high-depth TIFF, RAW and XMP/ratings/keywords | Requires further experimentation | Real RAW and digital TIFF corpus absent; ICC converted to display sRGB. XMP packets, manufacturer tags and consumer-specific discovery not validated. Retain ExifTool where complete metadata interoperability is required. |
| Gaussian1 global/regional focus metrics | Replace with limitations | Pinned grayscale/Gaussian rounding corrected; 302-view native replay preserves all current recommendations and regional mask counts. Larger-corpus/device validation remains open. |
| Edge extraction and subject evidence | Replace with limitations | Corrected arithmetic resolves the 48-versus-50 boundary; all 302 regional sufficiency assessments and global edge flags agree. Two global profile counts still differ slightly. Larger-corpus/device validation remains open. |
| Full focus decisions and sharper/softer recommendations | Ready to replace the policy implementation with equivalent inputs | Full Swift port agrees on 151 frozen-image decisions/reasons and 106 synthetic cases. Native pixel replay also preserves all recommendations. Production integration is separate; larger-corpus/device validation remains open. |
| SIFT supplementation | Swift-facing compiled implementation validated on macOS; retain production until app/device gate | Separate SIFTBridge wraps pinned OpenCV 4.11.0; all 11,325 pair decisions and raw evidence agree, restoring all three labeled SIFT-only links. iOS XCFramework/device validation remains open; no Python application runtime is required. See SIFT_GATE.md. |
| Native homographic alternative | Retain SIFT; tested request fails replacement gate | All returned confidences are 1, including unrelated/featureless controls; known crops misalign. Padding removes dimension rejection but does not recover validated match evidence. See GEOMETRY_GATE.md; human labels and held-out correspondence/coverage validation precede any replacement. |
| Face/body/animal/saliency and native quality evidence | Replace with limitations | Existing native evidence reused, including availability failure for unsupported aesthetics. No confidence-to-quality or aesthetic-to-merit equivalence assumed. iOS/iPadOS validation still needed. |
| Scene classification | Requires further experimentation | Optional Vision labels are evidence, not validated category assignments; no labeled confusion matrix. |
| Foundation Models semantic/aesthetic assessment | Retain existing implementation (disabled in accepted pipeline) | No unvalidated local language-model output is introduced. Availability and image capability need explicit checks before any future use; Vision evidence is the current fallback. |
| Tier ranking and standalone policy | Ready to replace the policy implementation with equivalent inputs | Full Swift port preserves tiers, explanations and ordering on the 151-image fixture and synthetic boundary cases. Full-batch references, ties, no quotas and advisory composition are unchanged. |
| Review UI and orchestration | Retain existing implementation | The Swift computational core is validated separately; production HTML, SIFT orchestration, database and menu behavior are unchanged. |
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
iPhone/iPad. Keep the accepted production implementation until that gate passes.
Expand labeled real crop/reframe/burst and confusing-negative cases before changing
algorithms or thresholds. Obtain the real 475-image manifest before claiming full
workflow parity. Photos, RAW/high-depth and broader app integration remain deferred.
