# Migration recommendation

This experiment does not authorize integration or dependency removal. The 475-image
workflow is not yet reproducible entirely in native Swift with accepted behavioral
parity. Keep the accepted pipeline as the working implementation.

| Feature | Recommendation | Evidence / remaining gate |
| --- | --- | --- |
| ImageIO display decode, EXIF orientation, bounded thumbnails | Ready to replace the bridge for standalone native display analysis | Already native in the accepted helper; retained decoding path, current JPEG/HEIC corpus processed without omissions. A library API and iOS device validation still precede shared app integration. |
| Vision feature prints, pinned revision 2 / scaleFit | Ready to replace the Python orchestration of these operations | Same native request and cutoff. Feature-print distance remains candidate evidence. |
| Swift connected components and pair-level rule | Ready to replace | Strict boundary tests, SIFT boolean classification support and chained groups preserved. Vision-only runtime deliberately lacks SIFT evidence. |
| Rotation/crop/resize/display export | Replace with limitations | Synthetic JPEG/HEIC/PNG/TIFF coverage and no-overwrite/source checks pass. Only 8-bit sRGB display derivatives; not high-depth or calibrated archival fidelity. Arbitrary-angle edges/alpha and repeated resampling require visual evaluation. |
| EXIF inspection and capture-date export | Replace with limitations | ImageIO property read and capture-date round trips tested. Maker notes deliberately removed, pixel/orientation tags normalized. No arbitrary metadata fidelity guarantee. |
| ICC, high-depth TIFF, RAW and XMP/ratings/keywords | Requires further experimentation | Real RAW and digital TIFF corpus absent; ICC converted to display sRGB. XMP packets, manufacturer tags and consumer-specific discovery not validated. Retain ExifTool where complete metadata interoperability is required. |
| Gaussian1 global focus metrics | Requires further experimentation | Close numerical/order agreement on 151 images at two scales, but measurable Laplacian differences. Establish regional/decision parity before Accelerate optimization or replacing production. |
| Regional/outside metrics and subject detail | Requires further experimentation | Four scale rows on two samples exercise native masks, dilations, guards and ratios. This is not broad portrait/group/wildlife validation. |
| Full focus decisions and sharper/softer recommendations | Retain existing implementation | Edge profiles, seeded sampling, remap interpolation, contrast/scale confirmation, cohort policies and direct-pair comparisons have not all been ported and validated. Global sharpness alone is insufficient. |
| SIFT supplementation | Retain existing implementation | Vision-only loses baseline links and a group in the current corpus; historical reviewed positives also need SIFT. No cutoff changes justified. |
| Native homographic alternative | Requires further experimentation | Probe returns a matrix, but no mutual inlier count/fraction/hull coverage equivalent. Needs cropped/reframed/burst positives and composition-difference negatives, and a validated photometric residual/overlap gate before use. |
| Face/body/animal/saliency and native quality evidence | Replace with limitations | Existing native evidence reused, including availability failure for unsupported aesthetics. No confidence-to-quality or aesthetic-to-merit equivalence assumed. iOS/iPadOS validation still needed. |
| Scene classification | Requires further experimentation | Optional Vision labels are evidence, not validated category assignments; no labeled confusion matrix. |
| Foundation Models semantic/aesthetic assessment | Retain existing implementation (disabled in accepted pipeline) | No unvalidated local language-model output is introduced. Availability and image capability need explicit checks before any future use; Vision evidence is the current fallback. |
| Tier ranking, standalone assessment, review UX | Retain existing implementation | Native evidence emission is not an implementation of `tiers.py`; no final tier/rank/standalone recommendation parity claimed. Preserve full actual batch, ties, no quotas, independent focus flags and advisory composition. |
| SQLite/history | Retain existing implementation | No portability blocker demonstrated; no experiment DB, schema or historical record changes. |
| Scanner capture, splitting, fixed retouch and ICC | Retain existing implementation | Explicitly outside scope; no changes. |

Next gate: port the complete edge-profile/confirmation policy and tier arithmetic
against frozen evidence fixtures; compare decisions at unchanged thresholds.
Benchmark Accelerate versus the scalar reference on those same pixels. Evaluate
native registration with labeled geometry/photometric evidence rather than treating
a returned matrix as proof. Obtain the real 475-image fixture manifest and labels,
then run full native and accepted pipelines sequentially, including standalone
assessment and image-preservation verification. Test device/library portability,
RAW/high-depth/wide-gamut cases and Photos/Photomator metadata imports separately,
using disposable derivatives and explicit future authorization for library actions.
