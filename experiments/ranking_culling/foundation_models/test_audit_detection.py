import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from audit_detection import audit
class AuditTests(unittest.TestCase):
    def fixture(self):
        h={'source_manifest_sha256':'hash','ids':['a'],'answers':{'a':{'scene':'portrait','interest':'','keep':'yes','notes':''}}}
        r={'manifest_sha256':'hash','images':[{'id':'a','kind':'solo','group':None,'path':'/example/a.jpg'}],'runs':[]}
        rows=[]
        for size in (1024,2048):rows.append({'id':'a','path':'/example/a.jpg','max_dimension':size,'status':'ok','requests':{name:{'status':'ok','observations':[{}]} for name in ('face_quality','landmarks','people')}})
        return h,r,{'rows':rows}
    def test_failures_not_counted_as_zero_faces(self):
        h,r,v=self.fixture();v['rows'][0]['requests']['face_quality']={'status':'failed'};value=audit(h,r,v)['groups']['portrait']['sizes']['1024'];self.assertEqual(value['valid'],0);self.assertEqual(value['below_count'],[])
    def test_one_face_insufficient_for_group_portrait(self):
        h,r,v=self.fixture();h['answers']['a']['scene']='group_portrait';self.assertEqual(audit(h,r,v)['groups']['group_portrait']['sizes']['2048']['meets_count'],0)
    def test_wrong_detection_path_rejected(self):
        h,r,v=self.fixture();v['rows'][0]['path']='/other.jpg'
        with self.assertRaises(ValueError):audit(h,r,v)
if __name__=='__main__':unittest.main()
