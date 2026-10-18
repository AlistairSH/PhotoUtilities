"""Freeze accepted local review evidence without a database or image mutations."""
import argparse
import base64
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from photo_utils import similarity
from photo_utils.similarity_native import native_rows


def digest(path):
    hasher=hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def freeze():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--auto-rotate',action='store_true')
    args=parser.parse_args()
    paths=similarity.collect_images([args.folder.resolve()])
    args.output.mkdir(parents=True,exist_ok=False,mode=0o700)
    pixels=args.output/'pixels';pixels.mkdir()
    hashes={str(p):digest(p) for p in paths}
    (args.output/'inventory.json').write_text(json.dumps(hashes,indent=2))
    views=[]
    def capture(paths,**kwargs):
        for row in native_rows(paths,**kwargs):
            if row['type'] in ('image','focus'):
                identity=f"{row['index']:04d}-{row['max_dimension']}"
                data=base64.b64decode(row['rgba'],validate=True)
                with (pixels/(identity+'.rgba')).open('xb') as file:
                    file.write(data)
                views.append({k:v for k,v in row.items() if k!='rgba'})
            yield row
    similarity.native_rows=capture
    started=time.perf_counter()
    result=similarity.analyze(paths,list(hashes.values()),tiers=True,auto_rotate=args.auto_rotate)
    for image in result['images']:
        image.pop('thumbnail',None)
    for p in paths:
        if digest(p)!=hashes[str(p)]:
            raise RuntimeError('Original changed during freeze')
    # A completion manifest is published only after all accepted processing succeeds.
    (args.output/'baseline.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    (args.output/'views.json').write_text(json.dumps(views,indent=2,allow_nan=False))
    provenance={'images':len(paths),'scale_rows':len(views),'elapsed_seconds':time.perf_counter()-started,
        'source_checksums_unchanged':True,'auto_rotate':args.auto_rotate,
        'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'baseline_source_sha256':{str(p.relative_to(Path(__file__).resolve().parents[2])):digest(p) for p in sorted((Path(__file__).resolve().parents[2]/'photo_utils').glob('*.py'))},
        'files':{p.name:digest(p) for p in (args.output/'baseline.json',args.output/'views.json',args.output/'inventory.json')},
        'pixels_sha256':{p.name:digest(p) for p in sorted(pixels.glob('*.rgba'))}}
    (args.output/'complete.json').write_text(json.dumps(provenance,indent=2))
    print(json.dumps({k:v for k,v in provenance.items() if k not in ('pixels_sha256','baseline_source_sha256','files')},indent=2))

if __name__=='__main__':
    freeze()
