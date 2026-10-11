import json
import tempfile
import unittest
from pathlib import Path

from report import render


class ReportTests(unittest.TestCase):
    def test_labels_array_is_not_a_dataset_and_labels_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            images = [{'path': str(folder/'a.jpg')}, {'path': str(folder/'b.jpg')}]
            pair = {'a': 0, 'b': 1, 'vision_distance': .55, 'opencv_thumbnail_rmse': .1,
                    'phash_hamming': 4, 'dhash_hamming': 7, 'inliers': 20,
                    'mutual_matches': 22, 'inlier_fraction': 20/22,
                    'coverage_a': .2, 'coverage_b': .3, 'sift_strength': 3.6,
                    'sift_candidate': True, 'status': 'geometry-estimated'}
            data = {'analyzer': 'hash-sift-spike-v1', 'images': images, 'pairs': [pair],
                    'seconds': {'hash_extraction': .01, 'sift_extraction': .02, 'pair_comparison': .03}}
            (folder/'fixture.json').write_text(json.dumps(data))
            labels = [{'dataset': 'fixture', 'a': 0, 'b': 1, 'label': 'basically_same', 'source': 'test'}]
            (folder/'labels.json').write_text(json.dumps(labels))
            render(folder, labels)
            report = (folder/'FINDINGS.md').read_text()
            self.assertIn('| vision_045 | 0/1 | 0/0 |', report)
            self.assertIn('| sift | 1/1 | 0/0 |', report)
            self.assertIn('| vision_045_or_sift | 1/1 | 0/0 |', report)
            self.assertIn('basically_same', (folder/'fixture-review.html').read_text())
            with self.assertRaises(FileExistsError):
                render(folder, labels)


if __name__ == '__main__':
    unittest.main()
