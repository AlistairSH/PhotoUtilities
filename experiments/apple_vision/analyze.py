"""Read-only feasibility runner; no production imports, database or file outputs."""
import argparse
import base64
import hashlib
import json
import platform
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np


def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def metrics(rgb):
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float64) / 255
    return {"laplacian_variance": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
            "mean_luminance_proxy": float(gray.mean()),
            "dark_fraction": float((gray <= 2 / 255).mean()),
            "bright_fraction": float((gray >= 253 / 255).mean())}


def assess(values, source_type, roi_known):
    # Softness alone never produces a verdict. Border inclusion invalidates scan quality.
    if source_type != "digital" or not roi_known:
        return "unable-to-determine"
    if max(values["dark_fraction"], values["bright_fraction"]) > 0.5:
        return "review"
    return "unable-to-determine"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--helper", type=Path, required=True)
    parser.add_argument("--source-type", choices=["digital", "vintage", "unknown"], default="unknown")
    parser.add_argument("--roi", nargs=4, type=float, metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"),
                        help="Explicit normalized photographic bounds; never guess Polaroid borders")
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("Apple Vision requires macOS; no analysis performed")
    if args.roi and not (0 <= args.roi[0] < args.roi[2] <= 1 and 0 <= args.roi[1] < args.roi[3] <= 1):
        parser.error("ROI must satisfy 0 <= left < right <= 1 and 0 <= top < bottom <= 1")
    try:
        paths = [p.resolve(strict=True) for p in args.images]
    except OSError as error:
        parser.error(str(error))
    before = [checksum(p) for p in paths]
    start = time.perf_counter()
    result = subprocess.run([str(args.helper.resolve()), *map(str, paths)], capture_output=True, timeout=120)
    if result.returncode:
        parser.error("Native Vision failed: " + result.stderr.decode(errors="replace").strip())
    data = json.loads(result.stdout)
    gray_images = []
    for row, source_hash in zip(data["images"], before):
        rgba = np.frombuffer(base64.b64decode(row.pop("rgba")), np.uint8).reshape(row["height"], row["width"], 4)
        rgb = rgba[:, :, :3]
        gray_images.append(cv2.resize(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), (64, 64)).astype(float) / 255)
        roi = rgb
        if args.roi:
            l, t, r, b = args.roi
            roi = rgb[int(t * len(rgb)):int(b * len(rgb)), int(l * rgb.shape[1]):int(r * rgb.shape[1])]
            if roi.size == 0:
                parser.error("ROI is empty at preview resolution")
        row["metrics"] = metrics(roi)
        row["quality_roi"] = args.roi
        row["confidence"] = "Unvalidated; operator review required"
        row["sha256"] = source_hash
        row["disposition"] = assess(row["metrics"], args.source_type, bool(args.roi) or args.source_type == "digital")
        row["limitations"] = ["No validated focus or pass threshold; clipping may be intentional",
                               "8-bit sRGB preview statistics; not archival pixel measurements",
                               "Similarity uses full frame; quality ROI is operator supplied",
                               "Untagged images interpreted in sRGB; no scanner calibration",
                               "Whole-frame quality includes physical borders unless ROI supplied"]
    for pair in data["pairs"]:
        a, b = gray_images[pair["a"]], gray_images[pair["b"]]
        pair["opencv_thumbnail_rmse"] = float(np.sqrt(np.mean((a - b) ** 2)))
    data["wall_seconds"] = time.perf_counter() - start
    data["inputs_unchanged"] = before == [checksum(p) for p in paths]
    if not data["inputs_unchanged"]:
        raise RuntimeError("Input checksum changed during experiment")
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
