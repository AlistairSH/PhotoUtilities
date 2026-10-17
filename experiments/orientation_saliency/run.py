"""Read-only four-orientation saliency/horizon-boundary hypothesis trial."""
import argparse
import base64
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import random
import subprocess
import time

import cv2
import numpy as np

POLICY = {
    'view_max_dimension':768,'rotations_clockwise':[0,90,180,270],
    'boundary':'Longest near-horizontal Canny/Hough segment, >=45% image width, <=20 degrees, center within middle 70% of image; not a semantic horizon',
    'native_horizon':'Vision angle/confidence recorded; Vision supplies no horizon height. Confidence >=0.5 required for a proposal.',
    'area':'Union of clipped detected region boxes; count pixels below estimated line / union pixels. Separate object and attention treatments.',
    'proposal':'>=65% area below line, >=15 percentage-point lead over next evaluable rotation; at least two evaluable rotations and >=1% image area. Thresholds fixed before this run, uncalibrated.',
    'meaning':'Independent experimental proposals, not accuracy measurements. No known upright labels assumed. All four candidates shown. No photo writes or CLI policy changes.'}


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def boundary(rgb):
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    edges=cv2.Canny(cv2.GaussianBlur(gray,(5,5),1),50,150)
    h,w=gray.shape
    lines=cv2.HoughLinesP(edges,1,np.pi/180,threshold=max(35,int(w*.12)),minLineLength=int(w*.45),maxLineGap=int(w*.04))
    candidates=[]
    for segment in [] if lines is None else lines[:,0]:
        x0,y0,x1,y1=map(float,segment)
        if x0>x1:x0,y0,x1,y1=x1,y1,x0,y0
        if x1-x0<w*.45:continue
        slope=(y1-y0)/(x1-x0);intercept=y0-slope*x0
        if abs(math.degrees(math.atan(slope)))>20:continue
        if not .15*h<=slope*w/2+intercept<=.85*h:continue
        candidates.append(dict(slope=slope,intercept=intercept,length=math.hypot(x1-x0,y1-y0),segment=[x0,y0,x1,y1]))
    return max(candidates,key=lambda c:c['length']) if candidates else None


def below_fraction(boxes,line,width,height):
    if line is None:return None
    mask=np.zeros((height,width),dtype=bool)
    for x,y,w,h in boxes:
        if not all(math.isfinite(v) for v in (x,y,w,h)) or min(w,h)<=0:raise ValueError('Invalid native region')
        left,right=max(0,math.floor(x*width)),min(width,math.ceil((x+w)*width))
        top,bottom=max(0,math.floor(y*height)),min(height,math.ceil((y+h)*height))
        if right>left and bottom>top:mask[top:bottom,left:right]=True
    count=int(mask.sum())
    if count<.01*width*height:return None
    yy,xx=np.indices(mask.shape)
    return float(np.count_nonzero(mask & (yy>=line['slope']*xx+line['intercept']))/count)


def proposal(candidates,kind):
    scored=[(c['scores'][kind],c['q']) for c in candidates if c['scores'][kind] is not None and c['horizon'].get('confidence',0)>=.5]
    scored.sort(reverse=True)
    if len(scored)<2:return {'q':None,'reason':'Insufficient evaluable horizon/region evidence'}
    best,q=scored[0];gap=best-scored[1][0]
    if best<.65 or gap<.15:return {'q':None,'reason':'Weak majority or close alternatives','best_fraction':best,'gap':gap}
    return {'q':q,'reason':'Area below estimated boundary','best_fraction':best,'gap':gap}


