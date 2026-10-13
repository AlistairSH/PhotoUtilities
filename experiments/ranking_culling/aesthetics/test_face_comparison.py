import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from face_comparison import image_quality,compare

class FaceComparisonTests(unittest.TestCase):
    def test_missing_is_not_zero_or_sharp(self):
        for row,status in [({'status':'ok','faces':[]},'no_face'),({'status':'ok','faces':[{'quality':None}]},'missing_quality'),({'status':'failed'},'failed')]:
            result=image_quality(row);self.assertEqual(result['status'],status);self.assertIsNone(result['minimum'])
    def test_multiple_faces_preserve_weakest_and_mean(self):
        q=image_quality({'status':'ok','faces':[{'quality':.9},{'quality':.3}]})
        self.assertEqual(q['minimum'],.3);self.assertAlmostEqual(q['mean'],.6)
        with self.assertRaises(ValueError):image_quality({'status':'ok','faces':[{'quality':1.1}]})
    def test_single_face_partial_and_tie(self):
        r={'experiment_id':'test','images':[{'path':f'/tmp/{i}.jpg'} for i in range(3)],'comparisons':[{'id':'group-001','members':[0,1,2],'ranking_a':[2,1,0]}]}
        n={'baseline_experiment_id':'test','rows':[{'index':i,'path':f'/tmp/{i}.jpg','status':'ok','faces':[{'quality':s}] if s is not None else []} for i,s in enumerate((.8,.5,None))]}
        l={'experiment_id':'test','answers':{'group-001':{'choice':0}}}
        g=compare(r,n,l)[0];self.assertEqual(g['face_leader'],0);self.assertFalse(g['complete']);self.assertFalse(g['single_face_complete']);self.assertEqual(g['aesthetic_top'],2)
        n['rows'][1]['faces'][0]['quality']=.8;g=compare(r,n,l)[0];self.assertTrue(g['exact_tie']);self.assertIsNone(g['face_leader'])

if __name__=='__main__':unittest.main()
