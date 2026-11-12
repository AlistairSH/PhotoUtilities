# Comparative findings — October 18, 2026

Historical initial spike. The subsequent [decision-parity report](DECISION_PARITY.md)
ports the complete focus/tier policies and corrects Gaussian/grayscale rounding.
Its current results supersede the initial focus-parity limitations below.

Unmerged local research; accepted algorithms and scanner processing unchanged.
Baseline `8809e81`; implementation milestone `4076a82`. Source and executable
fingerprints are recorded by the final comparison adapter. A subsequent
metadata-only correction normalizes derivative EXIF color-space tags to sRGB;
its expanded synthetic tests pass. It does not change the measured grouping or
focus algorithms. Build and reproduction
commands are in [README](README.md); recommendations are in [MIGRATION](MIGRATION.md).

## Current coverage

The actual PhotoSamples inventory is **151 images: 103 JPEG and 48 HEIC**, not the
historical 154 and not the requested 475-image batch. Each file was hashed before
and after comparison. No files were omitted on decode failure, substituted, edited,
archived or uploaded. No production SQLite or Photos library was opened.
Synthetic disposable files cover JPEG/HEIC/PNG/single-image TIFF input and output.
There are no representative RAW or real digital TIFF samples in this corpus.
Portrait/group/animal/landscape/urban categories are not manually labeled here;
subject detector evidence does not establish a verified photographic-category
accuracy benchmark. Burst/reframe/crop accuracy needs labeled cases.

## Grouping and focus comparison

The comparison feeds identical ImageIO/CoreGraphics display pixels to Swift and
the pinned Python/OpenCV/NumPy baseline. The Vision request is unchanged: revision
2, scaleFit; no automatic visual quarter-turn is enabled in this measurement run.
Every one of the **11,325** pairs is compared using both the accepted Vision OR
strict SIFT rule and the Vision-only ablation, with original thresholds.

| Measure | Accepted baseline | Native experiment |
| --- | ---: | ---: |
| Related components (size >1) | 23 | 22 |
| Standalone images | 86 | 88 |
| Baseline candidate links lost without SIFT | — | 3 |
| Pair-label differences (including likely/potential) | — | 6 |

These are disagreements with the accepted implementation, not manually verified
false-positive/false-negative rates. Historical reviewed comparisons also include
a SIFT-recovered positive beyond the Vision cutoff; see the preserved
`../similarity_compare/README.md`. Removing SIFT is not justified.

Global Gaussian1 metrics were compared on **302 scale rows** (1024 and 2048).

| Metric | Median relative difference | Maximum relative difference |
| --- | ---: | ---: |
| Laplacian variance | 0.3233% | 0.9835% |
| Tenengrad | 0.01636% | 0.1464% |
| Gradient energy p90 | effectively zero | 1.5625% |
| Luminance mean | 0.000203% | 0.01584% |
| Luminance standard deviation | 0.001438% | 0.02032% |

Among all 11,325 ordering comparisons at each scale, Tenengrad ordering agrees
completely. Laplacian ordering differs on five pairs at 1024 and three at 2048.
The scalar Gaussian and RGB-to-gray rounding differ from the OpenCV fixed-point
path. No thresholds were retuned. These results show close measurements, not that
one implementation is more photographically accurate. They do not establish
regional focus decisions, edge-profile confirmation or final ranking parity.

The separate regional smoke comparison uses one HEIC and one JPEG, both scales.
For 180 available region/outside/ratio scalar comparisons, median relative error
is 0.02405%, maximum 0.4371%. Mask usability and detector-region identity agree.
That sample is too small to establish subject-aware focus accuracy. Native regional
processing also remains a scalar reference implementation, not an optimized vImage
or vDSP implementation.

## Performance and memory

The final fixed-binary 151-image mixed Swift/Python pipeline completed in
**169.24 seconds**, including decode, Vision detection, global native focus, all
pairs, IPC and baseline work. Instrumented native global focus took 77.52 seconds
across 302 scale rows; measured Python baseline work accounted for 93.92 seconds.
These phases can overlap through streaming/backpressure and are not additive.
Parent peak RSS was 716,963,840 bytes (683.8 MiB), child peak RSS 845,004,800 bytes
(805.9 MiB). These are process peaks and must not be summed as a simultaneous
working-set measurement. No speedup factor can be derived from this mixed pipeline.
The independent initial run took 181.74 seconds, illustrating run-to-run variation.

