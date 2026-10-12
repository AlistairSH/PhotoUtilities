import unittest
import numpy as np
from patch_experiment import connected_sharp,combine,measure,primary_ids,select_subjects

class PatchTests(unittest.TestCase):
    def test_connected_not_isolated(self):
        def cells(points):return [{'cell':p,'sharp':True} for p in points]
        self.assertFalse(connected_sharp(cells([(0,0),(2,2),(4,4)])))
        self.assertTrue(connected_sharp(cells([(0,0),(0,1),(1,1)])))

    def test_veto_preserves_subject_miss_and_fallback(self):
        self.assertTrue(combine(True,True,False,True))
        self.assertTrue(combine(False,False,True,True))
        self.assertFalse(combine(False,True,False,True))

    def test_blank_subject_cannot_clear(self):
        for norm in [False,True]:
            r=measure(np.full((300,300),128,np.uint8),[.1,.1,.8,.8],'faces',norm)
            self.assertFalse(r['sharp']);self.assertFalse(r['supported'])

    def test_face_replaces_body_and_primary_keeps_large_co_subject(self):
        detectors={k:{'regions':[]} for k in ['faces','people','animals','objectness','attention']}
        detectors['faces']['regions']=[{'box':[.2,.2,.2,.2]},{'box':[.7,.2,.02,.02]}]
        detectors['people']['regions']=[{'box':[.1,.1,.4,.8]}]
        r=select_subjects(detectors)
        self.assertEqual([s['kind'] for s in r],['faces','faces'])
        self.assertEqual(primary_ids(r),{'faces 1'})
        r.append({'id':'animals 1','kind':'animals','box':[.1,.7,.04,.04]})
        self.assertIn('animals 1',primary_ids(r))

if __name__=='__main__':unittest.main()
