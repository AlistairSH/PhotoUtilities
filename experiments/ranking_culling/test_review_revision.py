import unittest
from review_revision import revise


def region(name,ratio,box):
    return {'id':name,'usable':True,'box':box,'smoothed':{'outside':{'pixels':1000},'region_to_outside':{'laplacian_variance':ratio,'tenengrad':ratio}}}


def decision(cues=None,global_low=False):
    return {'subject_cues':cues or [],'global_low_detail':global_low,'review_suggestion':bool(cues) or global_low,'severe_blur_candidate':False}


class RevisionTests(unittest.TestCase):
    def test_attention_only_fallback(self):
        row={'focus':{'regions':[region('attention 1',.5,[.1,.1,.7,.7])]}}
        self.assertTrue(revise(decision(),row,row)['review_suggestion'])

    def test_sharp_face_suppresses_broad_objectness_only(self):
        row={'focus':{'regions':[region('faces 1',2,[.2,.2,.1,.1]),region('objectness 1',.7,[0,0,.9,.9])]}}
        cues=[{'region':'objectness 1','box':[0,0,.9,.9],'reason':'test'}]
        self.assertFalse(revise(decision(cues),row,row)['review_suggestion'])
        self.assertTrue(revise(decision(cues,True),row,row)['review_suggestion'])

    def test_separate_subject_is_not_cleared_by_sharp_face(self):
        row={'focus':{'regions':[region('faces 1',2,[.2,.2,.1,.1])]}}
        cues=[{'region':'animals 1','box':[.7,.7,.1,.1],'reason':'test'}]
        self.assertTrue(revise(decision(cues),row,row)['review_suggestion'])


if __name__=='__main__':unittest.main()
