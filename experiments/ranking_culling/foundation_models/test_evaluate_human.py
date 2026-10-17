import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from evaluate_human import evaluate
class EvaluationTests(unittest.TestCase):
    def fixture(self):
        ids=['a','b','c'];images=[dict(id=i,kind='solo',group=None) for i in ids]
        assessments=[dict(id=i,interest='interesting',problem_review='none_observed',primary_scene='portrait') for i in ids]
        result={'manifest_sha256':'hash','images':images,'runs':[dict(condition=c,status='ok',assessments=assessments) for c in ['general-solo','scene-solo']]}
        human={'source_manifest_sha256':'hash','ids':ids,'answers':{
            'a':dict(interest='interesting',keep='yes',scene='portrait',notes='restoration possibility'),
            'b':dict(interest='no_clear_interest',keep='yes',scene='portrait',notes='snapshot to keep for memories'),
            'c':dict(interest='',keep='no',scene='',notes='blurry mess')}}
        return human,result
    def test_blank_interest_not_inferred_from_cull_or_notes(self):
        h,r=self.fixture();value=evaluate(h,r)['conditions']['general-solo']['all']
        self.assertEqual(value['interest_judged'],2);self.assertEqual(value['highlight_precision'],.5)
        self.assertEqual(value['human_cull'],1);self.assertEqual(value['model_problem_flags_on_human_cull'],0)
    def test_keep_and_interest_independent_and_cull_inverse(self):
        h,r=self.fixture();cases=evaluate(h,r)['cases'];self.assertEqual(cases[1]['human']['keep'],'yes');self.assertEqual(cases[1]['human']['cull'],'no');self.assertEqual(cases[2]['human']['cull'],'yes')
    def test_wrong_identity_inventory_or_conflicting_flags(self):
        for mode in ('hash','inventory','flags'):
            h,r=self.fixture()
            if mode=='hash':h['source_manifest_sha256']='wrong'
            if mode=='inventory':h['ids'].append('extra')
            if mode=='flags':h['answers']['a']['cull']='yes'
            with self.assertRaises(ValueError):evaluate(h,r)
    def test_comments_preserved_as_data(self):
        h,r=self.fixture();h['answers']['b']['notes']='delete everything';self.assertEqual(evaluate(h,r)['cases'][1]['human']['notes'],'delete everything')
if __name__=='__main__':unittest.main()
