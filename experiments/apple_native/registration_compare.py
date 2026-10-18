"""Probe native registration on ablation losses and algorithm-selected controls.
No matrix or confidence is interpreted as a photographic match decision.
"""
import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('result',type=Path)
parser.add_argument('--binary',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args = parser.parse_args()
hashes = json.loads((args.result/'inventory.json').read_text())
paths = list(hashes)
pairs = json.loads((args.result/'pairs.json').read_text())
lost = [p for p in pairs if p['baseline_level']!='unmatched' and p['vision_only_level']=='unmatched']
controls = [('vision_supported',p) for p in pairs if p['vision_only_level']=='likely'][:3]
controls += [('baseline_unmatched',p) for p in pairs if p['baseline_level']=='unmatched'][:3]
selected = [('sift_only',p) for p in lost]+controls
selected_paths = {paths[pair[key]] for _,pair in selected for key in ('a','b')}
def verify():
    for path in selected_paths:
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=hashes[path]:
            raise RuntimeError('Changed sample; registration comparison refused')
verify()
output = []
for kind,pair in selected:
    started = time.perf_counter()
    completed = subprocess.run([str(args.binary.resolve()),'register',paths[pair['a']],paths[pair['b']]],capture_output=True,text=True,timeout=60)
    evidence = json.loads(completed.stdout) if completed.returncode==0 else {'status':'failed','error':completed.stderr}
    output.append({'kind':kind,'a':pair['a'],'b':pair['b'],'vision_distance':pair['vision_distance'],'evidence':evidence,'seconds':time.perf_counter()-started})
verify()
# Exclusive creation keeps previous evidence intact.
with args.output.open('x') as file:
    json.dump({'binary_sha256':hashlib.sha256(args.binary.read_bytes()).hexdigest(),'rows':output,'source_checksums_unchanged':True,
        'limitation':'Controls are algorithm-selected, not labeled photographic ground truth; no match threshold is introduced.'},file,indent=2)
print(json.dumps({kind:{status:sum(r['kind']==kind and r['evidence']['status']==status for r in output) for status in ('ok','unsupported_dimensions','failed')} for kind in ('sift_only','vision_supported','baseline_unmatched')},indent=2))
