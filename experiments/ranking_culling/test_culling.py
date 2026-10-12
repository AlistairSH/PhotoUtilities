import copy
import unittest

from culling import screen


def analysis(value, peak=None):
    return {'subject':'unknown', 'scales':{scale:{
        'global':{'smoothed':{'laplacian_variance':value,'tenengrad':value}},
        'tile_tenengrad':[value if peak is None else peak]} for scale in ('1024','512')}}


class CullingTests(unittest.TestCase):
    def test_low_detail_is_review_only(self):
        decisions, rules = screen([analysis(i) for i in range(30)])
        self.assertEqual([i for i,d in enumerate(decisions) if d['review_shortlist']],[0,1,2])
        self.assertTrue(all(not d['severe_blur_candidate'] for d in decisions))
        self.assertIsNone(rules['severe_blur_threshold'])
        self.assertEqual(decisions[-1]['category'],'unassessed')

    def test_sharp_local_region_prevents_shortlisting(self):
        rows = [analysis(i) for i in range(30)]
        rows[0] = analysis(0,100)
        decisions,_ = screen(rows)
        self.assertFalse(decisions[0]['review_shortlist'])
        self.assertTrue(decisions[0]['stronger_region_retained'])

    def test_constant_low_texture_does_not_force_a_quota(self):
        decisions,_ = screen([analysis(0) for _ in range(30)])
        self.assertFalse(any(d['review_shortlist'] for d in decisions))

    def test_small_batch_is_not_screened(self):
        decisions,_ = screen([analysis(i) for i in range(10)])
        self.assertFalse(any(d['review_shortlist'] for d in decisions))

    def test_disagreement_at_one_scale_prevents_shortlisting(self):
        rows = [analysis(i) for i in range(30)]
        rows[0]['scales']['512']['global']['smoothed']['laplacian_variance']=100
        decisions,_ = screen(rows)
        self.assertFalse(decisions[0]['review_shortlist'])

    def test_no_face_detection_dependency_or_mutation(self):
        rows = [analysis(i) for i in range(30)]
        original=copy.deepcopy(rows)
        first,_=screen(rows)
        self.assertEqual(rows,original)
        for row in rows:
            row['subject']='faces'
        second,_=screen(rows)
        self.assertEqual([d['review_shortlist'] for d in first],[d['review_shortlist'] for d in second])

    def test_invalid_measurements_fail(self):
        for value in (float('nan'),float('inf'),-1):
            with self.assertRaises(ValueError):
                screen([analysis(value) for _ in range(30)])


if __name__ == '__main__':
    unittest.main()
