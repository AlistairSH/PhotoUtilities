"""Fixed-parameter probes on existing sample sets; reports, not production rules."""
import argparse
import base64
import csv
import html
import json
import os
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import quote

import cv2
import numpy as np

from edge_blur import extract,summarize,flags,SETTINGS
from subject_review import subject_evidence
from run import digest


def add_region_evidence(decision,rows):
    result=dict(decision);result['combined_global_review']=decision['combined_review']
    cues=[]
    for row in rows:
        eligible=[r for r in row['regions'] if not r['id'].startswith('attention')]
        if not eligible:eligible=row['regions']
        for region in eligible:
            triggered=flags(region['metrics'])
            if any(triggered.values()):cues.append({'scale':row['scale'],'region':region['id'],
                'methods':[k for k,v in triggered.items() if v], 'edges':region['metrics']['edges'],
                'median_width':region['metrics']['median_width']})
    result['region_probe_cues']=cues;result['combined_region_review']=decision['combined_review'] or bool(cues)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--benchmarks',nargs='+',type=Path,required=True)
    parser.add_argument('--helper',type=Path,required=True);parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();output=args.output_dir.resolve()
    repository=Path(__file__).resolve().parents[2]
    if output==repository or repository in output.parents:raise ValueError('Output outside repo required')
    records=[];previews={};hashes={};source_stats={}
    for benchmark in args.benchmarks:
        data=json.loads(benchmark.read_text());paths=data['samples']
        if any(output==Path(s['path']).parent or Path(s['path']).parent in output.parents for s in paths):raise ValueError('Output in sources refused')
        audit_path=benchmark.parent.parent/(Path(paths[0]['path']).parent.name+'-subjects-trial-01')/'subjects.json'
        audit=json.loads(audit_path.read_text())
        cached={(r['path'],r['max_dimension']):r for r in data['measurements']['gaussian1']}
        metadata={(r['path'],r['max_dimension']):r for r in audit['rows']}
        for s,sha in zip(paths,data['source_sha256']):
            p=Path(s['path']);assert not p.is_symlink() and digest(p)==sha
            hashes[s['path']]=sha;source_stats[s['path']]=(p.stat().st_size,p.stat().st_mtime_ns)
        with tempfile.TemporaryFile() as stream:
            proc=subprocess.run([str(args.helper.resolve()),'--pixels-only'],input=json.dumps([s['path'] for s in paths]).encode(),stdout=stream,stderr=subprocess.PIPE,timeout=180)
            if proc.returncode:raise RuntimeError(proc.stderr.decode(errors='replace'))
            stream.seek(0);count=0;complete=False
            for line in stream:
                row=json.loads(line)
                if complete:raise ValueError('Unexpected native output')
                if row['type']=='complete':complete=row['images']==len(paths);continue
                sample=paths[count//2];scale=(1024,2048)[count%2]
                if row['path']!=sample['path'] or row['index']!=count//2 or row['max_dimension']!=scale:raise ValueError('Native ordering mismatch')
                old=cached[(row['path'],scale)]
                if (row['width'],row['height'])!=(old['width'],old['height']):raise ValueError('Native geometry mismatch')
                w,h=row['width'],row['height'];rgb=np.frombuffer(base64.b64decode(row['rgba'],validate=True),np.uint8).reshape(h,w,4)[:,:,:3]
                gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY);edges=extract(gray)
                global_result=summarize(edges);regions=[];tiles=[]
                for kind in ('faces','people','animals','objectness','attention'):
                    for i,r in enumerate(metadata[(row['path'],scale)]['detectors'][kind].get('regions',[]),1):
                        regions.append({'id':f'{kind} {i}','box':r['box'],'metrics':summarize(edges,r.get('display_box',r['box']),gray.shape)})
                for y in range(4):
                    for x in range(4):tiles.append(summarize(edges,[x/4,y/4,.25,.25],gray.shape))
                records.append({'sample':sample,'scale':scale,'global':global_result,'flags':flags(global_result),'regions':regions,'tiles':tiles,
                    'baseline_flag':data['results'][row['path']]['gaussian1']['review_suggestion'],
                    'baseline_attention_v2_flag':bool(subject_evidence(cached[(row['path'],1024)],cached[(row['path'],2048)])) or data['results'][row['path']]['gaussian1']['global_low_detail']})
                if scale==1024:
                    ok,encoded=cv2.imencode('.jpg',cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,90]);assert ok
                    previews[row['path']]=base64.b64encode(encoded.tobytes()).decode('ascii')
                count+=1
                if count%10==0:print('Measured',benchmark.parent.name,count//2,'/',len(paths),flush=True)
        if not complete or count!=2*len(paths):raise ValueError('Incomplete native decode')
    paths=list(dict.fromkeys(r['sample']['path'] for r in records));decisions=[]
    for path in paths:
        rows=[r for r in records if r['sample']['path']==path]
        # High-recall exploratory screening: a flag at either native input scale
        # suggests review; record cross-scale agreement separately.
        decision={'path':path,'baseline':rows[0]['baseline_attention_v2_flag']}
        for method in ('edge_width','contrast_proxy','directional'):
            decision[method]=any(r['flags'][method] for r in rows)
            decision[method+'_both_scales']=all(r['flags'][method] for r in rows)
        decision['any_new_probe']=any(decision[m] for m in ('edge_width','contrast_proxy','directional'))
        decision['combined_review']=decision['baseline'] or decision['any_new_probe']
        # Diagnostic only: absolute sharp-subject override is not adopted. List
        # subjects with narrow edge evidence so users can assess that safeguard.
        decision['narrow_subject_regions']=[{'scale':r['scale'],'region':region['id']} for r in rows for region in r['regions']
            if region['id'].split()[0] in ('faces','people','animals') and region['metrics']['sufficient'] and region['metrics'].get('median_width',99)<3]
        decisions.append(add_region_evidence(decision,rows))
    esc=html.escape
    page=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'">',
          '<title>Edge blur experiments</title><style>body{font:16px system-ui;background:#f7f6f2;color:#242a30;max-width:1400px;margin:auto;padding:24px}table{border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #ccc;text-align:left}section{background:white;padding:16px;margin:20px 0}img{max-width:900px;width:100%}pre{white-space:pre-wrap}p{line-height:1.5}</style>',
          '<h1>Edge spread, contrast and directional blur experiments</h1><p>Gaussian σ=1 preprocessing and original native pixels. Parameters were fixed before inspecting new probe results. These are development-set diagnostics, not held-out validation. A probe at either scale suggests review to favor recall; cross-scale flags are exported separately. Existing reports and rules are unchanged.</p>',
          '<p>Edge width measures local 10–90% transitions. The contrast-aware proxy compares widths to contrast-dependent 3/5px limits; it is inspired by CPBD but is NOT an implementation or calibrated probability of CPBD. Directional evidence compares edge widths across opposing normal orientations and can also respond to scene geometry. Grain, scale, sharpening and low texture remain confounds. No absolute sharp-subject override is adopted.</p>',
          '<p>Illustrative thresholds: median edge width ≥4px; contrast-soft fraction ≥60%; directional width ratio ≥1.6 with broad-direction median ≥4.5px. At least 50 sampled edges required globally. Sparse edges mean insufficient evidence, not a pass. Complete measurements include tiles and all detected regions.</p>',
          '<p><a href="results.csv">Results CSV</a> · <a href="measurements.json">All measurements</a></p>']
    for decision in decisions:
        path=decision['path'];rows=[r for r in records if r['sample']['path']==path];s=rows[0]['sample'];name=Path(path).name
        page.append(f'<section id="{esc(name)}"><h2>{esc(Path(path).parent.name+" / "+name)}</h2><blockquote>{esc(s["notes"]) or "Awaiting user feedback"}</blockquote><p>Baseline (G1 + attention fallback): {decision["baseline"]}; global edge width: {decision["edge_width"]}; global contrast proxy: {decision["contrast_proxy"]}; global directional: {decision["directional"]}; combined global suggestion: {decision["combined_review"]}; including regional probes: {decision["combined_region_review"]}.</p>')
        page.append('<table><tr><th>Scale</th><th>Edges</th><th>Median width</th><th>Contrast soft fraction</th><th>Direction ratio</th></tr>')
        def value(x):return f'{x:.3f}' if x is not None else 'insufficient'
        for row in rows:
            m=row['global'];page.append(f'<tr><td>{row["scale"]}</td><td>{m["edges"]}</td><td>{value(m["median_width"])}</td><td>{value(m["contrast_soft_fraction"])}</td><td>{value(m["direction_ratio"])}</td></tr>')
        link=esc(quote(os.path.relpath(path,output)))
        page.append(f'</table><a href="{link}"><img loading="lazy" src="data:image/jpeg;base64,{previews[path]}" alt="{esc(name)}"></a><details><summary>Tiles, regions and evidence</summary><pre>'+esc(json.dumps({'decision':decision,'measurements':rows},indent=2))+'</pre></details></section>')
    page.append('</html>')
    for path,sha in hashes.items():
        p=Path(path)
        if digest(p)!=sha or (p.stat().st_size,p.stat().st_mtime_ns)!=source_stats[path]:raise ValueError('Source changed')
    output.mkdir(parents=True,exist_ok=False)
    (output/'report.html').write_text('\n'.join(page))
    (output/'measurements.json').write_text(json.dumps({'settings':SETTINGS,'records':records,'decisions':decisions,'source_sha256':hashes,'inputs_unchanged':True},indent=2))
    with (output/'results.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=[k for k in decisions[0] if k not in ('narrow_subject_regions','region_probe_cues')]);writer.writeheader()
        for d in decisions:writer.writerow({k:v for k,v in d.items() if k not in ('narrow_subject_regions','region_probe_cues')})
    print('Saved:',output/'report.html')


if __name__=='__main__':main()
