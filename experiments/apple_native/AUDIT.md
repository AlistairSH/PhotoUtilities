# Shared digital-photo dependency audit

Baseline: `experiment/ranking-culling` at `8809e81`; compared with `main`
`857f306` (processing modules identical). `experiment/apple-vision` at `051d05f`
contains the initial feasibility spike; accepted algorithms are in the later baseline.
This document describes an unmerged, offline experiment, not CLI changes.

| Operation / current implementation | Dependencies | Shared? | Native candidate | Behavior risks | Difficulty / value |
| --- | --- | --- | --- | --- | --- |
| Decode, orientation, 1024/2048 sRGB views: `photo_utils/native/vision.swift` | ImageIO, CoreGraphics, CoreImage | Yes | Retain existing path in Swift package | Thumbnail sampling, premultiplied alpha, color conversion affect metrics | Low / high, already native |
| Feature prints / distances: same helper | Vision revision 2, scaleFit | Yes | Retain, pin revision and <.45 / <.40 | Revision and preprocessing must match; distance is not identity | Low / high |
| SIFT: `similarity.py:sift_pair` | OpenCV + NumPy; 500 features, mutual .75 ratio, homography RANSAC 3px / 2000 / .995, >=12 inliers, >=.5 fraction, >=.1 coverage each | Yes | First measure Vision-only ablation; investigate Vision registration as subsequent geometric evidence | Global registration is not equivalent to sparse feature correspondences and hull coverage; crops/reframes can lose links | High / critical; retain until demonstrated |
| Connected components / pair classification: `similarity.py` | Python collections | Yes | Swift graph traversal, exact thresholds | Chaining and likely-only connectivity must survive | Low / worthwhile for standalone execution |
| Gaussian1 regional focus: `focus_measurements.py` | OpenCV grayscale, Gaussian, Sobel, Laplacian, masks; NumPy statistics | Yes | Swift scalar reference first, then Accelerate after parity | 8-bit Gaussian fixed-point rounding, reflect101 edges, mask guards, quantiles and box rounding | Medium / high |
| Contrast edge probes: `focus_edges.py` | NumPy random sampling/interpolation, OpenCV remap | Yes | Swift port with explicitly matched sampling/interpolation | RNG choice, bilinear quantization and profile interpolation change flags | High / high; not replaced by global sharpness |
| Focus policy: `focus_policy.py`, `focus.py` | Python + NumPy measurement inputs | Yes | Swift policy after complete regional and edge parity | Two scales, IoU .5, 10% cohort tail, 1.5x direct-pair comparisons; missing != sharp | Medium / critical; preserve existing implementation pending evidence |
| Detection, face quality, eyes/smile, aesthetics: `native/vision.swift` | Vision, CoreImage | Yes | Reuse existing native evidence with availability checks | Some ranking evidence requires newer OS; no unvalidated aesthetic proxy | Low / high |
| Endpoint clipping, saliency layout, tiers: `tiers.py` | NumPy + Python | Yes | Swift statistics and policy port | Full-batch solo references, percentile ties, sort stability, composition advisory only | Medium / high; defer replacement until policy parity |
| Preview JPEG + resize: `similarity.py` | OpenCV | Yes | ImageIO thumbnails + JPEG encoding | Filtering, alpha, color and lossy output differ | Low / worthwhile |
| Full-resolution rotation: `rotation.py` | ImageMagick, ExifTool, Python/SQLite | Yes | CoreImage transforms, ImageIO destination | Bit depth, ICC and metadata preservation require verification; display 8-bit is not archival | Medium / high |
| Derivative metadata: `rotation.py`, `retouch.py` metadata arguments | ExifTool | Partly (retouch scanner recipe excluded) | ImageIO properties + CGImageMetadata/XMP | Unsupported tags/maker notes, keywords/ratings consumers and stale dimensions; Photos does not auto-refresh | High / conditional |
| TIFF: `processing.py`, `scanning.py`, `retouch.py` | tifffile, NumPy, OpenCV, ImageMagick | Predominantly scanner specific | Retain; native experiment only tests single-image digital TIFF | Multi-page, scanner 16-bit and calibrated ICC are outside this experiment | No scanner migration |
| Jobs/history/lineage: `database.py` | stdlib SQLite | Yes persistence contract | Retain existing DB untouched; isolated experiment exports only | Never create competing routine state or rewrite records | No replacement warranted |
| Capture/split/retouch/orchestration | SANE, ImageMagick, OpenCV, NumPy, ExifTool, tifffile | Scanner specific | Retain | Explicitly excluded | Out of scope |

No production dependency can be removed from installation on this evidence.
Foundation Models experiments in `ranking_culling/foundation_models` provide
capability probes, not a validated aesthetic or photographic-merit score.
No cloud model, Metal implementation or new external dependency is justified.
The reusable library must avoid AppKit and process execution for iOS/iPadOS;
its macOS command-line harness is only a host adapter. An iOS build/test remains
required before claiming device portability.
