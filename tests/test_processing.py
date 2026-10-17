from photo_utils import database
import os
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import tifffile

from photo_utils.cli import build_parser, main, prompt_sheet_source
from photo_utils.processing import (
    ProcessingError,
    _thickest_border,
    detect_cards,
    list_sheet_sources,
    process_sheet,
)


def write_synthetic_sheet(path):
    sheet = np.full((1000, 1200, 3), 1200, dtype=np.uint16)
    card_width, card_height = 320, 260
    for index, (left, top, angle) in enumerate(
        ((100, 100, -1.5), (700, 100, 1.0), (100, 600, 1.2), (700, 600, -1.0))
    ):
        card = np.full((card_height, card_width, 3), 57500, dtype=np.uint16)
        card[18:242, 58:305] = 11000 + index * 1200
        card[45:105, 100:165] = (9000, 14000, 22000)
        card[130:205, 190:280] = (18000, 9000, 6000)
        matrix = cv2.getRotationMatrix2D(
            (card_width / 2.0, card_height / 2.0), angle, 1.0
        )
        card = cv2.warpAffine(
            card,
            matrix,
            (card_width, card_height),
            flags=cv2.INTER_LINEAR,
            borderValue=(1200, 1200, 1200),
        )
        sheet[top : top + card_height, left : left + card_width] = card
    tifffile.imwrite(
        path,
        sheet,
        photometric="rgb",
        resolution=(300, 300),
        resolutionunit="INCH",
    )


class ProcessingTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        state_patch = patch.dict(os.environ, {'PHOTO_UTILITIES_STATE_DIR': str(self.root / 'metadata-state')})
        state_patch.start()
        self.addCleanup(state_patch.stop)
        self.source = self.root / "20261010-001-master.tif"
        write_synthetic_sheet(self.source)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_detects_four_prints_and_rejects_non_print_sheet(self):
        image = tifffile.imread(self.source)
        cards = detect_cards(image)
        self.assertEqual(len(cards), 4)
        self.assertLess(cards[0].center[1], cards[-1].center[1])

        blank = np.zeros_like(image)
        with self.assertRaisesRegex(ProcessingError, "detected 0"):
            detect_cards(blank)

    def test_dry_run_reports_plan_without_creating_outputs(self):
        output_dir = self.root / "planned-prints"
        source_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        with patch("builtins.print"):
            self.assertEqual(
                process_sheet(self.source, output_dir=output_dir, dry_run=True), []
            )
        self.assertFalse(output_dir.exists())
        self.assertEqual(
            hashlib.sha256(self.source.read_bytes()).hexdigest(),
            source_hash,
        )

    def test_processes_four_upright_16_bit_tiffs_and_is_idempotent(self):
        output_dir = self.root / "processed"
        source_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        with patch("builtins.print"):
            outputs = process_sheet(self.source, output_dir=output_dir)
        self.assertEqual(len(outputs), 4)
        self.assertEqual([path.name for path in outputs], [
            "20261010-001-01-print.tif",
            "20261010-001-02-print.tif",
            "20261010-001-03-print.tif",
            "20261010-001-04-print.tif",
        ])
        for output in outputs:
            image = tifffile.imread(output)
            self.assertEqual(image.dtype, np.uint16)
            self.assertGreater(image.shape[0], image.shape[1])
            self.assertEqual(_thickest_border(image)[0], "bottom")
            with tifffile.TiffFile(output) as output_file:
                self.assertEqual(
                    output_file.pages[0].tags["BitsPerSample"].value,
                    (16, 16, 16),
                )
                self.assertEqual(
                    output_file.pages[0].tags["XResolution"].value,
                    (300, 1),
                )

        manifest = database.read_record(output_dir / "20261010-001-prints.manifest.json")
        self.assertEqual(manifest["status"], "completed")
        self.assertEqual(manifest["source_sha256"], source_hash)
        self.assertEqual(len(manifest["cards"]), 4)
        self.assertEqual(
            hashlib.sha256(self.source.read_bytes()).hexdigest(),
            source_hash,
        )
        output_hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in outputs]
        with patch("builtins.print"):
            repeated = process_sheet(self.source, output_dir=output_dir)
        self.assertEqual(
            [hashlib.sha256(path.read_bytes()).hexdigest() for path in repeated],
            output_hashes,
        )

    def test_interrupted_job_resumes_without_replacing_verified_derivatives(self):
        output_dir = self.root / "resumable"
        original_imwrite = tifffile.imwrite
        write_count = 0

        def fail_second_write(*args, **kwargs):
            nonlocal write_count
            write_count += 1
            if write_count == 2:
                raise OSError("synthetic interrupted write")
            return original_imwrite(*args, **kwargs)

        with patch("photo_utils.processing.tifffile.imwrite", side_effect=fail_second_write):
            with self.assertRaisesRegex(ProcessingError, "synthetic interrupted write"):
                process_sheet(self.source, output_dir=output_dir)
        manifest = database.read_record(output_dir / "20261010-001-prints.manifest.json")
        self.assertEqual(manifest["status"], "failed")
        first_output = output_dir / "20261010-001-01-print.tif"
        first_hash = hashlib.sha256(first_output.read_bytes()).hexdigest()

        with patch("builtins.print"):
            outputs = process_sheet(self.source, output_dir=output_dir)
        self.assertEqual(len(outputs), 4)
        self.assertEqual(
            hashlib.sha256(first_output.read_bytes()).hexdigest(),
            first_hash,
        )
        manifest = database.read_record(output_dir / "20261010-001-prints.manifest.json")
        self.assertEqual(manifest["status"], "completed")

    def test_unrecognized_output_directory_is_never_overwritten(self):
        output_dir = self.root / "existing"
        output_dir.mkdir()
        marker = output_dir / "keep.txt"
        marker.write_text("user data")
        with patch("builtins.print"):
            process_sheet(self.source, output_dir=output_dir)
        self.assertEqual(marker.read_text(), "user data")

    def test_output_directory_cannot_contain_the_source_sheet(self):
        with self.assertRaisesRegex(ProcessingError, "must not contain"):
            process_sheet(self.source, output_dir=self.root)

    def test_source_listing_excludes_derivatives_and_returns_recent_first(self):
        output_dir = self.root / "custom-output"
        output_dir.mkdir()
        tifffile.imwrite(
            output_dir / "20261010-001-01-print.tif",
            np.zeros((20, 20, 3), dtype=np.uint8),
            photometric="rgb",
        )
        (output_dir / "20261010-001-prints.manifest.json").write_text("{}")
        sources = list_sheet_sources(self.root)
        self.assertEqual(sources, [self.source])

    def test_cli_accepts_process_sheet_dry_run(self):
        args = build_parser().parse_args(
            ["process-sheet", str(self.source), "--dry-run"]
        )
        self.assertEqual(args.command, "process-sheet")
        self.assertTrue(args.dry_run)
        with patch("photo_utils.cli.process_and_retouch",return_value=None) as process:
            self.assertEqual(main(["process-sheet", str(self.source), "--dry-run"]), 0)
        process.assert_called_once_with(
            self.source,
            output_dir=None,
            dry_run=True,
            profile="polaroid",
            focus_review=True,tier_review=True,auto_rotate=True,kind="polaroids",find_similar_groups=False,
        )

    def test_menu_selects_recent_sheet_and_prompts_for_dry_run(self):
        with patch("photo_utils.cli.list_sheet_sources", return_value=[self.source]):
            with patch("builtins.input", side_effect=["e", "", "", "y", "", "q"]):
                with patch("photo_utils.cli.process_and_retouch",return_value=None) as process:
                    with patch("sys.stdin.isatty", return_value=True):
                        self.assertEqual(main([]), 0)
                    process.assert_called_once_with(
                        self.source,
                        dry_run=True,profile="polaroid",kind="polaroids",focus_review=True,
                    )

    def test_sheet_prompt_defaults_to_most_recent_candidate(self):
        with patch("photo_utils.cli.list_sheet_sources", return_value=[self.source]):
            with patch("builtins.input", return_value=""):
                self.assertEqual(prompt_sheet_source(self.root), self.source)

    def test_missing_or_corrupt_source_fails_without_creating_output(self):
        missing = self.root / "missing.tif"
        with self.assertRaisesRegex(ProcessingError, "does not exist"):
            process_sheet(missing)
        corrupt = self.root / "corrupt.tif"
        corrupt.write_bytes(b"not a TIFF")
        with self.assertRaisesRegex(ProcessingError, "Could not read TIFF"):
            process_sheet(corrupt)
        self.assertFalse(self.root.joinpath("missing-prints").exists())
        self.assertFalse(self.root.joinpath("corrupt-prints").exists())


if __name__ == "__main__":
    unittest.main()
