import os
import sqlite3
import stat
import sys
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import patch

from photo_utils.cli import build_parser, main, prompt_choice, prompt_scan_folder
from photo_utils.scanning import (
    ScanError,
    build_scan_command,
    connect_database,
    default_root,
    default_scan_folder,
    default_state_dir,
    ensure_visible,
    is_tiff,
    mark_abandoned_jobs_interrupted,
    parse_scanner_list,
    run_scan,
    select_scanner,
    sha256_file,
    validate_folder_name,
)


def create_fake_scanimage(path):
    path.write_text(
        f"#!{sys.executable}\n"
        + textwrap.dedent(
            """
            import pathlib
            import sys

            args = sys.argv[1:]
            if "--version" in args:
                print("scanimage (sane-backends) 1.4.0")
            elif "--list-devices" in args:
                print("device `pixma:test` is CANON CanoScan LiDE 400")
            elif "--dont-scan" in args:
                pass
            else:
                output = pathlib.Path(args[args.index("--output-file") + 1])
                output.write_bytes(b"II*\\x00synthetic scan")
            """
        )
    )
    path.chmod(0o755)


class ScannerParsingTests(unittest.TestCase):
    def test_parse_and_select_lide400(self):
        output = (
            "device `pixma:other` is CANON CanoScan LiDE 300\n"
            "device `pixma:04A91912_52CF8A` is CANON CanoScan LiDE 400 "
            "multi-function peripheral\n"
        )
        devices = parse_scanner_list(output)
        self.assertEqual(
            select_scanner(devices),
            (
                "pixma:04A91912_52CF8A",
                "CANON CanoScan LiDE 400 multi-function peripheral",
            ),
        )

    def test_select_requires_explicit_device_when_multiple_lide400s_exist(self):
        devices = [
            ("pixma:first", "Canon CanoScan LiDE 400"),
            ("pixma:second", "Canon CanoScan LiDE 400"),
        ]
        with self.assertRaisesRegex(ScanError, "More than one"):
            select_scanner(devices)

    def test_missing_device_has_actionable_error(self):
        with self.assertRaisesRegex(ScanError, "No Canon LiDE 400"):
            select_scanner([])


