import unittest

import cv2
import numpy as np

from quality import focus_fields,metrics
from region_focus import analyze_regions,masked_metrics


def detectors(box):
    return {name:{'status':'ok','regions':[{'box':box}] if name=='faces' else []}
            for name in ('faces','people','animals','attention','objectness')}


class RegionFocusTests(unittest.TestCase):
    def test_soft_subject_with_sharp_surroundings(self):
        rng=np.random.default_rng(6)
        image=rng.integers(0,256,(512,512,3),dtype=np.uint8)
        image[128:384,128:384]=cv2.GaussianBlur(image[128:384,128:384],(0,0),5)
        row=analyze_regions(image,detectors([.25,.25,.5,.5]))['regions'][0]
        self.assertLess(row['smoothed']['region_to_outside']['tenengrad'],.2)
        self.assertLess(row['smoothed']['region_to_outside']['laplacian_variance'],.2)

    def test_no_mask_boundary_edges(self):
        fields=focus_fields(np.full((100,100),100,np.uint8))
        mask=np.zeros((100,100),np.uint8);mask[20:80,20:80]=1
        measured=masked_metrics(fields,mask)
        self.assertEqual(measured['laplacian_variance'],0)
        self.assertEqual(measured['tenengrad'],0)

    def test_no_outside_when_region_fills_frame(self):
        row=analyze_regions(np.full((100,100,3),128,np.uint8),detectors([0,0,1,1]))['regions'][0]
        self.assertIsNone(row['smoothed']['outside'])
        self.assertEqual(row['smoothed']['region_to_outside'],{})

    def test_small_region_remains_visible_but_unmeasured(self):
        row=analyze_regions(np.zeros((100,100,3),np.uint8),detectors([.1,.1,.1,.1]))['regions'][0]
        self.assertFalse(row['usable'])
        self.assertIsNone(row['raw'])

    def test_shared_metric_values_preserved(self):
        gray=np.random.default_rng(42).integers(0,256,(50,50),dtype=np.uint8)
        value=gray.astype(np.float64)/255
        self.assertEqual(metrics(gray)['laplacian_variance'],float(cv2.Laplacian(value,cv2.CV_64F).var()))
        self.assertEqual(metrics(gray)['tenengrad'],float(np.mean(cv2.Sobel(value,cv2.CV_64F,1,0,ksize=3)**2+cv2.Sobel(value,cv2.CV_64F,0,1,ksize=3)**2)))


if __name__=='__main__':unittest.main()
