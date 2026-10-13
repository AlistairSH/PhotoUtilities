import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from schuhmann import comparisons,report

class SchuhmannTests(unittest.TestCase):
    def fixture(self):
        baseline={'experiment_id':'sample','images':[{'path':f'/tmp/{i}.jpg','aesthetics':{'preview':'','overallScore':.5}} for i in range(3)],
          'comparisons':[{'id':'group-016','members':[0,1,2],'ranking_a':[0,1,2],'weak':False,'chained':False}]}
        scores=[{'index':i,'path':f'/tmp/{i}.jpg','score':s,'crop_preview':''} for i,s in enumerate((4.,6.,5.))]
        labels={'experiment_id':'sample','answers':{'group-016':{'choice':2,'blind_choice':1}}}
        return baseline,scores,labels
    def test_native_scale_and_blind_choice_preserved(self):
        b,s,l=self.fixture();g=comparisons(b,s,l)[0]
        self.assertEqual(g['ranking'],[1,2,0]);self.assertEqual(g['gap'],1.)
        self.assertTrue(g['schuhmann_agrees']);self.assertFalse(g['apple_agrees'])
    def test_weak_and_tie_withhold_only_suggestion(self):
        b,s,l=self.fixture();b['comparisons'][0]['weak']=True
        g=comparisons(b,s,l)[0];self.assertEqual(g['raw_top'],1);self.assertIsNone(g['suggested_leader'])
        b['comparisons'][0]['weak']=False;s[2]['score']=6.;g=comparisons(b,s,l)[0]
        self.assertTrue(g['exact_tie']);self.assertIsNone(g['suggested_leader'])
    def test_invalid_identity_and_nonfinite_rejected(self):
        b,s,l=self.fixture();s[0]['score']=float('nan')
        with self.assertRaises(ValueError):comparisons(b,s,l)
        b,s,l=self.fixture();s[0]['path']='/tmp/other.jpg'
        with self.assertRaises(ValueError):comparisons(b,s,l)
        b,s,l=self.fixture();l['experiment_id']='wrong'
        with self.assertRaises(ValueError):comparisons(b,s,l)
    def test_crop_inspection_and_html_escape(self):
        b,s,l=self.fixture();b['images'][1]['path']='/tmp/<script>.jpg';s[1]['path']=b['images'][1]['path']
        document=report(b,s,comparisons(b,s,l),{})
        self.assertIn('&lt;script&gt;.jpg',document);self.assertIn('Actual 224×224 model view',document)
        self.assertNotIn('fetch(',document)

if __name__=='__main__':unittest.main()

class MissingSchuhmannTests(unittest.TestCase):
    def test_missing_inputs_never_rank_as_low_scores(self):
        b,s,l=SchuhmannTests().fixture()
        s[0].update({'status':'missing','score':None});g=comparisons(b,s,l)[0]
        self.assertNotIn(0,g['ranking']);self.assertIsNone(g['suggested_leader'])
        for row in s:row.update({'status':'missing','score':None})
        g=comparisons(b,s,l)[0];self.assertEqual(g['ranking'],[]);self.assertIsNone(g['raw_top'])
        self.assertIn('Original files unavailable',report(b,s,[g],{}))