class MenuTests(unittest.TestCase):
    def test_quit_exits_from_main_menu(self):
        with patch('builtins.input',side_effect=['q']), patch('sys.stdin.isatty',return_value=True), patch('photo_utils.cli.run_scan') as scan:
            self.assertEqual(main([]),0)
            scan.assert_not_called()

    def test_prompt_choice_uses_conventional_default_notation(self):
        with patch("builtins.input", side_effect=["", "d"]):
            with patch("builtins.print") as printed:
                self.assertEqual(
                    prompt_choice("Select an action", "DSQ"), "d"
                )
        self.assertEqual(
            [call.args[0] for call in printed.call_args_list],
            ["Please enter one of: D, S, Q."],
        )

    def test_prompt_choice_shows_uppercase_default(self):
        with patch("builtins.input", return_value="") as prompt:
            self.assertEqual(prompt_choice("Use default?", "YN", default="Y"), "y")
        self.assertEqual(prompt.call_args.args[0], "Use default? [Y/n]: ")

    def test_default_scan_folder_is_today_in_yyyymmdd(self):
        self.assertRegex(default_scan_folder(), r"^\d{8}$")
        args = build_parser().parse_args(["scan"])
        self.assertEqual(args.folder, default_scan_folder())

    def test_menu_scan_uses_default_date_folder_and_defaults_to_real_scan(self):
        default_folder = default_scan_folder()
        scanned_sheet = Path("/scans/20261009/sheet.tif")
        with patch("builtins.input", side_effect=["s", "", "", "", "q"]):
            with patch("sys.stdin.isatty", return_value=True):
                with patch("photo_utils.cli.run_scan", return_value=scanned_sheet) as run_scan:
                    with patch("photo_utils.cli.process_and_retouch",return_value=None) as process:
                        self.assertEqual(main([]), 0)
        run_scan.assert_called_once_with(
            folder=default_folder,
            root=default_root(),
            state_dir=default_state_dir(),
            dry_run=False,
        )
        process.assert_called_once_with(scanned_sheet,profile="polaroid",kind="polaroids",focus_review=True,dry_run=False)

    def test_menu_uses_scan_date_and_dry_run(self):
        with patch("builtins.input", side_effect=["s", "o", "y", "q"]):
            with patch("sys.stdin.isatty", return_value=True):
                with patch("photo_utils.cli.run_scan", return_value=None) as run_scan:
                    with patch("photo_utils.cli.process_and_retouch",return_value=None) as process:
                        self.assertEqual(main([]), 0)
        self.assertEqual(run_scan.call_args.kwargs["folder"], default_scan_folder())
        self.assertTrue(run_scan.call_args.kwargs["dry_run"])
        process.assert_not_called()

    def test_non_polaroid_scan_splits_without_polaroid_edits(self):
        scanned_sheet = Path("/scans/20261009/sheet.tif")
        with patch("builtins.input", side_effect=["s", "o", "", "q"]):
            with patch("sys.stdin.isatty", return_value=True):
                with patch("photo_utils.cli.run_scan", return_value=scanned_sheet):
                    with patch("photo_utils.cli.process_and_retouch",return_value=None) as process:
                        self.assertEqual(main([]), 0)
        process.assert_called_once_with(scanned_sheet,profile="none",kind="prints",focus_review=True,dry_run=False)

    def test_cli_capture_only_does_not_split_sheet(self):
        with patch("photo_utils.cli.run_scan", return_value=Path("/scans/sheet.tif")):
            with patch("photo_utils.cli.process_and_retouch",return_value=None) as process:
                self.assertEqual(main(["scan", "--capture-only"]), 0)
        process.assert_not_called()

    def test_scan_menu_can_process_existing_sheet_without_scanning(self):
        source = Path("/scans/older-sheet.tif")
        with patch("builtins.input", side_effect=["e", "", "", "", "", "q"]):
            with patch("sys.stdin.isatty", return_value=True):
                with patch("photo_utils.cli.list_sheet_sources", return_value=[source]):
                    with patch("photo_utils.cli.run_scan") as run_scan:
                        with patch("photo_utils.cli.process_and_retouch",return_value=None) as process:
                            self.assertEqual(main([]), 0)
        run_scan.assert_not_called()
        process.assert_called_once_with(
            source,
            dry_run=False,profile="polaroid",kind="polaroids",focus_review=True,
        )

    def test_menu_quit_does_not_run_a_command(self):
        with patch("builtins.input", return_value="q"):
            with patch("sys.stdin.isatty", return_value=True):
                self.assertEqual(main([]), 0)

    def test_menu_doctor_runs_diagnostics_without_scan_prompts(self):
        with patch("builtins.input", side_effect=["m","d","q"]):
            with patch("sys.stdin.isatty", return_value=True):
                with patch("photo_utils.cli.doctor") as doctor:
                    with patch("photo_utils.cli.run_scan") as run_scan:
                        self.assertEqual(main([]), 0)
        doctor.assert_called_once_with()
        run_scan.assert_not_called()

    def test_menu_reprompts_for_unsafe_custom_folder(self):
        with patch("builtins.input", side_effect=["n", "../escape", "safe-name"]):
            with patch("builtins.print") as printed:
                self.assertEqual(prompt_scan_folder(Path("/scans")), "safe-name")
        self.assertIn("not a path", str(printed.call_args.args[0]))

    def test_menu_handles_end_of_input_without_scanning(self):
        with patch("builtins.input", side_effect=["s", EOFError]):
            with patch("sys.stdin.isatty", return_value=True):
                with patch("photo_utils.cli.run_scan") as run_scan:
                    self.assertEqual(main([]), 0)
        run_scan.assert_not_called()

    def test_no_command_without_terminal_returns_usage_error(self):
        from io import StringIO

        stderr = StringIO()
        with patch("sys.stdin.isatty", return_value=False):
            with patch("sys.stderr", stderr):
                self.assertEqual(main([]), 2)
        self.assertIn("interactive menu requires a terminal", stderr.getvalue())


