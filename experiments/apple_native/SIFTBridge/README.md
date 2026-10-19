# SIFT for Swift — local portability experiment

`NativeSIFT` provides an owned Swift feature object and typed match evidence backed
by a small exception-safe C ABI over pinned **OpenCV 4.11.0** C++. Its application
runtime has no Python, shell processes, networking, filesystem or Photos-library
access. The CLI and Python comparison scripts are separate macOS research tools.

The Swift package declares macOS 14 / iOS 17 (including iPadOS). **Only arm64 macOS
has been compiled and run here.** Full Xcode, iOS SDKs and physical-device validation
are unavailable on this host. The XCFramework build path below is prepared, not
claimed as a successful device build. Photos support remains future work.

## API

```swift
import NativeSIFT

// Caller supplies bounded, upright sRGB RGBA8 display pixels, not original files.
let first = try SIFTFeatures(rgba: firstPixels, width: firstWidth, height: firstHeight)
let second = try SIFTFeatures(rgba: secondPixels, width: secondWidth, height: secondHeight)
let evidence = try first.compare(to: second)
// evidence.candidate supplements Vision; it is not a quality or retention verdict.
```

Each dimension must be 1...1024. Optional `bytesPerRow` supports padded rows.
Invalid/truncated buffers throw. Features own their descriptors and release them
on deinitialization; input pixels are neither retained nor modified. Extract once
and reuse features for multiple pairs. The object is not declared Sendable; callers
schedule work and bound concurrent extraction. Extraction is synchronous; any app
must provide task scheduling/cancellation between operations.

The accepted behavior is unchanged: 500-feature SIFT configuration (ties may
produce more), strict 0.75 ratio in both directions, sorted mutual matches, seeded
RANSAC at 3 px / 2,000 iterations / 0.995 confidence, then >=12 inliers, >=0.5 inlier
fraction and >=0.1 convex-hull coverage in both images. Failed geometry supplies
no candidate. The bridge preserves the calling thread's RNG state around RANSAC.
No C++ exception crosses the C/Swift boundary. Gray conversion follows the accepted
RGBA -> RGB -> gray path.

## Pin and build the macOS dependency

All source archives, headers, libraries and build outputs stay outside Git.
Download the public upstream tag, verify the archive, then extract it locally:

```sh
curl --fail --location --output /private/tmp/opencv-4.11.0.tar.gz \
  https://codeload.github.com/opencv/opencv/tar.gz/refs/tags/4.11.0
shasum -a 256 /private/tmp/opencv-4.11.0.tar.gz
```

Expected SHA-256:
`9a7c11f924eff5f8d8070e297b322ee68b9227e003fd600d4b8122198091665f`.
Stop on a mismatch. Extract only to a new external source directory.

CMake 3.31.6 and Ninja 1.11.1.3 were used from an isolated `/private/tmp` tools
installation; they are build tools, not application dependencies. With CMake,
Ninja and Apple compiler tools available:

```sh
experiments/apple_native/SIFTBridge/build_opencv_macos.sh \
  /path/to/opencv-4.11.0 /private/tmp/sift-dependency-new
OPENCV_ROOT=/private/tmp/sift-dependency-new/install \
  experiments/apple_native/SIFTBridge/build.sh
```

`CMAKE_BIN`, `NINJA_BIN` and `BUILD_JOBS` override tool paths/build parallelism.
`SIFT_BUILD_ROOT` chooses the Swift build directory. The final build line is the
binary directory. Run its `sift-checks` executable. The minimal static build uses
core, imgproc, features2d, flann and calib3d, plus bundled zlib and Carotene HAL.
Image codecs, Python bindings, Java, video backends and nonfree modules are disabled.
Some unrelated upstream data/notices may be installed; none is an application
runtime requirement. The local-prefix manifest uses unsafe include/link flags and
is intended for this research checkout, not distribution as a remote Swift package.

## Apple XCFramework path (requires full Xcode)

```sh
.venv/bin/python -B experiments/apple_native/SIFTBridge/build_apple_xcframework.py \
  /path/to/opencv-4.11.0 /private/tmp/sift-apple-new
.venv/bin/python -B experiments/apple_native/SIFTBridge/stage_apple_package.py \
  /private/tmp/sift-apple-new/opencv2.xcframework /private/tmp/sift-package-new
```

The recipe invokes the pinned upstream Apple builder for arm64 iOS device,
arm64/x86_64 iOS Simulator and arm64/x86_64 macOS slices. SwiftPM requires local
binary paths within the package. The staging script copies
sources and the built artifact into a new external directory, keeping binaries out
of Git. Add `/private/tmp/sift-package-new/SIFTBridge` as a local app package; its
manifest automatically selects `Artifacts/opencv2.xcframework` and avoids the
macOS prefix flags. Build an app against the **NativeSIFT library product**, not
the macOS CLI. A full Xcode
host must still verify framework assembly, simulator/device compilation, linking,
app packaging and real-device behavior. No simulator result substitutes for device
memory/thermal testing. The recipe fails early when Xcode/SDKs are unavailable;
it does not install Xcode or change the selected developer directory.

## Verify accepted behavior

```sh
.venv/bin/python -B experiments/apple_native/test_sift_cli.py \
  --binary /path/to/native-sift
.venv/bin/python -B experiments/apple_native/sift_compare.py \
  --binary /path/to/native-sift \
  --fixture /private/tmp/apple-native-decision-fixture-01 \
  --corpus /private/tmp/apple-native-corpus-final \
  --output /private/tmp/sift-parity-new
```

The comparison verifies metadata/pixel/original hashes, recomputes the unchanged
Python oracle from frozen pixels, and compares every native pair and Swift grouping
level. It also tests the deterministic geometry cases. Missing completion, changed
pixels, duplicate pairs and malformed identities fail visibly. Artifacts remain
private, outside Git. See [the SIFT gate](../SIFT_GATE.md) for measured results and
remaining limits.

## Attribution

OpenCV source is external and pinned, not vendored here. Retain the notices under
[Licenses](Licenses/OpenCV-Apache-2.0.txt) with distributed binaries. Additional
bundled notices cover Carotene, zlib and SoftFloat/fdlibm. Audit the actual dependency
build again before app distribution, especially if modules/third-party options
change. Public references: [OpenCV SIFT](https://docs.opencv.org/4.11.0/d7/d60/classcv_1_1SIFT.html)
and [upstream Apple builder](https://github.com/opencv/opencv/tree/4.11.0/platforms/apple).
