# Apple-native digital-photo experiment

Unmerged research on `experiment/apple-native`, branched from `8809e81` on
`experiment/ranking-culling`. Production Python, scanner, dependencies and SQLite
are unchanged. Nothing here moves, archives or deletes photos. No cloud inference,
Photos-library access, external Swift dependencies or model download.

Start with the latest [SIFT-for-Swift gate](SIFT_GATE.md),
the [native geometry gate](GEOMETRY_GATE.md),
the [edge correction and performance report](EDGE_PERFORMANCE.md),
the [decision-parity report](DECISION_PARITY.md),
[dependency audit](AUDIT.md), initial [comparison findings](FINDINGS.md) and
[migration recommendation](MIGRATION.md). The selected implementation investigates
native image handling, global/regional focus measurements, Vision-only grouping,
classification evidence, homographic registration, edge-profile measurement and
complete focus/tier decision replay. It is **not yet a native replacement for the
complete 475-image review workflow**. SIFT grouping and review HTML remain in the
accepted implementation; the decision-parity gate freezes that grouping and Vision
evidence while testing the Swift measurement and policy core.

## Build and verification

Swift 5.9+ package manifest; build with Apple Command Line Tools or Xcode and a
macOS 15+ SDK for the inherited aesthetics API. Base Vision analysis targets
macOS 14 / iOS 17; `--tiers` evidence needs macOS 15. Actual validation was macOS
only. The library avoids AppKit and process execution; iOS/iPadOS device builds,
thermal behavior and memory remain unverified. CLI executables are macOS harnesses.

From the repository root:

```sh
experiments/apple_native/build.sh
```

The final line is the binary directory. Set `NATIVE_BUILD_ROOT` to choose a build
root outside Git. Run `<binary-directory>/native-checks`; this self-contained
verification executable uses disposable synthetic files and needs no XCTest.
`swift test` is not the test command: this host's Command Line Tools lack XCTest.
An agent sandbox can block Swift caches, symbol generation, HEIC encoding and
Vision/CoreImage services; these checks required execution outside that sandbox.
The build script directs caches to the research build root and disables only the
SwiftPM build sandbox, not any OS permissions.

## Read-only batch evidence

Pass explicit paths as a JSON array on stdin:

```sh
printf '["/absolute/path/photo.jpg","/absolute/path/photo.heic"]' | /path/to/native-photo --focus
```

Options: `--focus` (1024/2048 global Gaussian1 measurements and detectors),
`--regions` with `--focus` (regional/outside measurements and 4x4 tiles),
`--tiers` (inherited native aesthetics, utility, face-quality and expression
**evidence**, not final tier assignments), `--auto-rotate` (unchanged conservative
face/body evidence), `--classify` (top five Vision labels, no aesthetic verdict),
`--comparison-pixels` (include decoded RGBA only for the comparison adapter).

JSON lines contain image/focus rows, all feature-print pair distances and a
completion row with Vision-only components. Feature-print revision 2 and scaleFit
remain pinned. Vision cutoffs remain strictly <.45 and <.40. Components chain;
SIFT is deliberately absent from this ablation and remains in production. Treat
nonzero exit, missing rows or missing completion as failed analysis. Partial
stdout is not a completed review. At most 500 explicit paths are allowed.

The Swift focus port uses the same derivative kernels, normalization,
reflect101 smoothing, 1-pixel metric guards, 3-pixel outside guards, population
variance, interpolated p90 and minimum 100 pixels. It preserves the pinned OpenCV
8-bit Gaussian kernel and integer rounding. Corrected float32 edge arithmetic
resolves the observed 48-versus-50 regional boundary without retuning thresholds.
Accelerate reductions and partial p90 selection are the default; `native-measure`
retains `--backend scalar` for reference. The 151-image replay preserves every
recommendation, with a measured speed improvement and a small remaining memory
increase. See [the performance report](EDGE_PERFORMANCE.md) for scope and limits.

## Comparative tests

Use the existing project `.venv`, including pinned NumPy/OpenCV, **only as the
baseline comparison adapter**. The native executable has no Python dependency.
Write to a new temporary research directory; paths must not already exist:

```sh
.venv/bin/python -B experiments/apple_native/compare.py ../PhotoSamples \
  --binary /path/to/native-photo --output /private/tmp/native-comparison-new --focus
.venv/bin/python -B experiments/apple_native/compare.py /path/to/small-sample-folder \
  --binary /path/to/native-photo --output /private/tmp/native-regions-new --regions
```

Collection is shallow and uses the existing input allowlist; no RAW comparison is
silently substituted. Inventory with SHA-256 is written first; every source hash
is verified afterward. The adapter uses identical decoded pixels for Swift and
Python measurements and identical Vision distances for the grouping ablation.
It writes explicit research JSON, not routine metadata or a new database.
Optional registration ablation against a completed run:

