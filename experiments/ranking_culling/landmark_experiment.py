"""Facial feature diagnostics and conservative sharp-eye counterfactual."""
import base64
import html
import json
from pathlib import Path
import subprocess
import tempfile
import cv2
import numpy as np
from edge_blur import extract, summarize
from run import digest


def feature_box(points, face):
    if len(points)<3:return None
    points=np.asarray(points);low=points.min(axis=0);high=points.max(axis=0)
    # Fixed padding around the feature, in face-relative units; no upscaling.
    pad=np.asarray(face[2:])*.025
    low=np.maximum(0,low-pad);high=np.minimum(1,high+pad)
    return [*low.tolist(),*(high-low).tolist()]


def sharp_eyes(faces):
    if not faces:return False
    # All detected faces must have supported narrow eye transitions. A missing
    # or obscured eye is uncertainty; never enough to clear a review suggestion.
    return all(all(f['features'].get(eye,{}).get('edges',0)>=20 and
        f['features'][eye]['median_width']<3 and
        f['features'][eye]['contrast_soft_fraction']<.4
        for eye in ('leftEye','rightEye')) for f in faces)


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent',type=Path,required=True)
    parser.add_argument('--helper',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();parent=args.parent;out=args.output_dir
    if out.exists():raise ValueError('Output exists')
    edge=json.loads((parent/'EdgeBlur-both-sets-trial-01/measurements.json').read_text())
    feedback=json.loads((parent/'EdgeBlur-both-sets-trial-01/user-review-feedback-v1.json').read_text())['groups']
    samples={r['sample']['path']:r['sample'] for r in edge['records']}
    hashes={p:digest(Path(p)) for p in samples};stats={p:(Path(p).stat().st_size,Path(p).stat().st_mtime_ns) for p in samples}
    if hashes!=edge['source_sha256']:raise ValueError('Source changed since edge experiment')
    geometry={}
    for folder in ('FocusTests','FocusTests2'):
        b=json.loads((parent/(folder+'-benchmark-trial-01')/'benchmark.json').read_text())
        geometry.update({(r['path'],r['max_dimension']):(r['width'],r['height']) for r in b['measurements']['gaussian1']})
    records=[];previews={}
    with tempfile.TemporaryFile() as stream:
        proc=subprocess.run([str(args.helper)],input=json.dumps(list(samples)).encode(),stdout=stream,stderr=subprocess.PIPE,timeout=600)
        if proc.returncode:raise RuntimeError(proc.stderr.decode())
        stream.seek(0);complete=False
        for line in stream:
            row=json.loads(line)
            if row['type']=='complete':complete=row['images']==len(samples);continue
            path=row['path'];scale=row['max_dimension'];w,h=row['width'],row['height']
            if (w,h)!=geometry[path,scale]:raise ValueError('Decode geometry changed')
            rgb=np.frombuffer(base64.b64decode(row.pop('rgba'),validate=True),np.uint8).reshape(h,w,4)[:,:,:3]
            gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY);faces=[]
            for face in row['detectors']['faces'].get('regions',[]):
                # Sample densely in an expanded face crop, retaining full 16px
                # profile context around feature samples; mask centers afterward.
                x,y,fw,fh=face['box'];x0=max(0,int(x*w)-20);y0=max(0,int(y*h)-20)
                x1=min(w,int((x+fw)*w)+21);y1=min(h,int((y+fh)*h)+21)
                edges=extract(gray[y0:y1,x0:x1],stride=1,maximum_edges=10000)
                edges['x']=[v+x0 for v in edges['x']];edges['y']=[v+y0 for v in edges['y']]
                features={};boxes={}
                for name,points in face['features'].items():
                    box=feature_box(points,face['box'])
                    if box is None:continue
                    boxes[name]=box;features[name]=summarize(edges,box,gray.shape)
                faces.append({**face,'points':face['features'],'features':features,'feature_boxes':boxes})
            records.append({'path':path,'scale':scale,'width':w,'height':h,'status':row['detectors']['faces']['status'],'faces':faces,'sharp_eyes':sharp_eyes(faces)})
            if scale==1024:
                ok,jpg=cv2.imencode('.jpg',cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR));assert ok
                previews[path]=base64.b64encode(jpg).decode()
            if len(records)%20==0:print('Measured',len(records)//2,'/',len(samples),flush=True)
    if not complete or len(records)!=2*len(samples):raise ValueError('Incomplete native output')
    decisions=[]
    for d in edge['decisions']:
        path=d['path'];rows=[r for r in records if r['path']==path]
        old=[r for r in edge['records'] if r['sample']['path']==path]
        semantic=any(r['id'].split()[0] in ('faces','people','animals') for r in old for r in r['regions'])
        regional=not semantic and any(r['id'].startswith('objectness') and r['metrics']['sufficient'] and r['metrics']['contrast_soft_fraction']>=.6 for o in old for r in o['regions'])
        candidate=d['baseline'] or d['contrast_proxy'] or regional
        # Only a new global suggestion can be vetoed: baseline focus misses,
        # animal cues and no-face regional suggestions stay eligible for review.
        animal=any(r['id'].startswith('animals') for o in old for r in o['regions'])
        supported=all(r['status']=='ok' and r['sharp_eyes'] for r in rows)
        veto=candidate and not d['baseline'] and d['contrast_proxy'] and not animal and supported
        decisions.append({'path':path,'baseline':d['baseline'],'candidate_before':candidate,'sharp_eyes_both_scales':supported,'veto':veto,'candidate_after':candidate and not veto})
    counts={}
    for group,names in feedback.items():
        subset=[d for d in decisions if Path(d['path']).name in names]
        counts[group]={'examples':len(subset),'before':sum(d['candidate_before'] for d in subset),'after':sum(d['candidate_after'] for d in subset),'cleared':[Path(d['path']).name for d in subset if d['veto']]}
    page=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Facial landmarks focus trial</title><style>body{font:16px system-ui;max-width:1200px;margin:auto;padding:24px;background:#faf9f5}section{background:white;padding:18px;margin:20px 0}svg{width:100%;max-width:950px}table{border-collapse:collapse}td,th{padding:7px;border-bottom:1px solid #ddd}pre{white-space:pre-wrap}</style><h1>Facial landmarks: sharp-eye safeguard</h1>',
    '<p>Apple Vision face landmarks revision 3, 76-point constellation; original sRGB pixels at 1024 and 2048. Gaussian σ=1 edge profiles sampled densely inside expanded face crops. Colored boxes/points mark eyes (green), eyebrows (yellow), nose (cyan), lips (magenta). Landmarks can be found on blurry faces, sunglasses or closed eyes; they are geometry, not evidence of focus.</p>',
    '<p>Fixed conservative counterfactual: each eye needs ≥20 profiles, median transition width &lt;3px and contrast-soft fraction &lt;40%, for every detected face at both scales. Only new global-contrast reviews can be cleared; baseline flags, detected-animal cases and no-face fallback cases are protected. Sparse support is unknown. This is development-set evidence; no working rule was replaced.</p>',
    '<pre>'+html.escape(json.dumps(counts,indent=2))+'</pre><p>All 92 samples tested. Reviewed cases appear first; other samples follow.</p>']
    reviewed={n for ns in feedback.values() for n in ns}
    for d in sorted(decisions,key=lambda d:(Path(d['path']).name not in reviewed,Path(d['path']).name)):
        path=d['path'];name=Path(path).name;rows=[r for r in records if r['path']==path];r=rows[0]
        page.append(f'<section id="{html.escape(name)}"><h2>{html.escape(name)}</h2><p>{html.escape(samples[path]["notes"] or "User feedback in prior review")}</p><p>Candidate before: {d["candidate_before"]}; after landmark safeguard: {d["candidate_after"]}; sharp-eye support both scales: {d["sharp_eyes_both_scales"]}.</p>')
        page.append(f'<svg viewBox="0 0 {r["width"]} {r["height"]}"><image width="{r["width"]}" height="{r["height"]}" href="data:image/jpeg;base64,{previews[path]}"/>')
        for f in r['faces']:
            for feature,box in f['feature_boxes'].items():
                color='lime' if 'Eye' in feature and 'Eyebrow' not in feature else 'yellow' if 'Eyebrow' in feature else 'cyan' if feature=='nose' else 'magenta'
                x,y,w,h=box;page.append(f'<rect x="{x*r["width"]}" y="{y*r["height"]}" width="{w*r["width"]}" height="{h*r["height"]}" fill="none" stroke="{color}"/>')
                for x,y in f['points'][feature]:page.append(f'<circle cx="{x*r["width"]}" cy="{y*r["height"]}" r="1.5" fill="{color}"/>')
        page.append('</svg><table><tr><th>Scale / face / feature</th><th>Profiles</th><th>Median width</th><th>Soft fraction</th></tr>')
        for row in rows:
            if not row['faces']:page.append(f'<tr><td>{row["scale"]}: no face landmarks</td><td colspan="3">Unknown</td></tr>')
            for i,f in enumerate(row['faces'],1):
                for feature,m in f['features'].items():
                    width='—' if m['median_width'] is None else f'{m["median_width"]:.2f}'
                    fraction='—' if m['contrast_soft_fraction'] is None else f'{m["contrast_soft_fraction"]:.2f}'
                    page.append(f'<tr><td>{row["scale"]} / {i} / {feature}</td><td>{m["edges"]}</td><td>{width}</td><td>{fraction}</td></tr>')
        page.append('</table></section>')
    for path,sha in hashes.items():
        p=Path(path)
        if digest(p)!=sha or (p.stat().st_size,p.stat().st_mtime_ns)!=stats[path]:raise ValueError('Original changed')
    out.mkdir(parents=True,exist_ok=False)
    export={'records':records,'decisions':decisions,'counts':counts,'source_sha256':hashes,'inputs_unchanged':True,'parameters':{'eye_padding_face_fraction':.025,'stride':1,'minimum_profiles_per_eye':20,'maximum_median_width':3,'maximum_soft_fraction':.4,'scales':[1024,2048]},'implementation_sha256':{p.name:digest(p) for p in [Path(__file__),Path(__file__).with_name('landmarks.swift'),Path(__file__).with_name('edge_blur.py')]}}
    (out/'measurements.json').write_text(json.dumps(export,indent=2));(out/'report.html').write_text('\n'.join(page)+'</html>')
    print(json.dumps(counts,indent=2));print('Saved',out/'report.html')

if __name__=='__main__':main()
