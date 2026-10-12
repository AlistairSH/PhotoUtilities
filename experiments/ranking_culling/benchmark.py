"""Compare fixed focus treatments to a user-annotated CSV; no threshold fitting."""
import argparse
import base64
import collections
import copy
import csv
import html
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import quote

import cv2
import numpy as np

from region_focus import analyze_regions
from subject_review import screen,POLICY
from run import digest

ALL_TREATMENTS=['raw','gaussian1','gaussian2','bilateral']
TREATMENTS=list(ALL_TREATMENTS)


def expectation(notes):
    note=notes.lower().strip()
    if not note:return 'unlabeled'
    if re.search(r'\b(?:entire|whole)\b.*\bout of focus\b',note):return 'whole_image_focus_miss'
    if 'focus miss across image' in note:return 'whole_image_focus_miss'
    if 'subject out of focus' in note:return 'subject_focus_miss'
    if 'polaroid softness' in note:return 'natural_softness'
    return 'no_explicit_focus_miss'


def samples(csv_path):
    with csv_path.open(newline='',encoding='utf-8-sig') as stream:rows=list(csv.reader(stream))
    result=[]
    for line,row in enumerate(rows,1):
        if len(row)!=4:raise ValueError(f'Expected four headerless columns at line {line}')
        filename,material,color,notes=row
        path=csv_path.parent/filename
        if Path(filename).name!=filename or path.is_symlink() or not path.is_file():raise ValueError(f'Invalid sample: {filename}')
        result.append({'filename':filename,'path':str(path.resolve()),'material':material or 'unlabeled',
                       'color':color,'notes':notes,'reference':expectation(notes)})
    if len({r['path'] for r in result})!=len(result):raise ValueError('Duplicate sample filename')
    return result


def evaluate(records,analyses):
    results={r['path']:{} for r in records}
    summaries={}
    # Evaluate within material, never pool Polaroids with film/digital.
    for treatment in TREATMENTS:
        decisions=[]
        for material in sorted({r['material'] for r in records}):
            paths={r['path'] for r in records if r['material']==material}
            rows=[r for r in analyses[treatment] if r['path'] in paths]
            decisions.extend(screen(rows))
        by_path={d['path']:d for d in decisions}
        summary=collections.Counter()
        for sample in records:
            d=by_path[sample['path']];results[sample['path']][treatment]=d
            expected=sample['reference'];flag=d['review_suggestion']
            if expected in ('whole_image_focus_miss','subject_focus_miss'):
                summary['explicit_misses']+=1;summary['caught' if flag else 'missed']+=1
            elif expected!='unlabeled':
                summary['other_annotated']+=1;summary['other_flagged']+=int(flag)
            else:summary['unlabeled']+=1
        summaries[treatment]=dict(summary)
    return results,summaries


def measurements_table(path,analyses):
    parts=['<details><summary>Regional Laplacian / Tenengrad measurements</summary><p>Values are measured on native previews at the listed scale. '
           'A lower ratio is less regional detail, not automatically worse focus.</p><table><tr><th>Scale</th><th>Treatment</th><th>Scope</th><th>Laplacian</th><th>Tenengrad</th><th>L/outside</th><th>T/outside</th></tr>']
    for treatment in TREATMENTS:
        for row in (r for r in analyses[treatment] if r['path']==path):
            focus=row['focus'];scale=row['max_dimension'];glob=focus['global']['smoothed']
            parts.append(f'<tr><td>{scale}</td><td>{treatment}</td><td>Global</td><td>{glob["laplacian_variance"]:.5g}</td><td>{glob["tenengrad"]:.5g}</td><td>—</td><td>—</td></tr>')
            for region in focus['regions']:
                measured=region['smoothed']
                if not measured or not measured['region']:continue
                values=measured['region'];ratio=measured['region_to_outside']
                l=ratio.get('laplacian_variance');t=ratio.get('tenengrad')
                ls=f'{l:.3f}' if l is not None else 'unavailable';ts=f'{t:.3f}' if t is not None else 'unavailable'
                parts.append(f'<tr><td>{scale}</td><td>{treatment}</td><td>{html.escape(region["id"])}</td><td>{values["laplacian_variance"]:.5g}</td><td>{values["tenengrad"]:.5g}</td><td>{ls}</td><td>{ts}</td></tr>')
    parts.append('</table></details>');return '\n'.join(parts)


