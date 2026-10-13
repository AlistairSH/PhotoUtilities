import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from unittest.mock import patch
from expanded import expanded_result

class ExpansionTests(unittest.TestCase):
    def fixture(self):
        images=[{'path':f'/tmp/{i}.jpg','aesthetics':{'status':'ok','overallScore':score}} for i,score in enumerate((.5,.4,.7))]
        r={'experiment_id':'original','images':images,'groups':[{'members':[0,1],'level':'likely'}],
           'pairs':[{'a':0,'b':1,'level':'likely'},{'a':0,'b':2,'level':'unmatched'},{'a':1,'b':2,'level':'unmatched'}],
           'unmatched':[2],'focus_rows':[]}
        c={'experiment_id':'original','corrections':[{'image_index':2,'filename':'2.jpg','intended_group':'group-001'}]}
        return r,c
    def test_expansion_preserves_baseline_and_pair_evidence(self):
        r,c=self.fixture();before=copy.deepcopy(r)
        with patch('expanded.relative_focus'):
            result,affected=expanded_result(r,c)
        self.assertEqual(r,before);self.assertEqual(result['pairs'],before['pairs'])
        self.assertEqual(result['groups'][0]['members'],[0,1,2]);self.assertEqual(result['unmatched'],[])
        self.assertEqual(affected,{'group-001'});g=result['comparisons'][0]
        self.assertEqual(g['ranking_a'][0],2);self.assertTrue(g['chained']);self.assertIsNone(g['winner_a']);self.assertEqual(g['excluded'],{})
    def test_wrong_identity_rejected(self):
        r,c=self.fixture();c['corrections'][0]['filename']='different.jpg'
        with self.assertRaises(ValueError):expanded_result(r,c)
    def test_duplicate_membership_rejected(self):
        r,c=self.fixture();c['corrections']*=2
        with self.assertRaises(ValueError):expanded_result(r,c)
    def test_group_id_retained_in_subset(self):
        from experiment import rank_groups
        r,_=self.fixture();r['groups'][0]['id']='group-020'
        self.assertEqual(rank_groups(r)[0]['id'],'group-020')

if __name__=='__main__':unittest.main()

class DiagnosticTests(unittest.TestCase):
    def test_zero_agreement_and_no_labels(self):
        from expanded import diagnose
        from experiment import rank_groups
        r={'experiment_id':'test','images':[{'path':f'/tmp/{i}.jpg','aesthetics':{'overallScore':score,'status':'ok','orientation':1,'isUtility':False}} for i,score in enumerate((.8,.4))],
           'groups':[{'members':[0,1],'level':'likely'}],'pairs':[{'a':0,'b':1,'level':'likely'}]}
        r['comparisons']=rank_groups(r)
        d=diagnose(r,{'experiment_id':'test','answers':{'group-001':{'choice':1}}},set())
        self.assertEqual(d['top1_hits'],0);self.assertIsNone(d['median_gap_matches']);self.assertEqual(d['top2_hits'],1)
        d=diagnose(r,{'experiment_id':'test','answers':{}},set())
        self.assertIsNone(d['uniform_random_expected_top1']);self.assertIsNone(d['median_gap_misses'])
