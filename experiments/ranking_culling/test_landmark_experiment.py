import unittest
from landmark_experiment import feature_box,sharp_eyes

class LandmarkTest(unittest.TestCase):
    def test_padding_clips_without_resizing(self):
        self.assertIsNone(feature_box([[0,0]], [0,0,1,1]))
        b=feature_box([[0,0],[.1,0],[.1,.1]],[0,0,1,1])
        self.assertEqual(b,[0.,0.,.125,.125])

    def test_sparse_or_blurred_co_primary_prevents_veto(self):
        good={'features':{eye:{'edges':20,'median_width':2.8,'contrast_soft_fraction':.3} for eye in ('leftEye','rightEye')}}
        self.assertTrue(sharp_eyes([good]))
        self.assertFalse(sharp_eyes([]))
        self.assertFalse(sharp_eyes([good,{'features':{}}]))
        bad={'features':{eye:{'edges':100,'median_width':6,'contrast_soft_fraction':.8} for eye in ('leftEye','rightEye')}}
        self.assertFalse(sharp_eyes([good,bad]))
        self.assertFalse(sharp_eyes([{'features':{'leftEye':good['features']['leftEye']}}]))

if __name__=='__main__':unittest.main()
