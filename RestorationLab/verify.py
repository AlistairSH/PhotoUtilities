from pathlib import Path
import argparse
parser=argparse.ArgumentParser(description="Read-only audit of the private restored JPEG collection.")
parser.add_argument("--workspace",type=Path,default=Path(__file__).resolve().parent.parent.parent)
args=parser.parse_args()
import json,hashlib,cv2
root=args.workspace.expanduser().resolve()
out=root/'Restored'
original=json.loads((out/'restoration-manifest.json').read_text())
current=json.loads((out/'jpeg-inventory.json').read_text())['files']
assert len(current)==len(original['records']) and len(current)>0
for r in original['records']:
 p=Path(r['source']);assert hashlib.sha256(p.read_bytes()).hexdigest()==r['source_sha256']
for r in current:
 p=Path(r['path']);assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256']
 a=cv2.imread(str(p));assert a is not None and list(a.shape)==r['shape']
assert not list(out.rglob('*.png'))
print(f'Verified {len(original["records"])} unchanged sources, {len(current)} current JPEGs, and no PNGs in Restored.')
