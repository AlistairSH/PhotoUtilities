"""Local subject-detector audit; overlays are HTML/SVG, original pixels are untouched."""
import argparse
import base64
import html
import json
import os
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import quote

import cv2
import numpy as np

from run import digest

COLORS = {'faces':'#ffcf33','people':'#00e5ff','animals':'#ff68e3',
          'attention':'#66ff66','objectness':'#ff8033'}
EXPECTED = {'000387090004.jpg':'Person and dog', '000438810025.jpg':'Person and dog',
            '000438810018.jpg':'Truck', '000438810032.jpg':'Person (soft face)',
            '000438810036.jpg':'Pickup and camper', '000438810035.jpg':'Person and dog',
            '000438850008.jpg':'Person and dog', '000438850017.jpg':'Silos and buildings',
            '000438850015.jpg':'Foreground person (background people also present)',
            '000438850030.jpg':'Dog (partial person at top)'}


def validate_regions(detectors):
    for detector in detectors.values():
        if detector['status'] != 'ok':
            continue
        for region in detector['regions']:
            box = region['box']
            if len(box) != 4 or not all(np.isfinite(v) for v in box):
                raise ValueError('Invalid region coordinates')
            x,y,w,h = box
            if min(w,h) <= 0 or min(x+w,1) <= max(x,0) or min(y+h,1) <= max(y,0):
                raise ValueError('Region does not intersect the image')
            # Vision can return a box extending beyond the image. Preserve its
            # raw coordinates; clip only the SVG display rectangle.
            left,top=max(x,0),max(y,0)
            region['display_box']=[left,top,min(x+w,1)-left,min(y+h,1)-top]