The two-image regional pipeline took 13.97 seconds; its instrumented native focus
work took 10.26 seconds across four scale rows, including additional global
reference work. Parent/child peak RSS were 385,515,520 / 340,869,120 bytes. This is
an algorithm/reference probe, not evidence of mobile performance or 475-image
scalability. There are 112,575 pairs at 475 images; no extrapolated latency or memory
claim replaces a real run. Device memory, thermal performance and independent,
sequential native-versus-baseline end-to-end benchmarks remain open.

Host: Apple Silicon arm64, reported macOS 27.0.1; Swift 6.4 Command Line Tools,
OpenCV 4.11.0, NumPy 2.0.2. Aesthetic APIs need the newer SDK/runtime described in
README. No external Swift package dependencies were introduced.

## Image handling and metadata

The verification executable passes **170 checks**, including strict grouping
boundaries/chaining, invalid distances, flat/detail/blur cases, empty masks,
CGFloat detector-region bridging, embedded EXIF rotation, 0/90/180/270 and arbitrary
rotation geometry, cropping/resizing, original hashes, no-overwrite collisions,
JPEG/HEIC/PNG/TIFF export, capture-date round trips declared 8-bit output depth and normalization of EXIF color-space tags to sRGB.
Synthetic orientation uses EXIF 6; exhaustive mirrored-orientation and real
photographic visual-fidelity validation remain open. Output is 8-bit sRGB display
processing, not preserved 16-bit masters, sensor RAW development or identical ICC
profile bytes. PNG/TIFF encoding is lossless for those rendered pixels; geometry,
resampling and color conversion can still change image information.

Supported metadata dictionaries are passed to ImageIO, geometry/orientation tags
normalized, and maker notes removed. Date tests do not prove keywords, ratings,
XMP, maker data or embedded-thumbnail interoperability. No claim is made about
Photos or Photomator discoverability or existing-library refresh behavior.

Vision homographic registration returned a finite matrix and confidence 1 for a
same-size sample pair. A subsequent ablation probe evaluated all three lost SIFT
links and three Vision-supported plus three baseline-unmatched controls; see the
local registration-ablation artifact for individual statuses. Two lost links had
unsupported dimensions; one produced a matrix. All six controls produced matrices,
and every returned confidence was 1, including baseline-unmatched controls.
Confidence or successful registration alone therefore cannot recover SIFT behavior. This is not a validated related-image decision: it lacks
the accepted sparse-match inlier/coverage evidence. Unequal thumbnail dimensions
return explicit unassessed status; no rescaling/threshold change is silently used.
Foundation Models is not invoked or treated as an aesthetic authority.

## Verification and failure evidence

The unchanged core suite ran 113 tests; one local HTTP test initially failed only
because the sandbox blocked loopback bind. Its isolated rerun outside the sandbox
passed; a final full-suite rerun outside the sandbox passed all 113 tests. Strict application Pyright: zero errors/warnings. Swift build succeeds.
This Command Line Tools installation lacks XCTest; native tests therefore use the
standalone verification executable. Initial sandboxed native image tests could
not use the necessary CoreImage/HEIC services; outside-sandbox tests passed.

The first regional run failed on a CGFloat-to-Double cast. It was corrected,
covered by a regression check and rerun successfully. Failed output remains in
its separate temporary directory and is not treated as completed analysis.
No original images were modified by failed or successful runs.

## Local research artifacts

Artifacts remain outside Git, in `/private/tmp`:

- `apple-native-corpus-final/`: final full-corpus inventory, pair evidence,
  focus comparisons, summary and source/executable fingerprints.
- `apple-native-corpus-01/`: initial full-corpus measurement evidence; its
  end-of-run binary fingerprint is not reliable provenance because optional
  instrumentation was rebuilt concurrently. The final rerun corrects this.
- `apple-native-regions-02/`: successful two-image regional comparison.
- `apple-native-regions-01/`: retained failed regional run.
- `apple-native-registration-01.json`: initial homographic evidence only.
- `apple-native-registration-ablation-final.json`: lost-link/control probe.
- `apple-native-evidence-smoke.jsonl`: successful one-HEIC classification and
  native quality-evidence smoke test; not final tier assignments.

Run `summarize.py RESULT_DIRECTORY` for aggregate statistics. Temporary artifacts
are not permanent archives; reproduce with the committed commands when needed.
