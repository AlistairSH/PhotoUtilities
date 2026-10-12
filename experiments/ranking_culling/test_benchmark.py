import unittest
import numpy as np
from pathlib import Path
from unittest.mock import patch

from benchmark import expectation,report
from region_focus import analyze_regions


class BenchmarkTests(unittest.TestCase):
    def test_background_blur_is_not_a_focus_miss_label(self):
        self.assertEqual(expectation('Background out window is out of focus'),'no_explicit_focus_miss')
        self.assertEqual(expectation('Portrait with subject out of focus and background in focus'),'subject_focus_miss')
        self.assertEqual(expectation('Street, focus miss across image'),'whole_image_focus_miss')
        self.assertEqual(expectation('Polaroid softness'),'natural_softness')
        self.assertEqual(expectation(''),'unlabeled')
        self.assertEqual(expectation('Dog and person, entire completely out of focus'),'whole_image_focus_miss')

    def test_filters_preserve_measurement_schema(self):
        rgb=np.random.default_rng(5).integers(0,256,(100,100,3),dtype=np.uint8)
        detectors={k:{'regions':[]} for k in ('faces','people','animals','objectness','attention')}
        values={t:analyze_regions(rgb,detectors,t) for t in ('raw','gaussian1','gaussian2','bilateral')}
        for row in values.values():
            self.assertEqual(len(row['tile_tenengrad']),16)
            self.assertTrue(np.isfinite(row['global']['smoothed']['tenengrad']))
        self.assertEqual(values['raw']['global']['smoothed'],values['raw']['global']['raw'])
        self.assertLess(values['gaussian2']['global']['smoothed']['laplacian_variance'],values['raw']['global']['smoothed']['laplacian_variance'])

    def test_unlabeled_two_treatment_report(self):
        sample={'path':'/tmp/photo.jpg','filename':'photo.jpg','material':'unconfirmed','color':'','notes':'','reference':'unlabeled'}
        decision={'review_suggestion':False,'subject_cues':[],'global_low_detail':False}
        results={sample['path']:{t:decision for t in ('raw','gaussian1')}}
        summaries={t:{'unlabeled':1} for t in ('raw','gaussian1')}
        preview={'width':100,'height':100,'thumbnail':'','detectors':{k:{'regions':[]} for k in ('faces','people','animals','objectness')}}
        with patch('benchmark.TREATMENTS',['raw','gaussian1']):
            page=report([sample],results,summaries,{sample['path']:preview},Path('/tmp/report'))
        self.assertIn('Awaiting labels',page)
        self.assertIn('No review trigger',page)
        self.assertIn('Whole-frame low-detail trigger',page)
        self.assertNotIn('bilateral',page.lower())


if __name__=='__main__':unittest.main()