```sh
.venv/bin/python -B experiments/apple_native/registration_compare.py /private/tmp/native-comparison-new \
  --binary /path/to/native-image --output /private/tmp/native-registration-new.json
```

This probes all lost SIFT links and six algorithm-selected controls, verifies the
selected source hashes and refuses an existing output. Controls are not manual
ground truth and no new acceptance threshold is introduced.

These artifacts include local paths/analysis and must remain outside Git.
Pipeline time includes IPC/backpressure and baseline Python work; parent/child
peak RSS are macOS `getrusage` bytes, not a mobile memory benchmark. No manual
false-positive/false-negative truth is inferred from agreement with an algorithm.

## Complete focus and tier decision replay

The package also builds `native-policy` and `native-measure`. The former consumes
frozen review evidence on stdin and returns decisions; the latter recomputes
regional focus, edges and exposure from checksum-verified frozen display pixels.
Neither invokes Python or Vision. The Python adapters freeze the accepted oracle
and compare outputs; they are test infrastructure, not native runtime dependencies.

See [the parity report](DECISION_PARITY.md) for freeze/replay commands and local
artifacts. Run the additional independent checks with:

```sh
.venv/bin/python -B experiments/apple_native/test_policy.py /path/to/native-policy
.venv/bin/python -B experiments/apple_native/test_measurements.py /path/to/native-measure
```

The older `native-photo --tiers` command still emits native quality **evidence**;
it does not automatically orchestrate the new policy engine or replace SIFT.
No new production command/menu behavior is introduced.

## Image and metadata probes

```sh
/path/to/native-image metadata /path/to/source.heic
/path/to/native-image derivative /path/to/source.jpg /private/tmp/new.png 90 1024
/path/to/native-image derivative /path/to/source.jpg /private/tmp/crop.tif 0 512 0 0 300 400
/path/to/native-image register /path/to/reference.jpg /path/to/floating.jpg
```

Derivative optional arguments are clockwise degrees, maximum dimension, then
crop x/y/width/height. Crop pixels use bottom-left origin after upright rotation.
Arbitrary rotation expands the canvas; it does not automatically crop corners or
infer a horizon. Resizing never upscales. Export extension explicitly chooses
JPEG, HEIC, PNG or TIFF. Decoder accepts ImageIO-supported single-image sources;
RAW development/preview behavior and real RAW compatibility are unvalidated.
A file accepted by ImageIO is not proof of archival fidelity.

**All derivatives are explicitly 8-bit sRGB display exports.** JPEG/HEIC are lossy;
PNG/TIFF encode the rendered display pixels losslessly, not the original sensor
or high-depth data. Embedded source ICC is converted to sRGB, not retained as the
same profile. Untagged source interpretation follows Apple's decoder. Alpha and
transparent arbitrary-rotation corners vary by output format. Repeated resampling
is not lossless. Original files are never rewritten; no-replace hard-link
publication refuses existing destinations, including symlinks, on the same volume.
Temporary exports live beside their destination and are removed after publication.

Supported EXIF/capture, TIFF, GPS and IPTC dictionaries are passed to ImageIO;
orientation and dimensions are normalized and stale maker notes removed. This
is not arbitrary EXIF/XMP/keywords/ratings preservation: ImageIO may ignore fields,
and embedded thumbnails and consumer caches need separate round-trip validation.
The derivative EXIF color-space tag is explicitly normalized to sRGB.
Source properties are inspectable, but original ICC binary identity, maker notes,
XMP packets and rating/keyword discovery in Photos/Photomator are not guaranteed.
No existing Photos library is touched or claimed to refresh from file edits.

Homography uses Vision revision 1 with equal thumbnail dimensions; unequal
geometry yields explicit unassessed status. Returned matrix/confidence is evidence
only, not SIFT-equivalent corroboration or a candidate match. Foundation Models
semantic/aesthetic scoring remains disabled; no model availability or score is
invented. Vision classification labels are optional local evidence only.

## Native geometry evaluation

`native-image register SOURCE FLOATING` retains the same-dimension registration
probe. `native-image register-canvas SOURCE FLOATING` explicitly experiments with
a common padded canvas. Both return evidence only. The [geometry gate](GEOMETRY_GATE.md)
records why the evaluated request does not replace SIFT and provides reproduction
commands plus a local visual review with optional explicit manual labels.

Explicit manual-label imports use `label_geometry.py`; see the human-review section
of [the geometry gate](GEOMETRY_GATE.md) for checksum binding and results.

## SIFT for Swift

The separate [SIFTBridge package](SIFTBridge/README.md) builds a Swift-facing,
statically linked OpenCV SIFT implementation. The macOS 151-image / 11,325-pair
replay matches accepted SIFT evidence and grouping. The base package still builds
without OpenCV; opt into the separate package explicitly. Native iOS/iPadOS is the
design target, but this host lacks full Xcode/iOS SDKs and no device build is
claimed. See [SIFT_GATE.md](SIFT_GATE.md) for measured scope and the next gate.
