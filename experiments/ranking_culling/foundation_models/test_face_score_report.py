import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from face_score_report import maximum_score,rank_group
class RawFaceTests(unittest.TestCase):
    def test_highest_raw_face_selected(self):
        value=maximum_score({'status':'ok','observations':[{'quality':.2},{'quality':.8}]});self.assertEqual(value['score'],.8);self.assertEqual(value['scores'],[.2,.8])
    def test_absent_or_failed_not_zero(self):
        for request in [{'status':'failed'},{'status':'ok','observations':[]},{'status':'ok','observations':[{'quality':None}]}]:self.assertIsNone(maximum_score(request)['score'])
    def test_invalid_scores_rejected(self):
        for score in [True,float('nan'),1.1,-.1]:
            with self.assertRaises(ValueError):maximum_score({'status':'ok','observations':[{'quality':score}]})
    def test_descending_ties_stable_unscored_retained(self):
        images=[{'id':id,'capture':{'score':score}} for id,score in [('a',.5),('b',None),('c',.8),('d',.5)]]
        self.assertEqual([r['id'] for r in rank_group(images)],['c','a','d','b'])
if __name__=='__main__':unittest.main()
