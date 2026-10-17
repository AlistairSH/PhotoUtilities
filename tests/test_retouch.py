from photo_utils import database
import os
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import tifffile

from photo_utils.retouch import (
    RetouchError,
    RetouchOptions,
    _icc_profile,
    _source_metadata,
    _verify_output,
    write_tiff as write_metadata_tiff,
    polaroid_magick_command,
    plan_retouch,
    retouch,
)
from photo_utils.cli import build_parser, main, process_and_retouch


def make_polaroid(*, colored=False):
    image = np.full((650, 500, 3), 56000, dtype=np.uint16)
    if colored:
        image[100:500, 50:450] = (42000, 11000, 8000)
    else:
        image[100:500, 50:450] = (33000, 33000, 33000)
        image[140:230, 100:210] = (44000, 44000, 44000)
        image[300:440, 280:390] = (25000, 25000, 25000)
    return image


def write_tiff(path, image, *, profile=None):
    options = {"photometric": "rgb", "metadata": None, "resolution": (300, 300)}
    if profile is not None:
        options["extratags"] = [(34675, "B", len(profile), profile, False)]
    tifffile.imwrite(path, image, **options)


class RetouchAnalysisTests(unittest.TestCase):
    def test_plan_records_full_frame_and_fixed_recipe(self):
        image = make_polaroid()
        plan = plan_retouch(image, RetouchOptions())
        self.assertEqual(
            plan.metrics["adjustment_region"],
            "entire TIFF, including Polaroid border",
        )
        self.assertEqual(plan.decisions["ImageMagick"], "fixed Polaroid recipe applied to the full TIFF")

    def test_command_matches_requested_magick_operations_and_order(self):
        command = polaroid_magick_command(
            Path("/opt/homebrew/bin/magick"),
            Path("/photos/input.tif"),
            Path("/photos/output.partial-test.tif"),
            Path("/System/Library/ColorSync/Profiles/sRGB Profile.icc"),
        )
        self.assertEqual(
            command,
            [
                "/opt/homebrew/bin/magick",
                "/photos/input.tif",
                "-sigmoidal-contrast",
                "4x35%",
                "-gamma",
                "1.70",
                "-level",
                "5%,98.5%",
                "-gamma",
                "1.09",
                "-channel",
                "R",
                "-gamma",
                "1.04",
                "+channel",
                "-profile",
                "/System/Library/ColorSync/Profiles/sRGB Profile.icc",
                "-depth",
                "16",
                "tiff:/photos/output.partial-test.tif",
            ],
        )

    def test_unknown_profile_is_rejected(self):
        with self.assertRaisesRegex(RetouchError, "Only the 'polaroid'"):
            plan_retouch(make_polaroid(), RetouchOptions(profile="faithful"))


class RetouchPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        state_patch = patch.dict(os.environ, {'PHOTO_UTILITIES_STATE_DIR': str(self.root / 'metadata-state')})
        state_patch.start()
        self.addCleanup(state_patch.stop)
        self.source = self.root / "print.tif"
        write_tiff(self.source, make_polaroid())
        self.source_bytes = self.source.read_bytes()
        self.source_hash = hashlib.sha256(self.source_bytes).hexdigest()
        self.srgb_profile = self.root / "sRGB Profile.icc"
        self.srgb_profile_bytes = b"test-srgb-profile"
        self.srgb_profile.write_bytes(self.srgb_profile_bytes)

        def fake_render(magick, source, output, srgb_profile):
            image, metadata = _source_metadata(source)
            processed = np.minimum(image.astype(np.uint32) + 1000, 65535).astype(np.uint16)
            metadata["ICCProfile"] = Path(srgb_profile).read_bytes()
            write_metadata_tiff(output, processed, metadata)

        self.tool_patches = [
            patch("photo_utils.retouch.resolve_magick", return_value=Path("/fake/magick")),
            patch(
                "photo_utils.retouch.resolve_srgb_profile",
                return_value=self.srgb_profile,
            ),
            patch(
                "photo_utils.retouch.resolve_exiftool",
                return_value=Path("/fake/exiftool"),
            ),
            patch(
                "photo_utils.retouch._check_tools",
                return_value={"imagemagick": "ImageMagick 7 Q16", "exiftool": "13.55"},
            ),
            patch("photo_utils.retouch._metadata_summary", return_value={}),
            patch("photo_utils.retouch._copy_metadata"),
            patch("photo_utils.retouch._render_polaroid", side_effect=fake_render),
        ]
        for tool_patch in self.tool_patches:
            tool_patch.start()

    def tearDown(self):
        for tool_patch in reversed(self.tool_patches):
            tool_patch.stop()
        self.temporary_directory.cleanup()

    def test_identified_print_retouch_versions_and_date_inheritance(self):
        day = self.root / "20200101"
        prints = day / "prints"
        prints.mkdir(parents=True)
        source = prints / "20200101-002-03-print.tif"
        source.write_bytes(self.source_bytes)
        with patch("builtins.print"):
            output = retouch(source)[0]
            original = output.read_bytes()
            self.assertEqual(retouch(source), [output])
            version = retouch(source, version_history=True)[0]
            next_version = retouch(source, version_history=True)[0]
        self.assertEqual(output, (day / "retouches" / "20200101-002-03-retouch.tif").resolve())
        self.assertEqual(version.name, "20200101-002-03-retouch-v02.tif")
        self.assertEqual(next_version.name, "20200101-002-03-retouch-v03.tif")
        self.assertEqual(output.read_bytes(), original)
        recipe = database.read_record(output.with_suffix(".tif.recipe.json"))
        self.assertEqual(recipe["parent_id"], "20200101-002-03")
        self.assertEqual(recipe["scan_date"], "20200101")
        self.assertEqual(database.query_jobs(job_type="retouch")[0]["processing_status"], "completed")
        output.write_bytes(b"existing changed output")
        with patch("builtins.print"), self.assertRaises(RetouchError):
            retouch(source)
        self.assertEqual(output.read_bytes(), b"existing changed output")

    def test_polaroid_recipe_is_applied_and_recorded_without_modifying_source(self):
        output_dir = self.root / "retouched"
        outputs = retouch(self.source, output_dir=output_dir)
        self.assertEqual(len(outputs), 1)
        output = outputs[0]
        self.assertNotEqual(output.read_bytes(), self.source_bytes)
        recipe_path = output.with_suffix(".tif.recipe.json")
        recipe = database.read_record(recipe_path)
        self.assertEqual(recipe["source_sha256"], self.source_hash)
        self.assertNotEqual(recipe["output_sha256"], self.source_hash)
        self.assertEqual(recipe["icc_profile"], "sRGB assigned")
        self.assertEqual(
            recipe["actual_parameters"]["adjustment_region"],
            "entire TIFF, including Polaroid border",
        )
        self.assertEqual(
            recipe["actual_parameters"]["imagemagick_arguments"],
            [
                "-sigmoidal-contrast", "4x35%", "-gamma", "1.70",
                "-level", "5%,98.5%", "-gamma", "1.09",
                "-channel", "R", "-gamma", "1.04", "+channel",
                "-profile", str(self.srgb_profile),
                "-depth", "16",
            ],
        )
        self.assertEqual(_icc_profile(output), self.srgb_profile_bytes)
        manifest = database.read_record(output_dir / "manifest.json")
        self.assertEqual(manifest["status"], "completed")

        repeated = retouch(self.source, output_dir=output_dir)
        self.assertEqual(repeated, outputs)
        self.assertNotEqual(output.read_bytes(), self.source_bytes)
        self.assertEqual(self.source.read_bytes(), self.source_bytes)

    def test_polaroid_output_adjusts_border_and_preserves_16_bit_rgb(self):
        output_dir = self.root / "adjusted"
        outputs = retouch(self.source, output_dir=output_dir)
        output = outputs[0]
        result, metadata = _source_metadata(output)
        source_image = tifffile.imread(self.source)
        self.assertTrue(np.all(result > source_image))
        self.assertTrue(np.all(result[0] > source_image[0]))
        self.assertEqual(result.dtype, np.uint16)
        self.assertEqual(result.shape, source_image.shape)
        self.assertIn("XResolution", metadata)
        with tifffile.TiffFile(output) as tif:
            self.assertEqual(tif.pages[0].tags["BitsPerSample"].value, (16, 16, 16))
            self.assertEqual(tif.pages[0].photometric, tifffile.PHOTOMETRIC.RGB)
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.source_hash)

    def test_output_has_srgb_profile_and_verification_rejects_other_profiles(self):
        profile = b"test-icc-profile-data"
        tagged = self.root / "tagged.tif"
        tagged_output = self.root / "tagged-output.tif"
        write_tiff(tagged, make_polaroid(), profile=profile)
        image, metadata = _source_metadata(tagged)
        self.assertEqual(metadata["ICCProfile"], profile)
        metadata["ICCProfile"] = self.srgb_profile_bytes
        write_metadata_tiff(tagged_output, image, metadata)
        _verify_output(tagged_output, self.srgb_profile_bytes)
        self.assertEqual(_icc_profile(tagged_output), self.srgb_profile_bytes)
        with self.assertRaisesRegex(RetouchError, "requested sRGB"):
            _verify_output(tagged_output, profile)
        self.assertIsNone(_icc_profile(self.source))

    def test_tagged_recipe_records_conversion_to_srgb(self):
        profile = b"test-icc-profile-data"
        tagged = self.root / "tagged-input.tif"
        write_tiff(tagged, make_polaroid(), profile=profile)
        outputs = retouch(tagged, output_dir=self.root / "tagged-output")
        recipe = database.read_record(outputs[0].with_suffix(".tif.recipe.json"))
        self.assertEqual(recipe["icc_profile"], "converted to sRGB")
        self.assertEqual(_icc_profile(outputs[0]), self.srgb_profile_bytes)

    def test_dry_run_does_not_create_output_directory_or_recipe(self):
        output_dir = self.root / "dry-run"
        self.assertEqual(retouch(self.source, output_dir=output_dir, dry_run=True), [])
        self.assertFalse(output_dir.exists())

    def test_failed_magick_render_does_not_publish_partial_output_or_modify_source(self):
        output_dir = self.root / "failed"
        with patch("photo_utils.retouch._render_polaroid", side_effect=OSError("synthetic render failure")):
            with self.assertRaisesRegex(RetouchError, "synthetic render failure"):
                retouch(self.source, output_dir=output_dir)
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertFalse((output_dir / self.source.name).exists())
        self.assertEqual(
            database.read_record(output_dir / "manifest.json")["status"],
            "failed",
        )
        self.assertEqual(list(output_dir.glob("*.partial-*")), [])

    def test_folder_processing_recurses_and_does_not_ingest_its_own_outputs(self):
        nested = self.root / "incoming" / "nested"
        nested.mkdir(parents=True)
        first = nested / "one.tif"
        second = nested / "two.tiff"
        write_tiff(first, make_polaroid())
        write_tiff(second, make_polaroid(colored=True))
        old_output = self.root / "incoming" / "previous-output"
        old_output.mkdir()
        write_tiff(old_output / "old-print.tif", make_polaroid())
        (old_output / "manifest.json").write_text(
            json.dumps({"algorithm": "faithful-polaroid-v2"})
        )
        source_root = self.root / "incoming"
        output_dir = self.root / "batch-retouched"
        outputs = retouch(source_root, output_dir=output_dir)
        self.assertEqual(
            [path.relative_to(output_dir.resolve()).as_posix() for path in outputs],
            ["nested/one.tif", "nested/two.tiff"],
        )
        with self.assertRaisesRegex(RetouchError, "already contains retouched derivatives"):
            retouch(output_dir, output_dir=self.root / "second-pass")

    def test_process_and_retouch_runs_after_sheet_split(self):
        outputs = [self.root / "prints" / "print-01.tif"]
        with patch("photo_utils.cli.process_sheet", return_value=outputs) as split:
            with patch("photo_utils.cli.retouch") as apply_retouch:
                process_and_retouch(self.source, profile="polaroid")
        split.assert_called_once_with(self.source, output_dir=None, dry_run=False,kind="polaroids")
        apply_retouch.assert_called_once()
        self.assertEqual(apply_retouch.call_args.args[0], outputs[0].parent)

    def test_cli_selects_polaroid_profile_and_scan_opt_out(self):
        automatic = build_parser().parse_args(["retouch", str(self.source)])
        self.assertEqual(automatic.profile, "polaroid")
        scan = build_parser().parse_args(["scan", "--retouch", "none"])
        self.assertEqual(scan.retouch, "none")

    def test_scan_command_routes_default_profile_through_polaroid_processing(self):
        with patch("photo_utils.cli.run_scan", return_value=self.source):
            with patch("photo_utils.cli.process_and_retouch") as pipeline:
                self.assertEqual(main(["scan"]), 0)
        pipeline.assert_called_once_with(self.source, profile="polaroid", kind="polaroids", find_similar_groups=False, focus_review=True,tier_review=True,auto_rotate=True)
