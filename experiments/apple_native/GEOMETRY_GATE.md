# Native geometry gate — October 18, 2026

**Retain SIFT. The tested Vision homographic-registration request is not an adequate
replacement for the accepted SIFT match evidence.** This gate replaces an open-ended
registration probe with reproducible known-transform cases and inspected controls.
It does not introduce a new matcher or change production grouping thresholds.

## What was evaluated

`geometry_evaluate.py` generates 13 deterministic synthetic cases: identity,
translation, rotation, perspective, unequal-size crop, rescaled crop, exposure,
blur, a moving-foreground burst proxy, half-changed content, rearranged tiles,
unrelated content and a featureless pair. Construction facts are explicit labels,
not claims about photographic identity or retention.

Nine existing-corpus controls comprise all three SIFT-only links, three
Vision-supported pairs and three baseline-unmatched pairs. These are algorithm
selected and **remain unjudged by a human**. Both the comparison inventory and
frozen fixture are checked; original files and selected frozen RGBA buffers are
hash verified. The buffers are exported to disposable PNGs for native decoding.
This is not a fresh end-to-end native grouping run.

Each pair is evaluated twice, using pinned Vision registration revision 1:

- `register`: existing same-dimension probe.
- `register-canvas`: experimental common canvas, bottom-left black padding with
  no aspect stretching or additional resize. The source dimensions and canvas
  policy accompany every successful result. Existing probe behavior is preserved.

The native executable returns geometric evidence only (`recommendation: unassessed`,
`sift_equivalent: false`). Python/OpenCV is the diagnostic oracle, including the
unchanged accepted SIFT implementation, not a new production dependency.

## Results and decision

The final local evaluation contains **22 cases / 44 runs**. The original mode
returns 19 matrices and three unsupported-dimension results; padding returns all
22 matrices. Every returned confidence is **1**, including unrelated content,
rearranged tiles and the featureless pair. Matrix availability and confidence
therefore cannot separate these controls.

Representative padded-mode diagnostics on known transforms:

| Synthetic case | Median transform error | Overlap NCC |
| --- | ---: | ---: |
| Identity | 0.004 px | 1.000 |
| Translation (18 px, −12 px) | 6.026 px | 0.585 |
| Rotation (4°) | 0.180 px | 0.987 |
| Perspective | 0.115 px | 0.983 |
| Unequal-size crop | 77.029 px | 0.001 |
| Rescaled crop | 12.028 px | 0.346 |

These are measured residuals, not acceptance cutoffs. Rotation/perspective results
show useful registration behavior, while the known crop exposes a large error
that merely eliminating the dimension restriction does not fix. The accepted
SIFT rule accepts these constructed same-content transform cases.

All three SIFT-only corpus links still yield accepted SIFT evidence when measured
from the frozen preview pixels. Padding produces matrices for the two formerly
unsupported links, but their overlap NCC is approximately **−0.191 and −0.034**;
the third link is approximately **0.800**. These observations do not establish
photographic correctness without labels. They do show that a returned matrix
cannot be counted as recovery of the lost SIFT grouping links.

A featureless identical pair has zero photometric error but undefined normalized
correlation and no accepted SIFT evidence. A half-changed-content construction
retains accepted SIFT evidence from its shared portion. Thus synthetic construction
labels, residuals and accepted grouping are distinct concepts; neither low residual
nor a broad “changed content” label defines a replacement grouping rule.

## Diagnostic contract and verification

Vision's floating-to-reference matrix is converted from lower-left pixel space
to top-left array space. The independently specified crop-coordinate check
verifies translation, overlap area and exact residual with a known matrix. Known
transform errors use a fixed nine-point grid. Residuals warp the floating image
into reference coordinates and exclude padding using a warped source mask, eroded
to avoid interpolation boundaries. NCC is explicitly absent for constant pixels;
singular and malformed/nonfinite matrices are handled separately. Raw grayscale
MAE is exposure dependent; no exposure-invariance claim is made.

Passed: geometry coordinate/overlap/flat/singular/malformed-matrix checks, the
249 native regression checks, strict production Pyright and whitespace validation.
Representative synthetic aligned output was visually inspected. The HTML review
shows reference, floating and native-aligned previews, alongside provenance and
measurements. It allows explicit manual labels for the nine corpus controls and
downloads them locally; default unjudged choices remain unjudged. Nothing is sent
to a server. No source photo, production module, DB or accepted threshold changed.

## Reproduce and review

Build using [README](README.md), then use a new output directory:

```sh
.venv/bin/python -B experiments/apple_native/test_geometry.py
.venv/bin/python -B experiments/apple_native/geometry_evaluate.py \
  --binary /path/to/native-image --output /private/tmp/native-geometry-new \
  --corpus /private/tmp/apple-native-corpus-final \
  --fixture /private/tmp/apple-native-decision-fixture-01
```

Omit both `--corpus` and `--fixture` for the synthetic-only suite. Apple Vision
requires a working local Apple runtime; failures/timeouts are recorded rather
than interpreted as nonmatches. Outputs and inputs stay outside Git.

Native-image binary SHA-256:
`f8e4e39acb37ed63316dbce693eab56e9d6083eb492f75292774ac2bf59b3f91`.
The summary records adapter/software versions; manual label exports include the
summary checksum so labels cannot silently lose their evaluation context.

Final private artifacts:

- `/private/tmp/apple-native-geometry-validated/summary.json`
- `/private/tmp/apple-native-geometry-validated/rows.jsonl`
- `/private/tmp/apple-native-geometry-validated/review.html`

The next useful input is explicit human review of the nine corpus controls,
especially the three SIFT-only links, followed by a larger labeled set of real
crops, reframes, burst motion and confusing negatives. The synthetic burst proxy
is not a validation on real burst photography. The historical 475-image manifest
and iOS/iPadOS behavior remain unverified. Do not tune a residual cutoff from these
controls or infer a universal precision/recall estimate. Keep accepted SIFT until
a candidate supplies validated local correspondence/coverage evidence and passes
held-out labeled cases and the complete grouping/decision gate.
