from contextlib import closing
import concurrent.futures
import io
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from photo_utils import database as store
from photo_utils.cli import main
from photo_utils.history_cli import export_job
from photo_utils.processing import process_sheet
from photo_utils.retouch import retouch, RetouchError
from photo_utils.scanning import run_scan
from tests import test_retouch as fixtures
from tests.test_processing import write_synthetic_sheet
from tests.test_scanning import create_fake_scanimage


def concurrent_job(arguments):
    state,index = arguments
    with store.use_state(state), store.transaction() as db:
        store.save_job(db,f'job-{index}','retouch',{'status':'running','created_at':'2026-10-10T10:00:00-04:00'})
    return index


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RetouchPipelineTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root.resolve()
        self.source = self.fixture.source.resolve()

    def test_external_retouch_and_full_recipe_in_database_without_sidecars(self):
        with patch('builtins.print'):
            output = retouch(self.source,output_dir=self.root/'standalone-outputs')[0]
        jobs = store.query_jobs()
        self.assertEqual(len(jobs),1)
        self.assertEqual(jobs[0]['job_type'],'retouch')
        self.assertIsNone(jobs[0]['parent_job_id'])
        assets = store.query_assets()
        external = next(row for row in assets if row['asset_type']=='external')
        result = next(row for row in assets if row['asset_type']=='retouch')
        self.assertEqual(result['parent_asset_id'],external['asset_id'])
        self.assertEqual(result['bit_depth'],16)
        history = store.history(result['asset_id'])
        self.assertEqual(len(history['lineage']),2)
        recipe = history['recipes'][0]['payload']
        self.assertEqual(recipe['actual_parameters']['imagemagick_arguments'][1],'4x35%')
        self.assertEqual(recipe['actual_parameters']['output_icc_profile_path'],str(self.fixture.srgb_profile))
        self.assertFalse(list(output.parent.glob('*.json')))
        self.assertEqual(self.source.read_bytes(),self.fixture.source_bytes)
        with patch('builtins.print'):
            self.assertEqual(retouch(self.source,output_dir=self.root/'standalone-outputs'),[output])
        self.assertEqual(len(store.query_jobs()),1)

    def test_scan_split_and_batch_retouch_relationships(self):
        executable = self.root/'scanimage'
        create_fake_scanimage(executable)
        from photo_utils import scanning
        actual_run = scanning.subprocess.run
        def acquire(command,**kwargs):
            if '--progress' in command:
                write_synthetic_sheet(Path(command[command.index('--output-file')+1]))
                return SimpleNamespace(returncode=0)
            return actual_run(command,**kwargs)
        with patch.dict(os.environ,{'PHOTO_UTILITIES_SCANIMAGE':str(executable)}), patch('builtins.print'), patch('photo_utils.scanning.subprocess.run',side_effect=acquire):
            master = run_scan(folder='date',root=self.root/'scans',state_dir=store.state_dir())
        with patch('builtins.print'):
            prints = process_sheet(master)
            outputs = retouch(prints[0].parent)
        self.assertEqual(len(outputs),4)
        assets = store.query_assets()
        masters = [row for row in assets if row['asset_type']=='master']
        self.assertEqual(len(masters),1)
        print_assets = [row for row in assets if row['asset_type']=='print']
        self.assertEqual(len(print_assets),4)
        self.assertTrue(all(row['parent_asset_id']==masters[0]['asset_id'] for row in print_assets))
        print_ids = {row['asset_id'] for row in print_assets}
        self.assertTrue(all(row['parent_asset_id'] in print_ids for row in assets if row['asset_type']=='retouch'))
        self.assertEqual(sorted(row['job_type'] for row in store.query_jobs()),['retouch','scan','split'])
        self.assertEqual({row['processing_date'] for row in assets},{master.parent.parent.name})
        self.assertFalse(list((self.root/'scans').rglob('*.json')))
        self.assertTrue(store.check_database(True)['database_ok'])

    def test_schema_upgrade_backs_up_and_preserves_existing_jobs(self):
        path = self.root/'old-state'/'jobs.sqlite3'
        path.parent.mkdir()
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE scan_jobs(job_id TEXT PRIMARY KEY,started_at TEXT NOT NULL,finished_at TEXT,status TEXT NOT NULL,device TEXT NOT NULL,output_path TEXT NOT NULL,partial_path TEXT NOT NULL,settings_json TEXT NOT NULL,sha256 TEXT,size_bytes INTEGER,error TEXT)")
            db.execute('INSERT INTO scan_jobs VALUES (?,?,NULL,?,?,?,?,?,NULL,NULL,NULL)',('legacy','2026-10-10T10:00:00-04:00','running','device',str(self.source),'partial','{}'))
        with closing(store.connect(path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM scan_jobs').fetchone()[0],1)
            self.assertEqual(db.execute('PRAGMA foreign_keys').fetchone()[0],1)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],store.SCHEMA_VERSION)
        backups = list(path.parent.glob('jobs.backup-*.sqlite3'))
        self.assertEqual(len(backups),1)
        with sqlite3.connect(backups[0]) as db:
            self.assertEqual(db.execute('SELECT job_id FROM scan_jobs').fetchone()[0],'legacy')
        with closing(store.connect(path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM scan_jobs').fetchone()[0],1)
        self.assertEqual(len(list(path.parent.glob('jobs.backup-*.sqlite3'))),1)

    def test_foreign_keys_and_transactions(self):
        with self.assertRaises(store.DatabaseError):
            with store.transaction() as db:
                store.save_job(db,'will-rollback','retouch',{'status':'running'})
                store.asset(db,self.source,parent='unknown-parent')
        self.assertFalse(store.query_jobs())
        with closing(store.connect()) as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_queries_exports_diagnostics_and_menu(self):
        with patch('builtins.print'):
            output = retouch(self.source,output_dir=self.root/'standalone-outputs')[0]
        job = store.query_jobs()[0]
        date = job['processing_date']
        asset = next(row for row in store.query_assets() if row['asset_type']=='retouch')
        for args in [['jobs','--date',date],['job','show',job['job_id']],['assets','--date',date],['recipe','show',asset['asset_id']],['history',asset['asset_id']],['db','check','--checksums']]:
            with patch('sys.stdout',new_callable=io.StringIO) as stream:
                self.assertEqual(main(args),0)
                self.assertTrue(stream.getvalue())
        export = self.root/'explicit-export.json'
        with patch('builtins.print'):
            export_job(job['job_id'],export)
        self.assertEqual(json.loads(export.read_text())['job']['job_id'],job['job_id'])
        with self.assertRaises(store.DatabaseError):
            export_job(job['job_id'],export)
        output.unlink()
        result = store.check_database()
        self.assertTrue(result['database_ok'])
        self.assertEqual(len(result['missing_files']),1)
        with patch('builtins.print'),self.assertRaises(RetouchError):
            retouch(self.source,output_dir=self.root/'standalone-outputs')
        with patch('sys.stdin.isatty',return_value=True),patch('builtins.input',side_effect=['m','h','2','9','q']),patch('builtins.print'):
            self.assertEqual(main([]),0)

    def test_naming_ledger_is_imported_without_reset_or_second_database(self):
        root = self.root/'scan-root'
        root.mkdir()
        legacy = root/'.photo-utils-naming.sqlite3'
        with sqlite3.connect(legacy) as db:
            db.execute('CREATE TABLE daily_ids(date TEXT PRIMARY KEY,number INTEGER)')
            db.execute("INSERT INTO daily_ids VALUES ('20261010',27)")
        before = legacy.read_bytes()
        self.assertEqual(store.reserve(root,'20261010')[1],28)
        self.assertEqual(store.reserve(root,'20261010')[1],29)
        self.assertEqual(legacy.read_bytes(),before)
        with store.use_state(self.root/'other-state'),self.assertRaises(store.DatabaseError):
            store.reserve(root,'20261010')

    def test_concurrent_metadata_operations(self):
        arguments = [(store.state_dir(),i) for i in range(12)]
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sorted(pool.map(concurrent_job,arguments)),list(range(12)))
        self.assertEqual(len(store.query_jobs()),12)
        self.assertTrue(store.check_database()['database_ok'])

    def test_batch_failure_records_partial_completion_and_resumes(self):
        incoming = self.root/'incoming'
        incoming.mkdir()
        for name in ['one.tif','two.tif']:
            (incoming/name).write_bytes(self.fixture.source_bytes)
        from photo_utils import retouch as module
        render = module._render_polaroid
        calls = 0
        def fail_second(*args,**kwargs):
            nonlocal calls
            calls += 1
            if calls==2:
                raise RetouchError('synthetic second-image failure')
            return render(*args,**kwargs)
        output_dir = self.root/'batch-output'
        with patch('builtins.print'),patch('photo_utils.retouch._render_polaroid',side_effect=fail_second),self.assertRaises(RetouchError):
            retouch(incoming,output_dir=output_dir)
        self.assertEqual(store.query_jobs()[0]['processing_status'],'partial')
        self.assertEqual(len([a for a in store.query_assets() if a['asset_type']=='retouch']),1)
        with patch('builtins.print'):
            outputs = retouch(incoming,output_dir=output_dir)
        self.assertEqual(len(outputs),2)
        self.assertEqual(store.query_jobs()[0]['processing_status'],'completed')
        self.assertFalse(list(output_dir.rglob('*.json')))

    def test_retouch_interrupted_after_publication_recovers_recipe(self):
        from photo_utils import retouch as module
        publish = module._publish_no_replace
        def interrupted(temporary,output):
            publish(temporary,output)
            raise KeyboardInterrupt()
        with patch('builtins.print'),patch('photo_utils.retouch._publish_no_replace',side_effect=interrupted),self.assertRaises(KeyboardInterrupt):
            retouch(self.source,output_dir=self.root/'standalone-outputs')
        self.assertEqual(store.query_jobs()[0]['processing_status'],'partial')
        with patch('builtins.print'):
            outputs = retouch(self.source,output_dir=self.root/'standalone-outputs')
        self.assertEqual(len(outputs),1)
        self.assertEqual(store.query_jobs()[0]['processing_status'],'completed')
        self.assertFalse(list(outputs[0].parent.glob('*.json')))
