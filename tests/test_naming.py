from photo_utils import database
import os
import concurrent.futures
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from photo_utils.naming import allocate, identity, existing_master, master_id
from photo_utils.processing import process_sheet, ProcessingError, detect_cards
from photo_utils.scanning import run_scan, ScanError
from tests.test_processing import write_synthetic_sheet
from tests.test_scanning import create_fake_scanimage
import tifffile


def simulated_cli_scan(arguments):
    root, state, executable = arguments
    with patch.dict(os.environ, {'PHOTO_UTILITIES_SCANIMAGE': str(executable)}), patch('builtins.print'):
        try:
            return run_scan(folder='ignored', root=root, state_dir=state).name
        except (ScanError,database.DatabaseError):
            return None


class NamingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        state_patch = patch.dict(os.environ, {'PHOTO_UTILITIES_STATE_DIR': str(self.root / 'metadata-state')})
        state_patch.start()
        self.addCleanup(state_patch.stop)

    def test_daily_sequence_rollover_and_width(self):
        self.assertEqual(allocate(self.root, '20261010'), 1)
        self.assertEqual(allocate(self.root, '20261010'), 2)
        self.assertEqual(allocate(self.root, '20261011'), 1)
        with sqlite3.connect(database.database_path()) as db:
            db.execute("UPDATE daily_ids SET number=999 WHERE date='20261010'")
        self.assertEqual(master_id('20261010', allocate(self.root, '20261010')), '20261010-1000')

    def test_concurrent_allocations_are_unique_and_persistent(self):
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
            numbers = list(pool.map(allocate, [self.root] * 16, ['20261010'] * 16))
        self.assertEqual(sorted(numbers), list(range(1, 17)))
        self.assertEqual(allocate(self.root, '20261010'), 17)

    def test_concurrent_scan_invocations_with_distinct_state_dirs(self):
        executable = self.root / 'scanimage'
        create_fake_scanimage(executable)
        root = self.root / 'photos'
        arguments = [(root, self.root / 'shared-state', executable) for i in range(4)]
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
            names = list(pool.map(simulated_cli_scan, arguments))
        names = [name for name in names if name]
        self.assertGreater(len(names), 0)
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(list(root.rglob('*-master.tif'))), len(names))

    def test_legacy_identity_is_persistent_without_changing_source(self):
        source = self.root / 'LiDE400-20261009T235900-0400-old.tif'
        source.write_bytes(b'original')
        expected, day = existing_master(source, dry_run=True)
        self.assertFalse((self.root / '.photo-utils-naming.sqlite3').exists())
        actual, day = existing_master(source)
        self.assertEqual(expected, actual)
        self.assertEqual(existing_master(source)[0], actual)
        self.assertEqual(day.name, '20261009')
        self.assertEqual(source.read_bytes(), b'original')

    def test_scan_failure_consumes_id_and_midnight_keeps_start_date(self):
        executable = self.root / 'scanimage'
        create_fake_scanimage(executable)
        state = self.root / 'state'
        scans = self.root / 'photos'
        def clock(value):
            mocked = patch('photo_utils.scanning.datetime')
            result = mocked.start()
            self.addCleanup(mocked.stop)
            result.now.return_value = value
            return result
        now = clock(datetime(2026, 10, 10, 23, 59, tzinfo=timezone(timedelta(hours=-4))))
        from photo_utils import scanning
        actual_run = scanning.subprocess.run
        def failed(command, **kwargs):
            if '--progress' in command:
                return type('Result', (), {'returncode': 1})()
            return actual_run(command, **kwargs)
        with patch.dict(os.environ, {'PHOTO_UTILITIES_SCANIMAGE': str(executable)}), patch('builtins.print'):
            with patch('photo_utils.scanning.subprocess.run', side_effect=failed):
                with self.assertRaises(ScanError):
                    run_scan(folder='ignored', root=scans, state_dir=state)
            def crossing_midnight(command, **kwargs):
                if '--progress' in command:
                    now.now.return_value = datetime(2026, 10, 11, 0, 1, tzinfo=timezone(timedelta(hours=-4)))
                return actual_run(command, **kwargs)
            with patch('photo_utils.scanning.subprocess.run', side_effect=crossing_midnight):
                output = run_scan(folder='ignored', root=scans, state_dir=state)
            self.assertEqual(output.name, '20261010-002-master.tif')
            output.unlink()
            now.now.return_value = datetime(2026, 10, 10, 23, 59, tzinfo=timezone(timedelta(hours=-4)))
            self.assertEqual(run_scan(folder='ignored', root=scans, state_dir=state).name, '20261010-003-master.tif')
            now.now.return_value = datetime(2026, 10, 11, 0, 1, tzinfo=timezone(timedelta(hours=-4)))
            self.assertEqual(run_scan(folder='ignored', root=scans, state_dir=state).name, '20261011-001-master.tif')
        with sqlite3.connect(state / 'jobs.sqlite3') as db:
            jobs = db.execute('SELECT status, settings_json FROM scan_jobs ORDER BY rowid').fetchall()
        self.assertEqual(jobs[0][0], 'failed')
        self.assertEqual(json.loads(jobs[1][1])['scan_date'], '20261010')
        self.assertTrue((scans / '20261010' / 'retouches').is_dir())

    def test_shared_stage_directory_date_inheritance_and_resume(self):
        day = self.root / '20200101'
        masters = day / 'masters'
        masters.mkdir(parents=True)
        first = masters / '20200101-001-master.tif'
        second = masters / '20200101-002-master.tif'
        write_synthetic_sheet(first)
        write_synthetic_sheet(second)
        original = first.read_bytes()
        with patch('builtins.print'):
            outputs = process_sheet(first)
            self.assertEqual(process_sheet(first), outputs)
            second_outputs = process_sheet(second)
        self.assertEqual([p.name for p in outputs], [f'20200101-001-{i:02d}-print.tif' for i in range(1, 5)])
        self.assertTrue(all(p.parent == day / 'prints' for p in outputs + second_outputs))
        self.assertEqual(first.read_bytes(), original)
        cards = detect_cards(tifffile.imread(first))
        self.assertLess(cards[0].center[0], cards[1].center[0])
        self.assertLess(cards[2].center[0], cards[3].center[0])
        self.assertLess(cards[1].center[1], cards[2].center[1])
        with patch('photo_utils.processing.plan_cards', return_value=[]):
            with self.assertRaises(ProcessingError):
                process_sheet(first)
        before = outputs[0].read_bytes()
        with patch('builtins.print'):
            self.assertEqual(process_sheet(first), outputs)
        self.assertEqual(outputs[0].read_bytes(), before)

    def test_interrupted_publication_resumes_assigned_prints(self):
        source = self.root / '20261010-001-master.tif'
        write_synthetic_sheet(source)
        link = os.link
        def interrupt_after_publish(temporary, final):
            link(temporary, final)
            raise KeyboardInterrupt()
        with patch('builtins.print'), patch('photo_utils.processing.os.link', side_effect=interrupt_after_publish):
            with self.assertRaises(KeyboardInterrupt):
                process_sheet(source)
        first = self.root / '20261010' / 'prints' / '20261010-001-01-print.tif'
        original = first.read_bytes()
        with patch('builtins.print'):
            outputs = process_sheet(source)
        self.assertEqual(len(outputs), 4)
        self.assertEqual(first.read_bytes(), original)

    def test_interrupted_scan_consumes_reserved_id(self):
        executable = self.root / 'scanimage'
        create_fake_scanimage(executable)
        from photo_utils import scanning
        actual_run = scanning.subprocess.run
        def interrupted(command, **kwargs):
            if '--progress' in command:
                raise KeyboardInterrupt()
            return actual_run(command, **kwargs)
        scans = self.root / 'photos'
        state = self.root / 'state'
        with patch.dict(os.environ, {'PHOTO_UTILITIES_SCANIMAGE': str(executable)}), patch('builtins.print'):
            with patch('photo_utils.scanning.subprocess.run', side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
                run_scan(folder='ignored', root=scans, state_dir=state)
            result = run_scan(folder='ignored', root=scans, state_dir=state)
        self.assertEqual(identity(result)[1], 2)
        with sqlite3.connect(state / 'jobs.sqlite3') as db:
            self.assertEqual(db.execute('SELECT status FROM scan_jobs ORDER BY rowid LIMIT 1').fetchone()[0], 'interrupted')

    def test_print_collision_preserves_existing_file(self):
        source = self.root / '20261010-001-master.tif'
        write_synthetic_sheet(source)
        prints = self.root / '20261010' / 'prints'
        prints.mkdir(parents=True)
        occupied = prints / '20261010-001-01-print.tif'
        occupied.write_bytes(b'preserve')
        with patch('builtins.print'), self.assertRaises(ProcessingError):
            process_sheet(source)
        self.assertEqual(occupied.read_bytes(), b'preserve')