class ScanSafetyTests(unittest.TestCase):
    def test_folder_name_rejects_paths(self):
        for value in ("", ".", "..", "../outside", "nested/folder", "nested\\folder"):
            with self.subTest(value=value):
                with self.assertRaises(ScanError):
                    validate_folder_name(value)

    def test_folder_name_accepts_single_name_with_spaces(self):
        self.assertEqual(validate_folder_name("Polaroid scans"), "Polaroid scans")

    def test_scan_command_uses_flatbed_high_bit_tiff_and_dry_run(self):
        command = build_scan_command(
            Path("/opt/homebrew/bin/scanimage"),
            "pixma:device",
            Path("/tmp/scan.tif"),
            600,
            "48-bit-color",
            dont_scan=True,
        )
        self.assertEqual(
            command,
            [
                "/opt/homebrew/bin/scanimage",
                "--device-name",
                "pixma:device",
                "--source",
                "Flatbed",
                "--mode",
                "48 bits color",
                "--resolution",
                "600",
                "--format=tiff",
                "--output-file",
                "/tmp/scan.tif",
                "--dont-scan",
            ],
        )

    def test_tiff_validation_and_streaming_checksum(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            image = Path(temporary_directory) / "scan.tif"
            image.write_bytes(b"II*\x00synthetic TIFF fixture")
            self.assertTrue(is_tiff(image))
            self.assertEqual(
                sha256_file(image),
                "6aa575a70fe50ab0cc89f946d96afb7a732dab149221e3844bd609403538795d",
            )
            image.write_bytes(b"not a TIFF")
            self.assertFalse(is_tiff(image))

    def test_ensure_visible_clears_hidden_flag_without_removing_other_flags(self):
        hidden_flag = 0x8000
        path = Path("/tmp/scan.tif")
        with patch("photo_utils.scanning.stat.UF_HIDDEN", hidden_flag, create=True):
            with patch.object(
                Path,
                "stat",
                side_effect=[
                    SimpleNamespace(st_flags=hidden_flag | 0x1),
                    SimpleNamespace(st_flags=0x1),
                ],
            ):
                with patch("photo_utils.scanning.os.chflags") as chflags:
                    ensure_visible(path)
        chflags.assert_called_once_with(path, 0x1)

    def test_successful_scan_is_published_checksummed_and_tracked(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            executable = temporary / "scanimage"
            create_fake_scanimage(executable)
            root = temporary / "photos"
            state_dir = temporary / "state"

            with patch.dict(
                os.environ, {"PHOTO_UTILITIES_SCANIMAGE": str(executable)}
            ):
                output = run_scan(
                    folder="sheet",
                    root=root,
                    state_dir=state_dir,
                )

            self.assertIsNotNone(output)
            self.assertTrue(output.is_file())
            self.assertTrue(is_tiff(output))
            self.assertFalse(output.name.startswith("."))
            self.assertFalse(list(output.parent.glob("*.partial-*.tif")))
            with sqlite3.connect(state_dir / "jobs.sqlite3") as connection:
                job = connection.execute(
                    "SELECT status, sha256, size_bytes FROM scan_jobs"
                ).fetchone()
            self.assertEqual(
                job, ("completed", sha256_file(output), output.stat().st_size)
            )

    def test_collision_never_overwrites_existing_image(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            executable = temporary / "scanimage"
            create_fake_scanimage(executable)
            root = temporary / "photos"
            destination = root / default_scan_folder() / "masters"
            destination.mkdir(parents=True)
            existing = destination / "already-there.tif"
            existing.write_bytes(b"keep this existing file")
            state_dir = temporary / "state"

            with patch.dict(
                os.environ, {"PHOTO_UTILITIES_SCANIMAGE": str(executable)}
            ):
                with patch(
                    "photo_utils.scanning.make_output_name",
                    return_value=existing.name,
                ):
                    with self.assertRaisesRegex(ScanError, "Refusing to overwrite"):
                        run_scan(
                            folder="sheet",
                            root=root,
                            state_dir=state_dir,
                        )

            self.assertEqual(existing.read_bytes(), b"keep this existing file")
            self.assertEqual(len(list(destination.glob("*.partial-*.tif"))), 1)
            with sqlite3.connect(state_dir / "jobs.sqlite3") as connection:
                status = connection.execute(
                    "SELECT status FROM scan_jobs"
                ).fetchone()[0]
            self.assertEqual(status, "failed")

    def test_recovery_marks_completed_and_incomplete_jobs(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            database = temporary / "jobs.sqlite3"
            complete_output = temporary / "complete.tif"
            complete_output.write_bytes(b"II*\x00completed scan")
            partial_output = temporary / "unfinished.partial.tif"
            partial_output.write_bytes(b"incomplete data")
            connection = connect_database(database)
            for job_id, output_path in (
                ("complete", complete_output),
                ("incomplete", temporary / "missing.tif"),
            ):
                connection.execute(
                    """
                    INSERT INTO scan_jobs
                        (job_id, started_at, status, device, output_path,
                         partial_path, settings_json)
                    VALUES (?, 'now', 'running', 'pixma:test', ?, ?, '{}')
                    """,
                    (job_id, str(output_path), str(partial_output)),
                )
            connection.commit()

            mark_abandoned_jobs_interrupted(connection)

            jobs = dict(
                connection.execute(
                    "SELECT job_id, status FROM scan_jobs"
                ).fetchall()
            )
            connection.close()
            self.assertEqual(
                jobs, {"complete": "completed", "incomplete": "interrupted"}
            )
            self.assertTrue(partial_output.exists())


if __name__ == "__main__":
    unittest.main()
