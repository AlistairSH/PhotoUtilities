import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from fm_run import validate
class ProtocolTests(unittest.TestCase):
    def row(self,id='a'):
        return dict(id=id,interest='interesting',problem_review='possible_problem',primary_scene='portrait',interest_reason='moment',problem_reason='soft subject',uncertainty='detail limited',secondary_tags=['low light'])
    def test_compelling_and_problem_can_coexist(self):
        self.assertEqual(validate({'images':[self.row()]},['a'])[0]['interest'],'interesting')
    def test_wrong_duplicate_and_missing_ids(self):
        for value,ids in [({'images':[self.row('b')]},['a']),({'images':[self.row(),self.row()]},['a','b']),({'images':[]},['a'])]:
            with self.assertRaises(ValueError):validate(value,ids)
    def test_unknown_vocabulary(self):
        for field in ('interest','problem_review','primary_scene'):
            row=self.row();row[field]='invented'
            with self.assertRaises(ValueError):validate({'images':[row]},['a'])
    def test_tags_and_explanations(self):
        for field,value in [('secondary_tags',['a']*5),('secondary_tags',[1]),('uncertainty',None)]:
            row=self.row();row[field]=value
            with self.assertRaises(ValueError):validate({'images':[row]},['a'])
    def test_order_can_reverse_with_correct_mapping(self):
        self.assertEqual(len(validate({'images':[self.row('b'),self.row('a')]},['a','b'])),2)
class ReportTests(unittest.TestCase):
    def test_scene_context_uses_scene_baseline(self):
        from report import summary
        a=ProtocolTests().row()
        b=dict(a,interest='maybe')
        result={'images':[{'id':'a','kind':'solo'}], 'runs':[
            {'condition':'general-solo','assessments':[a],'status':'ok','seconds':1},
            {'condition':'scene-solo','assessments':[b],'status':'ok','seconds':1},
            {'condition':'scene-group-g','assessments':[b],'status':'ok','seconds':1}],
            'seconds':3,'peak_child_rss_bytes':0}
        value=summary(result)
        self.assertEqual(value['context_changes'],[])
        self.assertEqual(value['general_vs_scene']['interest_changes'],1)
    def test_failed_calls_do_not_create_neutral_labels(self):
        from report import summary
        result={'images':[{'id':'a','kind':'solo'}], 'runs':[{'condition':'general-solo','status':'failed'}],'seconds':1,'peak_child_rss_bytes':0}
        value=summary(result)
        self.assertEqual(value['general-solo/solo']['n'],0)
        self.assertEqual(value['performance']['failed_calls'],1)
if __name__=='__main__':unittest.main()
