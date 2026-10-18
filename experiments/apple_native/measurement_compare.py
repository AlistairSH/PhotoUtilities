"""Attribute changed recommendations to native Gaussian1 and/or edge measurements."""
import argparse
import copy
import hashlib
import json
import resource
import subprocess
import time
from pathlib import Path
from freeze_evidence import digest
from policy_compare import differences,expected


def projection(result):
    result=copy.deepcopy(result)
    for image in result['images']:
        f=image['focus_review']
        f.pop('global_measurements',None);f.pop('global_lower_tail_fractions',None)
        for cue in f['subject_cues']:
            cue.pop('ratios_1024',None);cue.pop('ratios_2048',None)
        image['tier_review']={key:value for key,value in image['tier_review'].items() if key in (
            'id','detail_kind','reasons','composition_advisories','possible_cull','top_pick_reasons','tier','full_sample_rank')}
    return result


def compare():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixture',type=Path)
    parser.add_argument('--measure',type=Path,required=True)
    parser.add_argument('--policy',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    measure_sha=digest(args.measure);policy_sha=digest(args.policy)
    complete=json.loads((args.fixture/'complete.json').read_text())
    for name,sha in complete['files'].items():
        if digest(args.fixture/name)!=sha:raise RuntimeError('Frozen evidence changed: '+name)
    inventory=json.loads((args.fixture/'inventory.json').read_text())
    def verify_sources():
        for path,sha in inventory.items():
            if digest(Path(path))!=sha:raise RuntimeError('Source changed or missing: '+path)
    verify_sources()
    baseline=json.loads((args.fixture/'baseline.json').read_text())
    args.output.mkdir(parents=True,exist_ok=False)
    started=time.perf_counter()
    with (args.output/'measurement.stderr').open('w') as errors:
        process=subprocess.run([str(args.measure.resolve()),str(args.fixture.resolve()),str((args.output/'measurements.jsonl').resolve())],
            stdout=subprocess.DEVNULL,stderr=errors,timeout=7200)
    if process.returncode:raise RuntimeError('Native measurement failed; inspect measurement.stderr')
    measured=[]
    with (args.output/'measurements.jsonl').open() as file:
        for line in file:
            measured.append(json.loads(line))
    completion=measured.pop()
    if completion.get('type')!='complete' or completion.get('scale_rows')!=len(baseline['focus_rows']) or len(measured)!=len(baseline['focus_rows']):
        raise RuntimeError('Incomplete measurement replay')
    for i,row in enumerate(measured):
        b=baseline['focus_rows'][i]
        if (row['path'],row['max_dimension'])!=(b['path'],b['max_dimension']):raise RuntimeError('Measurement identity/order differs')
    expected_result=projection(expected(baseline))
    variants={}
    for name,use_focus,use_edges in [('native_gaussian1',True,False),('native_edges',False,True),('native_all',True,True)]:
        batch=copy.deepcopy(baseline)
        for row,new in zip(batch['focus_rows'],measured):
            if use_focus:row['focus']=new['focus']
            if use_edges:
                for key in ('edge_global','edge_flags','edge_regions'):row[key]=new[key]
            if 'exposure' in new:row['exposure']=new['exposure']
        replay=subprocess.run([str(args.policy.resolve())],input=json.dumps(batch),capture_output=True,text=True,timeout=120)
        if replay.returncode:raise RuntimeError(name+' policy failed: '+replay.stderr)
        actual=json.loads(replay.stdout)
        (args.output/(name+'.json')).write_text(json.dumps(actual,indent=2))
        changes=differences(expected_result,projection(actual))
        changed_ids=sorted({int(c['field'].split('/')[2]) for c in changes if c['field'].startswith('/images/')})
        explanation=[]
        for i in changed_ids:
            a=baseline['images'][i];b=actual['images'][i]
            explanation.append({'index':i,'path':a['path'],'baseline_focus':a['focus_review'],'native_focus':b['focus_review'],
                'baseline_tier':a['tier_review'],'native_tier':b['tier_review'],
                'measurement_evidence':[{'baseline':baseline['focus_rows'][j],'native':measured[j]} for j in (2*i,2*i+1)],
                'cause':'Native Gaussian1 region measurements' if use_focus and not use_edges else 'Native edge-profile extraction/summarization' if use_edges and not use_focus else 'Combined native pixel measurements; compare isolated variants for attribution'})
        (args.output/(name+'-differences.json')).write_text(json.dumps(changes,indent=2))
        (args.output/(name+'-explanations.json')).write_text(json.dumps(explanation,indent=2))
        variants[name]={'changed_images':len(changed_ids),'decision_field_differences':len(changes),
            'changed_focus_flags':sum(a['focus_review']['review_suggestion']!=b['focus_review']['review_suggestion'] for a,b in zip(baseline['images'],actual['images'])),
            'changed_tiers':sum(a['tier_review']['tier']!=b['tier_review']['tier'] for a,b in zip(baseline['images'],actual['images'])),
            'group_order_matches':baseline['groups']==actual['groups'],'standalone_order_matches':baseline['unmatched']==actual['unmatched']}
    edge_changes=[{'index':i//2,'scale':b['max_dimension'],'baseline':b['edge_flags'],'native':n['edge_flags']} for i,(b,n) in enumerate(zip(baseline['focus_rows'],measured)) if b['edge_flags']!=n['edge_flags']]
    (args.output/'edge-flag-differences.json').write_text(json.dumps(edge_changes,indent=2))
    verify_sources()
    summary={'images':len(baseline['images']),'scale_rows':len(measured),'source_checksums_unchanged':True,
        'elapsed_seconds':time.perf_counter()-started,'native_measurement_seconds':sum(r['measurement_seconds'] for r in measured),
        'parent_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'child_peak_rss_bytes':resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        'edge_flag_scale_differences':len(edge_changes),'variants':variants,
        'measure_binary_sha256':measure_sha,'policy_binary_sha256':policy_sha,'baseline_sha256':digest(args.fixture/'baseline.json'),
        'scope':'Same decoded pixels, accepted grouping and native Vision evidence. Swift regional focus, edge measurements and policy replay. Not native SIFT or independent detection parity.'}
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    compare()
