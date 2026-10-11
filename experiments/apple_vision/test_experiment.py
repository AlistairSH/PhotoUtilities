"""Numerical/safety checks and optional real native integration (synthetic fixtures)."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import cv2
import numpy as np
import tifffile

spec = importlib.util.spec_from_file_location("analysis_spike", Path(__file__).with_name("analyze.py"))
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


class MetricsTests(unittest.TestCase):
    def test_intentional_softness_is_never_rejected(self):
        rng = np.random.default_rng(10)
        sharp = rng.integers(30, 220, (256, 256, 3), dtype=np.uint8)
        soft = cv2.GaussianBlur(sharp, (31, 31), 8)
        self.assertLess(analysis.metrics(soft)["laplacian_variance"], analysis.metrics(sharp)["laplacian_variance"])
        for source in ["digital", "vintage", "unknown"]:
            self.assertEqual(analysis.assess(analysis.metrics(soft), source, True), "unable-to-determine")

    def test_unsupported_platform(self):
        with patch.object(analysis.platform, "system", return_value="Linux"), patch.object(sys, "argv", ["analyze", "--helper", "/missing", "/missing"]):
            with self.assertRaises(SystemExit) as error:
                analysis.main()
            self.assertEqual(error.exception.code, 2)

    def test_clipping_requires_context(self):
        values = analysis.metrics(np.full((20, 20, 3), 255, np.uint8))
        self.assertEqual(analysis.assess(values, "digital", True), "review")
        self.assertEqual(analysis.assess(values, "vintage", False), "unable-to-determine")

    @unittest.skipUnless(os.environ.get("VISION_SPIKE_HELPER"), "Set VISION_SPIKE_HELPER for native integration")
    def test_native_formats_duplicates_and_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            image = np.zeros((256, 320, 3), np.uint8)
            cv2.circle(image, (120, 120), 60, (40, 200, 140), -1)
            cv2.putText(image, "VISION", (20, 225), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            paths = []
            for name in ["a.png", "b.png", "c.jpg", "d.tif"]:
                path = folder / name
                self.assertTrue(cv2.imwrite(str(path), image))
                paths.append(str(path))
            oriented = folder / "oriented.tif"
            tifffile.imwrite(oriented, image, photometric="rgb", extratags=[(274, "H", 1, 6, False)])
            paths.append(str(oriented))
            heic = folder / "sample.heic"
            conversion = subprocess.run(["/usr/bin/sips", "-s", "format", "heic", paths[0], "--out", str(heic)], capture_output=True)
            self.assertEqual(conversion.returncode, 0, conversion.stderr)
            paths.append(str(heic))
            command = [sys.executable, str(Path(__file__).with_name("analyze.py")), "--helper", os.environ["VISION_SPIKE_HELPER"], *paths]
            output = subprocess.run(command, capture_output=True, text=True, check=True)
            result = json.loads(output.stdout)
            self.assertTrue(result["inputs_unchanged"])
            self.assertLess(result["pairs"][0]["vision_distance"], 1e-6)
            self.assertEqual(len(result["images"]), 6)
            self.assertEqual((result["images"][4]["width"], result["images"][4]["height"]), (256, 320))
            crop_command = command[:]
            crop_command.extend(["--source-type", "digital", "--roi", "0.2", "0.2", "0.8", "0.8"])
            crop = json.loads(subprocess.run(crop_command, capture_output=True, text=True, check=True).stdout)
            self.assertNotEqual(crop["images"][0]["metrics"], result["images"][0]["metrics"])
            bad = folder / "bad.tif"
            bad.write_text("not an image")
            failure = subprocess.run([os.environ["VISION_SPIKE_HELPER"], str(bad)], capture_output=True)
            self.assertNotEqual(failure.returncode, 0)


if __name__ == "__main__":
    unittest.main()
