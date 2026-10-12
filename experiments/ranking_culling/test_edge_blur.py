import unittest
import cv2
import numpy as np
from edge_blur import extract,summarize,flags
from edge_experiment import add_region_evidence


class EdgeTests(unittest.TestCase):
    def pattern(self):
        y,x=np.mgrid[:384,:384]
        return (((x//64+y//64)%2)*255).astype(np.uint8)

    def test_defocus_widens_edges(self):
        image=self.pattern();sharp=summarize(extract(image))
        blurred=summarize(extract(cv2.GaussianBlur(image,(0,0),3)))
        self.assertTrue(sharp['sufficient']);self.assertTrue(blurred['sufficient'])
        self.assertGreater(blurred['median_width'],sharp['median_width'])
        self.assertFalse(flags(sharp)['edge_width']);self.assertTrue(flags(blurred)['edge_width'])

    def test_directional_motion(self):
        image=self.pattern();kernel=np.ones((1,13),np.float32)/13
        moved=cv2.filter2D(image,-1,kernel)
        measured=summarize(extract(moved))
        self.assertTrue(flags(measured)['directional'])

    def test_flat_field_is_insufficient_not_sharp(self):
        measured=summarize(extract(np.full((200,200),100,np.uint8)))
        self.assertFalse(measured['sufficient']);self.assertFalse(any(flags(measured).values()))

    def test_contrast_scaling_preserves_width(self):
        image=self.pattern();reduced=(image.astype(float)*.5+50).astype(np.uint8)
        full=summarize(extract(image));dim=summarize(extract(reduced))
        self.assertAlmostEqual(full['median_width'],dim['median_width'],places=2)

    def test_region_probe_requires_sample_support(self):
        metric={'sufficient':True,'edges':73,'median_width':4.25,'contrast_soft_fraction':.7,
                'direction_ratio':1.1,'direction_wide_width':4.25}
        rows=[{'scale':1024,'regions':[{'id':'objectness 1','metrics':metric}]}]
        decision={'combined_review':False}
        self.assertTrue(add_region_evidence(decision,rows)['combined_region_review'])
        metric['sufficient']=False;metric['edges']=41
        self.assertFalse(add_region_evidence(decision,rows)['combined_region_review'])


if __name__=='__main__':unittest.main()
