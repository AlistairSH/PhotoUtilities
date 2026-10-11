# Apple Vision read-only feasibility spike

Independent experiment, not a `photo-utils analyze` production command. No
production modules, persistence, scanning or editing are imported. Inputs are
read-only; reports go to stdout and fixtures live in temporary directories.
Requires macOS 14+ for explicitly pinned Vision feature-print revision 2,
Command Line Tools, and the existing project virtual environment. Python reports
an unsupported-platform error elsewhere; there is no cross-platform Vision fallback.

From the repository root:

```sh
xcrun swiftc -module-cache-path /tmp/photo-vision-module-cache \
  experiments/apple_vision/vision.swift -o /tmp/photo-vision-spike
.venv/bin/python experiments/apple_vision/analyze.py \
  --helper /tmp/photo-vision-spike --source-type vintage /path/to/print.tif
.venv/bin/python experiments/apple_vision/analyze.py \
  --helper /tmp/photo-vision-spike --source-type vintage \
  --roi 0.1 0.1 0.9 0.75 /path/to/print.tif
VISION_SPIKE_HELPER=/tmp/photo-vision-spike .venv/bin/python -B \
  -m unittest discover -s experiments/apple_vision -q
.venv/bin/python experiments/apple_vision/benchmark.py /tmp/photo-vision-spike
```

ROI values are **examples, not measured Polaroid boundaries**. The operator must
supply the photographic bounds. Unspecified borders are included and vintage
quality remains `unable-to-determine`. Similarity always uses the full frame.
These are small-batch tools: previews and feature prints remain in memory and
pair comparisons are quadratic. Outputs contain private paths/checksums; keep
reports local and outside Git. No routine sidecars are written.

ImageIO creates oriented previews up to 1024 pixels; CoreGraphics converts to
8-bit sRGB RGBA. NumPy/OpenCV consumes those exact pixels. The luminance proxy
is gamma-encoded OpenCV grayscale, not linear scene luminance. ICC handling
uses the embedded source color space through native decoding/drawing; no
calibrated scanner profile or full ICC accuracy validation is claimed. Alpha
is premultiplied against black; transparent/multi-frame images need further
policy work (multi-frame input is refused). No automatic border detection.

Native Vision may need execution outside a restricted agent sandbox: observed
failure was pixel-buffer pool creation, while the same binary succeeded under
normal local execution. Never treat that failure as an image-quality verdict.

See [FINDINGS.md](FINDINGS.md) for measured results and unfinished acceptance gates.
