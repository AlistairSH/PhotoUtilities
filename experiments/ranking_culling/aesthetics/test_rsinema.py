import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from rsinema import compare,validate_values,render

class RsinemaTests(unittest.TestCase):
    def fixture(self):
        b={'experiment_id':'test','images':[{'path':f'/tmp/{i}.jpg','aesthetics':{'preview':''}} for i in range(3)],
           'comparisons':[{'id':'group-017','members':[0,1,2],'ranking_a':[0,2,1],'weak':False,'chained':False}]}
        s=[{'index':i,'path':f'/tmp/{i}.jpg','status':'ok','values':[v]*7,'crop_preview':''} for i,v in enumerate((3.,4.,2.))]
        l={'experiment_id':'test','answers':{'group-017':{'choice':1}}};p={'groups':[{'group':'group-017','raw_top':1}]}
        return b,s,l,p
    def test_shared_pick_dedup_and_fixed_axes(self):
        b,s,l,p=self.fixture();g=compare(b,s,l,p)[0]
        self.assertEqual(len(g['picks']),2);self.assertEqual(g['picks'][0]['roles'],['Human','Schuhmann'])
        self.assertEqual(g['overall_top'],1);self.assertEqual(g['apple_order'],[0,2,1]);self.assertEqual(len(g['rankings']),7)
    def test_invalid_values_and_identity(self):
        for values in ([0.]*6,[0.]*6+[float('nan')]):
            with self.assertRaises(ValueError):validate_values(values)
        b,s,l,p=self.fixture();s[1]['path']='/tmp/wrong.jpg'
        with self.assertRaises(ValueError):compare(b,s,l,p)
    def test_missing_and_undecided_not_invented(self):
        b,s,l,p=self.fixture();l['answers']['group-017']['choice']='none';s[1]={'index':1,'path':'/tmp/1.jpg','status':'missing'}
        g=compare(b,s,l,p)[0];self.assertEqual(g['human'],'none');self.assertTrue(g['partial']);self.assertNotIn(1,g['rankings'][0])
        self.assertEqual(g['picks'],[{'index':0,'roles':['Apple']}])
    def test_html_is_optional_chart_and_escapes_name(self):
        b,s,l,p=self.fixture();b['images'][0]['path']='/tmp/<bad>.jpg';s[0]['path']=b['images'][0]['path']
        document=render(b,s,compare(b,s,l,p),{}, {'group-017':''})
        self.assertIn('&lt;bad&gt;.jpg',document);self.assertIn('<details><summary>Show radar chart',document)
        self.assertNotIn('fetch(',document)

if __name__=='__main__':unittest.main()
