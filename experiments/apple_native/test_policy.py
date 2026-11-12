"""Independent differential and boundary checks against accepted policy modules."""
import copy
import json
import random
import subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from photo_utils import focus,tiers
from policy_compare import expected,differences


def fixture(count=3,seed=0):
    rng=random.Random(seed)
    result={'images':[],'groups':[],'unmatched':list(range(count)),
        'pairs':[{'a':a,'b':b,'level':'unmatched'} for a in range(count) for b in range(a+1,count)],'focus_rows':[]}
    for i in range(count):
        native={'status':'ok','face_qualities':[],'overallScore':rng.uniform(-1,1),'isUtility':False,'faces':[]}
        result['images'].append({'path':f'synthetic-{i}','ranking_native':copy.deepcopy(native)})
        detail=rng.choice([0,1,1.5,2,3,10])
        for scale in (1024,2048):
            metric={'pixels':1000,'laplacian_variance':detail,'tenengrad':detail}
            result['focus_rows'].append({'path':f'synthetic-{i}','max_dimension':scale,
                'focus':{'global':{'smoothed':metric},'tile_tenengrad':[detail]*16,'regions':[]},
                'edge_flags':{'contrast_proxy':False},'edge_regions':[],
                'exposure':{'global':0,'subjects':{}},'ranking_native':copy.deepcopy(native),'pixel_size':[1024,768]})
    return result


def finalize(result):
    rows=result['focus_rows']
    by_path={r['path']:r for r in focus.decisions(rows)}
    for image in result['images']:
        image['focus_review']=by_path[image['path']]
    focus.relative_focus(result,rows)
    tiers.rank(result,rows)
    return result


def run(binary):
    cases=[]
    # Exact ratio, clipping, cohort-size and tie boundaries; full-batch solo reference.
    for count in (1,2,3,19,20,21,40):
        for seed in range(8):
            cases.append(fixture(count,seed))
    for seed in range(50):
        r=fixture(6,seed)
        rng=random.Random(seed)
        r['groups']=[{'members':[0,1,2],'level':'potential'}]; r['unmatched']=[3,4,5]
        for pair in r['pairs']:
            if pair['b']<3:
                pair['level']=rng.choice(['likely','potential','unmatched'])
        for i,image in enumerate(r['images']):
            quality=rng.choice([None,0,0.5,0.6,0.65])
            image['ranking_native'].update(isUtility=rng.choice([False,False,True]),faces=[{'hasSmile':rng.choice([True,False]),
                'leftEyeClosed':rng.choice([True,False]),'rightEyeClosed':rng.choice([True,False]),'hasLeftEyePosition':True,'hasRightEyePosition':True}])
            for scale in (1024,2048):
                row=r['focus_rows'][2*i+(scale==2048)]
                row['ranking_native']=copy.deepcopy(image['ranking_native']);row['ranking_native']['face_qualities']=[] if quality is None else [quality]
                row['exposure']={'global':rng.choice([0,1.99,2,4]),'subjects':{}}
                kind=rng.choice(['faces','people','animals','objectness','attention'])
                # Keep corresponding boxes across scales in some cases and not others.
                box=[0.2,0.2,0.4,0.4] if seed%3 else [0.6,0.6,0.3,0.3]
                ratio=rng.choice([0.5,0.999,1,2]);metric=copy.deepcopy(row['focus']['global']['smoothed'])
                region={'id':kind+' 1','box':box,'usable':True,
                    'smoothed':{'region':metric,'outside':{'pixels':2000,'laplacian_variance':1,'tenengrad':1},
                                'region_to_outside':{'laplacian_variance':ratio,'tenengrad':ratio}}}
                row['focus']['regions']=[region]
                row['edge_flags']['contrast_proxy']=rng.choice([True,False])
                row['edge_regions']=[{'id':kind+' 1','box':box,'metrics':{'sufficient':rng.choice([True,False]),'contrast_soft_fraction':rng.choice([0.4,0.6,0.8])}}]
        cases.append(r)
    for i,result in enumerate(cases):
        finalized=finalize(result)
        completed=subprocess.run([binary],input=json.dumps(finalized),capture_output=True,text=True,timeout=20)
        if completed.returncode:
            raise AssertionError((i,completed.stderr))
        changes=differences(expected(finalized),json.loads(completed.stdout))
        if changes:
            raise AssertionError((i,changes[:3]))
    bad=finalize(fixture(2))
    for mutation in ('missing_scale','duplicate_scale','missing_pairs','bad_partition','bad_region','missing_ranking','unknown_subject','missing_region_pixels'):
        r=copy.deepcopy(bad)
        if mutation=='missing_scale':r['focus_rows'].pop()
        if mutation=='duplicate_scale':r['focus_rows'][1]=copy.deepcopy(r['focus_rows'][0])
        if mutation=='missing_pairs':r['pairs']=[]
        if mutation=='bad_partition':r['unmatched']=[0,0]
        if mutation=='bad_region':r['focus_rows'][0]['focus']['regions']=[{'id':'faces 1','box':[0.2,0.2],'usable':True,'smoothed':None}]
        if mutation=='missing_ranking':r['images'][0]['ranking_native'].pop('faces')
        if mutation in ('unknown_subject','missing_region_pixels'):
            r['focus_rows'][0]['focus']['regions']=[{'id':'alien 1' if mutation=='unknown_subject' else 'faces 1','box':[0,0,.5,.5],'usable':True,
                'smoothed':{'region':{'laplacian_variance':1,'tenengrad':1},'outside':None,'region_to_outside':{}}}]
        completed=subprocess.run([binary],input=json.dumps(r),capture_output=True,text=True,timeout=20)
        assert completed.returncode!=0 and not completed.stdout,mutation
    print(f'Passed {len(cases)} synthetic policy comparisons and 8 malformed-evidence rejection checks')

if __name__=='__main__':
    run(sys.argv[1])
