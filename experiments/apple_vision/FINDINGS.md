# Feasibility findings — October 11, 2026

Status: useful read-only spike; **not approved or ready for production integration**.
Branch `experiment/apple-vision` created from local `main`, preserving pre-existing
AGENTS.md/PROJECT.md edits. Remote freshness was not checked; nothing was pushed,
merged, committed, or uploaded. Scan/split/retouch/SQLite implementation unchanged.

## Native API and bridge findings

Actual host: Apple Silicon arm64, macOS 26.6.2 build 25G83, Swift 6.4.
The installed Vision SDK declares feature-print revision 1 (macOS 10.15+) and
revision 2 (macOS 14+). Runtime returned supported revisions [1, 2]; revision 2
produced 768-element prints. We pin revision 2 and `.scaleFit`; distances are
only comparable within the same revision/preprocessing. No calibrated duplicate
threshold is established.

The SDK also declares aesthetics assessment (macOS 15+), including `overallScore`
and `isUtility`. Apple describes aesthetics rather than technical focus; utility
images need not be poor quality. This API was inspected, not executed. No verified
generic focus classifier is claimed. Feature prints measure visual similarity,
not absolute quality.

PyObjC Vision/Foundation/Quartz imports were unavailable in the project environment.
Swift compiled against the installed SDK without any package/model download. We
selected a small Swift subprocess using Foundation/Vision/ImageIO/CoreGraphics,
leaving Python dependencies untouched. This establishes a working Swift route,
not a measured Swift-versus-PyObjC performance comparison. Installing/maintaining
three additional bridge packages has no demonstrated benefit yet.

Sources: [Apple feature-print request](https://developer.apple.com/documentation/vision/vngenerateimagefeatureprintrequest),
[Apple feature-print distance](https://developer.apple.com/documentation/vision/vnfeatureprintobservation/computedistance(_:to:)),
[Apple aesthetics request](https://developer.apple.com/documentation/vision/vncalculateimageaestheticsscoresrequest).
Local API availability was additionally checked in the installed SDK headers.

## Comparison

Deterministic synthetic graphic: sharp original, exact duplicate, Gaussian
softness, sharp region over soft background (shallow-depth proxy), horizontal
motion blur, brightened copy, white clipping, unrelated random noise. These
are controlled numerical fixtures, **not representative camera photographs**.

| Relative to sharp fixture | Vision distance | 64x64 grayscale RMSE |
| --- | ---: | ---: |
| Identical duplicate | 0.000 | 0.000 |
| Brightened copy | 0.134 | 0.241 |
| Soft background/sharp region | 0.473 | 0.030 |
| Gaussian softness | 1.011 | 0.039 |
| Motion blur | 1.034 | 0.039 |
| Unrelated noise | 1.072 | 0.177 |
| White clipping | 1.294 | 0.601 |

Vision adds useful tolerance for brightness changes beyond naive pixel matching.
But blur shifts the embedding strongly and an unrelated noise image is only
slightly farther away than blurred copies. Semantic near-duplicate matching
needs a labeled photo set; do not infer a universal distance cutoff.

OpenCV normalized Laplacian variance fell from 0.00423 (sharp) to 0.0000196
(Gaussian soft) and 0.000133 (motion). Noise scored 0.755, much higher than the
sharp fixture. Detail content, contrast, preview scale, grain and intentional
softness confound global blur measures. NumPy clipping and grayscale statistics
remain useful interpretable evidence; Vision does not replace them.

For one existing vintage print and its retouch, full-frame Vision distance was
0.239 and grayscale RMSE 0.229. Mean grayscale rose from 0.444 to 0.665; normalized
Laplacian variance rose from 0.000744 to 0.000953 without any sharpening recipe.
Contrast/exposure changes alone affect sharpness metrics. Both dispositions were
`unable-to-determine`; photographic bounds were not manually supplied, so these
full-frame values **must not be treated as border-excluded quality assessment**.
No private image or preview was sent for model/cloud visual inspection.

Only extreme (>50%) near-black/near-white grayscale occupancy in explicitly
identified digital inputs prompts `review`. This is an experimental heuristic,
not rejection or a validated quality label. All other cases are
`unable-to-determine`; no `pass` threshold is claimed. The intentional-softness
synthetic cases had zero review flags; a real-world false-positive rate remains
unknown. Clipped channels can be missed by grayscale occupancy; future work
should distinguish per-channel sensor/render clipping and lighting context.

## Verification and cost

- Existing regression suite: 68 tests passed. Application Pyright strict:
  zero errors/warnings. Experimental numerical/native tests: 4 passed, including
  duplicate distance, unchanged inputs, JPEG/PNG/TIFF/HEIC decoding, TIFF EXIF
  orientation 6 dimensions, ROI metric changes, unsupported-platform error, and corrupt-input failure.
- Native tests, synthetic benchmark and real TIFF comparison succeeded with
  `sandbox-exec` explicitly denying network access. No model downloads needed.
- Initial native execution inside the agent sandbox failed with OSStatus -6662
  (pixel-buffer pool); approved execution outside it succeeded. Decoder/Vision
  errors remain errors, not quality dispositions.
- Warm real two-image process: approximately 0.28 seconds end-to-end;
  `/usr/bin/time -l` reported about 109 MiB maximum resident set size for the
  timed Python process. This is **not an aggregate parent+helper peak**. First
  observed helper run was 0.37 seconds, Python wall time 0.46 seconds; compilation
  took approximately 10 seconds on the first run. Eight small synthetic inputs
  took approximately 0.10 seconds inside the helper, 0.19 seconds Python wall.
  Timing excludes input hashing and is approximate; caches/input sizes vary.
- Per-input SHA-256 matched before/after analysis. A separate snapshot covering
  all nine existing October 10 TIFFs plus production jobs.sqlite3 matched after
  subsequent tests/benchmarks. Snapshot was taken after the first pair analysis;
  its two hashes were independently verified then. No DB code is called by the
  experiment; production DB was never opened through SQLite.
- `git diff --check` clean. Generated images, previews, binaries and reports were
  kept in temporary storage; image/database patterns added to `.gitignore`.

## Recommendation and remaining gate

Retain Swift as the experimental native bridge. Prioritize opt-in similarity
candidate reporting alongside interpretable OpenCV/NumPy evidence, without
automatic clustering, deletion or focus decisions. Keep the production CLI as-is.

Before integration: obtain a separately chosen real digital-image set; manually
inspect naturally soft vintage scans, sharp/blurred digital frames, actual shallow
depth of field, noise, difficult lighting and distinct-but-similar scenes. Measure
false review flags/false merges, validate actual photographic ROI selection,
ICC conversions and all eight orientation pixel mappings (only orientation 6
shape tested so far), and measure aggregate memory on larger inputs. Aesthetics,
PyObjC runtime behavior and older macOS native error handling remain untested.
No digital fixture set was silently selected from unrelated personal folders.

This spike does not satisfy the representative visual-review acceptance gate.
Any production command/database schema integration or default scan-flow change
requires the subsequent review/authorization described in PROJECT.md.