def report(records,results,summaries,previews,output,analyses=None):
    esc=html.escape
    descriptions={'raw':'Raw (unfiltered)','gaussian1':'Gaussian σ=1','gaussian2':'Gaussian σ=2',
                  'bilateral':'Bilateral d=5, σColor=15 (8-bit units), σSpace=2'}
    description='; '.join(descriptions[t] for t in TREATMENTS)
    parts=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
           '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'">',
           '<title>FocusSamples benchmark</title><style>body{font:16px system-ui;background:#f7f6f2;color:#242a30;max-width:1400px;margin:auto;padding:24px}table{border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #ccc;text-align:left}section{background:white;padding:16px;margin:20px 0;border:1px solid #ccc}img{width:100%;max-width:900px;height:auto}.canvas{position:relative;max-width:900px}.canvas svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}p{line-height:1.5}pre{white-space:pre-wrap}a{color:#155b81}</style>',
           '<h1>FocusSamples benchmark</h1><p><a href="comparison.csv">Comparison CSV</a> · <a href="review.csv">Feedback CSV</a> · <a href="benchmark.json">Complete measurements</a></p><p>Supplied CSV notes are preserved verbatim; unlabeled samples await your feedback. No thresholds were fitted. '
           'Selected treatments use the same regional/global review policy and the same Vision boxes. '
           'Material reference batches are separate. The sharp-subject override has no calibrated absolute threshold yet; '
           'these results audit the current provisional rule, not a finished classifier.</p>',
           '<p>Selected treatments: '+esc(description)+'. '
           'All filtering is applied to native grayscale previews before region masks. This is fixed smoothing, not adaptive grain estimation. '
           'Both Laplacian and Tenengrad must show lower regional/outside detail at both 1024 and 2048. '
           'Whole-image suggestions require all six global/tile signals in the material batch bottom 10%; fewer than 20 disables that part.</p>',
           f'<p>{sum(r["reference"] in ("whole_image_focus_miss","subject_focus_miss") for r in records)} comments explicitly describe focus misses. Other comments generally describe intended focus, '
           'but are not definitive binary keep/cull labels. “Other flagged” therefore means disagreement requiring review, '
           'not a proven false positive. No holdout evaluation or general accuracy claim is possible from this run.</p>',
           '<p>“No review trigger” is not a focus pass. Without a source CSV, materials are unconfirmed and global reference ranks use this selected batch. A softness-heavy batch can change relative flags.</p>',
           '<table><tr><th>Treatment</th><th>Images flagged</th><th>Explicit misses caught</th><th>Other annotated flagged</th></tr>']
    for t,s in summaries.items():
        flagged=sum(results[r['path']][t]['review_suggestion'] for r in records)
        caught=f'{s.get("caught",0)}/{s["explicit_misses"]}' if s.get('explicit_misses') else 'Awaiting labels'
        other=f'{s.get("other_flagged",0)}/{s["other_annotated"]}' if s.get('other_annotated') else 'Awaiting labels'
        parts.append(f'<tr><td>{t}</td><td>{flagged}/{len(records)}</td><td>{caught}</td><td>{other}</td></tr>')
    parts.append('</table><h2>Samples</h2><p>Toggle measurement details for exact regions and cross-scale evidence. Yellow=faces, cyan=people, magenta=animals, orange=objectness; attention omitted from the overlay for clarity.</p>')
    colors={'faces':'#ffcf33','people':'#00e5ff','animals':'#ff68e3','objectness':'#ff8033'}
    for sample in records:
        name=sample['filename'];path=sample['path'];preview=previews[path]
        parts.extend([f'<section id="sample-{esc(name)}"><h2>{esc(name)}</h2><p>{esc(sample["material"])} · {esc(sample["color"])} · Reference: {esc(sample["reference"])}</p>',
                      f'<blockquote>{esc(sample["notes"]) or "No annotations supplied"}</blockquote>',
                      '<table><tr><th>Treatment</th><th>Review suggestion</th><th>Subject evidence</th><th>Whole-frame low-detail trigger</th></tr>'])
        for t,d in results[path].items():
            parts.append(f'<tr><td>{t}</td><td>{"YES" if d["review_suggestion"] else "No review trigger"}</td><td>{esc(", ".join(c["region"] for c in d["subject_cues"])) or "None"}</td><td>{d["global_low_detail"]}</td></tr>')
        parts.append('</table>')
        link=esc(quote(os.path.relpath(path,output)))
        w,h=preview['width'],preview['height']
        parts.append(f'<div class="canvas"><a href="{link}"><img loading="lazy" src="data:image/jpeg;base64,{preview["thumbnail"]}" alt="{esc(name)}"></a><svg viewBox="0 0 {w} {h}">')
        for kind,color in colors.items():
            for i,r in enumerate(preview['detectors'][kind].get('regions',[]),1):
                x,y,bw,bh=r.get('display_box',r['box']);x*=w;y*=h;bw*=w;bh*=h
                parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bw:.2f}" height="{bh:.2f}" fill="none" stroke="{color}" stroke-width="2" vector-effect="non-scaling-stroke"/><text x="{x+3:.2f}" y="{y+14:.2f}" fill="{color}" stroke="#111" stroke-width=".4" paint-order="stroke" font-size="14">{kind} {i}</text>')
        parts.append('</svg></div>')
        if analyses:parts.append(measurements_table(path,analyses))
        parts.append('<details><summary>Rule evidence and measurements</summary><pre>'+esc(json.dumps(results[path],indent=2))+'</pre></details></section>')
    parts.append('</html>');return '\n'.join(parts)


