# Swift focus and ranking decision parity — October 18, 2026

**The 151-image decision gate passes.** With accepted grouping and Vision evidence
held constant, replacing the Python measurements and decision rules with the Swift
implementation changes **zero focus recommendations, explanations, sharper/softer
highlights, tiers, group ordering or standalone ordering** in this corpus.

Implementation milestone: `1310b70` on `experiment/apple-native`. This is local,
unmerged research, not a production replacement or proof of photographic accuracy.
The accepted Python/scanner/SQLite code remains unchanged from `8809e81`.

## What was frozen and compared

The current PhotoSamples inventory contains 151 originals: 103 JPEG and 48 HEIC.
The accepted pipeline produced a frozen baseline, native Vision observations,
accepted Vision OR SIFT pair/group evidence, and the exact sRGB RGBA8 display
pixels at 1024 and 2048. Visual auto-rotation was disabled for this comparison;
embedded EXIF orientation is applied by the accepted decoder. The fixture is
about 2.1 GiB and lives outside Git in `/private/tmp`.

Original checksums were verified before and after freezing and measurement replay.
Frozen metadata and every replayed pixel buffer are checksum-verified. Missing,
changed or incomplete evidence is rejected; failures are not treated as unmatched
or sharp. No production database or Photos library was opened. No photograph,
preview or metadata was uploaded. No image was moved, deleted or overwritten.

Two gates separate policy behavior from image arithmetic:

1. **Policy-only:** feed identical accepted measurements to Swift. All serialized
   decision fields agree, with numeric fields compared at 1e-12 and categorical
   decisions, reasons and ordering compared exactly.
2. **Pixel replay:** recompute regional Gaussian1 focus, edge-profile evidence and
   endpoint clipping in Swift on identical decoded pixels, then run the Swift
   policies. Compare the resulting recommendations with the accepted baseline.

| Pixel-replay variant | Changed focus flags | Changed recommendations/reasons | Changed tiers | Ordering |
| --- | ---: | ---: | ---: | --- |
| Native Gaussian1; accepted edges | 0 | 0 | 0 | Identical |
| Native edges; accepted Gaussian1 | 0 | 0 | 0 | Identical |
| Native Gaussian1 and edges | 0 | 0 | 0 | Identical |

Endpoint clipping was independently recomputed and matches all 151 small-scale
exposure records exactly, so it introduces no attribution ambiguity between the
three variants. The native result preserves **61 focus-review flags**, **4 sharper
and 6 softer highlights**, and **12 Top Pick / 112 Review (Keep & Review) / 27
Possible Cull** suggestions. Focus flags remain independent of tiers; nothing
selects an image for deletion. The accepted 23 groups and 86 standalone images
are fixed inputs here, not a new demonstration of native SIFT parity.

**Changed-recommendation inventory: empty.** Each variant has an empty differences
file and an empty per-image explanation file. Future nonzero comparisons record
every changed image, old/new decisions and evidence at both scales, with separate
Gaussian1-only and edge-only runs to identify the contributing component.

## Implementation and numerical findings

Swift now implements:

- Grayscale conversion and the pinned baseline's sigma-one fixed-point Gaussian
  for 8-bit regional focus; full-image Laplacian/Sobel fields, guarded region and
  outside statistics, p90, 4x4 tiles, and clipping.
- Float32 Gaussian/Sobel edge profiles, quantized bilinear remapping, seeded edge
  selection, profile width/contrast summaries and original minimum-sample rules.
- Cohort tails, attention fallback, subject matching, contrast/scale confirmation,
  independent direct-pair sharper/softer comparisons, and complete tier/rank rules.
- Full-batch standalone references, missing face-quality handling, percentile ties,
  stable ordering, no quotas, advisory-only composition and original reason text.

No thresholds or ranking rules were retuned. The 8-bit Gaussian uses the baseline's
integer kernel and a single final rounding. Seed-zero sampling reproduces NumPy
2.0.2 PCG64 and choice behavior, verified by full-vector hashes on both sides of
its choice-strategy boundary. See [algorithm attribution](THIRD_PARTY.md).

The first spike's approximately 0.32% median Laplacian difference was traced to
rounding/preprocessing and corrected. In this replay, maximum global absolute
errors are **5.06e-14** for Laplacian variance and **3.37e-14** for Tenengrad.
Regional/outside selected-pixel counts agree throughout the corpus.