def render(rows, baseline, destination):
    esc=html.escape
    parts=['<!doctype html><html lang="en"><head><meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width,initial-scale=1">',
           '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'">',
           '<title>Subject detection audit</title><style>',
           'body{font:16px system-ui,sans-serif;background:#f7f6f2;color:#242a30;margin:auto;max-width:1300px;padding:24px}',
           'section{background:white;border:1px solid #ccc;border-radius:8px;padding:16px;margin:24px 0}',
           '.canvas{position:relative;max-width:1000px;margin-top:12px}.canvas img{display:block;width:100%;height:auto}',
           '.canvas svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}',
           'label{margin-right:16px}table{border-collapse:collapse}td,th{padding:8px;text-align:left;border-bottom:1px solid #ddd}',
           'p{line-height:1.5}.failure{color:#a21818}summary{cursor:pointer}a{color:#155b81}']
    for name in COLORS:
        parts.append(f'input.{name}:not(:checked)~.canvas .{name}{{display:none}}')
    parts.extend(['</style></head><body><h1>Subject detection audit</h1>',
        '<p>The existing pipeline only runs face rectangles; the previous culling decisions use global/tile focus, '
        'not detected subject focus. This diagnostic additionally tests full-body people, cat/dog recognition, '
        'attention saliency and objectness saliency at 1024 and 2048 pixels. These extra detectors are not yet '
        'used by ranking or culling.</p>',
        '<p>Vehicles and buildings have no semantic detector in this test. Saliency rectangles indicate visually '
        'prominent regions, not recognized trucks or buildings. Inspect coverage as well as detection counts. '
        'All raw observations are shown without a new confidence cutoff; Vision observation scores are not '
        'focus probabilities. Checkbox controls show or hide individual layers.</p>'])
    person_names={'000387090004.jpg','000438810025.jpg','000438810032.jpg',
                  '000438810035.jpg','000438850008.jpg','000438850015.jpg'}
    dog_names={'000387090004.jpg','000438810025.jpg','000438810035.jpg',
               '000438850008.jpg','000438850030.jpg'}
    sample=[r for r in rows if r['max_dimension']==1024]
    people=[r for r in sample if Path(r['path']).name in person_names]
    dogs=[r for r in sample if Path(r['path']).name in dog_names]
    if people or dogs:
        found=lambda r,name: bool(r['detectors'][name].get('regions'))
        parts.append(f'<p><strong>1024-pixel sample:</strong> face regions in {sum(found(r,"faces") for r in people)}/{len(people)} photos with a main person; '
                     f'body regions in {sum(found(r,"people") for r in people)}/{len(people)}; '
                     f'animal regions in {sum(found(r,"animals") for r in dogs)}/{len(dogs)} photos with a dog. '
                     'Counts alone do not prove that regions cover the intended subject; inspect the overlays.</p>')
    filenames=list(dict.fromkeys(row['path'] for row in rows))
    for path in filenames:
        name=Path(path).name
        parts.append(f'<section><h2>{esc(name)}</h2><p>Expected subject: {esc(EXPECTED.get(name,"Operator review"))}</p>')
        prior=baseline.get(path)
        if prior:
            counts={scale:sum(f['usable'] for f in prior['analysis']['scales'][scale]['faces']) for scale in ('1024','512')}
            parts.append(f'<p>Previous pipeline: {len(prior["analysis"]["scales"]["1024"]["faces"])} face observations; '
                         f'{counts["1024"]} usable at 1024, {counts["512"]} usable at 512.</p>')
        for row in (r for r in rows if r['path']==path):
            if row['max_dimension']==2048:
                parts.append('<details><summary>2048-pixel comparison</summary>')
            parts.append(f'<h3>{row["max_dimension"]}-pixel detection ({row["width"]}×{row["height"]})</h3>')
            parts.append('<table><tr><th>Detector</th><th>Regions</th><th>Revision</th><th>Animal labels / error</th></tr>')
            for detector,result in row['detectors'].items():
                labels=', '.join(f'{label["identifier"]} {label["confidence"]:.3f}' for region in result.get('regions',[]) for label in region.get('labels',[]))
                detail=result.get('error',labels)
                count=len(result['regions']) if result['status']=='ok' else 'FAILED'
                parts.append(f'<tr><td>{esc(detector)}</td><td>{count}</td><td>{result["revision"]}</td><td>{esc(detail)}</td></tr>')
            parts.append('</table>')
            for detector,color in COLORS.items():
                control=f'{row["index"]}-{row["max_dimension"]}-{detector}'
                parts.append(f'<input class="{detector}" id="{control}" type="checkbox" checked><label for="{control}" style="color:{color};background:#242a30;padding:2px 4px">{detector}</label>')
            link=esc(quote(os.path.relpath(path,destination.parent)))
            parts.append(f'<div class="canvas"><a href="{link}"><img src="data:image/jpeg;base64,{row["thumbnail"]}" alt="{esc(name)}"></a><svg viewBox="0 0 {row["width"]} {row["height"]}" aria-label="Detection overlays">')
            for detector,result in row['detectors'].items():
                for index,region in enumerate(result.get('regions',[]),1):
                    x,y,w,h=region.get('display_box',region['box'])
                    x,w=x*row['width'],w*row['width'];y,h=y*row['height'],h*row['height']
                    focus=region.get('focus',{}).get('smoothed')
                    ratio=focus['region_to_outside'].get('tenengrad') if focus else None
                    note=f' T/out {ratio:.2f}' if ratio is not None else ''
                    parts.append(f'<g class="{detector}"><rect x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" height="{h:.3f}" fill="none" stroke="{COLORS[detector]}" stroke-width="2" vector-effect="non-scaling-stroke"/>'
                                 f'<text x="{x+3:.3f}" y="{max(14,y+14):.3f}" fill="{COLORS[detector]}" stroke="#111" stroke-width=".5" paint-order="stroke" font-size="14">{detector} {index}{note}</text></g>')
            parts.append('</svg></div><details><summary>Raw observations</summary><pre style="white-space:pre-wrap">'+esc(json.dumps(row['detectors'],indent=2))+'</pre></details>')
            if row['max_dimension']==2048:parts.append('</details>')
        parts.append('</section>')
    parts.append('</body></html>')
    return '\n'.join(parts)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images',nargs='+',type=Path)
    parser.add_argument('--helper',required=True,type=Path)
    parser.add_argument('--baseline-export',type=Path)
    parser.add_argument('--output-dir',required=True,type=Path)
    args=parser.parse_args()
    if any(p.is_symlink() for p in args.images):raise ValueError('Symlink inputs refused')
    paths=[p.resolve(strict=True) for p in args.images]
    if len(set(paths))!=len(paths):raise ValueError('Duplicate image inputs')
    output=args.output_dir.resolve()
    repository=Path(__file__).resolve().parents[2]
    if output==repository or repository in output.parents or any(output==p.parent or p.parent in output.parents for p in paths):
        raise ValueError('Output must be separate from repository and sources')
    hashes=[digest(p) for p in paths]
    stats=[(p.stat().st_size,p.stat().st_mtime_ns) for p in paths]
    baseline={}
    if args.baseline_export:
        data=json.loads(args.baseline_export.read_text())
        baseline={row['path']:row for row in data['images']}
        identities=dict(zip(data['paths'],data['hashes']))
        if any(identities.get(str(p))!=sha for p,sha in zip(paths,hashes)):
            raise ValueError('Baseline source identity mismatch')
    rows=[]
    completed=False
    with tempfile.TemporaryFile() as stream:
        result=subprocess.run([str(args.helper.resolve())],input=json.dumps(list(map(str,paths))).encode(),
                              stdout=stream,stderr=subprocess.PIPE,timeout=600)
        if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace'))
        stream.seek(0)
        for line in stream:
            row=json.loads(line)
            if completed:raise ValueError('Output after completion')
            if row['type']=='complete':
                completed=row['images']==len(paths);environment=row['os'];continue
            index,scale=divmod(len(rows),2)
            if row['type']!='image' or row['index']!=index or row['path']!=str(paths[index]) or row['max_dimension']!=(1024,2048)[scale]:
                raise ValueError('Native identity mismatch')
            w,h=row['width'],row['height']
            if min(w,h)<1 or max(w,h)>row['max_dimension']:raise ValueError('Invalid preview dimensions')
            validate_regions(row['detectors'])
            rgba=np.frombuffer(base64.b64decode(row.pop('rgba'),validate=True),np.uint8).reshape(h,w,4)
            ok,encoded=cv2.imencode('.jpg',cv2.cvtColor(rgba[:,:,:3],cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,90])
            if not ok:raise ValueError('Preview encoding failed')
            row['thumbnail']=base64.b64encode(encoded.tobytes()).decode('ascii')
            rows.append(row)
    if not completed or len(rows)!=len(paths)*2:raise ValueError('Incomplete subject audit')
    document=render(rows,baseline,output/'subjects.html')
    if hashes!=[digest(p) for p in paths] or stats!=[(p.stat().st_size,p.stat().st_mtime_ns) for p in paths]:
        raise ValueError('Sources changed; refusing to publish')
    output.mkdir(parents=True,exist_ok=False)
    (output/'subjects.html').write_text(document)
    native_source=Path(__file__).with_name('subjects.swift')
    payload={'source_sha256':hashes,'source_paths':list(map(str,paths)), 'inputs_unchanged':True,
             'os':environment,'helper_sha256':digest(args.helper),'native_source_sha256':digest(native_source),
             'version':'subject-audit-v1','rows':[{k:v for k,v in r.items() if k!='thumbnail'} for r in rows]}
    (output/'subjects.json').write_text(json.dumps(payload,indent=2))
    for row in rows:
        print(Path(row['path']).name,row['max_dimension'],{name:len(r.get('regions',[])) if r['status']=='ok' else 'FAILED' for name,r in row['detectors'].items()})
    print('Saved:',output/'subjects.html')


if __name__=='__main__':main()
