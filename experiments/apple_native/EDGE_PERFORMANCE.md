# Edge-boundary correction and native performance — October 18, 2026

Implementation milestones: `5a0026f` (edge arithmetic and Accelerate backend) and
`915d6f7` (bounded variance scratch and unused-background avoidance), exclusively on
`experiment/apple-native`. Production code, dependencies, scanner processing and
SQLite remain unchanged. Nothing was pushed, merged, archived or uploaded.

This follows the [decision-parity gate](DECISION_PARITY.md). It addresses the
specific 48-versus-50 regional edge discrepancy and measures native performance
without changing the accepted algorithms or thresholds.

## The edge discrepancy

The traced 2048 display view has 41,498 eligible edge candidates. The original
native Gaussian/Sobel arithmetic differed slightly from the baseline near the
75th-percentile cutoff. Exactly two lattice points swapped candidate membership.
Although the candidate count and random seed were identical, the candidate-array
indices shifted between those points. Only **1,210 of the 3,000 sampled locations**
were common to both implementations. The resulting face region had 48 instead of
50 accepted profiles.

Matching the pinned baseline's Gaussian accumulation and explicit fused operations,
separable Sobel grouping and float32 comparison restores the same ordered 3,000
sampled locations in this case. The traced Gaussian pixels match exactly. Both
implementations now produce **2,143 global profiles and 50 face-region profiles**,
with the same face soft fraction, **0.72**. The minimum remains 50; no contrast,
cohort, matching, grouping or ranking threshold was adjusted.

The new trace tool checks the frozen view/pixel hashes and writes intermediate
float buffers plus profiles only to a new local directory. Regression checks use
a synthetic Gaussian buffer hash and explicit 49/50/51 profile-count cases, so the
threshold tests do not require committing private photos.

The floating operations were investigated against the pinned
[OpenCV separable-filter implementation](https://github.com/opencv/opencv/blob/4.11.0/modules/imgproc/src/filter.simd.hpp)
and [magnitude implementation](https://github.com/opencv/opencv/blob/4.11.0/modules/core/src/mathfuncs_core.simd.hpp).
This is independent Swift arithmetic; the native package does not link OpenCV.
Matching this traced Gaussian does not imply every edge intermediate is bit-exact
on every architecture or SDK.

## Native optimization

`Statistics.swift` adds an explicit `scalar`/`accelerate` backend:

- Accelerate/vDSP computes means and centered population variances.
- An exact three-way partial selection replaces full energy-array sorting for p90.
  Interpolation and minimum pixel counts are unchanged.
- Variance uses at most **65,536 doubles (512 KiB)** of scratch per call, independent
  of region size. Centered squares preserve low-contrast behavior; the unstable
  shortcut `E[x²] - E[x]²` is not used.
- Background statistics that no semantic region can consume are skipped.
- The scalar reduction/full-sort implementation remains available as a reference.

The benchmark compares these statistical backends with the **same corrected edge
extractor**. It selects fixed image indices 0, 19, 80 and 140 at both scales,
runs each backend three times sequentially, and alternates the order to reduce
cache/order bias. All selected pixel buffers are checksum-verified.

| Median over three runs, eight views | Scalar | Optimized |
| --- | ---: | ---: |
| Wall time | 5.760 s | 1.763 s |
| Native compute time | 5.663 s | 1.720 s |
| Focus-statistics time | 5.183 s | 1.259 s |

That is **3.27× overall** and **4.12× for focus statistics** in this paired subset
benchmark. The gain combines vDSP reductions and avoiding full sorts; it is not
attributed solely to Accelerate. It is not a 475-image or mobile throughput claim.

Parallel reductions change floating-point summation order. Raw numeric benchmark
outputs are compared at relative 1e-9 / absolute 1e-12, with exact categorical
comparisons. Observed deltas above the tighter original 1e-12 checker were about
2.31e-11 relative at most. Final recommendation/reason/order comparisons retain
the existing decision gate and do not relax any photographic policy threshold.

## Full-corpus gate

The final default-backend replay covers **151 images / 302 views** from identical
frozen decoded pixels. All three substitutions (native Gaussian1, native edges,
and both together) preserve every focus recommendation, reason, sharper/softer
highlight, tier and ordering. Global edge flags and regional sufficiency now agree
on every view. Two global profile counts still differ slightly; this is decision
parity, not a claim of universal bit-exact measurements. Source checksums remain
unchanged.

| Sequential frozen-corpus replay | Earlier scalar | Final optimized |
| --- | ---: | ---: |
| Wall time | 300.13 s | 71.20 s |
| Native compute time | 295.31 s | 67.03 s |
| Peak child RSS | 524.06 MiB | 550.09 MiB |

These full runs were separate milestones; use the paired benchmark above for the
controlled speedup claim. The bounded scratch version reduces the first optimized
run's 584.81 MiB peak, but **a 26.03 MiB increase over the earlier scalar run
remains**. Parent peak RSS in the final run was 93.36 MiB. This memory tradeoff
requires device measurement before mobile integration.

Validation passed: **249 native checks**, 106 synthetic policy comparisons,
eight malformed-evidence rejection checks, five synthetic pixel comparisons and
a changed-pixel rejection check. Strict Pyright reports zero errors or warnings.
Production source files match the accepted baseline.

Private local artifacts (not committed):

- `/private/tmp/apple-native-edge-diagnosis-03.json`
- `/private/tmp/apple-native-paired-benchmark-final/summary.json`
- `/private/tmp/apple-native-accelerated-parity-final/summary.json`

Measurement binary SHA-256:
`9a2d07ac5799de8558865617179fe5de9d5a4f18cd08ebf8af164ad2e26d61a3`.

The available corpus is 151 images, not the historical 475-image set. Grouping and
Vision evidence remain frozen; this replay excludes source decoding, fresh Vision
requests, SIFT and review HTML. SIFT remains necessary in the accepted pipeline.
The next research gate is a labeled geometry/photometric evaluation of a native
SIFT alternative, retaining the existing implementation until it passes.

## Reproduce

Build using [README](README.md). Use the same frozen fixture described in the
parity report and new output paths for every invocation:

```sh
/path/to/native-edge-probe /private/tmp/apple-native-decision-fixture-01 19 2048 /private/tmp/edge-trace-new
.venv/bin/python -B experiments/apple_native/diagnose_edges.py \
  /private/tmp/apple-native-decision-fixture-01 /private/tmp/edge-trace-new \
  --index 19 --scale 2048 --output /private/tmp/edge-diagnosis-new.json
.venv/bin/python -B experiments/apple_native/benchmark_native.py \
  /private/tmp/apple-native-decision-fixture-01 --binary /path/to/native-measure \
  --output /private/tmp/native-benchmark-new --repeats 3
.venv/bin/python -B experiments/apple_native/measurement_compare.py \
  /private/tmp/apple-native-decision-fixture-01 --measure /path/to/native-measure \
  --policy /path/to/native-policy --output /private/tmp/native-parity-new
```

Direct replay can select the reference backend with
`native-measure FIXTURE NEW_OUTPUT_JSONL --backend scalar`; default replay uses
`accelerate`. Neither backend writes original photographs or routine tracking
state. Native trace/measurement tools contain no Python runtime dependency;
Python/OpenCV remains the local test oracle.
