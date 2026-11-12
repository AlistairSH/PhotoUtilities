"""Compare compiled Swift/C++ SIFT against the unchanged accepted Python oracle.
Identical frozen previews, fixed Vision distances; no production DB or photo writes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from photo_utils.similarity import sift_pair, components
from geometry_evaluate import constructed_cases, features

FIELDS=('mutual_matches','inliers','inlier_fraction','coverage_a','coverage_b','sift_candidate')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_native(binary, output, images, pairs, expected):
    manifest=output/'input.json'
    manifest.write_text(json.dumps({'images':images,'pairs':pairs}))
    started=time.perf_counter()
    with (output/'native.jsonl').open('x') as stdout, (output/'native.stderr').open('x') as stderr:
        command=[str(binary),str(manifest)]
        if sys.platform=='darwin': command=['/usr/bin/time','-l']+command
        process=subprocess.run(command,stdout=stdout,stderr=stderr,timeout=600)
    if process.returncode:
        raise RuntimeError('Native replay failed; see retained stderr')
    rows=[json.loads(line) for line in (output/'native.jsonl').read_text().splitlines()]
    if not rows or rows[-1].get('type')!='complete' or rows[-1]['images']!=len(images) or rows[-1]['pairs']!=len(pairs):
        raise RuntimeError('Missing native completion')
    image_rows=[r for r in rows if r['type']=='image']
    actual=[r for r in rows if r['type']=='pair']
    if len(rows)!=len(images)+len(pairs)+1 or [r['index'] for r in image_rows]!=list(range(len(images))) or len(actual)!=len(pairs):
        raise RuntimeError('Unexpected native row identities/counts')
    differences=[]
    for a,b,e in zip(actual,pairs,expected):
        if (a['a'],a['b'])!=(b['a'],b['b']):
            raise RuntimeError('Native pair order mismatch')
        for key in FIELDS:
            same = a[key]==e[key] if key in ('mutual_matches','inliers','sift_candidate') else math.isclose(a[key],e[key],rel_tol=1e-12,abs_tol=1e-12)
            if not same:
                differences.append({'a':a['a'],'b':a['b'],'field':key,'baseline':e[key],'native':a[key]})
    memory=re.search(r'^\s*(\d+)\s+maximum resident set size', (output/'native.stderr').read_text(),re.M)
    return actual, {'wall_seconds':time.perf_counter()-started,'native_seconds':rows[-1]['seconds'],
                    'native_peak_rss_bytes':int(memory.group(1)) if memory else None,
                    'field_differences':differences,'native_complete':rows[-1]},image_rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--corpus',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(mode=0o700,parents=True,exist_ok=False);args.output.chmod(0o700)
    binary=args.binary.resolve(); binary_hash=digest(binary)
    complete=json.loads((args.fixture/'complete.json').read_text())
    for name,sha in complete['files'].items():
        if digest(args.fixture/name)!=sha: raise RuntimeError('Frozen metadata changed')
    inventory=json.loads((args.fixture/'inventory.json').read_text())
    if inventory!=json.loads((args.corpus/'inventory.json').read_text()): raise RuntimeError('Inventories differ')
    def verify_sources():
        for path,sha in inventory.items():
            if not Path(path).is_file() or digest(Path(path))!=sha: raise RuntimeError('Original missing or changed: '+path)
    verify_sources()
    paths=list(inventory)
    views=json.loads((args.fixture/'views.json').read_text())
    baseline=json.loads((args.corpus/'pairs.json').read_text())
    if len(baseline)!=len(paths)*(len(paths)-1)//2 or len({(p['a'],p['b']) for p in baseline})!=len(baseline):
        raise RuntimeError('Incomplete/duplicate accepted pair evidence')
    images=[]; extracted=[]; expected_counts=[]
    for index,path in enumerate(paths):
        view=next(v for v in views if v['index']==index and v['max_dimension']==1024)
        if view['path']!=path: raise RuntimeError('Frozen view identity changed')
        pixels=args.fixture/'pixels'/f'{index:04d}-1024.rgba';sha=complete['pixels_sha256'][pixels.name]
        if digest(pixels)!=sha: raise RuntimeError('Frozen pixels changed')
        images.append({'index':index,'width':view['width'],'height':view['height'],'pixels':str(pixels),'sha256':sha})
        rgba=np.frombuffer(pixels.read_bytes(),np.uint8).reshape(view['height'],view['width'],4)
        f=features(cv2.cvtColor(rgba,cv2.COLOR_RGBA2BGR));extracted.append(f);expected_counts.append(len(f['points']))
    matcher=cv2.BFMatcher(cv2.NORM_L2)
    expected=[sift_pair(extracted[p['a']],extracted[p['b']],matcher) for p in baseline]
    print('Frozen-pixel Python oracle ready',flush=True)
    historical_differences=[{'a':p['a'],'b':p['b'],'field':k} for p,e in zip(baseline,expected) for k in FIELDS if p[k]!=e[k]]
    pair_input=[{k:p[k] for k in ('a','b','vision_distance')} for p in baseline]
    native,corpus_stats,native_images=run_native(binary,args.output,images,pair_input,expected)
    corpus_stats['keypoint_count_differences']=sum(a['keypoints']!=e for a,e in zip(native_images,expected_counts))
    corpus_stats['historical_field_differences']=historical_differences
    corpus_stats['pair_level_differences']=sum(a['level']!=b['baseline_level'] for a,b in zip(native,baseline))
    expected_groups=components(len(paths),[dict(p,level=p['baseline_level']) for p in baseline])
    actual_groups=components(len(paths),native)
    corpus_stats['components_match']=actual_groups==expected_groups
    corpus_stats['groups']=sum(len(g)>1 for g in actual_groups)
    corpus_stats['standalone']=sum(len(g)==1 for g in actual_groups)
    corpus_stats['sift_only_links_recovered']=sum(p['baseline_level']!='unmatched' and p['vision_only_level']=='unmatched' and a['level']==p['baseline_level'] for a,p in zip(native,baseline))
    synthetic=args.output/'synthetic';synthetic.mkdir(mode=0o700)
    inputs=[];pairs=[];oracle=[];names=[]
    for name,a,b,_,label in constructed_cases():
        start=len(inputs)
        for image in (a,b):
            rgba=cv2.cvtColor(image,cv2.COLOR_BGR2RGBA);pixel=synthetic/f'{len(inputs):04d}.rgba'
            pixel.write_bytes(rgba.tobytes())
            inputs.append({'index':len(inputs),'width':image.shape[1],'height':image.shape[0],'pixels':str(pixel),'sha256':digest(pixel)})
        pairs.append({'a':start,'b':start+1,'vision_distance':1.})
        oracle.append(sift_pair(features(a),features(b),matcher));names.append({'case':name,'construction':label})
    _,synthetic_stats,_=run_native(binary,synthetic,inputs,pairs,oracle)
    synthetic_stats['cases']=names
    verify_sources()
    if digest(binary)!=binary_hash: raise RuntimeError('Native binary changed')
    summary={'images':len(images),'pairs':len(baseline),'binary_sha256':binary_hash,
             'opencv_python_version':cv2.__version__,'corpus':corpus_stats,'synthetic':synthetic_stats,
             'memory_note':'Native peak RSS is measured by macOS /usr/bin/time -l around the native child, excluding the Python oracle process.',
             'source_checksums_unchanged':True,'pixels':{p['pixels']:p['sha256'] for p in images},
             'scope':'Frozen upright RGBA8 previews and Vision distances; native SIFT and Swift pair classification. No fresh decoding/Vision, app/device validation or Photos integration.'}
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps({k:v for k,v in summary.items() if k!='pixels'},indent=2))
    if corpus_stats['field_differences'] or corpus_stats['keypoint_count_differences'] or corpus_stats['pair_level_differences'] or not corpus_stats['components_match'] or synthetic_stats['field_differences']:
        raise SystemExit('Parity gate failed; evidence retained')


if __name__=='__main__':
    main()
