"""Replay fixed accepted evidence through Swift; report every decision difference."""
import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected(result):
    return {'images':[{k:im[k] for k in ('path','focus_review','focus_comparison','tier_review') if k in im} for im in result['images']],
            'groups':result['groups'],'unmatched':result['unmatched']}


def differences(a,b,path=''):
    if isinstance(a,bool) or isinstance(b,bool):
        return [] if type(a)==type(b) and a==b else [{'field':path,'baseline':a,'native':b}]
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):
        return [] if math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-12) else [{'field':path,'baseline':a,'native':b}]
    if isinstance(a,dict) and isinstance(b,dict):
        result=[]
        for key in sorted(a.keys()|b.keys()):
            if key not in a or key not in b:
                result.append({'field':path+'/'+key,'baseline':a.get(key),'native':b.get(key),'missing_key':True})
            else:
                result.extend(differences(a[key],b[key],path+'/'+key))
        return result
    if isinstance(a,list) and isinstance(b,list) and len(a)==len(b):
        return [item for i,(x,y) in enumerate(zip(a,b)) for item in differences(x,y,path+'/'+str(i))]
    return [] if a==b else [{'field':path,'baseline':a,'native':b}]


def compare():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixture',type=Path)
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    completion=json.loads((args.fixture/'complete.json').read_text())
    for name,sha in completion['files'].items():
        if digest(args.fixture/name)!=sha:
            raise RuntimeError('Changed frozen evidence: '+name)
    baseline=json.loads((args.fixture/'baseline.json').read_text())
    args.output.mkdir(parents=True,exist_ok=False)
    completed=subprocess.run([str(args.binary.resolve())],input=json.dumps(baseline),capture_output=True,text=True,timeout=120)
    (args.output/'stderr.txt').write_text(completed.stderr)
    if completed.returncode:
        raise RuntimeError('Policy evidence rejected; inspect stderr.txt')
    actual=json.loads(completed.stdout)
    (args.output/'native.json').write_text(json.dumps(actual,indent=2,allow_nan=False))
    changed=differences(expected(baseline),actual)
    summary={'images':len(baseline['images']),'scales':len(baseline['focus_rows']),
        'field_differences':len(changed),'changed_images':len({c['field'].split('/')[2] for c in changed if c['field'].startswith('/images/')}),
        'changed_focus_flags':sum(a['focus_review']['review_suggestion']!=b['focus_review']['review_suggestion'] for a,b in zip(baseline['images'],actual['images'])),
        'changed_tiers':sum(a['tier_review']['tier']!=b['tier_review']['tier'] for a,b in zip(baseline['images'],actual['images'])),
        'group_order_matches':baseline['groups']==actual['groups'],'standalone_order_matches':baseline['unmatched']==actual['unmatched'],
        'baseline_sha256':digest(args.fixture/'baseline.json'),'binary_sha256':digest(args.binary),
        'comparison':'Same frozen evidence; grouping, detection and image measurements held constant. Floating outputs compared at 1e-12; decisions/reasons/orders exact.'}
    (args.output/'differences.json').write_text(json.dumps(changed,indent=2))
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
    if changed:
        raise SystemExit(1)

if __name__=='__main__':
    compare()
