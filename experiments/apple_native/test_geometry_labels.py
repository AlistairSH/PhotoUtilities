"""Reject mislabeled provenance and preserve explicit unjudged states."""
import copy
import hashlib
import json
from label_geometry import bind_labels


def main():
    def control(case, baseline, vision):
        return {'case':case,'mode':'register-canvas','label':'unjudged',
                'baseline_pair':{'baseline_level':baseline,'vision_only_level':vision},
                'sift':{'sift_candidate':True},'evidence':{'confidence':1},'diagnostics':{}}
    data=json.dumps({'rows':[control('a','potential','unmatched'),control('b','unmatched','unmatched')]}).encode()
    labels={'binding':{'summary_sha256':hashlib.sha256(data).hexdigest()},
            'rows':[{'case':'a','label':'related'},{'case':'b','label':'uncertain'}]}
    r=bind_labels(data,labels)
    assert r['judged_pairs']==1 and r['accepted_agrees']==1 and r['vision_only_agrees']==0
    assert r['human_confirmed_sift_only']==['a']
    assert r['rows'][1]['accepted_agrees'] is None
    unjudged=copy.deepcopy(labels)
    unjudged['rows'][0]['label']='unjudged'
    assert bind_labels(data,unjudged)['judged_pairs']==0
    bad=[]
    x=copy.deepcopy(labels); x['binding']['summary_sha256']='wrong';bad.append(x)
    x=copy.deepcopy(labels); x['rows'].append(x['rows'][0]);bad.append(x)
    x=copy.deepcopy(labels); x['rows'][0]['case']='unknown';bad.append(x)
    x=copy.deepcopy(labels); x['rows'][0]['label']='keep';bad.append(x)
    x=copy.deepcopy(labels); x['rows'].pop();bad.append(x)
    for x in bad:
        try:
            bind_labels(data,x)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid labels accepted')
    print('Passed label binding, exclusion, agreement and five malformed-input checks')


if __name__=='__main__':
    main()
