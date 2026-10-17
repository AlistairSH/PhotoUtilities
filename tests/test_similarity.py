import base64
from contextlib import closing
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from photo_utils import database, similarity
from photo_utils.cli import main, process_and_retouch
from photo_utils.similarity_report import render


def fixture_result(paths, hashes):
    ok, png = cv2.imencode('.jpg', np.zeros((20, 20, 3), np.uint8))
    assert ok
    return {'analyzer': similarity.VERSION, 'parameters': similarity.PARAMETERS,
            'backends': {'opencv': cv2.__version__},
            'images': [{'path': str(p), 'sha256': h, 'thumbnail': base64.b64encode(png).decode(),
                        'width': 20, 'height': 20} for p, h in zip(paths, hashes)],
            'pairs': [{'a': 0, 'b': 1, 'vision_distance': .3, 'sift_candidate': False, 'level': 'likely'}],
            'groups': [{'members': [0, 1], 'level': 'likely'}], 'unmatched': []}


class SimilarityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.images = self.root / 'photos'
        self.images.mkdir()
        self.paths = [self.images / 'a.jpg', self.images / 'b.jpg']
        for index, path in enumerate(self.paths):
            cv2.imwrite(str(path), np.full((20, 20, 3), index * 20, np.uint8))
        self.state = self.root / 'state'
        self.real_print = print
        self.print_patch = patch('builtins.print')
        self.print_patch.start()
        self.addCleanup(self.print_patch.stop)

    def analyze(self, paths, hashes, threshold=.45):
        return fixture_result(paths, hashes)

    def test_graph_chains_and_fixed_classification(self):
        pairs = [{'a': 0, 'b': 1, 'level': 'likely'}, {'a': 1, 'b': 2, 'level': 'potential'}]
        self.assertEqual(similarity.components(4, pairs), [[0, 1, 2], [3]])
        self.assertEqual(similarity.components(4, pairs, likely_only=True), [[0, 1], [2], [3]])
        self.assertEqual(similarity.classify(.399, False), 'likely')
        self.assertEqual(similarity.classify(.4, False), 'potential')
        self.assertEqual(similarity.classify(.449, True), 'likely')
        self.assertEqual(similarity.classify(.45, False), 'unmatched')
        self.assertEqual(similarity.classify(.7, True), 'potential')

    def test_sift_geometric_transform_and_insufficient_features(self):
        rng = np.random.default_rng(12)
        gray = rng.integers(0, 256, (512, 512), dtype=np.uint8)
        shifted = cv2.warpAffine(gray, np.float32([[1, 0, 12], [0, 1, 8]]), (512, 512))
        detector = cv2.SIFT_create(nfeatures=500)
        def features(image):
            points, descriptors = detector.detectAndCompute(image, None)
            return {'points': np.asarray([k.pt for k in points], np.float32),
                    'descriptors': descriptors, 'shape': image.shape}
        match = similarity.sift_pair(features(gray), features(shifted), cv2.BFMatcher(cv2.NORM_L2))
        self.assertTrue(match['sift_candidate'])
        self.assertGreater(match['inliers'], 100)
        empty = features(np.zeros((512, 512), np.uint8))
        self.assertFalse(similarity.sift_pair(empty, empty, cv2.BFMatcher(cv2.NORM_L2))['sift_candidate'])

    def test_discovery_dedup_recursion_and_preview_exclusion(self):
        sub = self.images / 'sub'
        sub.mkdir()
        (sub / 'c.HEIC').write_bytes(b'fixture')
        (self.images / 'a.before-after.jpg').write_bytes(b'preview')
        self.assertEqual(similarity.collect_images([self.images, self.paths[0]]), self.paths)
        self.assertEqual(len(similarity.collect_images([self.images], True)), 3)

    def test_dry_run_and_no_db_do_not_open_database(self):
        with patch.object(database, 'connect', side_effect=AssertionError('database opened')), \
                patch.object(similarity, 'analyze', side_effect=self.analyze) as analyze:
            self.assertIsNone(similarity.find_similar([self.images], dry_run=True, state_dir=self.state))
            analyze.assert_not_called()
            report = similarity.find_similar([self.images], no_db=True, state_dir=self.state)
        self.assertTrue(report.is_file())
        self.assertFalse(self.state.exists())

    def test_completed_persistence_preserves_source_metadata_and_derivative_lineage(self):
        with database.use_state(self.state), database.transaction() as db:
            source = database.asset(db, self.paths[0], sha=database.digest(self.paths[0]), metadata={'user': 'keep'})
            derivative = self.root / 'edited.jpg'
            derivative.write_bytes(self.paths[0].read_bytes())
            child = database.asset(db, derivative, 'retouch', parent=source, sha=database.digest(derivative))
        with patch.object(similarity, 'analyze', side_effect=self.analyze):
            report = similarity.find_similar([self.images], state_dir=self.state)
            second = similarity.find_similar([self.images], state_dir=self.state)
        self.assertEqual(second.name, 'similarity-v02.html')
        with database.use_state(self.state):
            jobs = database.query_jobs(job_type='similarity')
            self.assertEqual(len(jobs), 2)
            self.assertTrue(all(j['processing_status'] == 'completed' for j in jobs))
            details = database.job_details(jobs[0]['job_id'])
            self.assertEqual(len(details['job']['metadata']['images']), 2)
            self.assertNotIn('thumbnail', details['job']['metadata']['images'][0])
            history = database.history(child)
            self.assertEqual(len([r for r in history['recipes'] if r['stage'] == 'similarity']), 2)
            with closing(database.connect()) as db:
                self.assertEqual(db.execute('SELECT metadata_json FROM assets WHERE asset_id=?', (source,)).fetchone()[0], '{"user": "keep"}')
            self.assertTrue(database.check_database(True)['database_ok'])
        self.assertTrue(report.exists())
        self.assertFalse(list(self.images.glob('*.json')))

    def test_change_during_analysis_fails_without_report(self):
        def changed(paths, hashes, threshold):
            result = fixture_result(paths, hashes)
            paths[0].write_bytes(b'changed externally')
            return result
        with patch.object(similarity, 'analyze', side_effect=changed):
            with self.assertRaisesRegex(similarity.SimilarityError, 'changed during analysis'):
                similarity.find_similar([self.images], state_dir=self.state)
        self.assertFalse((self.images / 'similarity.html').exists())
        with database.use_state(self.state):
            self.assertEqual(database.query_jobs()[0]['processing_status'], 'failed')

    def test_explicit_collision_and_concurrent_publication_never_overwrite(self):
        report = self.images / 'report.html'
        report.write_text('keep')
        with patch.object(similarity, 'analyze') as analyze:
            with self.assertRaisesRegex(similarity.SimilarityError, 'overwrite'):
                similarity.find_similar([self.images], report=report)
            analyze.assert_not_called()
        with self.assertRaises(similarity.SimilarityError):
            similarity.publish_report(report, 'replace', versioned=False)
        self.assertEqual(report.read_text(), 'keep')
        self.assertEqual(similarity.publish_report(report, 'new', versioned=True).name, 'report-v02.html')
        self.assertFalse(list(self.images.glob('*.partial')))

    def test_incomplete_native_output_is_rejected(self):
        with patch.object(similarity, 'native_rows', return_value=iter([{'type': 'complete', 'images': 2}])):
            with self.assertRaisesRegex(similarity.SimilarityError, 'Incomplete'):
                similarity.analyze(self.paths, ['a', 'b'])

    def test_html_embeds_previews_and_escapes_names_without_network(self):
        result = fixture_result(self.paths, ['a', 'b'])
        result['images'][0]['path'] = str(self.images / '<bad&name>.HEIC')
        page = render(result, self.images / 'similarity.html', 'today')
        self.assertIn('data:image/jpeg;base64,', page)
        self.assertIn('&lt;bad&amp;name&gt;.HEIC', page)
        self.assertNotIn('<bad&name>', page)
        self.assertIn('id="unmatched"', page)
        self.assertNotIn('https://', page)

    def test_ordinary_prints_reject_polaroid_edit_before_acquisition(self):
        for args in (['scan','--kind','prints','--retouch','polaroid'],['process-sheet',str(self.paths[0]),'--kind','prints','--retouch','polaroid']):
            with patch('photo_utils.cli.run_scan') as scan, patch('photo_utils.cli.process_sheet') as split:
                self.assertEqual(main(args),1)
                scan.assert_not_called();split.assert_not_called()

    def test_scan_followup_analyzes_originals_before_retouch(self):
        order = []
        with patch('photo_utils.cli.process_sheet', side_effect=lambda *a, **k: order.append('split') or self.paths), \
                patch('photo_utils.cli.find_similar', side_effect=lambda *a, **k: order.append('similar')), \
                patch('photo_utils.cli.retouch', side_effect=lambda *a, **k: order.append('retouch')):
            process_and_retouch(self.paths[0], find_similar_groups=True)
        self.assertEqual(order, ['split', 'similar', 'retouch'])

    def test_native_failure_records_failed_job(self):
        with patch.object(similarity, 'analyze', side_effect=similarity.SimilarityError('native failed')):
            with self.assertRaisesRegex(similarity.SimilarityError, 'native failed'):
                similarity.find_similar([self.images], state_dir=self.state)
        with database.use_state(self.state):
            self.assertEqual(database.query_jobs()[0]['processing_status'], 'failed')

    def test_cli_persists_multi_target_configuration(self):
        with patch.object(similarity, 'analyze', side_effect=self.analyze):
            self.assertEqual(main(['similar', *map(str, self.paths), '--state-dir', str(self.state)]), 0)
        with database.use_state(self.state):
            job = database.query_jobs(job_type='similarity')[0]
            details = database.job_details(job['job_id'])
            self.assertEqual(details['job']['settings']['cli_configuration']['targets'], list(map(str, self.paths)))


if __name__ == '__main__':
    unittest.main()
