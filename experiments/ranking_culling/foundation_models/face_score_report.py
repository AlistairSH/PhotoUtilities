"""Raw maximum-face-score review; explicit experimental export, no image writes."""
from __future__ import annotations
import argparse, collections, hashlib, html, json, math
from pathlib import Path

def maximum_score(request):
    if request.get('status')!='ok':return {'status':'failed','score':None,'faces':None,'scores':[]}
    faces=request.get('observations',[])
    if not faces:return {'status':'no_face','score':None,'faces':0,'scores':[]}
    scores=[f.get('quality') for f in faces]
    if any(s is None for s in scores):return {'status':'missing_quality','score':None,'faces':len(faces),'scores':scores}
    if any(isinstance(s,bool) or not isinstance(s,(int,float)) or not math.isfinite(s) or not 0<=s<=1 for s in scores):raise ValueError('Invalid native capture score')
    return {'status':'scored','score':max(scores),'faces':len(faces),'scores':scores}

def rank_group(images):
    # Original order resolves exact ties; absent measurements are not zero scores.
    return sorted(images,key=lambda i:(i['capture']['score'] is None,-i['capture']['score'] if i['capture']['score'] is not None else 0))

def main():
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);p.add_argument('--vision',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.resolve().is_relative_to(Path(__file__).resolve().parents[3]):raise ValueError('Private output must remain outside Git')
    result=json.loads(a.results.read_text());vision=json.loads(a.vision.read_text());native={(r['id'],r['max_dimension']):r for r in vision['rows'] if r.get('status')=='ok'}
    groups=collections.defaultdict(list);solos=[];data=[]
    for image in result['images']:
        row=native.get((image['id'],2048))
        if not row or row['path']!=image['path']:raise ValueError('Native identity mismatch')
        record=dict(image,capture=maximum_score(row['requests']['face_quality']));data.append(record)
        if image['group']:groups[image['group']].append(record)
        else:solos.append(record)
    for gid in groups:groups[gid]=rank_group(groups[gid])
    solos=rank_group(solos)
    distribution={}
    for kind,rows in [('grouped',[r for r in data if r['group']]),('solo',solos)]:
        values=[r['capture']['score'] for r in rows if r['capture']['score'] is not None]
        bins=[sum(lo<=v<hi for v in values) for lo,hi in [(0,.1),(.1,.2),(.2,.3),(.3,.4),(.4,.5),(.5,.6),(.6,.7),(.7,1.01)]]
        distribution[kind]={'total':len(rows),'scored':len(values),'min':min(values) if values else None,'max':max(values) if values else None,'bins':bins}
    a.output.mkdir(exist_ok=False,parents=True)
    export={'policy':'maximum raw detected human-face capture quality at 2048; stable descending within group','solo_threshold':None,'distribution':distribution,'groups':{gid:[r['id'] for r in rows] for gid,rows in groups.items()},'images':[{k:v for k,v in r.items() if k!='thumbnail'} for r in data],'model_results_sha256':hashlib.sha256(a.results.read_bytes()).hexdigest(),'vision_sha256':hashlib.sha256(a.vision.read_bytes()).hexdigest()}
    (a.output/'results.json').write_text(json.dumps(export,indent=2))
    def card(image):
        c=image['capture'];score=c['score'];display=f'{score:.3f}' if score is not None else c['status'].replace('_',' ')
        score_text=html.escape(', '.join(f'{s:.3f}' if s is not None else 'unavailable' for s in c['scores']))
        return f'<article data-id="{image["id"]}" data-kind="{image["kind"]}" data-score="{score if score is not None else ""}"><h3>{image["id"]} · {html.escape(Path(image["path"]).name)}</h3><img src="data:image/jpeg;base64,{image["thumbnail"]}" alt="Local photograph"><p>Highest face score: <b>{display}</b> · Faces: {c["faces"] if c["faces"] is not None else "unknown"}</p><p>All raw face scores: {score_text}</p><p class="flag" hidden>Interesting: exceptional face-capture score</p></article>'
    sections=''.join('<section><h2>'+html.escape(gid)+'</h2><div class="cards">'+''.join(card(r) for r in rows)+'</div></section>' for gid,rows in groups.items())
    sections+='<section><h2>Solo images</h2><p>Scored solos are shown in descending order; unscored photos remain available below.</p><div class="cards">'+''.join(card(r) for r in solos)+'</div></section>'
    table='<table><tr><th>Maximum-face-score range</th><th>Grouped photos</th><th>Solos</th></tr>'+''.join(f'<tr><td>{label}</td><td>{distribution["grouped"]["bins"][i]}</td><td>{distribution["solo"]["bins"][i]}</td></tr>' for i,label in enumerate(['0–0.099','0.1–0.199','0.2–0.299','0.3–0.399','0.4–0.499','0.5–0.599','0.6–0.699','0.7–1.0']))+'</table>'
    document='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Raw face-capture score review</title><style>body{font:16px system-ui;margin:24px;background:#f4f3ef}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:20px}article{background:white;padding:16px;border:3px solid transparent}article.interesting{border-color:#24824c}img{width:100%;display:block}td,th{padding:7px;text-align:left}.flag{color:#176e39}header{background:#f4f3ef;padding:12px;position:sticky;top:0;z-index:1}</style><header><h1>Raw face-capture score review</h1><p>Group order uses the highest raw detected face score. No score is unassessed, not zero. Existing model judgments and keep labels are unchanged.</p><label>Solo high-score cutoff <input id="cutoff" type="number" min="0" max="1" step="0.01" placeholder="Choose a cutoff"></label> <button id="export">Export cutoff and solo highlights</button><p id="status">Solo highlighting is off until you choose a cutoff.</p></header>'''+table+sections+'''<script>
    function selection(){const input=document.querySelector('#cutoff');if(input.value==='')return {threshold:null,ids:[]};const threshold=Number(input.value);if(!Number.isFinite(threshold)||threshold<0||threshold>1)return {threshold:null,ids:[]};return {threshold,ids:[...document.querySelectorAll('article[data-kind="solo"]')].filter(a=>a.dataset.score!==''&&Number(a.dataset.score)>=threshold).map(a=>a.dataset.id)}}
    document.querySelector('#cutoff').oninput=()=>{const state=selection();document.querySelectorAll('article[data-kind="solo"]').forEach(a=>{const flag=state.ids.includes(a.dataset.id);a.classList.toggle('interesting',flag);a.querySelector('.flag').hidden=!flag});document.querySelector('#status').textContent=state.threshold===null?'Solo highlighting is off until you choose a valid cutoff.':state.ids.length+' solos highlighted at raw score ≥ '+state.threshold;};
    document.querySelector('#export').onclick=()=>{const state=selection();const data={policy:'maximum_raw_face_capture_quality',resolution:2048,solo_threshold:state.threshold,interesting_solo_ids:state.ids};const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='face-capture-score-policy.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
    </script></html>'''
    (a.output/'review.html').write_text(document);print(json.dumps(distribution,indent=2))
if __name__=='__main__':main()
