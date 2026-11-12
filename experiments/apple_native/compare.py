"""Offline comparison adapter; no production DB, writes only a new research directory."""
import argparse
import base64
import copy
import hashlib
import json
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from photo_utils.similarity import collect_images, sift_pair, classify, components
from photo_utils.focus_measurements import analyze_regions


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest() if hasattr(hashlib,'file_digest') else hashlib.sha256(source.read()).hexdigest()


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--focus',action='store_true')
    parser.add_argument('--limit',type=int)
    parser.add_argument('--regions',action='store_true')
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error('--limit must be positive')
    if args.regions:
        args.focus = True
    paths = collect_images([args.folder.resolve()])
    if args.limit:
        paths = paths[:args.limit]
    args.output.mkdir(parents=True,exist_ok=False)
    binary_sha256 = digest(args.binary)
    hashes = {str(p):digest(p) for p in paths}
    (args.output/'inventory.json').write_text(json.dumps(hashes,indent=2))
    detector = cv2.SIFT_create(nfeatures=500)
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    features, pairs, comparisons = [], [], []
    seen_pairs = set()
    native_focus_scales = []
    started = time.perf_counter()
    baseline_seconds = 0
    command = [str(args.binary.resolve()),'--comparison-pixels'] + (['--focus'] if args.focus else []) + (['--regions'] if args.regions else [])
    with (args.output/'native.stderr').open('w') as errors:
        process = subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,text=True)
        process.stdin.write(json.dumps(list(hashes))); process.stdin.close()
        complete = None
        try:
            for line in process.stdout:
                row = json.loads(line)
                if row['type'] in ('image','focus'):
                    expected_index = len(features) if row['type']=='image' else len(features)-1
                    if row['index'] != expected_index or row['path'] != str(paths[expected_index]):
                        raise RuntimeError('Native identity/order mismatch')
                    rgba = np.frombuffer(base64.b64decode(row['rgba'],validate=True),np.uint8).reshape(row['height'],row['width'],4)
                    rgb = rgba[:,:,:3]
                    before = time.perf_counter()
                    if args.focus:
                        native_focus_scales.append((row['index'],row['max_dimension']))
                        baseline = analyze_regions(rgb,copy.deepcopy(row['detectors']))['global']['smoothed']
                        native = row['native_focus_global']
                        if args.regions:
                            region_baseline = analyze_regions(rgb,copy.deepcopy(row['detectors']))
                            native_regions = row['native_focus_regions']
                            if len(native_regions['regions']) != len(region_baseline['regions']):
                                raise RuntimeError('Missing regional measurements')
                            row['region_comparison'] = {'baseline':region_baseline,'native':native_regions}

                        comparisons.append({'path':row['path'],'scale':row['max_dimension'], 'native':native,'baseline':baseline,'native_seconds':row.get('native_focus_seconds'),
                            'relative_error':{k:abs(native[k]-baseline[k])/max(abs(baseline[k]),1e-12) for k in baseline if k!='pixels'},'regions':row.get('region_comparison')})
                    if row['type']=='image':
                        points,descriptors = detector.detectAndCompute(cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY),None)
                        features.append({'points':np.asarray([k.pt for k in points],dtype=np.float32),'descriptors':descriptors,'shape':rgb.shape[:2]})
                        print(f'Compared image {len(features)}/{len(paths)}',flush=True)
                    baseline_seconds += time.perf_counter()-before
                elif row['type']=='pair':
                    key = (row['a'],row['b'])
                    if not 0 <= key[0] < key[1] < len(paths) or key in seen_pairs:
                        raise RuntimeError('Invalid or duplicate comparison')
                    seen_pairs.add(key)
                    before = time.perf_counter()
                    sift = sift_pair(features[row['a']],features[row['b']],matcher)
                    row.update(sift)
                    row['baseline_level'] = classify(row['vision_distance'],sift['sift_candidate'])
                    pairs.append(row)
                    if len(pairs)%1000==0:
                        print(f'Compared {len(pairs)} pairs',flush=True)
                    baseline_seconds += time.perf_counter()-before
                elif row['type']=='complete':
                    complete = row
                else:
                    raise RuntimeError('Unknown native row')
            code = process.wait()
            if args.focus and native_focus_scales != [(i,s) for i in range(len(paths)) for s in (1024,2048)]:
                raise RuntimeError('Incomplete or duplicate focus scales')
            if code or complete is None or complete.get('images') != len(paths) or len(features)!=len(paths) or len(pairs)!=len(paths)*(len(paths)-1)//2:
                raise RuntimeError(f'Incomplete native analysis, exit {code}; inspect native.stderr')
        finally:
            if process.poll() is None:
                process.kill(); process.wait()
    changed = [p for p in paths if digest(p)!=hashes[str(p)]]
    if changed:
        raise RuntimeError('Source checksum changed')
    baseline_pairs = [dict(p,level=p['baseline_level']) for p in pairs]
    native_pairs = [dict(p,level=p['vision_only_level']) for p in pairs]
    lost = [p for p in pairs if p['baseline_level']!='unmatched' and p['vision_only_level']=='unmatched']
    summary = {'images':len(paths),'pairs':len(pairs),'extensions':{e:sum(p.suffix.lower()==e for p in paths) for e in sorted({p.suffix.lower() for p in paths})},
        'source_checksums_unchanged':True,'baseline_components':components(len(paths),baseline_pairs),
        'native_components':components(len(paths),native_pairs),'sift_only_links':len(lost),
        'pair_level_differences':sum(p['baseline_level']!=p['vision_only_level'] for p in pairs),
        'elapsed_pipeline_seconds':time.perf_counter()-started,'python_baseline_work_seconds':baseline_seconds,
        'parent_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'child_peak_rss_bytes':resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        'host':platform.platform(),'opencv':cv2.__version__,'numpy':np.__version__,
        'native_binary_sha256':binary_sha256,'experiment_source_sha256':{str(p.relative_to(Path(__file__).parent)):digest(p) for p in sorted(Path(__file__).parent.rglob('*.swift'))},'focus_rows':len(comparisons),'native_focus_seconds':sum(c.get('native_seconds') or 0 for c in comparisons),
        'focus_relative_error_max':{k:max(c['relative_error'][k] for c in comparisons) for k in comparisons[0]['relative_error']} if comparisons else {},
        'limitations':['Pipeline time includes IPC, decoding, native Vision and Python work; not an independent speedup benchmark.',
            'SIFT-only link loss is disagreement with baseline, not manually judged false-negative ground truth.',
            'Regional comparison enabled; full contrast confirmation and tier parity are not established.' if args.regions else 'Global focus only; regional focus, contrast confirmation and tier parity are not established.']}
    for name,value in [('summary',summary),('pairs',pairs),('focus',comparisons)]:
        (args.output/(name+'.json')).write_text(json.dumps(value,indent=2))
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    run()
