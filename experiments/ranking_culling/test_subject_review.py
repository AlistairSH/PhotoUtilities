import copy
import unittest

from subject_review import subject_evidence,screen


def row(kind='faces',lap=.4,ten=.5,box=None):
    return {'focus':{'regions':[{'id':kind+' 1','box':box or [.2,.2,.3,.3],'usable':True,
        'smoothed':{'outside':{'pixels':1000},'region_to_outside':{'laplacian_variance':lap,'tenengrad':ten}}}]}}


class SubjectReviewTests(unittest.TestCase):
    def test_both_metrics_both_scales_required(self):
        self.assertEqual(len(subject_evidence(row(),row())),1)
        self.assertEqual(subject_evidence(row(),row(lap=1.2)),[])
        self.assertEqual(subject_evidence(row(ten=1.2),row()),[])

    def test_attention_only_can_trigger(self):
        self.assertEqual(len(subject_evidence(row('attention'),row('attention'))),1)

    def test_attention_does_not_trigger_when_another_region_exists(self):
        small=row('attention');small['focus']['regions'].extend(row('faces',lap=2,ten=2)['focus']['regions'])
        self.assertEqual(subject_evidence(small,copy.deepcopy(small)),[])

    def test_different_regions_cannot_be_paired(self):
        self.assertEqual(subject_evidence(row(),row(box=[.7,.7,.2,.2])),[])

    def test_other_subjects_are_retained(self):
        small=row('people');small['focus']['regions'].extend(row('animals')['focus']['regions'])
        large=copy.deepcopy(small)
        self.assertEqual([c['region'] for c in subject_evidence(small,large)],['people 1','animals 1'])

    def test_missing_background_produces_no_flag(self):
        small=row();small['focus']['regions'][0]['smoothed']['outside']=None
        self.assertEqual(subject_evidence(small,row()),[])

    def test_whole_review_keeps_uncertainty_without_severe_verdict(self):
        rows=[]
        for scale in (1024,2048):
            r=row();r.update(path='/tmp/image.jpg',max_dimension=scale)
            r['focus'].update(global_values={})
            r['focus']['global']={'smoothed':{'laplacian_variance':1.,'tenengrad':1.}}
            r['focus']['tile_tenengrad']=[1.]
            rows.append(r)
        decision=screen(rows)[0]
        self.assertTrue(decision['review_suggestion'])
        self.assertFalse(decision['severe_blur_candidate'])
        self.assertFalse(decision['global_low_detail'])
        for r in rows:r['focus']['regions']=[]
        self.assertEqual(screen(rows)[0]['category'],'unassessed')


if __name__=='__main__':unittest.main()
