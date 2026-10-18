# Migration recommendation

This experiment does not authorize integration or dependency removal. Current decision validation is documented in [DECISION_PARITY.md](DECISION_PARITY.md).
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
| Edge extraction and subject evidence | Requires further experimentation | Complete native extractor preserves current recommendations, but one face has 48 versus 50 usable edges. Resolve/test that specific sample-count boundary before integration. |
| Full focus decisions and sharper/softer recommendations | Ready to replace the policy implementation with equivalent inputs | Full Swift port agrees on 151 frozen-image decisions/reasons and 106 synthetic cases. Native pixel replay also preserves all recommendations. Production integration is separate; edge-boundary limitation still applies. |
| SIFT supplementation | Retain existing implementation | Vision-only loses baseline links and a group in the current corpus; historical reviewed positives also need SIFT. No cutoff changes justified. |
| Native homographic alternative | Requires further experimentation | Probe returns a matrix, but no mutual inlier count/fraction/hull coverage equivalent. Needs cropped/reframed/burst positives and composition-difference negatives, and a validated photometric residual/overlap gate before use. |
| Face/body/animal/saliency and native quality evidence | Replace with limitations | Existing native evidence reused, including availability failure for unsupported aesthetics. No confidence-to-quality or aesthetic-to-merit equivalence assumed. iOS/iPadOS validation still needed. |
| Scene classification | Requires further experimentation | Optional Vision labels are evidence, not validated category assignments; no labeled confusion matrix. |
| Foundation Models semantic/aesthetic assessment | Retain existing implementation (disabled in accepted pipeline) | No unvalidated local language-model output is introduced. Availability and image capability need explicit checks before any future use; Vision evidence is the current fallback. |
| Tier ranking and standalone policy | Ready to replace the policy implementation with equivalent inputs | Full Swift port preserves tiers, explanations and ordering on the 151-image fixture and synthetic boundary cases. Full-batch references, ties, no quotas and advisory composition are unchanged. |
| Review UI and orchestration | Retain existing implementation | The Swift computational core is validated separately; production HTML, SIFT orchestration, database and menu behavior are unchanged. |
| SQLite/history | Retain existing implementation | No portability blocker demonstrated; no experiment DB, schema or historical record changes. |
| Scanner capture, splitting, fixed retouch and ICC | Retain existing implementation | Explicitly outside scope; no changes. |

Next gate: investigate the observed 50-versus-48 face-edge boundary without changing
thresholds, then benchmark Accelerate against the scalar replay using the same
frozen decision gate. Keep SIFT while validating a native alternative on labeled
geometry/photometric cases; successful registration alone is insufficient. Obtain
the real 475-image manifest and labels for a larger sequential comparison. Device,
RAW/high-depth and Photos/Photomator checks remain separate, lower-priority gates.