def main():
    global TREATMENTS
    parser=argparse.ArgumentParser(description=__doc__)
    inputs=parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--csv',type=Path);inputs.add_argument('--folder',type=Path,help='Unlabeled, shallow image folder; sources remain read-only')
    parser.add_argument('--treatments',nargs='+',choices=ALL_TREATMENTS,default=ALL_TREATMENTS)
    parser.add_argument('--audit',type=Path,required=True)
    parser.add_argument('--helper',type=Path,required=True);parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();TREATMENTS=args.treatments
    if len(set(TREATMENTS))!=len(TREATMENTS):parser.error('Duplicate treatments')
    if args.csv:records=samples(args.csv);csv_sha=digest(args.csv)
    else:
        paths=sorted(p for p in args.folder.iterdir() if p.is_file() and not p.is_symlink() and p.suffix.lower() in {'.jpg','.jpeg','.png','.heic','.heif','.tif','.tiff'})
        if not paths:parser.error('No supported images')
        records=[{'filename':p.name,'path':str(p.resolve()),'material':'unconfirmed','color':'','notes':'','reference':'unlabeled'} for p in paths]
        csv_sha=None
    audit=json.loads(args.audit.read_text());paths=[Path(r['path']) for r in records]
    if audit['source_paths']!=list(map(str,paths)) or audit['source_sha256']!=[digest(p) for p in paths]:raise ValueError('Audit inputs differ from CSV sources')
    stats=[(p.stat().st_size,p.stat().st_mtime_ns) for p in paths]
    output=args.output_dir.resolve();repository=Path(__file__).resolve().parents[2]
    if output==repository or repository in output.parents or any(output==p.parent or p.parent in output.parents for p in paths):raise ValueError('Unsafe output directory')
    analyses={t:[] for t in TREATMENTS};previews={};count=0;complete=False
    with tempfile.TemporaryFile() as stream:
        proc=subprocess.run([str(args.helper.resolve()),'--pixels-only'],input=json.dumps(list(map(str,paths))).encode(),stdout=stream,stderr=subprocess.PIPE,timeout=180)
        if proc.returncode:raise RuntimeError(proc.stderr.decode(errors='replace'))
        stream.seek(0)
        for line in stream:
            row=json.loads(line)
            if complete:raise ValueError('Unexpected output')
            if row['type']=='complete':complete=row['images']==len(paths);continue
            detected=audit['rows'][count]
            for key in ('index','path','width','height','max_dimension'):
                if row[key]!=detected[key]:raise ValueError('Native identity mismatch')
            w,h=row['width'],row['height'];rgb=np.frombuffer(base64.b64decode(row['rgba'],validate=True),np.uint8).reshape(h,w,4)[:,:,:3]
            for treatment in TREATMENTS:
                value={k:row[k] for k in ('index','path','max_dimension','width','height')}
                value['focus']=analyze_regions(rgb,copy.deepcopy(detected['detectors']),treatment)
                analyses[treatment].append(value)
            if row['max_dimension']==1024:
                ok,encoded=cv2.imencode('.jpg',cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,90])
                if not ok:raise ValueError('Preview encoding failed')
                previews[row['path']]={'width':w,'height':h,'detectors':detected['detectors'],'thumbnail':base64.b64encode(encoded.tobytes()).decode('ascii')}
            count+=1
            if count%10==0:print('Measured',count//2,'/',len(paths),flush=True)
    if not complete or count!=len(paths)*2:raise ValueError('Incomplete decoding')
    results,summaries=evaluate(records,analyses)
    document=report(records,results,summaries,previews,output,analyses)
    if (args.csv and csv_sha!=digest(args.csv)) or audit['source_sha256']!=[digest(p) for p in paths] or stats!=[(p.stat().st_size,p.stat().st_mtime_ns) for p in paths]:raise ValueError('Sources or annotations changed')
    output.mkdir(parents=True,exist_ok=False)
    (output/'benchmark.html').write_text(document)
    payload={'version':'focus-benchmark-v1','csv_sha256':csv_sha,'audit_sha256':digest(args.audit),'samples':records,'summaries':summaries,'results':results,
             'treatments':TREATMENTS,'measurements':analyses,'policy':POLICY,'inputs_unchanged':True,'source_sha256':audit['source_sha256'],
             'backends':{'opencv':cv2.__version__,'numpy':np.__version__,'native_os':audit['os']},'helper_sha256':digest(args.helper)}
    (output/'benchmark.json').write_text(json.dumps(payload,indent=2))
    with (output/'comparison.csv').open('x',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['filename','material','color','user_notes','interpreted_reference',*TREATMENTS])
        for r in records:writer.writerow([r['filename'],r['material'],r['color'],r['notes'],r['reference'],*[results[r['path']][t]['review_suggestion'] for t in TREATMENTS]])
    with (output/'review.csv').open('x',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['filename','focus_assessment','subject','material','notes'])
        for r in records:writer.writerow([r['filename'],'','',r['material'],r['notes']])
    print(json.dumps(summaries));print('Saved:',output/'benchmark.html')


if __name__=='__main__':main()
