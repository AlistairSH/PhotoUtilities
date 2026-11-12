# SIFT for Swift gate — October 18, 2026

**The macOS Swift/C++ SIFT implementation passes the accepted 151-image grouping
gate.** It recovers all three human-confirmed SIFT-only links without changing any
matching or grouping threshold. This is a native compiled implementation with no
Python application runtime. It is not yet an iOS/iPadOS build or device-validation
claim. Photos integration remains deferred.

## Implementation

The separate [SIFTBridge package](SIFTBridge/README.md) exposes `SIFTFeatures` and
`SIFTMatch` to Swift through a small C ABI over OpenCV **4.11.0**, the exact version
used by the accepted oracle. The shared library accepts caller-supplied upright
sRGB RGBA8 previews and returns reusable feature objects and structured evidence.
It does not decode originals, run subprocesses or require a file path. This allows
future file and PhotoKit adapters to supply the same computational core.

OpenCV is built statically from external source with only core, imgproc,
features2d, flann and calib3d. The wrapper preserves explicit SIFT settings,
strict bidirectional ratio tests, sorted mutual pairs, seeded RANSAC and both
spatial coverage checks. Native exceptions become Swift errors; opaque feature
ownership releases descriptors on deinitialization. Invalid dimensions, strides
and truncated buffers are rejected before image access. A short geometry lock
and RNG restoration prevent the seeded operation leaking RNG state to callers.
The API is synchronous and deliberately not declared Sendable; app scheduling,
cancellation between operations and bounded concurrency are future integration work.

The native harness imports the existing Swift `Grouping` implementation for
pair-level decisions. Both the production Python CLI and the previous default
native package remain unchanged; SIFT is an opt-in separate package/dependency.

## Measured parity

The experiment verifies all 151 originals and every selected frozen 1024 preview
hash. It recomputes the unchanged Python SIFT oracle from those exact pixels and
checks that oracle against the previously accepted pair evidence before evaluating
the native implementation.

| Check | Result |
| --- | ---: |
| Images / pairs | 151 / 11,325 |
| Historical versus freshly recomputed Python evidence differences | 0 |
| Native keypoint-count differences | 0 |
| Native SIFT evidence field differences | 0 |
| Swift pair-level differences | 0 |
| Components | Identical: 23 groups, 86 standalone |
| Human-confirmed SIFT-only links recovered | 3 / 3 |
| Synthetic construction cases | 13; no evidence differences |
| Original checksums after replay | Unchanged |

Integer counts, booleans and pair levels are compared exactly; floating fractions
and coverages use relative/absolute 1e-12. The comparison is against accepted
behavior, not a general photographic accuracy claim. Vision distances and decoded
pixels are frozen. No new Vision inference, source decoding, focus measurement,
Photos access, archiving, review-session mutations or SQLite operation occurs.
The earlier [focus/decision gate](EDGE_PERFORMANCE.md) is separate validation.

The native corpus harness took **41.06 s wall / 40.93 s measured computation**;
the 13 synthetic pairs took about **0.84 s computation**. These are sequential
frozen-preview runs, not a controlled speed comparison with Python and not an
end-to-end photo-library processing time.

An independent launch of the final binary took **39.01 s wall**, with **599.36 MiB
peak RSS** (628,473,856 bytes). The parity harness's resource run measured
651.45 MiB (683,098,112 bytes). These observed peaks are substantial for mobile:
**memory optimization and device measurements remain required**. Scoped Foundation
autorelease pools bound batch-temporary lifetimes, but did not establish a lower
peak RSS; allocator/OpenCV extraction behavior needs further profiling. No memory
improvement claim is made. The independent replay agrees on every feature/pair row.

Validation also passed **13 native Swift/C boundary checks**, including empty
features, identical textured inputs, repeated matching, padded rows, buffer
validation and preservation of input bytes; **seven malformed/changed-input
harness rejection cases**; strict production Pyright; Python 3.9 parsing; build
script syntax; and whitespace checks. Synthetic packaging-layout checks verify
external staging,
collision/recursive-copy refusal and required platform manifests; they do not
validate actual framework binaries. The linked native executable uses system
Apple/Swift libraries and statically linked OpenCV, with no Python dynamic dependency.

## Cross-platform status and next gate

The library manifest declares macOS 14 / iOS 17 (including iPadOS). A separate
Apple XCFramework build recipe uses OpenCV's pinned upstream tooling to assemble
macOS, iOS device and iOS Simulator slices. The manifest supports that binary
target instead of the local macOS static prefix. Because binary-target paths must
be inside their package, a staging helper copies sources and the framework to a
new external package directory; no dependency binary enters Git. Neither the
source interface nor
its C++ implementation depends on AppKit, UIKit, the CLI, or Python.

**This host only has Command Line Tools. Full Xcode and the iOS SDK are absent.**
The iOS recipe preflight fails with that explicit reason, before creating output;
no Xcode installation or selected-developer-directory change was attempted.
XCFramework assembly, consumer-app linking, device execution and Intel Mac builds
remain unverified. The current local-prefix SwiftPM mode uses unsafe build flags;
it is a research build path, not a redistributable remote Swift package.

Next on a full Xcode host: assemble the framework, compile a minimal Swift app
against the library for simulator and an actual iPhone/iPad, replay the same
checksum-bound fixtures, then measure memory, scheduling and thermal behavior.
Do not treat simulator success as device validation. The historical 475-image
set remains unavailable. No Photos functionality is implemented in this milestone.

## Provenance and local artifacts

- Implementation/build/reproduction: [SIFTBridge README](SIFTBridge/README.md).
- Private parity results: `/private/tmp/apple-native-sift-parity-final/summary.json`.
- Independent native resource replay: `/private/tmp/apple-native-sift-resource-final.jsonl`
  and `/private/tmp/apple-native-sift-resource-final.stderr`.
- iOS preflight diagnostic: `/private/tmp/photo-sift-ios-preflight.log`.
- Native harness SHA-256:
  `26279778e9db2d6e92741533138f5ebbe15454e257f85165a77b20ae8187b85e`.
- Upstream 4.11.0 source archive SHA-256:
  `9a7c11f924eff5f8d8070e297b322ee68b9227e003fd600d4b8122198091665f`.

OpenCV source, libraries, tools and private fixtures remain outside Git. License
notices for the linked build are retained under `SIFTBridge/Licenses`; this does
not vendor OpenCV source. No push, merge, photo upload or production integration
was performed.
