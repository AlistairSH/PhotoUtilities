import unittest
from run import below_fraction,proposal

class OrientationGeometryTests(unittest.TestCase):
    def test_union_is_not_box_count_and_overlap_is_not_double_counted(self):
        line={'slope':0,'intercept':50}
        self.assertEqual(below_fraction([[0,.5,1,.5]],line,100,100),1)
        self.assertEqual(below_fraction([[0,.5,1,.5]]*3,line,100,100),1)
        self.assertEqual(below_fraction([[0,0,1,1]],line,100,100),.5)
        self.assertEqual(below_fraction([[0,0,1,.5]],line,100,100),0)

    def test_missing_and_tiny_regions_are_unknown(self):
        self.assertIsNone(below_fraction([],{'slope':0,'intercept':50},100,100))
        self.assertIsNone(below_fraction([[0,.5,.01,.01]],{'slope':0,'intercept':50},100,100))
        self.assertIsNone(below_fraction([[0,0,1,1]],None,100,100))

    def test_no_forced_orientation_for_ties_or_one_candidate(self):
        rows=[{'q':q,'scores':{'objects':.8},'horizon':{'confidence':1}} for q in (0,2)]
        self.assertIsNone(proposal(rows,'objects')['q'])
        self.assertIsNone(proposal(rows[:1],'objects')['q'])
        rows[1]['scores']['objects']=.2
        self.assertEqual(proposal(rows,'objects')['q'],0)
        rows[0]['horizon']['confidence']=.1
        self.assertIsNone(proposal(rows,'objects')['q'])

if __name__=='__main__':unittest.main()