Edge arithmetic is **not bit-exact**. Thirteen of 302 global scale rows have a
different accepted-profile count. The largest global median-width difference is
0.108 pixels; the largest global soft-fraction difference is 0.01316. All 302
global edge-flag dictionaries nevertheless agree.

There is **one regional sufficiency disagreement**: a face region at 2048 has 50
profiles in the baseline and 48 in Swift, crossing the unchanged 50-edge minimum.
The baseline's soft fraction is 0.72; the native value is 0.8125 but insufficient.
Neither assessment allows that face to clear a global softness flag, so the final
recommendation is unchanged. This is a concrete remaining gate: inspect profile
selection/float32 convolution/remap differences around the 50-sample boundary and
validate additional boundary cases before promotion. Do not lower the minimum or
retune the contrast threshold to conceal the difference.

## Performance and limits

The scalar native pixel replay plus policy comparisons took **300.13 seconds**;
instrumented native measurement work was **295.31 seconds** across 302 views.
Parent peak RSS was 96,141,312 bytes (91.7 MiB); child peak RSS was 549,519,360 bytes
(524.1 MiB). Peaks belong to different processes and are not additive. This run
excludes fresh Vision inference, source decoding and SIFT matching. The accepted
freeze took 158.22 seconds but includes different operations; these timings are
not a like-for-like speedup benchmark. The scalar reference is not performance-ready
for an unmeasured mobile workload. Accelerate optimization should retain this
fixture as its decision regression gate.

The 475-image fixture, independent manual accuracy labels, real RAW/high-depth
inputs and iOS/iPadOS hardware validation remain unavailable/unverified. Detection
and feature-print revisions are held fixed, and SIFT grouping is inherited. This
proves decision compatibility on the available corpus, not improved focus accuracy,
complete native workflow replacement or general aesthetic judgment.

## Verification

- 181 native checks: prior image/export safety plus pinned Gaussian pixel vectors,
  PCG64/choice vectors and edge-empty behavior.
- 106 independent synthetic differential policy cases, covering ties, cohort-size
  boundaries, clipping, face evidence, composition, groups and standalone references.
- Eight malformed-evidence rejection checks, including missing/duplicate scales,
  incomplete pairs, bad partition/boxes, missing ranking and region metrics.
- Four synthetic pixel cases: flat RGB, sharp step, blurred step and noisy RGB;
  border-touching/clipped regions, mask counts, focus/edge flags and clipping.
- Changed frozen-pixel rejection; all 151 originals' source hashes unchanged.
- Thirteen existing focus/tier tests pass; strict application Pyright: zero errors.
- Final input-validation refinements were followed by a fresh 151-image policy
  replay (zero field differences) and synthetic measurement tests. They do not
  alter the pixel arithmetic measured in the full replay.

## Reproduce and inspect

Build with [README](README.md)'s instructions. From the repository root, choose
new output directories; existing outputs are refused:

```sh
.venv/bin/python -B experiments/apple_native/freeze_evidence.py ../PhotoSamples \
  --output /private/tmp/native-decision-fixture-new
.venv/bin/python -B experiments/apple_native/policy_compare.py /private/tmp/native-decision-fixture-new \
  --binary /path/to/native-policy --output /private/tmp/native-policy-new
.venv/bin/python -B experiments/apple_native/measurement_compare.py /private/tmp/native-decision-fixture-new \
  --measure /path/to/native-measure --policy /path/to/native-policy \
  --output /private/tmp/native-measurement-new
.venv/bin/python -B experiments/apple_native/summarize_measurements.py \
  /private/tmp/native-decision-fixture-new /private/tmp/native-measurement-new
.venv/bin/python -B experiments/apple_native/test_policy.py /path/to/native-policy
.venv/bin/python -B experiments/apple_native/test_measurements.py /path/to/native-measure
```

Local evidence from this run:

- `/private/tmp/apple-native-decision-fixture-01/`: baseline, views, pixels,
  original checksums and completion hashes.
- `/private/tmp/apple-native-policy-parity-final/`: final policy result, empty
  differences and summary with baseline/binary fingerprints.
- `/private/tmp/apple-native-measurement-parity-01/`: native pixel measurements,
  three policy results, complete changed-recommendation/explanation files,
  empty edge-flag differences, numeric diagnostics and timings.

Temporary artifacts are not permanent archives. No private sample data is committed.
The next focused work is the 50-edge boundary discrepancy, Accelerate performance,
and preserving SIFT's recovered links in a native/shared architecture. Optional
metadata/RAW/Foundation Models work remains lower priority.
