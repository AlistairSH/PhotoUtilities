"""Sequential paired scalar/Accelerate benchmark on an explicit frozen-view subset."""
import argparse
import hashlib
import json
import math
import statistics
import subprocess
import time
from pathlib import Path
from freeze_evidence import digest
from policy_compare import differences


def benchmark():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('fixture',type=Path);p.add_argument('--binary',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--repeats',type=int,default=3)
    p.add_argument('--indices',default='0,19,80,140')
    a=p.parse_args()
    if a.repeats<1:p.error('repeats must be positive')
    ids=[int(x) for x in a.indices.split(',')]
    manifest=json.loads((a.fixture/'complete.json').read_text())
    if digest(a.fixture/'views.json')!=manifest['files']['views.json']:raise RuntimeError('Changed frozen views')
    views=[v for v in json.loads((a.fixture/'views.json').read_text()) if v['index'] in ids]
    if len(views)!=2*len(ids) or len(set(ids))!=len(ids):raise RuntimeError('Requested indices/scales missing or duplicated')
    a.output.mkdir(parents=True,exist_ok=False,mode=0o700)
    subset=a.output/'fixture';subset.mkdir();(subset/'pixels').mkdir()
    (subset/'views.json').write_text(json.dumps(views))
    hashes={}
    for view in views:
        name=f"{view['index']:04d}-{view['max_dimension']}.rgba"
        (subset/'pixels'/name).symlink_to((a.fixture/'pixels'/name).resolve())
        hashes[name]=manifest['pixels_sha256'][name]
    (subset/'complete.json').write_text(json.dumps({'files':{'views.json':digest(subset/'views.json')},'pixels_sha256':hashes,
        'origin_complete_sha256':digest(a.fixture/'complete.json')}))
    sha=digest(a.binary);runs=[];reference=None;max_relative_delta=0.0
    for repeat in range(a.repeats):
        for backend in (('scalar','accelerate') if repeat%2==0 else ('accelerate','scalar')):
            name=f'{repeat+1}-{backend}';started=time.perf_counter()
            with (a.output/(name+'.stderr')).open('w') as errors:
                completed=subprocess.run([str(a.binary.resolve()),str(subset.resolve()),str((a.output/(name+'.jsonl')).resolve()),'--backend',backend],
                    stdout=subprocess.DEVNULL,stderr=errors,timeout=1800)
            if completed.returncode:raise RuntimeError(name+' failed')
            wall=time.perf_counter()-started
            rows=[json.loads(line) for line in (a.output/(name+'.jsonl')).read_text().splitlines()]
            if rows.pop().get('type')!='complete' or len(rows)!=len(views):raise RuntimeError('Incomplete benchmark')
            metrics=[{k:r[k] for k in ('path','max_dimension','focus','edge_global','edge_flags','edge_regions','exposure')} for r in rows]
            if reference is None:reference=metrics
            changed=differences(reference,metrics)
            significant=[]
            for item in changed:
                x,y=item.get('baseline'),item.get('native')
                numeric=isinstance(x,(int,float)) and isinstance(y,(int,float)) and not isinstance(x,bool) and not isinstance(y,bool)
                if not numeric or not math.isclose(x,y,rel_tol=1e-9,abs_tol=1e-12):significant.append(item)
                elif abs(x)>1e-12:max_relative_delta=max(max_relative_delta,abs(x-y)/abs(x))
            if significant:raise RuntimeError('Scalar/Accelerate disagreement: '+str(significant[:1]))
            runs.append({'repeat':repeat+1,'backend':backend,'wall_seconds':wall,'compute_seconds':sum(r['measurement_seconds'] for r in rows),
                'focus_seconds':sum(r['focus_seconds'] for r in rows),'edge_seconds':sum(r['edge_seconds'] for r in rows)})
            print(name,round(wall,3),'seconds',flush=True)
    median={b:{key:statistics.median(r[key] for r in runs if r['backend']==b) for key in ('wall_seconds','compute_seconds','focus_seconds','edge_seconds')} for b in ('scalar','accelerate')}
    summary={'indices':ids,'scale_rows':len(views),'repeats':a.repeats,'binary_sha256':sha,'scalar_accelerate_evidence_agrees_at_tolerance':True,'numeric_tolerance':{'relative':1e-9,'absolute':1e-12},'max_relative_delta_above_1e_12_checker':max_relative_delta,
        'medians':median,'wall_speedup':median['scalar']['wall_seconds']/median['accelerate']['wall_seconds'],
        'focus_speedup':median['scalar']['focus_seconds']/median['accelerate']['focus_seconds'],'runs':runs,
        'scope':'Same refined edge extractor in both modes; Accelerate reductions plus exact quickselect replace scalar reductions/full sorts. Paired sequential subset benchmark, not mobile/end-to-end throughput.'}
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))

if __name__=='__main__':benchmark()