def render(results,summary):
    esc=html.escape;sections=[]
    for image in results:
        choices=image['proposals']
        def description(kind):
            p=choices[kind]
            return ('Unassessed — '+p['reason']) if p['q'] is None else str(p['q']*90)+'° clockwise ('+str(round(p['best_fraction']*100))+'% below, '+str(round(p['gap']*100))+' point lead)'
        cards=[]
        for c in image['candidates']:
            if c['status']!='ok':
                cards.append('<article><h3>'+str(c['q']*90)+'° — failed</h3><p>'+esc(c.get('error',''))+'</p></article>');continue
            w,h=c['width'],c['height'];overlays=''
            for kind,color in [('objects','#ad7dff'),('attention','#00d9ed')]:
                for x,y,bw,bh in c['detectors'][kind].get('boxes',[]):
                    overlays+='<rect class="'+kind+'" x="'+str(x*w)+'" y="'+str(y*h)+'" width="'+str(bw*w)+'" height="'+str(bh*h)+'" fill="none" stroke="'+color+'" stroke-width="3"/>'
            line=c['boundary']
            if line:overlays+='<line class="boundary" x1="0" y1="'+str(line['intercept'])+'" x2="'+str(w)+'" y2="'+str(line['slope']*w+line['intercept'])+'" stroke="#ffcf00" stroke-width="4"/>'
            scores=' · '.join(kind+': '+('Unassessed' if c['scores'][kind] is None else str(round(c['scores'][kind]*100))+'% below') for kind in ('objects','attention'))
            selected=[kind for kind in ('objects','attention') if choices[kind]['q']==c['q']]
            badge=' / '.join(selected)+' proposal' if selected else 'Candidate'
            cards.append('<article><h3>'+str(c['q']*90)+'° clockwise · '+esc(badge)+'</h3><svg viewBox="0 0 '+str(w)+' '+str(h)+'"><image width="'+str(w)+'" height="'+str(h)+'" href="data:image/jpeg;base64,'+c['thumbnail']+'"/>'+overlays+'</svg><p>'+esc(scores)+'</p><p>'+('Yellow line: estimated boundary' if line else 'No qualifying boundary')+'</p><label><input type="radio" name="label-'+str(image['index'])+'" value="'+str(c['q'])+'">This version is upright</label></article>')
        obj,att=choices['objects']['q'],choices['attention']['q']
        state='changed' if any(q not in (None,0) for q in (obj,att)) else 'unassessed' if obj is None and att is None else 'unchanged'
        different=obj is not None and att is not None and obj!=att
        sections.append('<section data-state="'+state+'" data-disagree="'+str(different).lower()+'" data-index="'+str(image['index'])+'"><h2>'+esc(Path(image['path']).name)+'</h2><p><b>Objects:</b> '+esc(description('objects'))+'<br><b>Attention:</b> '+esc(description('attention'))+'</p><div class="cards">'+''.join(cards)+'</div><label><input type="radio" name="label-'+str(image['index'])+'" value="uncertain">Unsure / none of these</label></section>')
    inventory=json.dumps([{'index':i['index'],'path':i['path'],'sha256':i['sha256']} for i in results]).replace('<','\\u003c')
    return '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; script-src 'unsafe-inline'; style-src 'unsafe-inline'"><title>Orientation experiment — objects and attention</title><style>body{font:16px system-ui;margin:24px;background:#f7f6f2;color:#243242}section{margin:30px 0;background:white;padding:18px;border-radius:8px}.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}article{border:1px solid #ccd5df;border-radius:6px;padding:10px}h3{font-size:15px}svg{display:block;width:100%;height:300px;background:#eee}nav{position:sticky;top:0;background:#e5effb;padding:14px;z-index:2}label{display:inline-block;margin:6px}button,select{padding:8px}pre{white-space:pre-wrap}@media(max-width:1000px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}}</style></head><body><h1>Orientation experiment</h1><p>Available photos selected from the main review, including previously rotated examples when requested. Four quarter-turn candidates per photo, mixed together; originals unchanged. Counts and missing files are listed below.</p><p>Purple: objects. Cyan: attention areas. Yellow: estimated horizon-like boundary. A long image edge can be a building, tabletop or scan border rather than the real horizon. These proposals need human review.</p><pre>'''+esc(json.dumps(summary,indent=2))+'''</pre><details><summary>Fixed experimental rules</summary><pre>'''+esc(json.dumps(POLICY,indent=2))+'''</pre></details><nav><label>Show <select id="filter"><option value="all">All photos</option><option value="changed">A method proposes a rotation</option><option value="disagree">Methods disagree</option><option value="unassessed">Both unassessed</option></select></label><label><input id="objects" type="checkbox" checked>Objects</label><label><input id="attention" type="checkbox" checked>Attention</label><label><input id="boundary" type="checkbox" checked>Boundary</label><button id="export">Export my orientation choices</button></nav>'''+''.join(sections)+'''<script>
function update(){let f=document.getElementById('filter').value;document.querySelectorAll('section').forEach(s=>s.hidden=!(f==='all'||(f==='disagree'?s.dataset.disagree==='true':s.dataset.state===f)));['objects','attention','boundary'].forEach(k=>document.querySelectorAll('svg .'+k).forEach(e=>e.style.display=document.getElementById(k).checked?'':'none'))}
document.querySelectorAll('nav input,nav select').forEach(e=>e.onchange=update);
const inventory='''+inventory+''';document.getElementById('export').onclick=()=>{let labels=inventory.map(i=>({...i,chosen_quarter_turns_clockwise:document.querySelector('input[name="label-'+i.index+'"]:checked')?.value??null}));let url=URL.createObjectURL(new Blob([JSON.stringify({experiment:'orientation-saliency-v1',labels},null,2)],{type:'application/json'}));let a=document.createElement('a');a.href=url;a.download='orientation-review-choices.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
</script></body></html>'''


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--include-previously-rotated',action='store_true');parser.add_argument('--shuffle-seed',type=int,default=42);parser.add_argument('--report',type=Path,required=True);parser.add_argument('--helper',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);a=parser.parse_args()
    text=a.report.read_text();paths=[];previously_rotated=[];uncertain_count=0
    for card in re.findall(r'<figure\b.*?</figure>',text,re.S):
        uncertain='Orientation uncertain' in card
        rotated=re.search(r'Rotated (\d+)° clockwise',card) is not None
        if not uncertain and not (a.include_previously_rotated and rotated):continue
        relative=html.unescape(re.search(r'<figcaption>(.*?)</figcaption>',card).group(1))
        path=(a.report.parent/relative).resolve()
        paths.append(path)
        if uncertain:uncertain_count+=1
        if rotated:previously_rotated.append(str(path))
    if uncertain_count!=89 or len(set(paths))!=len(paths):raise ValueError('Expected the 89 uncertain photos and unique input identities')
    requested_count=len(paths)
    missing=[str(p) for p in paths if not p.is_file()]
    paths=[p for p in paths if p.is_file()]
    if a.include_previously_rotated:random.Random(a.shuffle_seed).shuffle(paths)
    a.output.mkdir(parents=True,exist_ok=False)
    originals={str(p):{'sha256':digest(p),'size':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns} for p in paths}
    record={'status':'running','source_report':str(a.report.resolve()),'source_report_sha256':digest(a.report),'policy':POLICY,'inputs':originals,'missing_source_paths':missing,'previously_rotated_sources':previously_rotated,'shuffle_seed':a.shuffle_seed if a.include_previously_rotated else None}
    (a.output/'run.json').write_text(json.dumps(record,indent=2))
    started=time.monotonic();results=[];current=[]
    try:
        with (a.output/'native-errors.log').open('w') as errors,subprocess.Popen([str(a.helper)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,text=True) as process:
            process.stdin.write(json.dumps(list(map(str,paths))));process.stdin.close()
            for line in process.stdout:
                row=json.loads(line);expected_index=len(results);expected_q=len(current)
                if row['index']!=expected_index or row['q']!=expected_q or row['path']!=str(paths[expected_index]):raise ValueError('Native identity/order mismatch')
                if row['status']=='ok':
                    w,h=row['width'],row['height']
                    rgb=np.frombuffer(base64.b64decode(row.pop('rgba'),validate=True),np.uint8).reshape(h,w,4)[:,:,:3]
                    line=boundary(rgb);row['boundary']=line
                    row['scores']={kind:below_fraction(d.get('boxes',[]),line,w,h) if d['status']=='ok' else None for kind,d in row['detectors'].items()}
                    ok,jpg=cv2.imencode('.jpg',cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,82])
                    if not ok:raise ValueError('Preview encoding failed')
                    row['thumbnail']=base64.b64encode(jpg).decode()
                else:row.update(scores={'objects':None,'attention':None},horizon={})
                current.append(row)
                if len(current)==4:
                    item={'index':expected_index,'path':str(paths[expected_index]),'sha256':originals[str(paths[expected_index])]['sha256'],'candidates':current,
                        'proposals':{k:proposal(current,k) for k in ('objects','attention')}}
                    results.append(item);current=[]
                    with (a.output/'checkpoint.jsonl').open('a') as checkpoint:checkpoint.write(json.dumps(item)+'\n')
                    print('Processed '+str(len(results))+'/'+str(len(paths)),flush=True)
            if process.wait(timeout=30)!=0:raise RuntimeError('Native helper failed; see native-errors.log')
        if current or len(results)!=len(paths):raise ValueError('Incomplete native output')
        for p in paths:
            before=originals[str(p)]
            if digest(p)!=before['sha256'] or p.stat().st_size!=before['size'] or p.stat().st_mtime_ns!=before['mtime_ns']:raise ValueError('Source changed during experiment: '+str(p))
        summary={'requested_uncertain_photos':uncertain_count,'previously_rotated_added':len(previously_rotated),'requested_total':requested_count,'missing_source_paths':missing,'photos':len(results),'candidate_views':4*len(results),'source_bytes_verified_unchanged':True}
        for kind in ('objects','attention'):
            qs=[r['proposals'][kind]['q'] for r in results]
            summary[kind]={'rotation_proposed':sum(q not in (None,0) for q in qs),'current_orientation_proposed':qs.count(0),'unassessed':qs.count(None)}
        summary['both_propose_same_orientation']=sum(r['proposals']['objects']['q'] is not None and r['proposals']['objects']['q']==r['proposals']['attention']['q'] for r in results)
        summary['both_propose_different_orientations']=sum(all(r['proposals'][k]['q'] is not None for k in ('objects','attention')) and r['proposals']['objects']['q']!=r['proposals']['attention']['q'] for r in results)
        summary['seconds']=round(time.monotonic()-started,1)
        (a.output/'results.json').write_text(json.dumps({'policy':POLICY,'summary':summary,'images':results}))
        (a.output/'review.html').write_text(render(results,summary))
        record.update(status='completed',summary=summary);print(json.dumps(summary,indent=2))
    except BaseException as e:
        record.update(status='failed',error=str(e));raise
    finally:(a.output/'run.json').write_text(json.dumps(record,indent=2))


if __name__=='__main__':main()
