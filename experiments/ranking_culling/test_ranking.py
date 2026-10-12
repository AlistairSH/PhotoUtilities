from pathlib import Path
import unittest

import cv2
import numpy as np

from quality import measure, metrics
from ranking import rank_group
from run import make_report


class FocusTests(unittest.TestCase):
    def test_blur_reduces_both_metrics(self):
        rng = np.random.default_rng(42)
        sharp = (rng.random((256,256))*255).astype(np.uint8)
        blur = cv2.GaussianBlur(sharp, (0,0), 3)
        for metric in ('laplacian_variance', 'tenengrad'):
            self.assertGreater(metrics(sharp)[metric], metrics(blur)[metric])

    def test_noise_inflates_raw_laplacian(self):
        rng = np.random.default_rng(42)
        smooth = np.full((256,256), 128, np.uint8)
        noisy = np.clip(smooth.astype(float)+rng.normal(0,10,smooth.shape),0,255).astype(np.uint8)
        self.assertGreater(metrics(noisy)['laplacian_variance'], metrics(smooth)['laplacian_variance'])
        self.assertLess(metrics(cv2.GaussianBlur(noisy,(0,0),1))['laplacian_variance'], metrics(noisy)['laplacian_variance'])

    def test_face_focus_overrides_sharp_background(self):
        rng = np.random.default_rng(5)
        image = rng.integers(0,256,(512,512,3),dtype=np.uint8)
        a, b = image.copy(), cv2.GaussianBlur(image,(0,0),3)
        a[128:384,128:384] = cv2.GaussianBlur(image[128:384,128:384],(0,0),5)
        b[128:384,128:384] = image[128:384,128:384]
        faces = [{'box':[.25,.25,.5,.5],'detection_confidence':1.}]
        analyses = [measure(a,faces),measure(b,faces)]
        ranked = rank_group([0,1],analyses)
        self.assertEqual(ranked['basis'],'faces')
        self.assertEqual(ranked['suggested'],1)

    def test_missing_faces_force_uncertain_global_fallback(self):
        image = np.full((128,128,3),128,np.uint8)
        faces = [{'box':[.25,.25,.5,.5],'detection_confidence':1.}]
        ranked = rank_group([0,1],[measure(image,faces),measure(image,[])])
        self.assertEqual(ranked['basis'],'global')
        self.assertTrue(ranked['uncertain'])
        self.assertTrue(ranked['near_tie'])

    def test_tiny_faces_are_not_measured(self):
        image = np.zeros((256,256,3),np.uint8)
        analysis = measure(image,[{'box':[.1,.1,.01,.01],'detection_confidence':1.}])
        self.assertEqual(analysis['subject'],'unknown')
        self.assertFalse(analysis['scales']['1024']['faces'][0]['usable'])

    def test_report_preserves_group_evidence_and_unmatched(self):
        image = np.full((128,128,3),128,np.uint8)
        analyses = [measure(image,[]) for _ in range(3)]
        result = {'images':[{'path':f'/tmp/source/a&{i}.jpg','thumbnail':''} for i in range(3)],
                  'groups':[{'members':[1,0],'level':'potential'}], 'unmatched':[2],
                  'pairs':[{'a':0,'b':1,'level':'potential'}], 'created_at':'test'}
        document, ranked = make_report(result,analyses,Path('/tmp/report/ranking.html'))
        self.assertEqual(result['groups'][0]['members'],[1,0])
        self.assertEqual(ranked[0]['members'],[1,0])
        self.assertIn('Potential matches',document)
        self.assertIn('a&amp;2.jpg',document)
        self.assertIn('UNCERTAIN',document)
        self.assertEqual(document.count('<figure>'),3)


if __name__ == '__main__':
    unittest.main()
