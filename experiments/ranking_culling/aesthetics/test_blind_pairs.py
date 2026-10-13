import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from blind_pairs import prepare,render,evaluate

class BlindTests(unittest.TestCase):
    def test_key_separated_and_only_disagreements(self):
        r={'experiment_id':'original','images':[{'path':f'/private/photo-{i}.jpg','sha256':str(i),'aesthetics':{'preview':''}} for i in range(6)],
           'comparisons':[{'id':'group-'+str(i),'members':[2*i,2*i+1],'ranking_a':[2*i,2*i+1]} for i in range(3)]}
        labels={'experiment_id':'original','answers':{'group-0':{'choice':1},'group-1':{'choice':2},'group-2':{'choice':'none'}}}
        public,key=prepare(r,labels);self.assertEqual(len(public['pairs']),1)
        document=render(public)
        for secret in ('photo-0.jpg','photo-1.jpg','source_group','"origin"','group-0'):
            self.assertNotIn(secret,document)
        slots=key['pairs']['pair-01']['slots']
        human=next(k for k,v in slots.items() if v['origin']=='human')
        result=evaluate(key,{'experiment_id':public['experiment_id'],'answers':{'pair-01':{'choice':human}}})
        self.assertEqual(result['prior_choice_consistency'],1)
        with self.assertRaises(ValueError):evaluate(key,{'experiment_id':'original','answers':{}})
        self.assertNotEqual(public['experiment_id'],'original')

if __name__=='__main__':unittest.main()
